# System Architecture Overview

## Summary

Five Docker services coordinated by Docker Compose, routed by Nginx, deployed on AWS EC2 behind Cloudflare. Two frontend applications share one FastAPI backend. CPU-bound solver work is offloaded to background workers via a Redis job queue. PostgreSQL is the authoritative record for all job state.

---

## Architecture Diagram

```
                    ┌────────────────────────────────┐
                    │      Cloudflare  ·  AWS EC2    |
                    └────────────────┬───────────────┘
                                     │
                               ┌─────▼──────┐
                               │    Nginx   │
                               └─────┬──────┘
                ┌──────────────────── ┼ ───────────────────┐
           ┌────▼─────┐        /api/ │             ┌───────▼────────┐
           │   SAT    │              │             │    Sudoku      │
           │ Frontend │              │             │   Frontend     │
           └──────────┘       ┌──────▼──────┐      └────────────────┘
                              │   FastAPI   │
                              │   Backend   │
                              └──────┬──────┘
               ┌─────────────────────┼──────────────────────┐
          ┌────▼─────────┐    ┌──────▼──────┐   ┌───────────▼──────┐
          │  PostgreSQL  │    │    Redis    │   │  C SAT Solver    │
          │ (source of   │    │   (queue)   │   │     Binary       │
          │   truth)     │    └──────┬──────┘   └──────────────────┘
          └──────────────┘           │
                  ▲                  │
                  └────────┬─────────┘
                      ┌────▼────┐
                      │Worker×2 │
                      └─────────┘
```

---

## Docker Services

| Service | Image | Role |
|---|---|---|
| `redis` | Custom Dockerfile.redis | Job queue transport layer. Healthchecked with `redis-cli ping`. Data persisted via named volume. |
| `backend` | Dockerfile.backend | FastAPI application. Depends on Redis health check before starting. Hosts all API routes. |
| `worker-1` | Dockerfile.worker | Background worker. Polls Redis queue, invokes C binary, writes results to PostgreSQL. |
| `worker-2` | Dockerfile.worker | Identical to worker-1. `WORKER_ID` env var differentiates log output. Horizontal scale example. |
| `frontend` | Dockerfile.frontend | Nginx serving two static frontends (`/frontend`, `/sudoku_frontend`) and proxying `/api/` to backend. |

All services share a single Docker bridge network (`sat-solver-network`). Workers and backend access PostgreSQL on the host via `host.docker.internal`.

---

## Request Flow — Async Job (SAT Solver)

```
1. Client → POST /jobs/submit (formula in RPN)
2. FastAPI: normalize → SHA-256 hash → UPSERT formula into PostgreSQL
3. FastAPI: check for cached completed result → return run_id (< 10 ms)
4. FastAPI: check for existing active run → return run_id
5. FastAPI: INSERT run into PostgreSQL (status: CREATED)
6. FastAPI: enqueue run_id to Redis q:pending
   └─ if enqueue fails → UPDATE run status to FAILED, return HTTP 503
7. FastAPI: UPDATE run status to QUEUED, return run_id (< 100 ms total)

8. Worker: BRPOPLPUSH q:pending → q:processing (atomic)
9. Worker: fetch payload from Redis, update metadata (attempts, last_claimed_at)
10. Worker: invoke C binary via subprocess with formula + timeout
11. Worker: parse stdout (variable assignments) + check exit code (10=SAT, 20=UNSAT)
12. Worker: INSERT result into PostgreSQL (results table)
13. Worker: UPDATE run status → COMPLETED / FAILED / TIMEOUT
14. Worker: ACK — LREM from q:processing, DEL payload + metadata keys

15. Client polls GET /jobs/status/{run_id} → COMPLETED
16. Client fetches GET /jobs/result/{run_id} → assignment, result, runtime
```

---

## Request Flow — Sync Solve (Sudoku)

```
1. Client → POST /sudoku/solve (9×9 grid)
2. FastAPI: constraint propagation on input grid
3. FastAPI: encode grid to CNF (729 variables, ~3000 clauses)
4. FastAPI: invoke C binary directly (subprocess, 250 s timeout)
5. FastAPI: decode SAT output → reconstruct 9×9 solution
6. FastAPI: return solution (or UNSAT) synchronously
```

---

## Nginx Routing

```nginx
# satsolver.ahmadq.me
server {
    location /     { root /frontend;        }
    location /api/ { proxy_pass backend:8000; }
}

# sudokusolver.ahmadq.me
server {
    location /     { root /sudoku_frontend; }
    location /api/ { proxy_pass backend:8000; }
}
```

One container, two `server {}` blocks, one backend. Static assets served directly by Nginx; API calls proxied over the Docker bridge network.

---

## Key Architectural Decisions

**PostgreSQL over Redis as source of truth:** Every job's authoritative state lives in PostgreSQL. Redis is the transport layer. If Redis enqueue fails, the run is immediately marked `FAILED` in PostgreSQL — no silent loss.

**Async workers over in-process threads:** Solver invocations are subprocess calls that block for up to 10 s. Offloading to workers keeps the FastAPI event loop free for other requests and allows the worker count to scale independently of the API.

**Two workers as the default:** Two workers provide concurrency without complex orchestration. Adding a third is a one-line Docker Compose change (`worker-3` with an identical config).
