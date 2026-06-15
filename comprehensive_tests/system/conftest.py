"""
Session-scoped fixture that starts the full Docker Compose stack,
waits for health checks, runs all system tests, then tears down.

Prerequisites:
- Docker Desktop running
- Local PostgreSQL on port 5432 (sat_solver DB) — used by backend/workers via host.docker.internal
- Solver binaries in ./bin/ (optional — affects /ready endpoint but not /health)

Run with:
    pytest comprehensive_tests/system/ -m system -v --timeout=300
"""

import pathlib
import subprocess
import time

import pytest
import requests


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# system/ -> comprehensive_tests/ -> project root
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent

# ---------------------------------------------------------------------------
# Base URLs
# ---------------------------------------------------------------------------

BASE_API = "http://localhost:8000"
BASE_NGINX = "http://localhost:80"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def wait_for_url(url: str, timeout: int = 120, interval: int = 3, expected_status: int = 200) -> bool:
    """
    Poll *url* with a GET request until it responds with *expected_status* or
    the *timeout* (seconds) is exceeded.

    Returns True on success, raises TimeoutError on failure.
    """
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == expected_status:
                return True
        except Exception as exc:
            last_error = exc
        time.sleep(interval)
    raise TimeoutError(
        f"URL {url} did not become ready within {timeout}s. "
        f"Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Session fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def compose_stack():
    """
    Start the full Docker Compose stack (5 services), wait until the backend
    health endpoint responds with HTTP 200, yield URL bases for tests, then
    unconditionally tear the stack down.

    The fixture calls ``docker compose up --build -d`` so images are always
    rebuilt from the current source tree.  After all tests complete it calls
    ``docker compose down -v`` to remove containers *and* named volumes
    (including the Redis data volume).
    """

    # ------------------------------------------------------------------
    # 1. Build and start all services
    # ------------------------------------------------------------------
    subprocess.run(
        ["docker", "compose", "up", "--build", "-d"],
        check=True,
        timeout=300,
        cwd=str(PROJECT_ROOT),
    )

    # ------------------------------------------------------------------
    # 2. Wait for backend /health to return 200 (up to 120 s)
    # ------------------------------------------------------------------
    try:
        wait_for_url(f"{BASE_API}/health", timeout=120, interval=3)
    except TimeoutError:
        # Dump recent logs to help diagnose the failure before tearing down
        subprocess.run(
            ["docker", "compose", "logs", "--tail=50"],
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        pytest.fail("Backend did not become healthy within 120 seconds")

    # ------------------------------------------------------------------
    # 3. Yield URL bases to all tests
    # ------------------------------------------------------------------
    yield {"api": BASE_API, "nginx": BASE_NGINX}

    # ------------------------------------------------------------------
    # 4. Tear down — always runs even if tests fail
    # ------------------------------------------------------------------
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        check=False,
        timeout=60,
        cwd=str(PROJECT_ROOT),
    )
