# Database Schema & Deduplication

## Overview

PostgreSQL is the authoritative source of truth for all job state. Three tables capture the full lifecycle of a solver job: formula storage, run tracking, and result persistence.

---

## Schema

### `formulas` table

```sql
CREATE TABLE formulas (
    id               SERIAL PRIMARY KEY,
    normalized_input TEXT NOT NULL,
    hash             VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 hex
    notation         VARCHAR(20) NOT NULL,
    created_at       TIMESTAMP DEFAULT NOW()
);
```

One row per unique formula. The `hash` column has a `UNIQUE` constraint that drives deduplication. `normalized_input` stores the formula after whitespace normalization. `notation` records the input format (currently `RPN`).

### `runs` table

```sql
CREATE TABLE runs (
    id          SERIAL PRIMARY KEY,
    formula_id  INTEGER REFERENCES formulas(id),
    status      VARCHAR(20) NOT NULL,   -- state machine
    mode        VARCHAR(30) NOT NULL,   -- RPN | CNF_SUDOKU
    timeout_s   INTEGER NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    started_at  TIMESTAMP,              -- set on PROCESSING transition
    finished_at TIMESTAMP               -- set on terminal state
);
```

One row per solver invocation. Multiple runs can reference the same formula (e.g., if caching is disabled or a prior run failed).

### `results` table

```sql
CREATE TABLE results (
    id            SERIAL PRIMARY KEY,
    run_id        INTEGER UNIQUE REFERENCES runs(id),  -- one result per run
    result        VARCHAR(10),         -- SAT | UNSAT
    assignment    JSONB,               -- variable → value mapping
    stdout        TEXT,
    stderr        TEXT,
    error_type    VARCHAR(50),
    error_message TEXT,
    runtime_s     FLOAT
);
```

Written once by the worker on job completion. `run_id` has a `UNIQUE` constraint enforced by `ON CONFLICT (run_id) DO NOTHING` in the INSERT — idempotent write in case of worker retry.

---

## Job Status State Machine

```
CREATED     -- run row inserted, not yet in Redis queue
    │
    ▼
QUEUED      -- run_id pushed to Redis q:pending
    │
    ▼
PROCESSING  -- worker claimed the job (BRPOPLPUSH)
    │
    ├──▶ COMPLETED   -- solver returned exit 10 (SAT) or 20 (UNSAT)
    ├──▶ FAILED      -- solver error, subprocess exception, or Redis enqueue failure
    └──▶ TIMEOUT     -- subprocess.TimeoutExpired raised
```

Additional states defined but not yet used in normal flow: `CANCELLED`, `RETRYING`.

### Timestamp handling

The `UPDATE_RUN_STATUS` query uses conditional `CASE` expressions:

```sql
UPDATE runs
SET status = %s,
    started_at = CASE
        WHEN %s = 'PROCESSING' THEN NOW()
        ELSE started_at
    END,
    finished_at = CASE
        WHEN %s IN ('COMPLETED', 'FAILED', 'TIMEOUT', 'CANCELLED') THEN NOW()
        ELSE finished_at
    END
WHERE id = %s;
```

Timestamps are set server-side with `NOW()` — not passed from the application layer. This prevents clock skew if workers run on different hosts in the future.

---

## SHA-256 Deduplication

### Normalization

Before hashing, the formula is normalized:
1. Split on whitespace
2. Validate each token against the operator allowlist (`&&`, `||`, `!`, `=>`, `<=>`) or as alphanumeric
3. Rejoin with single spaces (collapses any extra whitespace)

This ensures `"a  b ||"` and `"a b ||"` produce the same hash.

### Hashing

```python
hash_input = f"{notation}:{normalized_rpn}"
hashed_value = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
```

The `notation:` prefix prevents hash collisions between the same token sequence interpreted under different input formats. If a future input mode is added, its hashes will not collide with existing RPN hashes even if the token strings are identical.

### UPSERT

```sql
INSERT INTO formulas (normalized_input, hash, notation)
VALUES (%s, %s, %s)
ON CONFLICT (hash)
DO UPDATE SET hash = EXCLUDED.hash
RETURNING id;
```

`ON CONFLICT (hash)` returns the existing `id` if the formula is already stored, or inserts and returns the new `id`. The `DO UPDATE SET hash = EXCLUDED.hash` is a no-op update that satisfies the `RETURNING` requirement on conflict.

---

## Result Caching

After getting or creating a `formula_id`, `JobService` checks for a prior completed run:

```sql
SELECT id, status FROM runs
WHERE formula_id = %s AND status = 'COMPLETED'
ORDER BY finished_at DESC
LIMIT 1;
```

If found, the existing `run_id` is returned immediately — no new run is created, no Redis enqueue happens. The client fetches the cached result from the `results` table.

It also checks for an active run (CREATED, QUEUED, PROCESSING):

```sql
SELECT id, status FROM runs
WHERE formula_id = %s AND status IN ('CREATED', 'PROCESSING', 'QUEUED');
```

If found, the existing `run_id` is returned — the client can poll it for the result. This prevents duplicate solver invocations for the same formula submitted concurrently.

**Note:** Both cache checks are disabled for `CNF_SUDOKU` mode, because Sudoku results are puzzle-specific and caching them across sessions is not meaningful.

---

## Connection Pool

```python
psycopg2.ThreadedConnectionPool(
    minconn=DB_POOL_MIN,
    maxconn=DB_POOL_MAX,
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    connect_timeout=5,
)
```

`ThreadedConnectionPool` is safe for multi-threaded use (FastAPI runs workers in threads). Connections are borrowed with `pool.getconn()` and returned with `pool.putconn(conn)` in a `finally` block inside every `DatabaseService` method. This prevents connection leaks regardless of whether the operation succeeds or raises.
