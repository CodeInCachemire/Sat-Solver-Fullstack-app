# Layered Architecture & Dependency Injection

## Overview

The backend is organized into four strict layers. Each layer communicates only with its immediate neighbor — no router accesses the database directly, no service calls the HTTP layer, no data layer knows about business rules.

---

## The Four Layers

```
Layer 1 — API Routers
          /api/jobs, /api/sudoku, /api/health, /sync
          Responsibility: HTTP boundary only.
          - Parse and validate request shapes (Pydantic schemas)
          - Call the appropriate service method
          - Serialize the response
          - No business logic, no SQL, no Redis calls

Layer 2 — Service Classes
          JobService, QueueService, DatabaseService
          Responsibility: one class, one domain.
          - JobService: orchestrates the full job lifecycle
          - QueueService: owns all Redis queue operations
          - DatabaseService: owns all PostgreSQL operations
          Services are composed via constructor injection — they
          receive their dependencies, they don't instantiate them.

Layer 3 — Data Layer
          psycopg2.ThreadedConnectionPool, redis.ConnectionPool
          Responsibility: connection lifecycle management.
          - Initialized once at app startup (FastAPI lifespan)
          - Expose get/release functions; no query logic here
          - Pool teardown handled at shutdown

Layer 4 — Solver Layer
          backend/app/solvers/satsolver.py, sudoku_solver.py
          Responsibility: C binary invocation.
          - subprocess.run() with timeout
          - Parse stdout, check exit code
          - Return (process, runtime) tuple to the service layer
          - Completely decoupled — swapping the binary needs no
            changes above this layer
```

---

## Dependency Injection Wiring

FastAPI's `Depends()` system wires layers together without tight coupling. Dependencies are declared in `backend/app/core/dependencies.py`.

### QueueService — Singleton

```python
_queue_service: Optional[QueueService] = None

def init_queue_service() -> None:
    global _queue_service
    _queue_service = QueueService(get_redis_client())

# Called once in FastAPI lifespan (startup)
```

`QueueService` is initialized once with a reference to the Redis connection pool. All requests share the same instance — there is no per-request construction cost.

### DatabaseService — Generator Dependency (per-request)

```python
def get_db():
    yield DatabaseService(get_connection, release_connection)
```

`get_db` is a generator. FastAPI calls it before the handler runs and resumes it (past `yield`) when the handler completes — whether it returned normally or raised an exception. The `DatabaseService` is constructed with references to the pool's `get_conn` and `release_conn` functions. Connections are borrowed inside `DatabaseService` methods and returned in `finally` blocks. The generator pattern ensures the finally path runs unconditionally.

### JobService — Composed per-request

```python
def get_job_service(db: DatabaseService = Depends(get_db)) -> JobService:
    if _queue_service is None:
        raise RuntimeError("QueueService not initialized")
    return JobService(db, _queue_service)
```

`JobService` receives a fresh `DatabaseService` (per-request) and the singleton `QueueService`. It is constructed per-request but has no per-request state — it is purely a composition of its dependencies.

### Route handler — no service state

```python
@jobs_router.post("/submit", response_model=JobSubmitResponse)
def submit_job(
    request: JobSubmitRequest,
    job_service: JobService = Depends(get_job_service)
):
    return job_service.submit_job(request.formula, notation=request.notation, mode=request.mode)
```

The handler contains zero business logic. It receives a fully-wired `JobService` and delegates immediately.

---

## JobService Orchestration

`JobService.submit_job()` is the most complex method in the system. Its steps, in order:

```
1. Normalize formula (collapse whitespace, validate tokens against allowlist)
2. SHA-256 hash with notation prefix
3. UPSERT formula into PostgreSQL (get or create formula_id)
4. Check for cached completed run on this formula_id → return if found
5. Check for active (CREATED/QUEUED/PROCESSING) run → return if found
6. Create new run in PostgreSQL (status: CREATED)
7. Enqueue run_id to Redis
   └─ if redis.RedisError → update run to FAILED, raise HTTP 503
8. Update run status to QUEUED
9. Return JobSubmitResponse with run_id
```

Steps 4 and 5 are skipped for Sudoku mode (`CNF_SUDOKU`) because Sudoku results are puzzle-specific and not worth caching across sessions.

---

## Why This Structure

**Handlers stay thin:** A handler that calls one service method is testable in isolation. You can unit-test the service with a mock `DatabaseService` without spinning up a full HTTP server.

**Connection safety is structural, not by discipline:** The generator dependency ensures `release_conn()` is called in `finally` regardless of what happens in the handler. There is no way to forget to release a connection — the framework enforces it.

**Swapping implementations is localized:** Replacing PostgreSQL with a different store means rewriting `DatabaseService` and updating `get_db()`. Nothing else changes. The same applies to swapping Redis or the solver binary.

**No global state in handlers:** The singleton pattern for `QueueService` is an implementation detail of the dependency provider, not something handlers know about. From a handler's perspective, it just receives a `JobService` — how that was constructed is not its concern.
