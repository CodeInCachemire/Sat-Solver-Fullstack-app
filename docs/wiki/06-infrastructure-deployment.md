# Infrastructure & Deployment

## Overview

The application runs as five Docker services on AWS EC2, behind Cloudflare for DNS, CDN, and SSL. A single Nginx container routes two subdomains and proxies API traffic to the backend. GitHub Actions handles CI on every push to `main`.

---

## Docker Compose Services

### `redis`

```yaml
build: Dockerfile.redis
ports: "6379:6379"
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 10s
  timeout: 5s
  retries: 3
volumes:
  - redis-data:/data   # persistent queue data across restarts
```

Standalone Redis instance. The backend and workers do not start until this health check passes (`depends_on: redis: condition: service_healthy`). Queue data is persisted via a named volume so in-flight jobs survive container restarts.

### `backend`

```yaml
build: Dockerfile.backend
ports: "8000:8000"
depends_on:
  redis:
    condition: service_healthy
extra_hosts:
  - "host.docker.internal:host-gateway"
volumes:
  - ./bin:/app/bin:ro   # C solver binaries, read-only
```

The `host.docker.internal` extra host allows the backend to reach a PostgreSQL instance running on the host machine (used for local development and the current deployment). `./bin` is mounted read-only — the C binary is built outside Docker and injected at runtime.

### `worker-1` / `worker-2`

```yaml
build: Dockerfile.worker
environment:
  WORKER_ID: worker-1   # differentiates log output only
volumes:
  - ./bin:/app/bin:ro
```

Identical images differentiated only by `WORKER_ID`. Both poll the same Redis queue. Adding a third worker is a copy-paste of this block with `WORKER_ID: worker-3`. Workers do not expose any ports — they only communicate outbound to Redis and PostgreSQL.

### `frontend` (Nginx)

```yaml
build: Dockerfile.frontend
ports: "80:80"
depends_on:
  - backend
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:80/"]
```

Serves both static frontends and proxies `/api/` to the backend container. The Dockerfile copies `frontend/` and `sudoku_frontend/` directories into the Nginx image at build time.

---

## Nginx Configuration

```nginx
# satsolver.ahmadq.me
server {
    listen 80;
    server_name satsolver.ahmadq.me;

    location / {
        root /usr/share/nginx/html/frontend;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# sudokusolver.ahmadq.me
server {
    listen 80;
    server_name sudokusolver.ahmadq.me;

    location / {
        root /usr/share/nginx/html/sudoku_frontend;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000/;
        # ... same headers
    }
}
```

One container, two `server {}` blocks, one backend upstream. Both subdomains proxy to `backend:8000` via the Docker bridge network (`sat-solver-network`). Static files are served directly by Nginx from the image filesystem — no I/O round-trip to the backend.

---

## AWS + Cloudflare

```
Browser
  │
  ▼  DNS → Cloudflare
Cloudflare
  │  Cache static assets (JS, CSS, HTML)
  │  SSL termination (HTTPS → HTTP to origin)
  │
  ▼  HTTP to origin
AWS EC2
  │
  ▼
Docker Compose (all 5 services)
```

**Cloudflare responsibilities:**
- DNS resolution for both subdomains
- CDN caching of static frontend assets — reduces origin load for returning visitors
- SSL/TLS termination — the EC2 instance serves HTTP on port 80; Cloudflare provides HTTPS to browsers
- DDoS protection at the edge

**AWS responsibilities:**
- EC2 instance running Docker Compose
- Inbound port 80 open (Cloudflare → EC2)
- PostgreSQL running on the host (not containerized in current deployment)

---

## GitHub Actions CI

```yaml
# .github/workflows/ci.yml
on:
  push:    { branches: [main] }
  pull_request: { branches: [main] }

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install build dependencies
        run: sudo apt-get install -y build-essential python3 python3-pip
      - name: Build
        run: mkdir -p bin && make clean && make
      - name: Verify binaries
        run: |
          test -x bin/satsolver_opt
          test -x bin/testrunner
      - name: Run tests
        run: python3 test/run_tests.py
```

The CI pipeline validates the C solver on every push. The backend and frontend have no build step — they are validated at runtime. The Python test runner feeds known SAT/UNSAT formulas to the solver binary and checks exit codes and variable assignments against expected outputs.

---

## Docker Network

All services share `sat-solver-network` (bridge driver). Inter-service communication uses container names as hostnames:

```
backend  → redis:6379       (queue operations)
worker-1 → redis:6379       (queue operations)
worker-2 → redis:6379       (queue operations)
frontend → backend:8000     (API proxy)
backend  → host.docker.internal:5432  (PostgreSQL on host)
worker-* → host.docker.internal:5432  (PostgreSQL on host)
```

The backend and workers use `extra_hosts: host.docker.internal:host-gateway` to resolve the host machine's IP — enabling access to a PostgreSQL instance running outside Docker.

---

## Environment Configuration

Environment variables are loaded at runtime from `.env.dev` (development) or injected by the hosting environment (production). Key variables:

| Variable | Used by | Purpose |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | backend, workers | PostgreSQL connection |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` | backend, workers | Redis connection |
| `GEMINI_API_KEY` | backend | Google Gemini image extraction |
| `ALLOWED_ORIGINS` | backend | CORS origin whitelist |
| `WORKER_ID` | workers | Log differentiation |

CORS origins are configured in the backend to allow both subdomains (`satsolver.ahmadq.me`, `sudokusolver.ahmadq.me`) plus localhost for development.
