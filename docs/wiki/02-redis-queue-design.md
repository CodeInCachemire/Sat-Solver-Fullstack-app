# Redis Queue Design

## Overview

The job queue is a Redis-backed three-stage pipeline. Jobs move forward only — they never re-enter a prior stage. All queue state mutations use pipelined transactions.

---

## Queue Stages

```
q:pending     → jobs waiting to be claimed by a worker
q:processing  → jobs currently held by a worker (in-flight)
q:dead        → jobs that exhausted max retries (3 attempts, currently unused path)
```

Jobs are stored as `run_id` integers in Redis lists. Payload and metadata live in separate keys:

```
job:{run_id}:payload  → JSON string (formula, mode, timeout_s)
job:{run_id}:meta     → HASH (attempts, created_at, last_claimed_at)
job:{run_id}:status   → string (mirrors PostgreSQL status; authoritative copy is in DB)
```

All keys have a 1-hour TTL set at enqueue time.

---

## Connection Pool Configuration

```python
redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    max_connections=REDIS_POOL_MAX_CONN,
    decode_responses=True,          # decode bytes → str at pool level
    socket_connect_timeout=3,       # fail fast on connection refused
    socket_timeout=15,              # MUST be above worker poll_timeout (5 s)
    health_check_interval=30,       # ping idle connections before use
    retry_on_timeout=True,          # retry on transient network blips
)
```

### Why `socket_timeout = 15 s` when the worker polls at 5 s

Workers call `BRPOPLPUSH` with a 5-second blocking timeout. If `socket_timeout` were also 5 s, there is a race condition: the OS socket layer could terminate the connection at the exact moment the blocking pop naturally returns `None` (no job available). This produces a spurious `TimeoutError` or `ConnectionError` instead of a clean `None`. Setting `socket_timeout` to 15 s ensures the socket outlives the blocking operation by a 3× margin.

---

## Enqueue (API → Queue)

```
Pipeline (transaction=True):
  SET  job:{run_id}:payload  <json>   EX 3600
  HSET job:{run_id}:meta     attempts=0, created_at=<now>, last_claimed_at=0
  SET  job:{run_id}:status   QUEUED   EX 3600
  RPUSH q:pending            <run_id>
```

All four commands execute atomically. If the pipeline fails, none of them apply — the caller catches `redis.RedisError` and marks the run `FAILED` in PostgreSQL.

---

## Claim (Queue → Worker)

```python
run_id_str = redis.brpoplpush("q:pending", "q:processing", timeout=5)
```

`BRPOPLPUSH` atomically moves the `run_id` from `q:pending` to `q:processing`. This is the critical choice:

| Operation | Behavior on worker crash |
|---|---|
| `BLPOP` | Job removed from queue. If worker crashes, job is gone. |
| `BRPOPLPUSH` | Job moved to `q:processing`. If worker crashes, `run_id` remains in `q:processing` — visible, inspectable, re-queueable. |

After a successful claim, a pipeline updates metadata:

```
Pipeline (transaction=True):
  HSET job:{run_id}:meta  last_claimed_at=<now>
  HINCRBY job:{run_id}:meta  attempts  1
```

Metadata update failure is non-fatal — logged but does not abort the job.

---

## Ack (Job Completed Successfully)

```
Pipeline (transaction=True):
  LREM q:processing  1  <run_id>
  DEL  job:{run_id}:payload
  DEL  job:{run_id}:meta
```

Status key (`job:{run_id}:status`) is left to expire via TTL. Database status is the canonical record.

---

## Fail (Job Failed or Timed Out)

```
Pipeline (transaction=True):
  LREM q:processing  1  <run_id>
  HSET job:{run_id}:meta  failed_at=<now>  last_error=<reason>
```

The worker handles DB status update separately. `fail()` on the queue is non-fatal if it itself errors — the database record is already updated before `fail()` is called.

---

## Worker Poll Loop

```python
while self.running:
    job = self.queue.claim(timeout_s=5)   # blocks up to 5 s
    if job is None:
        continue                           # no job, poll again — no CPU spin

    run_id, payload = job
    # ... invoke solver, write result, ack or fail
```

The worker's main loop uses the blocking pop to avoid busy-waiting. When `q:pending` is empty, the worker blocks at Redis for up to 5 s then loops — consuming no CPU while idle.

SIGTERM and SIGINT are handled via `signal.signal()` — `self.running = False` causes the loop to exit cleanly after the current job finishes.

---

## Why Pipeline `transaction=True` on Every Mutation

Redis pipelines batch multiple commands into a single round-trip. With `transaction=True`, they execute as a `MULTI/EXEC` block — atomically. Without this, a connection drop between two commands in a mutation leaves the queue in a partially-updated state (e.g., payload written but `run_id` not pushed to `q:pending`). With it, either all commands apply or none do.
