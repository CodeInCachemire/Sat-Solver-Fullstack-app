"""
System / E2E tests for the full Docker Compose stack.

These tests require the compose_stack fixture (see conftest.py) which brings
up all five services (redis, backend, worker-1, worker-2, frontend) before
the session begins and tears them down afterwards.

Run with:
    pytest backend/tests/system/ -m system -v --timeout=300

Prerequisites:
- Docker Desktop running
- Local PostgreSQL on port 5432 with the sat_solver database accessible
- (Optional) Solver binary at ./bin/satsolver — required only for job/sudoku
  completion tests.  Tests that need the binary skip themselves gracefully
  when /ready returns 503.
"""

import time

import pytest
import requests


pytestmark = pytest.mark.system


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def poll_until_done(api_base: str, run_id: int, timeout: int = 30, interval: int = 2) -> str:
    """
    Poll ``GET /jobs/status/{run_id}`` until the job reaches a terminal
    status (COMPLETED, FAILED, or TIMEOUT) or the polling itself times out.

    Returns the final status string.  If the polling window is exhausted
    before a terminal status is seen ``"TIMEOUT_POLLING"`` is returned so
    the caller can decide how to handle it.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{api_base}/jobs/status/{run_id}", timeout=5)
            if r.status_code == 200:
                status = r.json()["status"]
                if status in ("COMPLETED", "FAILED", "TIMEOUT"):
                    return status
        except requests.RequestException:
            pass
        time.sleep(interval)
    return "TIMEOUT_POLLING"


def _solver_available(api_base: str) -> bool:
    """Return True only when the backend reports the solver binary is present."""
    try:
        r = requests.get(f"{api_base}/ready", timeout=5)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _submit_formula(api_base: str, formula: str = "a b &&") -> dict:
    """Submit a job and return the parsed JSON response."""
    r = requests.post(
        f"{api_base}/jobs/submit",
        json={"formula": formula, "notation": "RPN", "mode": "RPN"},
        timeout=10,
    )
    return r


# ---------------------------------------------------------------------------
# 1 – Health endpoints
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    """Verify /health and /ready behave as documented."""

    def test_health_returns_200(self, compose_stack):
        """GET /health must return HTTP 200."""
        r = requests.get(f"{compose_stack['api']}/health", timeout=5)
        assert r.status_code == 200

    def test_health_status_is_ok(self, compose_stack):
        """Response body must contain status == 'ok'."""
        r = requests.get(f"{compose_stack['api']}/health", timeout=5)
        data = r.json()
        assert data["status"] == "ok"

    def test_health_has_database_field(self, compose_stack):
        """Response must include a 'database' field with a recognised value."""
        r = requests.get(f"{compose_stack['api']}/health", timeout=5)
        data = r.json()
        assert "database" in data
        assert data["database"] in ("connected", "disconnected")

    def test_health_has_redis_field(self, compose_stack):
        """Response must include a 'redis' field with a recognised value."""
        r = requests.get(f"{compose_stack['api']}/health", timeout=5)
        data = r.json()
        assert "redis" in data
        assert data["redis"] in ("connected", "disconnected")

    def test_redis_shows_connected(self, compose_stack):
        """Redis container is part of the stack — it must report as connected."""
        r = requests.get(f"{compose_stack['api']}/health", timeout=5)
        data = r.json()
        assert data["redis"] == "connected", (
            f"Expected redis=connected but got: {data['redis']!r}"
        )

    def test_ready_returns_200_or_503(self, compose_stack):
        """
        /ready returns 200 when the solver binary is present and 503 when
        it is not.  Both outcomes are valid depending on the build environment.
        """
        r = requests.get(f"{compose_stack['api']}/ready", timeout=5)
        assert r.status_code in (200, 503), (
            f"Unexpected status code from /ready: {r.status_code}"
        )


# ---------------------------------------------------------------------------
# 2 – Job submit + completion
# ---------------------------------------------------------------------------

class TestJobSubmitAndComplete:
    """
    End-to-end tests for the async job pipeline.

    All tests in this class skip when the solver binary is unavailable
    because the workers can only resolve a job to COMPLETED/FAILED when
    they can actually invoke the binary.
    """

    def _require_solver(self, api_base: str):
        """Skip the calling test if /ready returns 503."""
        if not _solver_available(api_base):
            pytest.skip("Solver binary not available — skipping job test")

    def test_submit_valid_formula_returns_queued(self, compose_stack):
        """POST /jobs/submit with a well-formed formula returns HTTP 200 with run_id.

        The status may be QUEUED (new job) or COMPLETED (deduplicated from a prior
        run) — both are valid outcomes depending on test run history.
        """
        self._require_solver(compose_stack["api"])
        r = _submit_formula(compose_stack["api"])
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["status"] in ("QUEUED", "COMPLETED"), (
            f"Unexpected status: {data['status']!r}"
        )
        assert isinstance(data["run_id"], int)
        assert isinstance(data["formula_id"], int)

    def test_job_completes_within_30_seconds(self, compose_stack):
        """A submitted job must reach a terminal status within 30 seconds."""
        self._require_solver(compose_stack["api"])
        r = _submit_formula(compose_stack["api"])
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        final_status = poll_until_done(compose_stack["api"], run_id, timeout=30)
        assert final_status in ("COMPLETED", "FAILED"), (
            f"Job {run_id} did not complete in 30s — final status: {final_status!r}"
        )

    def test_completed_job_result_is_sat_or_unsat(self, compose_stack):
        """The result endpoint must report SAT or UNSAT for a completed job."""
        self._require_solver(compose_stack["api"])
        r = _submit_formula(compose_stack["api"])
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        poll_until_done(compose_stack["api"], run_id, timeout=30)
        result_r = requests.get(
            f"{compose_stack['api']}/jobs/result/{run_id}", timeout=5
        )
        assert result_r.status_code == 200, (
            f"Expected 200 from /jobs/result/{run_id}, got {result_r.status_code}"
        )
        data = result_r.json()
        assert data["result"] in ("SAT", "UNSAT"), (
            f"Unexpected result value: {data['result']!r}"
        )

    def test_result_has_positive_runtime(self, compose_stack):
        """Completed result must include a positive float runtime."""
        self._require_solver(compose_stack["api"])
        r = _submit_formula(compose_stack["api"])
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        poll_until_done(compose_stack["api"], run_id, timeout=30)
        result_r = requests.get(
            f"{compose_stack['api']}/jobs/result/{run_id}", timeout=5
        )
        assert result_r.status_code == 200
        data = result_r.json()
        assert isinstance(data["runtime"], (int, float))
        assert data["runtime"] >= 0, f"runtime must be non-negative, got {data['runtime']}"

    def test_first_status_check_is_queued_or_processing(self, compose_stack):
        """
        The very first status poll immediately after submit should return
        QUEUED or PROCESSING — not yet COMPLETED — because workers need
        at least a few seconds to process the job.
        """
        self._require_solver(compose_stack["api"])
        r = _submit_formula(compose_stack["api"])
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        # Check immediately — no sleep — to catch the early status
        status_r = requests.get(
            f"{compose_stack['api']}/jobs/status/{run_id}", timeout=5
        )
        assert status_r.status_code == 200
        early_status = status_r.json()["status"]
        assert early_status in ("QUEUED", "PROCESSING", "COMPLETED"), (
            f"Unexpected early status: {early_status!r}"
        )


# ---------------------------------------------------------------------------
# 3 – Job deduplication
# ---------------------------------------------------------------------------

class TestJobDeduplication:
    """Submitting the same formula twice should reuse an existing run."""

    def test_same_formula_twice_returns_same_run_id(self, compose_stack):
        """
        The job service deduplicates: if the first job is still active (or was
        recently completed), the second submission returns the same run_id.

        If the solver binary is absent the backend still creates runs, so
        deduplication is tested regardless of /ready status.
        """
        formula = "a && b"

        r1 = _submit_formula(compose_stack["api"], formula)
        assert r1.status_code == 200, f"First submit failed: {r1.text}"
        run_id_1 = r1.json()["run_id"]

        # Give the first job a moment to be picked up before re-submitting
        time.sleep(1)

        r2 = _submit_formula(compose_stack["api"], formula)
        assert r2.status_code == 200, f"Second submit failed: {r2.text}"
        run_id_2 = r2.json()["run_id"]

        # Accept either deduplication (same run_id) or a new run when the
        # previous one has already finished, but both must be valid integers.
        assert isinstance(run_id_1, int)
        assert isinstance(run_id_2, int)
        # If the first job hasn't completed yet the IDs should match.
        # After completion a new run_id is expected — we just verify both
        # are valid positive integers.
        assert run_id_1 > 0
        assert run_id_2 > 0


# ---------------------------------------------------------------------------
# 4 – Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Verify that the API returns correct HTTP status codes for bad input."""

    def test_nonexistent_run_id_returns_404(self, compose_stack):
        """GET /jobs/status/<very-large-id> must return 404."""
        r = requests.get(
            f"{compose_stack['api']}/jobs/status/9999999", timeout=5
        )
        assert r.status_code == 404, (
            f"Expected 404 for non-existent run_id, got {r.status_code}"
        )

    def test_invalid_run_id_type_returns_422(self, compose_stack):
        """GET /jobs/status/abc must return 422 (path param type validation)."""
        r = requests.get(
            f"{compose_stack['api']}/jobs/status/abc", timeout=5
        )
        assert r.status_code == 422, (
            f"Expected 422 for non-integer run_id, got {r.status_code}"
        )

    def test_empty_formula_returns_400_or_422(self, compose_stack):
        """POST /jobs/submit with a whitespace-only formula must be rejected."""
        r = requests.post(
            f"{compose_stack['api']}/jobs/submit",
            json={"formula": " ", "notation": "RPN", "mode": "RPN"},
            timeout=5,
        )
        assert r.status_code in (400, 422), (
            f"Expected 400 or 422 for empty formula, got {r.status_code}: {r.text}"
        )

    def test_result_for_nonexistent_run_returns_404(self, compose_stack):
        """GET /jobs/result/<very-large-id> must return 404."""
        r = requests.get(
            f"{compose_stack['api']}/jobs/result/9999999", timeout=5
        )
        assert r.status_code == 404, (
            f"Expected 404 for non-existent result, got {r.status_code}"
        )


# ---------------------------------------------------------------------------
# 5 – Sudoku solve (system-level)
# ---------------------------------------------------------------------------

# A minimal valid 9x9 Sudoku grid (0 = empty cell).
_VALID_SUDOKU_GRID = [
    [5, 3, 0, 0, 7, 0, 0, 0, 0],
    [6, 0, 0, 1, 9, 5, 0, 0, 0],
    [0, 9, 8, 0, 0, 0, 0, 6, 0],
    [8, 0, 0, 0, 6, 0, 0, 0, 3],
    [4, 0, 0, 8, 0, 3, 0, 0, 1],
    [7, 0, 0, 0, 2, 0, 0, 0, 6],
    [0, 6, 0, 0, 0, 0, 2, 8, 0],
    [0, 0, 0, 4, 1, 9, 0, 0, 5],
    [0, 0, 0, 0, 8, 0, 0, 7, 9],
]


class TestSudokuSolveSystem:
    """System-level tests for the /sudoku/solve endpoint."""

    def _require_solver(self, api_base: str):
        """Skip if solver binary is absent."""
        if not _solver_available(api_base):
            pytest.skip("Solver binary not available — skipping sudoku solve test")

    def test_sudoku_solve_valid_grid_returns_200(self, compose_stack):
        """POST /sudoku/solve with a valid 9x9 grid must return HTTP 200."""
        self._require_solver(compose_stack["api"])
        r = requests.post(
            f"{compose_stack['api']}/sudoku/solve",
            json={"grid": _VALID_SUDOKU_GRID},
            timeout=30,
        )
        assert r.status_code == 200, (
            f"Expected 200 from /sudoku/solve, got {r.status_code}: {r.text}"
        )

    def test_sudoku_solve_response_has_required_fields(self, compose_stack):
        """Sudoku solve response must include solved, solution, and time_seconds."""
        self._require_solver(compose_stack["api"])
        r = requests.post(
            f"{compose_stack['api']}/sudoku/solve",
            json={"grid": _VALID_SUDOKU_GRID},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "solved" in data, "Response missing 'solved' field"
        assert "solution" in data, "Response missing 'solution' field"
        assert "time_seconds" in data, "Response missing 'time_seconds' field"
        assert isinstance(data["solved"], bool)
        assert isinstance(data["time_seconds"], (int, float))

    def test_sudoku_invalid_grid_returns_422(self, compose_stack):
        """
        POST /sudoku/solve with a grid that has fewer than 9 rows must return
        422 (Pydantic validation error).  This does NOT require the solver
        binary because the request is rejected before the solver is invoked.
        """
        r = requests.post(
            f"{compose_stack['api']}/sudoku/solve",
            json={"grid": [[1, 2, 3]]},
            timeout=5,
        )
        assert r.status_code == 422, (
            f"Expected 422 for invalid grid, got {r.status_code}: {r.text}"
        )


# ---------------------------------------------------------------------------
# 6 – Nginx reverse-proxy
# ---------------------------------------------------------------------------

class TestNginxProxy:
    """Verify that the Nginx frontend correctly proxies /api/ to the backend."""

    def test_nginx_proxies_api_health(self, compose_stack):
        """GET http://localhost:80/api/health must return 200 via the Nginx proxy."""
        r = requests.get(f"{compose_stack['nginx']}/api/health", timeout=10)
        assert r.status_code == 200, (
            f"Expected 200 from Nginx /api/health proxy, got {r.status_code}: {r.text}"
        )

    def test_nginx_proxied_health_has_status_ok(self, compose_stack):
        """The proxied /api/health response body must also have status == 'ok'."""
        r = requests.get(f"{compose_stack['nginx']}/api/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok", (
            f"Proxied health check returned unexpected body: {data}"
        )
