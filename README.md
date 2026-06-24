# SAT Solver — Full-Stack Application

**Live:** [satsolver.ahmadq.me](https://satsolver.ahmadq.me) · [sudokusolver.ahmadq.me](https://sudokusolver.ahmadq.me)

![CI](https://github.com/CodeInCachemire/sat-solver-full-app/actions/workflows/ci.yml/badge.svg)

A production-deployed full-stack application built around a custom **DPLL SAT solver written in C**, exposed as two web tools via a shared Python backend: a general propositional logic terminal and a Sudoku solver with image upload and live NYT daily puzzle integration.

---
## Deep Documentation

Per-subsystem design docs in order [`docs/wiki/`](docs/wiki/):

1. [System Architecture](docs/wiki/01-system-architecture.md)
2. [Redis Queue Design](docs/wiki/02-redis-queue-design.md)
3. [Layered Architecture & Dependency Injection](docs/wiki/03-layered-architecture-di.md)
4. [C SAT Solver Pipeline](docs/wiki/04-c-solver-pipeline.md)
5. [Database Schema & Deduplication](docs/wiki/05-database-schema-deduplication.md)
6. [Infrastructure & Deployment](docs/wiki/06-infrastructure-deployment.md)

## Architecture

```
                    ┌────────────────────────────────┐
                    │      Cloudflare  ·  AWS EC2    │
                    └────────────────┬───────────────┘
                                     │
                               ┌─────▼──────┐
                               │    Nginx   │  routes two subdomains
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
                      │Worker×2 │  claim → invoke C binary → write DB
                      └─────────┘  (horizontally scalable)
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **PostgreSQL is source of truth, not Redis** | If Redis enqueue fails after a run is created in the DB, the run is immediately marked `FAILED`. Job state never silently disappears — the DB is always consistent. |
| **`BRPOPLPUSH` for atomic job claiming** | Moves a job from `q:pending` → `q:processing` atomically. A worker crash leaves the `run_id` in `q:processing` — visible and recoverable — rather than silently dropped from the queue. |
| **`socket_timeout` deliberately above worker `poll_timeout`** | Redis socket timeout is 15 s; worker blocking-pop timeout is 5 s. If they were equal, the OS socket layer could kill an in-progress `BRPOPLPUSH` at the same moment it naturally returns, causing a spurious connection error. |
| **Redis pipelines with `transaction=True`** | All queue mutations (enqueue, claim metadata, ack, fail) are batched into a single round-trip and executed atomically. Prevents partial state (e.g. job in queue but metadata not written) if the connection drops mid-operation. |
| **Strict four-layer architecture** | API routers handle HTTP only. `JobService`, `QueueService`, `DatabaseService` each own one responsibility. Solver layer invokes the C binary. No layer reaches past its neighbor. |
| **FastAPI `Depends()` for DI** | `QueueService` is a singleton initialized at startup. `DatabaseService` is a generator dependency — constructed per-request, connection returned to pool in the `finally` path regardless of exceptions. Services are composed, not coupled. |
| **SHA-256 deduplication before queuing** | Formula tokens are validated, normalized (whitespace collapsed), then SHA-256 hashed with a `notation:` prefix. `UPSERT ON CONFLICT (hash)` deduplicates storage. A completed result is returned in < 10 ms on repeat submission without touching the queue. |
| **Tseitin transform for SAT encoding** | Converts arbitrary propositional formulas to CNF with linear clause growth while preserving equisatisfiability. Sudoku uses direct CNF encoding: 729 boolean variables (9×9 × 9 values), ~3,000 clauses, with constraint propagation run as a pre-step to reduce the search space. |

---

## Tech Stack

| Layer | Technology |
|---|---|
| SAT Solver | C — DPLL, Tseitin transform, recursive-descent parser, custom lexer, DIMACS CNF parser |
| API | Python 3.11, FastAPI |
| Database | PostgreSQL · `psycopg2.ThreadedConnectionPool` |
| Queue | Redis · `redis.ConnectionPool` · `BRPOPLPUSH` |
| Image Extraction | Google Gemini API |
| Frontend (SAT) | Vanilla JS, HTML/CSS — terminal theme |
| Frontend (Sudoku) | Vanilla JS, HTML/CSS — newspaper theme |
| Containerisation | Docker · Docker Compose (5 services) |
| Reverse Proxy | Nginx — two subdomains, one backend |
| Hosting | AWS EC2 · Cloudflare DNS + CDN |
| CI | GitHub Actions |

---

## Running Locally

**Prerequisites:** Docker, Docker Compose, a local PostgreSQL instance.

```bash
# Fill in credentials
cp .env.aws.example .env.dev

# Build and start all 5 services (Redis, Backend, Worker×2, Nginx+Frontend)
docker compose up --build

# SAT solver terminal  →  http://localhost
# Backend API docs     →  http://localhost:8000/docs
```

**Run the C solver directly:**

```bash
make

# Propositional formula in RPN
echo "a b || a ! &&" | ./bin/satsolver_opt

# Direct CNF (DIMACS) input
./bin/satsolver_opt --cnf < formula.cnf
```

---

## Project Structure

```
├── src/                    # C SAT solver source — DPLL, Tseitin, lexer, parser, CNF parser
├── backend/
│   └── app/
│       ├── api/            # FastAPI routers — HTTP boundary, no business logic
│       ├── services/       # JobService · QueueService · DatabaseService
│       ├── solvers/        # Subprocess wrappers for the C binary
│       ├── db/             # Connection pool, SQL queries
│       └── redis/          # Redis pool, session management
├── frontend/               # SAT solver terminal UI
├── sudoku_frontend/        # Sudoku solver UI
├── docs/wiki/              # Per-subsystem design documentation
├── docker-compose.yml
└── nginx.conf
```

---

## CI

Every push to `main` triggers a GitHub Actions workflow that:

1. Builds the C solver and test runner via `make`
2. Verifies compiled binaries exist and are executable
3. Runs the full SAT solver unit test suite via `python3 test/run_tests.py`

See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---
