"""
Integration tests for backend.app.services.database_service module.
Tests against a real PostgreSQL instance to verify actual database behaviour.

Prerequisites:
- postgres-test container running on localhost:5433
- Start with: docker compose -f docker-compose.test.yml up -d

Run only integration tests with:
    pytest backend/tests/integration/ -m integration

Skip integration tests with:
    pytest -m "not integration"
"""

import json
import pytest

from backend.app.core.constants import JobStatus, SolverMode

# Mark every test in this file as an integration test
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_formula(db_service, suffix="abc123", notation="RPN"):
    """Insert a formula and return its id."""
    return db_service.get_or_create_formula(
        f"a && b ({suffix})", suffix, notation
    )


def _make_run(db_service, formula_id, mode=SolverMode.CNF_SUDOKU, timeout_s=5):
    """Create a run and return its id."""
    return db_service.create_run(formula_id, mode, timeout_s)


# ---------------------------------------------------------------------------
# TestFormulaOperations
# ---------------------------------------------------------------------------

class TestFormulaOperations:
    """Tests for get_or_create_formula and get_formula_by_id."""

    def test_insert_new_formula_returns_int_id(self, db_service):
        """get_or_create_formula returns an integer id for a new formula."""
        formula_id = db_service.get_or_create_formula("a && b", "hash_new_1", "RPN")
        assert isinstance(formula_id, int)
        assert formula_id > 0

    def test_same_hash_returns_same_id(self, db_service):
        """Inserting the same hash twice returns the same id both times."""
        id1 = db_service.get_or_create_formula("a && b", "hash_dup", "RPN")
        id2 = db_service.get_or_create_formula("a && b", "hash_dup", "RPN")
        assert id1 == id2

    def test_different_hashes_return_different_ids(self, db_service):
        """Two different hashes produce two distinct formula ids."""
        id1 = db_service.get_or_create_formula("a && b", "hash_alpha", "RPN")
        id2 = db_service.get_or_create_formula("c || d", "hash_beta", "RPN")
        assert id1 != id2

    def test_formula_stored_with_correct_normalized_input(self, db_service):
        """get_formula_by_id returns the normalized_input that was stored."""
        normalized = "p && q && r"
        formula_id = db_service.get_or_create_formula(normalized, "hash_norm_01", "RPN")
        retrieved = db_service.get_formula_by_id(formula_id)
        assert retrieved == normalized


# ---------------------------------------------------------------------------
# TestRunLifecycle
# ---------------------------------------------------------------------------

class TestRunLifecycle:
    """Tests for create_run, update_run_status, get_run_by_id, and
    get_status_by_run_id."""

    def test_create_run_returns_int_id(self, db_service):
        """create_run returns an integer run id."""
        formula_id = _make_formula(db_service, "hash_run_01")
        run_id = _make_run(db_service, formula_id)
        assert isinstance(run_id, int)
        assert run_id > 0

    def test_initial_run_status_is_created(self, db_service):
        """A freshly created run has status CREATED."""
        formula_id = _make_formula(db_service, "hash_run_02")
        run_id = _make_run(db_service, formula_id)
        status_data = db_service.get_status_by_run_id(run_id)
        assert status_data is not None
        assert status_data["status"] == JobStatus.CREATED

    def test_update_run_status_to_queued(self, db_service):
        """update_run_status to QUEUED is reflected by get_status_by_run_id."""
        formula_id = _make_formula(db_service, "hash_run_03")
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.QUEUED)
        status_data = db_service.get_status_by_run_id(run_id)
        assert status_data["status"] == JobStatus.QUEUED

    def test_update_run_status_to_processing_sets_started_at(self, db_service):
        """Transitioning to PROCESSING sets started_at to a non-None value."""
        formula_id = _make_formula(db_service, "hash_run_04")
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.PROCESSING)
        run_data = db_service.get_run_by_id(run_id)
        assert run_data["started_at"] is not None

    def test_update_run_status_to_completed_sets_finished_at(self, db_service):
        """Transitioning to COMPLETED sets finished_at to a non-None value."""
        formula_id = _make_formula(db_service, "hash_run_05")
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.PROCESSING)
        db_service.update_run_status(run_id, JobStatus.COMPLETED)
        run_data = db_service.get_run_by_id(run_id)
        assert run_data["finished_at"] is not None

    def test_get_run_by_id_returns_all_eight_fields(self, db_service):
        """get_run_by_id returns a dict with all 8 expected keys."""
        formula_id = _make_formula(db_service, "hash_run_06")
        run_id = _make_run(db_service, formula_id)
        run_data = db_service.get_run_by_id(run_id)
        assert run_data is not None
        for key in ("id", "formula_id", "status", "created_at",
                    "started_at", "finished_at", "timeout_s", "mode"):
            assert key in run_data, f"Missing key: {key}"

    def test_get_status_by_run_id_for_missing_id_returns_none(self, db_service):
        """get_status_by_run_id returns None for a non-existent run id."""
        result = db_service.get_status_by_run_id(999999)
        assert result is None

    def test_get_run_by_id_for_missing_id_returns_none(self, db_service):
        """get_run_by_id returns None for a non-existent run id."""
        result = db_service.get_run_by_id(999999)
        assert result is None


# ---------------------------------------------------------------------------
# TestInsertAndGetResult
# ---------------------------------------------------------------------------

class TestInsertAndGetResult:
    """Tests for insert_result and get_result_by_run_id."""

    def _setup_completed_run(self, db_service, hash_suffix):
        """Helper: create a formula + run in COMPLETED state, return run_id."""
        formula_id = _make_formula(db_service, hash_suffix)
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.PROCESSING)
        db_service.update_run_status(run_id, JobStatus.COMPLETED)
        return run_id

    def test_insert_result_stores_data(self, db_service):
        """After insert_result, get_result_by_run_id returns a non-None dict."""
        run_id = self._setup_completed_run(db_service, "hash_res_01")
        db_service.insert_result(run_id, "SAT", {"x1": True},
                                 "stdout text", "stderr text",
                                 None, None, 0.5)
        result = db_service.get_result_by_run_id(run_id)
        assert result is not None
        assert isinstance(result, dict)

    def test_result_field_is_correct(self, db_service):
        """The result field "SAT" is stored and retrieved intact."""
        run_id = self._setup_completed_run(db_service, "hash_res_02")
        db_service.insert_result(run_id, "SAT", None, "", "", None, None, 0.1)
        result = db_service.get_result_by_run_id(run_id)
        assert result["result"] == "SAT"

    def test_assignment_stored_and_retrieved(self, db_service):
        """An assignment dict is stored as JSON and can be retrieved."""
        run_id = self._setup_completed_run(db_service, "hash_res_03")
        assignment = {"x1": True, "x2": False}
        db_service.insert_result(run_id, "SAT", assignment, "", "", None, None, 0.2)
        result = db_service.get_result_by_run_id(run_id)
        # The service stores it as JSON; it may come back as str or dict
        raw = result["assignment"]
        if isinstance(raw, str):
            retrieved = json.loads(raw)
        else:
            retrieved = raw
        assert retrieved == assignment

    def test_assignment_none_stored_as_null(self, db_service):
        """Passing None for assignment stores NULL and retrieves as None."""
        run_id = self._setup_completed_run(db_service, "hash_res_04")
        db_service.insert_result(run_id, "UNSAT", None, "", "", None, None, 0.05)
        result = db_service.get_result_by_run_id(run_id)
        assert result["assignment"] is None

    def test_runtime_s_stored_correctly(self, db_service):
        """runtime_s is stored and retrieved with reasonable float precision."""
        run_id = self._setup_completed_run(db_service, "hash_res_05")
        db_service.insert_result(run_id, "SAT", None, "", "", None, None, 0.042)
        result = db_service.get_result_by_run_id(run_id)
        assert result["runtime_s"] == pytest.approx(0.042, rel=1e-3)

    def test_duplicate_insert_ignored_on_conflict_do_nothing(self, db_service):
        """Inserting a result for the same run_id twice does not raise and
        keeps only the first result (ON CONFLICT DO NOTHING)."""
        run_id = self._setup_completed_run(db_service, "hash_res_06")
        db_service.insert_result(run_id, "SAT", None, "first", "", None, None, 0.1)
        # Second insert should be silently ignored
        db_service.insert_result(run_id, "UNSAT", None, "second", "", None, None, 0.9)
        result = db_service.get_result_by_run_id(run_id)
        # Only the first row should be present
        assert result["result"] == "SAT"
        assert result["stdout"] == "first"


# ---------------------------------------------------------------------------
# TestDeduplicationQueries
# ---------------------------------------------------------------------------

class TestDeduplicationQueries:
    """Tests for get_active_run and get_completed_run deduplication helpers."""

    def test_get_active_run_returns_tuple_for_queued_run(self, db_service):
        """A run in QUEUED state is found by get_active_run."""
        formula_id = _make_formula(db_service, "hash_dedup_01")
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.QUEUED)
        active = db_service.get_active_run(formula_id)
        assert active is not None
        assert active[0] == run_id
        assert active[1] == JobStatus.QUEUED

    def test_get_active_run_returns_tuple_for_processing_run(self, db_service):
        """A run in PROCESSING state is found by get_active_run."""
        formula_id = _make_formula(db_service, "hash_dedup_02")
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.PROCESSING)
        active = db_service.get_active_run(formula_id)
        assert active is not None
        assert active[0] == run_id
        assert active[1] == JobStatus.PROCESSING

    def test_get_active_run_returns_none_for_completed_run(self, db_service):
        """A run in COMPLETED state is NOT returned by get_active_run."""
        formula_id = _make_formula(db_service, "hash_dedup_03")
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.PROCESSING)
        db_service.update_run_status(run_id, JobStatus.COMPLETED)
        active = db_service.get_active_run(formula_id)
        assert active is None

    def test_get_completed_run_returns_tuple_for_completed_run(self, db_service):
        """get_completed_run returns (run_id, 'COMPLETED') for a completed run."""
        formula_id = _make_formula(db_service, "hash_dedup_04")
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.PROCESSING)
        db_service.update_run_status(run_id, JobStatus.COMPLETED)
        completed = db_service.get_completed_run(formula_id)
        assert completed is not None
        assert completed[0] == run_id
        assert completed[1] == JobStatus.COMPLETED

    def test_get_completed_run_returns_none_for_queued_run(self, db_service):
        """get_completed_run returns None when the run is only QUEUED."""
        formula_id = _make_formula(db_service, "hash_dedup_05")
        run_id = _make_run(db_service, formula_id)
        db_service.update_run_status(run_id, JobStatus.QUEUED)
        completed = db_service.get_completed_run(formula_id)
        assert completed is None

    def test_get_active_run_returns_none_when_no_runs_exist(self, db_service):
        """get_active_run returns None for a formula that has no runs at all."""
        formula_id = _make_formula(db_service, "hash_dedup_06")
        # Intentionally create NO run for this formula
        active = db_service.get_active_run(formula_id)
        assert active is None


# ---------------------------------------------------------------------------
# TestConcurrency
# ---------------------------------------------------------------------------

class TestConcurrency:
    """Tests for idempotency and UPSERT behaviour under repeated calls."""

    def test_upsert_is_idempotent(self, db_service, pg_connection):
        """Calling get_or_create_formula 3 times with the same hash always
        returns the same id and results in exactly one row in formulas."""
        hash_value = "hash_idem_01"
        id1 = db_service.get_or_create_formula("x && y", hash_value, "RPN")
        id2 = db_service.get_or_create_formula("x && y", hash_value, "RPN")
        id3 = db_service.get_or_create_formula("x && y", hash_value, "RPN")

        assert id1 == id2 == id3

        # Verify only one row exists in the database
        with pg_connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM formulas WHERE hash = %s", (hash_value,))
            count = cur.fetchone()[0]
        assert count == 1
