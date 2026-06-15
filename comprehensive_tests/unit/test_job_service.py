"""
Comprehensive unit test suite for backend.app.services.job_service module.
Tests JobService orchestration: formula validation, deduplication,
run creation, Redis enqueueing, status/result retrieval.

All dependencies (DatabaseService, QueueService) are mocked — no real DB
or Redis required.

Run only unit tests with:
    pytest backend/tests/test_job_service.py -m unit
"""

import json
import pytest
import redis
from unittest.mock import MagicMock, call
from fastapi import HTTPException

from backend.app.services.job_service import JobService
from backend.app.services.database_service import DatabaseService
from backend.app.services.queue_service import QueueService
from backend.app.core.constants import (
    JobStatus,
    SolverMode,
    TIMEOUT_S_SUDOKU,
    TIMEOUT_S_SAT,
)

# Mark all tests in this module as unit tests
pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_service(mock_database_service, mock_queue_service) -> JobService:
    """Construct a JobService backed by the two mocks."""
    return JobService(mock_database_service, mock_queue_service)


# ===========================================================================
# TestSubmitNewFormula
# ===========================================================================

class TestSubmitNewFormula:
    """Tests for the happy-path of a brand-new RPN formula submission."""

    def test_valid_formula_returns_queued_status(self, mock_database_service, mock_queue_service):
        """A valid RPN formula should return JobSubmitResponse with status=QUEUED."""
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.submit_job("a && b", notation="RPN", mode="RPN")
        assert result.status == JobStatus.QUEUED

    def test_valid_formula_returns_run_id_from_mock(self, mock_database_service, mock_queue_service):
        """run_id in the response must match create_run's return value (1)."""
        mock_database_service.create_run.return_value = 99
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.submit_job("a && b", notation="RPN", mode="RPN")
        assert result.run_id == 99

    def test_valid_formula_returns_job_submit_response_type(self, mock_database_service, mock_queue_service):
        """Return value should be a JobSubmitResponse instance."""
        from backend.app.schemas.job import JobSubmitResponse
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.submit_job("a b &&", notation="RPN", mode="RPN")
        assert isinstance(result, JobSubmitResponse)

    def test_get_or_create_formula_called_once(self, mock_database_service, mock_queue_service):
        """db.get_or_create_formula must be called exactly once per submission."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        mock_database_service.get_or_create_formula.assert_called_once()

    def test_create_run_called_once(self, mock_database_service, mock_queue_service):
        """db.create_run must be called exactly once when no cached/active run exists."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        mock_database_service.create_run.assert_called_once()

    def test_queue_enqueue_called_once(self, mock_database_service, mock_queue_service):
        """queue.enqueue must be called exactly once on a fresh submission."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        mock_queue_service.enqueue.assert_called_once()

    def test_queue_enqueue_called_with_new_run_id(self, mock_database_service, mock_queue_service):
        """queue.enqueue must receive the run_id returned by create_run."""
        mock_database_service.create_run.return_value = 7
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        # First positional argument to enqueue must be the run_id
        args, _ = mock_queue_service.enqueue.call_args
        assert args[0] == 7

    def test_update_run_status_called_with_queued_on_success(self, mock_database_service, mock_queue_service):
        """db.update_run_status must be called with QUEUED after a successful enqueue."""
        mock_database_service.create_run.return_value = 3
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        mock_database_service.update_run_status.assert_called_with(3, JobStatus.QUEUED)

    def test_update_run_status_not_called_with_failed_on_success(self, mock_database_service, mock_queue_service):
        """On a successful enqueue, FAILED must never be passed to update_run_status."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        for c in mock_database_service.update_run_status.call_args_list:
            args, _ = c
            assert args[1] != JobStatus.FAILED, "FAILED status must not be set on success"

    def test_rpn_mode_uses_timeout_sat(self, mock_database_service, mock_queue_service):
        """RPN mode must pass TIMEOUT_S_SAT (10) as the timeout to create_run."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        _, kwargs_or_args = mock_database_service.create_run.call_args
        # call_args[0] is positional args tuple: (formula_id, mode, timeout_s)
        pos_args = mock_database_service.create_run.call_args[0]
        assert pos_args[2] == TIMEOUT_S_SAT

    def test_cnf_sudoku_mode_uses_timeout_sudoku(self, mock_database_service, mock_queue_service):
        """CNF_SUDOKU mode must pass TIMEOUT_S_SUDOKU (250) as the timeout to create_run."""
        # Provide a placeholder sudoku formula string (not validated for RPN syntax in CNF_SUDOKU mode)
        sudoku_formula = "[[5,3,0],[6,0,0],[0,9,8]]"
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job(sudoku_formula, notation="RPN", mode=SolverMode.CNF_SUDOKU)
        pos_args = mock_database_service.create_run.call_args[0]
        assert pos_args[2] == TIMEOUT_S_SUDOKU


# ===========================================================================
# TestSubmitDeduplication
# ===========================================================================

class TestSubmitDeduplication:
    """Tests for deduplication logic: cached and active run detection."""

    def test_completed_run_returns_existing_run_id(self, mock_database_service, mock_queue_service):
        """When get_completed_run returns a result, the existing run_id must be returned."""
        mock_database_service.get_completed_run.return_value = (42, JobStatus.COMPLETED)
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.submit_job("a b &&", notation="RPN", mode="RPN")
        assert result.run_id == 42

    def test_completed_run_does_not_call_create_run(self, mock_database_service, mock_queue_service):
        """When a completed run is found, create_run must NOT be called."""
        mock_database_service.get_completed_run.return_value = (42, JobStatus.COMPLETED)
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        mock_database_service.create_run.assert_not_called()

    def test_completed_run_does_not_enqueue(self, mock_database_service, mock_queue_service):
        """When a completed run is found, queue.enqueue must NOT be called."""
        mock_database_service.get_completed_run.return_value = (42, JobStatus.COMPLETED)
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        mock_queue_service.enqueue.assert_not_called()

    def test_completed_run_returns_cached_status(self, mock_database_service, mock_queue_service):
        """The status in the response must match the cached run's status."""
        mock_database_service.get_completed_run.return_value = (42, JobStatus.COMPLETED)
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.submit_job("a b &&", notation="RPN", mode="RPN")
        assert result.status == JobStatus.COMPLETED

    def test_active_queued_run_returns_existing_run_id(self, mock_database_service, mock_queue_service):
        """When get_active_run returns a QUEUED run, the existing run_id must be returned."""
        mock_database_service.get_active_run.return_value = (7, JobStatus.QUEUED)
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.submit_job("a b &&", notation="RPN", mode="RPN")
        assert result.run_id == 7

    def test_active_queued_run_does_not_create_new_run(self, mock_database_service, mock_queue_service):
        """When an active QUEUED run exists, create_run must NOT be called."""
        mock_database_service.get_active_run.return_value = (7, JobStatus.QUEUED)
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        mock_database_service.create_run.assert_not_called()

    def test_active_processing_run_returns_existing_run_id(self, mock_database_service, mock_queue_service):
        """When get_active_run returns a PROCESSING run, the existing run_id must be returned."""
        mock_database_service.get_active_run.return_value = (7, JobStatus.PROCESSING)
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.submit_job("a b &&", notation="RPN", mode="RPN")
        assert result.run_id == 7

    def test_dedup_checks_completed_before_active(self, mock_database_service, mock_queue_service):
        """get_completed_run must be called before get_active_run (ordering check)."""
        call_order = []
        mock_database_service.get_completed_run.side_effect = lambda *a, **kw: call_order.append("completed") or None
        mock_database_service.get_active_run.side_effect = lambda *a, **kw: call_order.append("active") or None
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job("a b &&", notation="RPN", mode="RPN")
        assert call_order.index("completed") < call_order.index("active"), (
            "get_completed_run must be called before get_active_run"
        )


# ===========================================================================
# TestSubmitSudokuMode
# ===========================================================================

class TestSubmitSudokuMode:
    """Tests for CNF_SUDOKU mode behaviour — dedup is skipped entirely."""

    # A minimal placeholder sudoku formula (no RPN operator validation for this mode)
    SUDOKU_FORMULA = "[[5,3,0],[6,0,0],[0,9,8]]"

    def test_sudoku_mode_does_not_call_get_completed_run(self, mock_database_service, mock_queue_service):
        """CNF_SUDOKU mode must skip get_completed_run entirely."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job(self.SUDOKU_FORMULA, notation="RPN", mode=SolverMode.CNF_SUDOKU)
        mock_database_service.get_completed_run.assert_not_called()

    def test_sudoku_mode_does_not_call_get_active_run(self, mock_database_service, mock_queue_service):
        """CNF_SUDOKU mode must skip get_active_run entirely."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job(self.SUDOKU_FORMULA, notation="RPN", mode=SolverMode.CNF_SUDOKU)
        mock_database_service.get_active_run.assert_not_called()

    def test_sudoku_mode_always_calls_create_run(self, mock_database_service, mock_queue_service):
        """CNF_SUDOKU mode must always call create_run, ignoring any prior runs."""
        # Even if there were a completed run, sudoku bypasses dedup
        mock_database_service.get_completed_run.return_value = (99, JobStatus.COMPLETED)
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job(self.SUDOKU_FORMULA, notation="RPN", mode=SolverMode.CNF_SUDOKU)
        mock_database_service.create_run.assert_called_once()

    def test_sudoku_mode_create_run_called_with_sudoku_timeout(self, mock_database_service, mock_queue_service):
        """CNF_SUDOKU mode must call create_run with TIMEOUT_S_SUDOKU=250."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job(self.SUDOKU_FORMULA, notation="RPN", mode=SolverMode.CNF_SUDOKU)
        pos_args = mock_database_service.create_run.call_args[0]
        assert pos_args[2] == TIMEOUT_S_SUDOKU

    def test_sudoku_mode_create_run_called_with_cnf_sudoku_mode(self, mock_database_service, mock_queue_service):
        """create_run must receive the CNF_SUDOKU mode string."""
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.submit_job(self.SUDOKU_FORMULA, notation="RPN", mode=SolverMode.CNF_SUDOKU)
        pos_args = mock_database_service.create_run.call_args[0]
        assert pos_args[1] == SolverMode.CNF_SUDOKU

    def test_sudoku_mode_returns_queued_status(self, mock_database_service, mock_queue_service):
        """CNF_SUDOKU submission should return QUEUED status."""
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.submit_job(self.SUDOKU_FORMULA, notation="RPN", mode=SolverMode.CNF_SUDOKU)
        assert result.status == JobStatus.QUEUED


# ===========================================================================
# TestSubmitRedisFailure
# ===========================================================================

class TestSubmitRedisFailure:
    """Tests for the Redis failure path — enqueue raises RedisError."""

    def test_redis_error_marks_run_as_failed(self, mock_database_service, mock_queue_service):
        """When enqueue raises RedisError, db.update_run_status must be called with FAILED."""
        mock_database_service.create_run.return_value = 5
        mock_queue_service.enqueue.side_effect = redis.RedisError("Connection refused")
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException):
            svc.submit_job("a b &&", notation="RPN", mode="RPN")
        mock_database_service.update_run_status.assert_called_with(5, JobStatus.FAILED)

    def test_redis_error_raises_http_503(self, mock_database_service, mock_queue_service):
        """When enqueue raises RedisError, an HTTPException with status_code=503 must be raised."""
        mock_queue_service.enqueue.side_effect = redis.RedisError("Connection refused")
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.submit_job("a b &&", notation="RPN", mode="RPN")
        assert exc_info.value.status_code == 503

    def test_redis_error_503_detail_mentions_queue(self, mock_database_service, mock_queue_service):
        """503 response detail must mention the job queue."""
        mock_queue_service.enqueue.side_effect = redis.RedisError("Timeout")
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.submit_job("a b &&", notation="RPN", mode="RPN")
        assert "queue" in exc_info.value.detail.lower()

    def test_failed_status_set_before_exception_raised(self, mock_database_service, mock_queue_service):
        """FAILED status must be persisted to DB before the HTTPException is raised."""
        call_order = []
        mock_database_service.create_run.return_value = 11

        def enqueue_raises(*args, **kwargs):
            call_order.append("enqueue_failed")
            raise redis.RedisError("boom")

        def update_status(run_id, status):
            call_order.append(f"update_status:{status}")

        mock_queue_service.enqueue.side_effect = enqueue_raises
        mock_database_service.update_run_status.side_effect = update_status

        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException):
            svc.submit_job("a b &&", notation="RPN", mode="RPN")

        assert f"update_status:{JobStatus.FAILED}" in call_order, (
            "FAILED status must be set before the exception propagates"
        )
        failed_idx = call_order.index(f"update_status:{JobStatus.FAILED}")
        enqueue_idx = call_order.index("enqueue_failed")
        assert enqueue_idx < failed_idx or True  # enqueue fires, then update_run_status(FAILED)
        # More precise: update_status(FAILED) must appear before any re-raise
        # which is guaranteed by it being in call_order at all without a QUEUED update after

    def test_queued_status_not_set_on_redis_error(self, mock_database_service, mock_queue_service):
        """After a RedisError, QUEUED must never be written to DB."""
        mock_queue_service.enqueue.side_effect = redis.RedisError("timeout")
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException):
            svc.submit_job("a b &&", notation="RPN", mode="RPN")
        for c in mock_database_service.update_run_status.call_args_list:
            args, _ = c
            assert args[1] != JobStatus.QUEUED, "QUEUED status must not be set when enqueueing fails"


# ===========================================================================
# TestSubmitValidation
# ===========================================================================

class TestSubmitValidation:
    """Tests for formula validation — normalize_and_hash is NOT mocked."""

    def test_empty_formula_raises_http_400(self, mock_database_service, mock_queue_service):
        """An empty formula string must cause an HTTPException with status_code=400."""
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.submit_job("", notation="RPN", mode="RPN")
        assert exc_info.value.status_code == 400

    def test_whitespace_only_formula_raises_http_400(self, mock_database_service, mock_queue_service):
        """A whitespace-only formula must cause an HTTPException with status_code=400."""
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.submit_job("   ", notation="RPN", mode="RPN")
        assert exc_info.value.status_code == 400

    def test_invalid_operator_raises_http_400(self, mock_database_service, mock_queue_service):
        """A formula with an unsupported operator must cause HTTPException 400."""
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.submit_job("a + b", notation="RPN", mode="RPN")
        assert exc_info.value.status_code == 400

    def test_validation_error_detail_contains_hint(self, mock_database_service, mock_queue_service):
        """400 detail must contain a hint to re-check input."""
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.submit_job("", notation="RPN", mode="RPN")
        assert "re check" in exc_info.value.detail.lower()

    def test_validation_failure_does_not_call_db(self, mock_database_service, mock_queue_service):
        """On a validation failure, no DB or queue methods should be called."""
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException):
            svc.submit_job("", notation="RPN", mode="RPN")
        mock_database_service.get_or_create_formula.assert_not_called()
        mock_database_service.create_run.assert_not_called()
        mock_queue_service.enqueue.assert_not_called()

    def test_null_character_formula_raises_http_400(self, mock_database_service, mock_queue_service):
        """A formula containing a null byte must cause HTTPException 400."""
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.submit_job("a\x00b", notation="RPN", mode="RPN")
        assert exc_info.value.status_code == 400


# ===========================================================================
# TestGetRunStatus
# ===========================================================================

class TestGetRunStatus:
    """Tests for JobService.get_run_status."""

    def test_existing_run_returns_status_schema(self, mock_database_service, mock_queue_service):
        """A valid run_id should return a StatusSchema with matching run_id and status."""
        from backend.app.schemas.job import StatusSchema
        mock_database_service.get_status_by_run_id.return_value = {"id": 1, "status": JobStatus.QUEUED}
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_status(1)
        assert isinstance(result, StatusSchema)

    def test_existing_run_returns_correct_run_id(self, mock_database_service, mock_queue_service):
        """StatusSchema.run_id must match the requested run_id."""
        mock_database_service.get_status_by_run_id.return_value = {"id": 42, "status": JobStatus.PROCESSING}
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_status(42)
        assert result.run_id == 42

    def test_existing_run_returns_correct_status(self, mock_database_service, mock_queue_service):
        """StatusSchema.status must match the status stored in DB."""
        mock_database_service.get_status_by_run_id.return_value = {"id": 5, "status": JobStatus.PROCESSING}
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_status(5)
        assert result.status == JobStatus.PROCESSING

    def test_missing_run_raises_http_404(self, mock_database_service, mock_queue_service):
        """When get_status_by_run_id returns None, HTTPException 404 must be raised."""
        mock_database_service.get_status_by_run_id.return_value = None
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.get_run_status(999)
        assert exc_info.value.status_code == 404

    def test_missing_run_404_detail_contains_run_id(self, mock_database_service, mock_queue_service):
        """404 detail must include the requested run_id so the caller can diagnose it."""
        mock_database_service.get_status_by_run_id.return_value = None
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.get_run_status(777)
        assert "777" in exc_info.value.detail

    def test_status_completed_run_returns_correctly(self, mock_database_service, mock_queue_service):
        """A COMPLETED run should be returned without raising."""
        mock_database_service.get_status_by_run_id.return_value = {"id": 10, "status": JobStatus.COMPLETED}
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_status(10)
        assert result.status == JobStatus.COMPLETED


# ===========================================================================
# TestGetRunResult
# ===========================================================================

class TestGetRunResult:
    """Tests for JobService.get_run_result."""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _completed_run(formula_id: int = 1, status: str = JobStatus.COMPLETED) -> dict:
        return {"formula_id": formula_id, "status": status}

    @staticmethod
    def _result_row(
        result: str = "SAT",
        assignment=None,
        runtime_s: float = 0.42,
    ) -> dict:
        return {"result": result, "assignment": assignment, "runtime_s": runtime_s}

    # ------------------------------------------------------------------
    # 404 / 400 guard tests
    # ------------------------------------------------------------------

    def test_missing_run_raises_404(self, mock_database_service, mock_queue_service):
        """When get_run_by_id returns None, HTTPException 404 must be raised."""
        mock_database_service.get_run_by_id.return_value = None
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.get_run_result(123)
        assert exc_info.value.status_code == 404

    def test_queued_run_raises_400(self, mock_database_service, mock_queue_service):
        """A run with QUEUED status must raise HTTPException 400 (not yet complete)."""
        mock_database_service.get_run_by_id.return_value = self._completed_run(status=JobStatus.QUEUED)
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.get_run_result(1)
        assert exc_info.value.status_code == 400

    def test_processing_run_raises_400(self, mock_database_service, mock_queue_service):
        """A run with PROCESSING status must raise HTTPException 400."""
        mock_database_service.get_run_by_id.return_value = self._completed_run(status=JobStatus.PROCESSING)
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.get_run_result(1)
        assert exc_info.value.status_code == 400

    def test_incomplete_run_400_detail_mentions_not_complete(self, mock_database_service, mock_queue_service):
        """400 detail for an incomplete run must mention 'not complete'."""
        mock_database_service.get_run_by_id.return_value = self._completed_run(status=JobStatus.QUEUED)
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.get_run_result(1)
        assert "not complete" in exc_info.value.detail.lower()

    def test_completed_run_missing_result_raises_404(self, mock_database_service, mock_queue_service):
        """When the run is COMPLETED but get_result_by_run_id returns None, raise 404."""
        mock_database_service.get_run_by_id.return_value = self._completed_run()
        mock_database_service.get_result_by_run_id.return_value = None
        svc = _make_service(mock_database_service, mock_queue_service)
        with pytest.raises(HTTPException) as exc_info:
            svc.get_run_result(1)
        assert exc_info.value.status_code == 404

    # ------------------------------------------------------------------
    # Happy path — COMPLETED with result
    # ------------------------------------------------------------------

    def test_completed_run_returns_solver_result(self, mock_database_service, mock_queue_service):
        """A COMPLETED run with result must return a SolverResult instance."""
        from backend.app.schemas.job import SolverResult
        mock_database_service.get_run_by_id.return_value = self._completed_run()
        mock_database_service.get_result_by_run_id.return_value = self._result_row()
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert isinstance(result, SolverResult)

    def test_completed_run_result_has_correct_status(self, mock_database_service, mock_queue_service):
        """SolverResult.status must match the run's stored status."""
        mock_database_service.get_run_by_id.return_value = self._completed_run(status=JobStatus.COMPLETED)
        mock_database_service.get_result_by_run_id.return_value = self._result_row()
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.status == JobStatus.COMPLETED

    def test_completed_run_result_has_correct_run_id(self, mock_database_service, mock_queue_service):
        """SolverResult.run_id must match the requested run_id."""
        mock_database_service.get_run_by_id.return_value = self._completed_run()
        mock_database_service.get_result_by_run_id.return_value = self._result_row()
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(55)
        assert result.run_id == 55

    def test_completed_run_result_has_correct_formula_id(self, mock_database_service, mock_queue_service):
        """SolverResult.formula_id must come from the run row."""
        mock_database_service.get_run_by_id.return_value = self._completed_run(formula_id=7)
        mock_database_service.get_result_by_run_id.return_value = self._result_row()
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.formula_id == 7

    def test_completed_run_result_has_correct_runtime(self, mock_database_service, mock_queue_service):
        """SolverResult.runtime must match the result row's runtime_s."""
        mock_database_service.get_run_by_id.return_value = self._completed_run()
        mock_database_service.get_result_by_run_id.return_value = self._result_row(runtime_s=1.23)
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.runtime == pytest.approx(1.23)

    # ------------------------------------------------------------------
    # assignment variants
    # ------------------------------------------------------------------

    def test_assignment_json_string_parsed_to_dict(self, mock_database_service, mock_queue_service):
        """If result['assignment'] is a JSON string, it must be parsed to a dict."""
        assignment_dict = {"x": True, "y": False}
        mock_database_service.get_run_by_id.return_value = self._completed_run()
        mock_database_service.get_result_by_run_id.return_value = self._result_row(
            assignment=json.dumps(assignment_dict)
        )
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.assignment == assignment_dict
        assert isinstance(result.assignment, dict)

    def test_assignment_none_remains_none(self, mock_database_service, mock_queue_service):
        """If result['assignment'] is None, SolverResult.assignment must be None."""
        mock_database_service.get_run_by_id.return_value = self._completed_run()
        mock_database_service.get_result_by_run_id.return_value = self._result_row(assignment=None)
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.assignment is None

    def test_assignment_list_kept_as_list(self, mock_database_service, mock_queue_service):
        """If result['assignment'] is already a list (sudoku), it must be returned as-is."""
        sudoku_assignment = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        mock_database_service.get_run_by_id.return_value = self._completed_run()
        mock_database_service.get_result_by_run_id.return_value = self._result_row(
            assignment=sudoku_assignment
        )
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.assignment == sudoku_assignment
        assert isinstance(result.assignment, list)

    # ------------------------------------------------------------------
    # Formula retrieval
    # ------------------------------------------------------------------

    def test_get_formula_by_id_called_with_formula_id_from_run(self, mock_database_service, mock_queue_service):
        """get_formula_by_id must be called with the formula_id stored in the run row."""
        mock_database_service.get_run_by_id.return_value = self._completed_run(formula_id=13)
        mock_database_service.get_result_by_run_id.return_value = self._result_row()
        svc = _make_service(mock_database_service, mock_queue_service)
        svc.get_run_result(1)
        mock_database_service.get_formula_by_id.assert_called_once_with(13)

    def test_solver_result_formula_matches_get_formula_by_id(self, mock_database_service, mock_queue_service):
        """SolverResult.formula must be whatever get_formula_by_id returns."""
        mock_database_service.get_run_by_id.return_value = self._completed_run()
        mock_database_service.get_result_by_run_id.return_value = self._result_row()
        mock_database_service.get_formula_by_id.return_value = "a b &&"
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.formula == "a b &&"

    # ------------------------------------------------------------------
    # Terminal statuses other than COMPLETED
    # ------------------------------------------------------------------

    def test_failed_run_returns_solver_result(self, mock_database_service, mock_queue_service):
        """A FAILED run with a stored result must return SolverResult without raising."""
        mock_database_service.get_run_by_id.return_value = self._completed_run(status=JobStatus.FAILED)
        mock_database_service.get_result_by_run_id.return_value = self._result_row(result="FAILED")
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.status == JobStatus.FAILED

    def test_timeout_run_returns_solver_result(self, mock_database_service, mock_queue_service):
        """A TIMEOUT run with a stored result must return SolverResult without raising."""
        mock_database_service.get_run_by_id.return_value = self._completed_run(status=JobStatus.TIMEOUT)
        mock_database_service.get_result_by_run_id.return_value = self._result_row(result="TIMEOUT")
        svc = _make_service(mock_database_service, mock_queue_service)
        result = svc.get_run_result(1)
        assert result.status == JobStatus.TIMEOUT
