"""
Comprehensive unit test suite for backend.app.worker module.
Tests the Worker class and sudoku_helper function with all external
dependencies (subprocess, DB, queue) mocked.

Run only unit tests:
    pytest backend/tests/test_worker.py -m unit
"""

import json
import signal
import subprocess
import pytest
from unittest.mock import MagicMock, patch, call

from backend.app.worker import Worker, sudoku_helper
from backend.app.services.queue_service import QueueService
from backend.app.services.database_service import DatabaseService
from backend.app.core.constants import (
    JobStatus,
    SolverMode,
    SolverExitCodes,
    TIMEOUT_S_SAT,
    TIMEOUT_S_SUDOKU,
)

# ---------------------------------------------------------------------------
# Module-level marker
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_process(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    """Build a mock object that mimics subprocess.CompletedProcess."""
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


STANDARD_PAYLOAD = {
    "formula": "a && b",
    "mode": "RPN",
    "formula_id": 1,
    "timeout_s": 10,
}

RUN_ID = 42


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_queue():
    svc = MagicMock(spec=QueueService)
    svc.claim.return_value = None
    svc.ack.return_value = None
    svc.fail.return_value = None
    return svc


@pytest.fixture
def mock_db():
    svc = MagicMock(spec=DatabaseService)
    svc.update_run_status.return_value = None
    svc.insert_result.return_value = None
    return svc


@pytest.fixture
def worker(mock_queue, mock_db):
    return Worker(queue=mock_queue, db=mock_db, poll_timeout_s=5)


# ===========================================================================
# TestSignalHandling
# ===========================================================================

class TestSignalHandling:
    """Worker signal handling and initial state."""

    def test_worker_starts_with_running_true(self, worker):
        assert worker.running is True

    def test_handle_shutdown_signal_sigterm_sets_running_false(self, worker):
        worker._handle_shutdown_signal(signal.SIGTERM, None)
        assert worker.running is False

    def test_handle_shutdown_signal_sigint_sets_running_false(self, worker):
        worker._handle_shutdown_signal(signal.SIGINT, None)
        assert worker.running is False

    def test_handle_shutdown_signal_called_twice_stays_false(self, worker):
        worker._handle_shutdown_signal(signal.SIGTERM, None)
        worker._handle_shutdown_signal(signal.SIGTERM, None)
        assert worker.running is False

    def test_install_signal_handlers_registers_sigterm(self, worker):
        with patch("signal.signal") as mock_signal:
            worker.install_signal_handlers()
            calls = mock_signal.call_args_list
            registered_sigs = [c[0][0] for c in calls]
            assert signal.SIGTERM in registered_sigs

    def test_install_signal_handlers_registers_sigint(self, worker):
        with patch("signal.signal") as mock_signal:
            worker.install_signal_handlers()
            calls = mock_signal.call_args_list
            registered_sigs = [c[0][0] for c in calls]
            assert signal.SIGINT in registered_sigs


# ===========================================================================
# TestProcessJobSAT  (mode="RPN", rc=10)
# ===========================================================================

class TestProcessJobSAT:
    """_process_job with RPN mode and SAT return code (10)."""

    def _run(self, worker, mock_db, mock_queue, monkeypatch):
        mock_proc = make_mock_process(
            returncode=SolverExitCodes.SAT,
            stdout="SAT\nv 1 2 0\n",
        )
        monkeypatch.setattr(
            "backend.app.worker.run_solver",
            lambda **kw: (mock_proc, 0.05),
        )
        monkeypatch.setattr(
            "backend.app.worker.parse_solver_output",
            lambda stdout: ("SAT", {"1": True, "2": True}),
        )
        worker._process_job(RUN_ID, STANDARD_PAYLOAD)

    def test_update_run_status_processing_called_first(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        first_call = mock_db.update_run_status.call_args_list[0]
        assert first_call == call(RUN_ID, JobStatus.PROCESSING)

    def test_insert_result_called_with_sat(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_db.insert_result.assert_called_once()
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "SAT"
        assert kwargs["run_id"] == RUN_ID

    def test_update_run_status_completed_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        status_calls = [c[0][1] for c in mock_db.update_run_status.call_args_list]
        assert JobStatus.COMPLETED in status_calls

    def test_queue_ack_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.ack.assert_called_once_with(RUN_ID)

    def test_queue_fail_not_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.fail.assert_not_called()

    def test_insert_result_error_type_is_none(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["error_type"] is None
        assert kwargs["error_message"] is None

    def test_runtime_s_forwarded_to_insert_result(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["runtime_s"] == pytest.approx(0.05)


# ===========================================================================
# TestProcessJobUNSAT  (mode="RPN", rc=20)
# ===========================================================================

class TestProcessJobUNSAT:
    """_process_job with RPN mode and UNSAT return code (20)."""

    def _run(self, worker, mock_db, mock_queue, monkeypatch):
        mock_proc = make_mock_process(
            returncode=SolverExitCodes.UNSAT,
            stdout="UNSAT\n",
        )
        monkeypatch.setattr(
            "backend.app.worker.run_solver",
            lambda **kw: (mock_proc, 0.03),
        )
        monkeypatch.setattr(
            "backend.app.worker.parse_solver_output",
            lambda stdout: ("UNSAT", None),
        )
        worker._process_job(RUN_ID, STANDARD_PAYLOAD)

    def test_insert_result_called_with_unsat(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "UNSAT"

    def test_update_run_status_completed_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        status_calls = [c[0][1] for c in mock_db.update_run_status.call_args_list]
        assert JobStatus.COMPLETED in status_calls

    def test_queue_ack_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.ack.assert_called_once_with(RUN_ID)

    def test_queue_fail_not_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.fail.assert_not_called()

    def test_insert_result_error_fields_are_none(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["error_type"] is None
        assert kwargs["error_message"] is None


# ===========================================================================
# TestProcessJobParseError  (rc=30)
# ===========================================================================

class TestProcessJobParseError:
    """_process_job when solver returns PARSE_ERROR exit code (30)."""

    def _run(self, worker, mock_db, mock_queue, monkeypatch):
        mock_proc = make_mock_process(
            returncode=SolverExitCodes.PARSE_ERROR,
            stdout="",
            stderr="Syntax error in formula",
        )
        monkeypatch.setattr(
            "backend.app.worker.run_solver",
            lambda **kw: (mock_proc, 0.01),
        )
        worker._process_job(RUN_ID, STANDARD_PAYLOAD)

    def test_insert_result_result_is_parse_error(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "PARSE_ERROR"

    def test_insert_result_error_type_is_parse_error(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["error_type"] == "PARSE_ERROR"

    def test_insert_result_assignment_is_none(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["assignment"] is None

    def test_update_run_status_failed_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        status_calls = [c[0][1] for c in mock_db.update_run_status.call_args_list]
        assert JobStatus.FAILED in status_calls

    def test_queue_ack_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.ack.assert_called_once_with(RUN_ID)

    def test_stderr_forwarded_to_insert_result(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["stderr"] == "Syntax error in formula"


# ===========================================================================
# TestProcessJobUnexpectedRC  (rc=99)
# ===========================================================================

class TestProcessJobUnexpectedRC:
    """_process_job when solver returns an unexpected exit code."""

    def _run(self, worker, mock_db, mock_queue, monkeypatch):
        mock_proc = make_mock_process(returncode=99, stdout="", stderr="")
        monkeypatch.setattr(
            "backend.app.worker.run_solver",
            lambda **kw: (mock_proc, 0.02),
        )
        worker._process_job(RUN_ID, STANDARD_PAYLOAD)

    def test_insert_result_result_is_unexpected_returncode(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "UNEXPECTED_RETURNCODE"

    def test_insert_result_error_type_is_unexpected_rc(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["error_type"] == "UNEXPECTED_RC"

    def test_insert_result_error_message_contains_rc(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert "99" in kwargs["error_message"]

    def test_update_run_status_failed_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        status_calls = [c[0][1] for c in mock_db.update_run_status.call_args_list]
        assert JobStatus.FAILED in status_calls

    def test_queue_ack_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.ack.assert_called_once_with(RUN_ID)

    def test_insert_result_assignment_is_none(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["assignment"] is None


# ===========================================================================
# TestProcessJobTimeout
# ===========================================================================

class TestProcessJobTimeout:
    """_process_job when run_solver raises subprocess.TimeoutExpired."""

    def _run(self, worker, mock_db, mock_queue, monkeypatch):
        def raise_timeout(**kw):
            raise subprocess.TimeoutExpired(cmd="solver", timeout=TIMEOUT_S_SAT)

        monkeypatch.setattr("backend.app.worker.run_solver", raise_timeout)
        worker._process_job(RUN_ID, STANDARD_PAYLOAD)

    def test_insert_result_result_is_timeout(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "TIMEOUT"

    def test_insert_result_error_type_is_timeout(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["error_type"] == "TIMEOUT"

    def test_insert_result_assignment_is_none(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["assignment"] is None

    def test_insert_result_stdout_and_stderr_empty(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["stdout"] == ""
        assert kwargs["stderr"] == ""

    def test_update_run_status_timeout_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        status_calls = [c[0][1] for c in mock_db.update_run_status.call_args_list]
        assert JobStatus.TIMEOUT in status_calls

    def test_queue_ack_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.ack.assert_called_once_with(RUN_ID)


# ===========================================================================
# TestProcessJobBinaryNotFound
# ===========================================================================

class TestProcessJobBinaryNotFound:
    """_process_job when run_solver raises FileNotFoundError."""

    def _run(self, worker, mock_db, mock_queue, monkeypatch):
        monkeypatch.setattr(
            "backend.app.worker.run_solver",
            lambda **kw: (_ for _ in ()).throw(FileNotFoundError("solver binary not found")),
        )
        worker._process_job(RUN_ID, STANDARD_PAYLOAD)

    def test_insert_result_result_is_error(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "ERROR"

    def test_insert_result_error_type_is_binary_not_found(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["error_type"] == "BINARY_NOT_FOUND"

    def test_insert_result_assignment_is_none(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["assignment"] is None

    def test_insert_result_runtime_is_zero(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["runtime_s"] == 0

    def test_update_run_status_failed_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        status_calls = [c[0][1] for c in mock_db.update_run_status.call_args_list]
        assert JobStatus.FAILED in status_calls

    def test_queue_ack_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.ack.assert_called_once_with(RUN_ID)


# ===========================================================================
# TestProcessJobGenericException
# ===========================================================================

class TestProcessJobGenericException:
    """_process_job when run_solver raises a generic RuntimeError."""

    def _run(self, worker, mock_db, mock_queue, monkeypatch):
        monkeypatch.setattr(
            "backend.app.worker.run_solver",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("test error")),
        )
        worker._process_job(RUN_ID, STANDARD_PAYLOAD)

    def test_insert_result_result_is_exec_error(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "EXEC_ERROR"

    def test_insert_result_error_type_is_execution_error(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["error_type"] == "EXECUTION_ERROR"

    def test_insert_result_error_message_is_test_error(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["error_message"] == "test error"

    def test_insert_result_assignment_is_none(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["assignment"] is None

    def test_insert_result_runtime_is_zero(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["runtime_s"] == 0

    def test_update_run_status_failed_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        status_calls = [c[0][1] for c in mock_db.update_run_status.call_args_list]
        assert JobStatus.FAILED in status_calls

    def test_queue_ack_called(self, worker, mock_db, mock_queue, monkeypatch):
        self._run(worker, mock_db, mock_queue, monkeypatch)
        mock_queue.ack.assert_called_once_with(RUN_ID)


# ===========================================================================
# TestProcessJobSudokuMode
# ===========================================================================

SUDOKU_GRID = [
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

SUDOKU_PAYLOAD_JSON = {
    "formula": json.dumps(SUDOKU_GRID),
    "mode": SolverMode.CNF_SUDOKU,
    "formula_id": 2,
}

SUDOKU_PAYLOAD_LIST = {
    "formula": SUDOKU_GRID,
    "mode": SolverMode.CNF_SUDOKU,
    "formula_id": 2,
}


class TestProcessJobSudokuMode:
    """_process_job in CNF_SUDOKU mode."""

    def _patch_sudoku_helper(self, monkeypatch, returncode: int):
        mock_proc = make_mock_process(
            returncode=returncode,
            stdout="v 1 2 3 0\n",
        )
        calls = []

        def fake_sudoku_helper(puzzle):
            calls.append(puzzle)
            return mock_proc, 1.2

        monkeypatch.setattr("backend.app.worker.sudoku_helper", fake_sudoku_helper)
        monkeypatch.setattr(
            "backend.app.worker.decode_solution",
            lambda lines: {"grid": [[1] * 9] * 9},
        )
        return calls

    # --- JSON string formula is parsed to list before passing to sudoku_helper ---

    def test_json_string_formula_parsed_to_list(self, worker, mock_db, mock_queue, monkeypatch):
        calls = self._patch_sudoku_helper(monkeypatch, returncode=SolverExitCodes.SAT)
        worker._process_job(RUN_ID, SUDOKU_PAYLOAD_JSON)
        assert len(calls) == 1
        assert calls[0] == SUDOKU_GRID  # list, not the raw JSON string

    def test_list_formula_passed_directly_to_sudoku_helper(self, worker, mock_db, mock_queue, monkeypatch):
        calls = self._patch_sudoku_helper(monkeypatch, returncode=SolverExitCodes.SAT)
        worker._process_job(RUN_ID, SUDOKU_PAYLOAD_LIST)
        assert calls[0] == SUDOKU_GRID

    def test_run_solver_not_called_in_sudoku_mode(self, worker, mock_db, mock_queue, monkeypatch):
        self._patch_sudoku_helper(monkeypatch, returncode=SolverExitCodes.SAT)
        with patch("backend.app.worker.run_solver") as mock_run_solver:
            worker._process_job(RUN_ID, SUDOKU_PAYLOAD_JSON)
            mock_run_solver.assert_not_called()

    def test_rc_10_gives_result_sat(self, worker, mock_db, mock_queue, monkeypatch):
        self._patch_sudoku_helper(monkeypatch, returncode=SolverExitCodes.SAT)
        worker._process_job(RUN_ID, SUDOKU_PAYLOAD_JSON)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "SAT"

    def test_rc_20_gives_result_unsat(self, worker, mock_db, mock_queue, monkeypatch):
        self._patch_sudoku_helper(monkeypatch, returncode=SolverExitCodes.UNSAT)
        worker._process_job(RUN_ID, SUDOKU_PAYLOAD_JSON)
        kwargs = mock_db.insert_result.call_args[1]
        assert kwargs["result"] == "UNSAT"

    def test_update_run_status_completed_on_sat(self, worker, mock_db, mock_queue, monkeypatch):
        self._patch_sudoku_helper(monkeypatch, returncode=SolverExitCodes.SAT)
        worker._process_job(RUN_ID, SUDOKU_PAYLOAD_JSON)
        status_calls = [c[0][1] for c in mock_db.update_run_status.call_args_list]
        assert JobStatus.COMPLETED in status_calls

    def test_queue_ack_called_on_sat(self, worker, mock_db, mock_queue, monkeypatch):
        self._patch_sudoku_helper(monkeypatch, returncode=SolverExitCodes.SAT)
        worker._process_job(RUN_ID, SUDOKU_PAYLOAD_JSON)
        mock_queue.ack.assert_called_once_with(RUN_ID)

    def test_invalid_json_string_falls_back_to_raw_value(self, worker, mock_db, mock_queue, monkeypatch):
        """Non-JSON string formula should be passed as-is to sudoku_helper."""
        calls = self._patch_sudoku_helper(monkeypatch, returncode=SolverExitCodes.SAT)
        bad_json_payload = {
            "formula": "not-valid-json",
            "mode": SolverMode.CNF_SUDOKU,
            "formula_id": 3,
        }
        worker._process_job(RUN_ID, bad_json_payload)
        assert calls[0] == "not-valid-json"


# ===========================================================================
# TestRunForeverLoop
# ===========================================================================

class TestRunForeverLoop:
    """run_forever loop behaviour."""

    def test_loop_exits_when_running_is_false_after_none_claim(self, worker, mock_queue, monkeypatch):
        """claim returns None twice; second None call sets running=False so loop exits."""
        call_count = [0]

        def claim_side_effect(timeout_s=5):
            call_count[0] += 1
            if call_count[0] >= 2:
                worker.running = False
            return None

        mock_queue.claim.side_effect = claim_side_effect
        monkeypatch.setattr("signal.signal", lambda *a: None)

        worker.run_forever()

        assert not worker.running
        assert mock_queue.claim.call_count >= 2

    def test_process_job_called_when_claim_returns_job(self, worker, mock_queue, monkeypatch):
        """When claim returns a job tuple, _process_job is called with correct args."""
        job_payload = {"formula": "a && b", "mode": "RPN", "formula_id": 1}
        process_job_calls = []

        def claim_side_effect(timeout_s=5):
            if not process_job_calls:
                return (RUN_ID, job_payload)
            worker.running = False
            return None

        mock_queue.claim.side_effect = claim_side_effect
        monkeypatch.setattr("signal.signal", lambda *a: None)

        original_process_job = worker._process_job

        def mock_process_job(run_id, payload):
            process_job_calls.append((run_id, payload))

        worker._process_job = mock_process_job

        worker.run_forever()

        assert len(process_job_calls) == 1
        assert process_job_calls[0] == (RUN_ID, job_payload)

    def test_loop_continues_when_claim_raises_exception(self, worker, mock_queue, monkeypatch):
        """Claim raising an exception should not call _process_job; loop continues."""
        call_count = [0]

        def claim_side_effect(timeout_s=5):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Redis unavailable")
            worker.running = False
            return None

        mock_queue.claim.side_effect = claim_side_effect
        monkeypatch.setattr("signal.signal", lambda *a: None)
        monkeypatch.setattr("time.sleep", lambda s: None)

        process_job_calls = []
        worker._process_job = lambda run_id, payload: process_job_calls.append((run_id, payload))

        worker.run_forever()

        assert len(process_job_calls) == 0
        assert mock_queue.claim.call_count >= 2

    def test_current_run_id_reset_after_job(self, worker, mock_queue, monkeypatch):
        """_current_run_id should be None after a job completes."""
        job_payload = {"formula": "a && b", "mode": "RPN", "formula_id": 1}
        called = [False]

        def claim_side_effect(timeout_s=5):
            if not called[0]:
                called[0] = True
                return (RUN_ID, job_payload)
            worker.running = False
            return None

        mock_queue.claim.side_effect = claim_side_effect
        monkeypatch.setattr("signal.signal", lambda *a: None)
        worker._process_job = lambda run_id, payload: None  # no-op

        worker.run_forever()

        assert worker._current_run_id is None

    def test_loop_sleeps_two_seconds_on_claim_exception(self, worker, mock_queue, monkeypatch):
        """When claim raises, run_forever should sleep for 2 seconds."""
        sleep_calls = []
        call_count = [0]

        def claim_side_effect(timeout_s=5):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("Redis down")
            worker.running = False
            return None

        mock_queue.claim.side_effect = claim_side_effect
        monkeypatch.setattr("signal.signal", lambda *a: None)
        monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))

        worker.run_forever()

        assert 2 in sleep_calls


# ===========================================================================
# TestSudokuHelper  (standalone function)
# ===========================================================================

class TestSudokuHelper:
    """sudoku_helper standalone function."""

    def test_propagate_called_with_puzzle(self, monkeypatch):
        propagate_calls = []
        mock_proc = make_mock_process(returncode=SolverExitCodes.SAT)

        def fake_propagate(puzzle):
            propagate_calls.append(puzzle)
            return puzzle  # pass-through

        monkeypatch.setattr("backend.app.worker.propagate", fake_propagate)
        monkeypatch.setattr("backend.app.worker.encode_sudoku", lambda p: "cnf_string")
        monkeypatch.setattr(
            "backend.app.worker.run_solver_sudoku",
            lambda formula, timeout_s: (mock_proc, 1.0),
        )

        sudoku_helper(SUDOKU_GRID)

        assert len(propagate_calls) == 1
        assert propagate_calls[0] == SUDOKU_GRID

    def test_encode_sudoku_called_with_propagated_result(self, monkeypatch):
        propagated = [[9] * 9] * 9
        encode_calls = []
        mock_proc = make_mock_process(returncode=SolverExitCodes.SAT)

        monkeypatch.setattr("backend.app.worker.propagate", lambda p: propagated)

        def fake_encode(puzzle):
            encode_calls.append(puzzle)
            return "cnf_formula"

        monkeypatch.setattr("backend.app.worker.encode_sudoku", fake_encode)
        monkeypatch.setattr(
            "backend.app.worker.run_solver_sudoku",
            lambda formula, timeout_s: (mock_proc, 0.5),
        )

        sudoku_helper(SUDOKU_GRID)

        assert len(encode_calls) == 1
        assert encode_calls[0] is propagated

    def test_run_solver_sudoku_called_with_formula_and_timeout(self, monkeypatch):
        solver_calls = []
        mock_proc = make_mock_process(returncode=SolverExitCodes.SAT)

        monkeypatch.setattr("backend.app.worker.propagate", lambda p: p)
        monkeypatch.setattr("backend.app.worker.encode_sudoku", lambda p: "the_cnf")

        def fake_run_solver_sudoku(formula, timeout_s):
            solver_calls.append({"formula": formula, "timeout_s": timeout_s})
            return mock_proc, 2.5

        monkeypatch.setattr("backend.app.worker.run_solver_sudoku", fake_run_solver_sudoku)

        sudoku_helper(SUDOKU_GRID)

        assert len(solver_calls) == 1
        assert solver_calls[0]["formula"] == "the_cnf"
        assert solver_calls[0]["timeout_s"] == TIMEOUT_S_SUDOKU

    def test_returns_process_and_runtime_tuple(self, monkeypatch):
        mock_proc = make_mock_process(returncode=SolverExitCodes.SAT)

        monkeypatch.setattr("backend.app.worker.propagate", lambda p: p)
        monkeypatch.setattr("backend.app.worker.encode_sudoku", lambda p: "cnf")
        monkeypatch.setattr(
            "backend.app.worker.run_solver_sudoku",
            lambda formula, timeout_s: (mock_proc, 3.14),
        )

        result = sudoku_helper(SUDOKU_GRID)

        assert isinstance(result, tuple)
        assert len(result) == 2
        proc, runtime = result
        assert proc is mock_proc
        assert runtime == pytest.approx(3.14)

    def test_timeout_s_equals_constant(self, monkeypatch):
        """run_solver_sudoku must receive TIMEOUT_S_SUDOKU (250), not TIMEOUT_S_SAT."""
        received_timeout = []
        mock_proc = make_mock_process(returncode=SolverExitCodes.SAT)

        monkeypatch.setattr("backend.app.worker.propagate", lambda p: p)
        monkeypatch.setattr("backend.app.worker.encode_sudoku", lambda p: "cnf")
        monkeypatch.setattr(
            "backend.app.worker.run_solver_sudoku",
            lambda formula, timeout_s: (received_timeout.append(timeout_s) or (mock_proc, 0.1)),
        )

        sudoku_helper(SUDOKU_GRID)

        assert received_timeout[0] == TIMEOUT_S_SUDOKU
        assert received_timeout[0] != TIMEOUT_S_SAT

    def test_propagate_exception_propagates_to_caller(self, monkeypatch):
        monkeypatch.setattr(
            "backend.app.worker.propagate",
            lambda p: (_ for _ in ()).throw(ValueError("bad grid")),
        )
        monkeypatch.setattr("backend.app.worker.encode_sudoku", lambda p: "cnf")
        monkeypatch.setattr(
            "backend.app.worker.run_solver_sudoku",
            lambda formula, timeout_s: (make_mock_process(10), 0.0),
        )

        with pytest.raises(ValueError, match="bad grid"):
            sudoku_helper(SUDOKU_GRID)
