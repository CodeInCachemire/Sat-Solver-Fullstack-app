"""
Comprehensive unit tests for DatabaseService.
All tests use MagicMock — no real PostgreSQL connection is created.
"""

import json
import pytest
from unittest.mock import MagicMock, call
from backend.app.services.database_service import DatabaseService
from backend.app.core.constants import JobStatus
from backend.app.db import queries

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_conn(fetchone_return=None):
    """Build a fake psycopg2 connection/cursor chain."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_return
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    return mock_conn, mock_cursor


def make_db_service(mock_conn):
    """Construct a DatabaseService backed by a fake connection."""
    get_conn = MagicMock(return_value=mock_conn)
    release_conn = MagicMock()
    svc = DatabaseService(get_conn, release_conn)
    return svc, get_conn, release_conn


# ---------------------------------------------------------------------------
# TestGetOrCreateFormula
# ---------------------------------------------------------------------------

class TestGetOrCreateFormula:
    """Tests for DatabaseService.get_or_create_formula."""

    def test_returns_formula_id_from_fetchone(self):
        """Should return the integer formula_id from fetchone()[0]."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(42,))
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_or_create_formula("a && b", "abc123", "infix")

        assert result == 42

    def test_execute_called_with_correct_query(self):
        """execute should receive UPSERT_INTO_FORMULAS with the right params."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(1,))
        svc, _, _ = make_db_service(mock_conn)

        svc.get_or_create_formula("a && b", "hash_val", "infix")

        mock_cursor.execute.assert_called_once_with(
            queries.UPSERT_INTO_FORMULAS,
            ("a && b", "hash_val", "infix")
        )

    def test_execute_called_with_correct_params_order(self):
        """Parameter order must be (normalized_input, hash_value, notation)."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(5,))
        svc, _, _ = make_db_service(mock_conn)

        svc.get_or_create_formula("p || q", "deadbeef", "cnf")

        args = mock_cursor.execute.call_args[0][1]
        assert args == ("p || q", "deadbeef", "cnf")

    def test_release_conn_always_called(self):
        """release_conn must be called even when execute succeeds."""
        mock_conn, _ = make_mock_conn(fetchone_return=(7,))
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_or_create_formula("x", "h", "n")

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_exception(self):
        """release_conn must be called even when execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("DB error")
        svc, get_conn, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.get_or_create_formula("x", "h", "n")

        release_conn.assert_called_once_with(mock_conn)

    def test_get_conn_called_once(self):
        """get_conn should be called exactly once per invocation."""
        mock_conn, _ = make_mock_conn(fetchone_return=(3,))
        svc, get_conn, _ = make_db_service(mock_conn)

        svc.get_or_create_formula("a", "b", "c")

        get_conn.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateRun
# ---------------------------------------------------------------------------

class TestCreateRun:
    """Tests for DatabaseService.create_run."""

    def test_returns_run_id_from_fetchone(self):
        """Should return the integer run_id from fetchone()[0]."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(99,))
        svc, _, _ = make_db_service(mock_conn)

        result = svc.create_run(formula_id=1, mode="dpll")

        assert result == 99

    def test_execute_called_with_correct_query(self):
        """execute should receive INSERT_INTO_RUNS."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(10,))
        svc, _, _ = make_db_service(mock_conn)

        svc.create_run(formula_id=1, mode="dpll", timeout_s=10)

        mock_cursor.execute.assert_called_once_with(
            queries.INSERT_INTO_RUNS,
            (1, JobStatus.CREATED, 10, "dpll")
        )

    def test_job_status_created_is_passed(self):
        """The status parameter must be JobStatus.CREATED."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(2,))
        svc, _, _ = make_db_service(mock_conn)

        svc.create_run(formula_id=5, mode="cdcl")

        args = mock_cursor.execute.call_args[0][1]
        assert args[1] == JobStatus.CREATED

    def test_default_timeout_is_5(self):
        """Default timeout_s should be 5 when not supplied."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(2,))
        svc, _, _ = make_db_service(mock_conn)

        svc.create_run(formula_id=3, mode="dpll")

        args = mock_cursor.execute.call_args[0][1]
        assert args[2] == 5

    def test_custom_timeout_is_passed(self):
        """Custom timeout_s must be forwarded to execute."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(4,))
        svc, _, _ = make_db_service(mock_conn)

        svc.create_run(formula_id=3, mode="dpll", timeout_s=30)

        args = mock_cursor.execute.call_args[0][1]
        assert args[2] == 30

    def test_release_conn_always_called(self):
        """release_conn must be called after successful create_run."""
        mock_conn, _ = make_mock_conn(fetchone_return=(8,))
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.create_run(formula_id=1, mode="dpll")

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_exception(self):
        """release_conn must be called even when execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = RuntimeError("fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(RuntimeError):
            svc.create_run(formula_id=1, mode="dpll")

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestUpdateRunStatus
# ---------------------------------------------------------------------------

class TestUpdateRunStatus:
    """Tests for DatabaseService.update_run_status."""

    def test_execute_called_with_correct_query(self):
        """execute should receive UPDATE_RUN_STATUS."""
        mock_conn, mock_cursor = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        svc.update_run_status(run_id=7, status="PROCESSING")

        mock_cursor.execute.assert_called_once_with(
            queries.UPDATE_RUN_STATUS,
            ("PROCESSING", "PROCESSING", "PROCESSING", 7)
        )

    def test_status_passed_three_times(self):
        """Status must appear exactly 3 times in the params tuple (conditional SQL)."""
        mock_conn, mock_cursor = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        svc.update_run_status(run_id=3, status="COMPLETED")

        args = mock_cursor.execute.call_args[0][1]
        assert args == ("COMPLETED", "COMPLETED", "COMPLETED", 3)

    def test_run_id_is_last_param(self):
        """run_id must be the 4th (last) parameter."""
        mock_conn, mock_cursor = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        svc.update_run_status(run_id=55, status="FAILED")

        args = mock_cursor.execute.call_args[0][1]
        assert args[3] == 55

    def test_returns_none(self):
        """update_run_status should return None."""
        mock_conn, _ = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        result = svc.update_run_status(run_id=1, status="QUEUED")

        assert result is None

    def test_release_conn_always_called(self):
        """release_conn must be called after update."""
        mock_conn, _ = make_mock_conn()
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.update_run_status(run_id=1, status="PROCESSING")

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_exception(self):
        """release_conn must be called even when execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("DB failure")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.update_run_status(run_id=1, status="PROCESSING")

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestGetFormulaById
# ---------------------------------------------------------------------------

class TestGetFormulaById:
    """Tests for DatabaseService.get_formula_by_id."""

    def test_returns_normalized_input_string(self):
        """Should return the string from fetchone()[0]."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=("a && b",))
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_formula_by_id(formula_id=1)

        assert result == "a && b"

    def test_returns_none_when_fetchone_is_none(self):
        """Should return None when no row is found."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=None)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_formula_by_id(formula_id=999)

        assert result is None

    def test_execute_called_with_correct_query_and_params(self):
        """execute should use GET_FORMULA_BY_ID with (formula_id,)."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=("x",))
        svc, _, _ = make_db_service(mock_conn)

        svc.get_formula_by_id(formula_id=4)

        mock_cursor.execute.assert_called_once_with(queries.GET_FORMULA_BY_ID, (4,))

    def test_release_conn_always_called(self):
        """release_conn must be called after get_formula_by_id."""
        mock_conn, _ = make_mock_conn(fetchone_return=("z",))
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_formula_by_id(formula_id=2)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_when_not_found(self):
        """release_conn must be called even when result is None."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_formula_by_id(formula_id=2)

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestGetRunById
# ---------------------------------------------------------------------------

class TestGetRunById:
    """Tests for DatabaseService.get_run_by_id."""

    def _make_run_row(self):
        """Return a realistic 8-element tuple mimicking a runs row."""
        from datetime import datetime
        now = datetime(2024, 1, 1, 12, 0, 0)
        return (101, 5, "COMPLETED", now, now, now, 10, "dpll")

    def test_returns_dict_with_all_eight_keys(self):
        """Should return dict with id, formula_id, status, created_at, started_at, finished_at, timeout_s, mode."""
        row = self._make_run_row()
        mock_conn, _ = make_mock_conn(fetchone_return=row)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_run_by_id(run_id=101)

        assert set(result.keys()) == {"id", "formula_id", "status", "created_at",
                                       "started_at", "finished_at", "timeout_s", "mode"}

    def test_dict_values_mapped_correctly(self):
        """Each dict value must correspond to the correct tuple index."""
        row = self._make_run_row()
        mock_conn, _ = make_mock_conn(fetchone_return=row)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_run_by_id(run_id=101)

        assert result["id"] == row[0]
        assert result["formula_id"] == row[1]
        assert result["status"] == row[2]
        assert result["created_at"] == row[3]
        assert result["started_at"] == row[4]
        assert result["finished_at"] == row[5]
        assert result["timeout_s"] == row[6]
        assert result["mode"] == row[7]

    def test_returns_none_when_fetchone_is_none(self):
        """Should return None when no run is found."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_run_by_id(run_id=9999)

        assert result is None

    def test_execute_called_with_correct_query_and_params(self):
        """execute should use GET_RUN_BY_ID with (run_id,)."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=self._make_run_row())
        svc, _, _ = make_db_service(mock_conn)

        svc.get_run_by_id(run_id=77)

        mock_cursor.execute.assert_called_once_with(queries.GET_RUN_BY_ID, (77,))

    def test_release_conn_always_called(self):
        """release_conn must be called after get_run_by_id."""
        mock_conn, _ = make_mock_conn(fetchone_return=self._make_run_row())
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_run_by_id(run_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_when_not_found(self):
        """release_conn must be called even when result is None."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_run_by_id(run_id=1)

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestGetStatusByRunId
# ---------------------------------------------------------------------------

class TestGetStatusByRunId:
    """Tests for DatabaseService.get_status_by_run_id."""

    def test_returns_dict_with_id_and_status(self):
        """Should return dict containing exactly 'id' and 'status' keys."""
        mock_conn, _ = make_mock_conn(fetchone_return=(12, "PROCESSING"))
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_status_by_run_id(run_id=12)

        assert set(result.keys()) == {"id", "status"}

    def test_dict_values_mapped_correctly(self):
        """id and status must map to the correct tuple indices."""
        mock_conn, _ = make_mock_conn(fetchone_return=(12, "PROCESSING"))
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_status_by_run_id(run_id=12)

        assert result["id"] == 12
        assert result["status"] == "PROCESSING"

    def test_returns_none_when_fetchone_is_none(self):
        """Should return None when no run is found."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_status_by_run_id(run_id=999)

        assert result is None

    def test_execute_called_with_correct_query_and_params(self):
        """execute should use GET_RUN_STATUS_BY_ID with (run_id,)."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(1, "CREATED"))
        svc, _, _ = make_db_service(mock_conn)

        svc.get_status_by_run_id(run_id=8)

        mock_cursor.execute.assert_called_once_with(queries.GET_RUN_STATUS_BY_ID, (8,))

    def test_release_conn_always_called(self):
        """release_conn must be called after get_status_by_run_id."""
        mock_conn, _ = make_mock_conn(fetchone_return=(3, "QUEUED"))
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_status_by_run_id(run_id=3)

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestInsertResult
# ---------------------------------------------------------------------------

class TestInsertResult:
    """Tests for DatabaseService.insert_result."""

    def test_execute_called_once(self):
        """execute must be called exactly once."""
        mock_conn, mock_cursor = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        svc.insert_result(1, "SAT", {"x1": True}, "out", "err", None, None, 1.23)

        assert mock_cursor.execute.call_count == 1

    def test_execute_called_with_correct_query(self):
        """execute must use INSERT_RESULT."""
        mock_conn, mock_cursor = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        svc.insert_result(1, "SAT", None, "out", "err", None, None, 0.5)

        assert mock_cursor.execute.call_args[0][0] == queries.INSERT_RESULT

    def test_assignment_none_passes_none_not_json(self):
        """When assignment=None the stored value must be None, not json.dumps(None)."""
        mock_conn, mock_cursor = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        svc.insert_result(1, "UNSAT", None, "", "", None, None, 0.1)

        params = mock_cursor.execute.call_args[0][1]
        assert params[2] is None

    def test_assignment_dict_passes_json_string(self):
        """When assignment is a dict it must be serialised with json.dumps."""
        assignment = {"x1": True, "x2": False}
        mock_conn, mock_cursor = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        svc.insert_result(2, "SAT", assignment, "stdout", "stderr", None, None, 2.5)

        params = mock_cursor.execute.call_args[0][1]
        assert params[2] == json.dumps(assignment)

    def test_all_params_passed_in_order(self):
        """Params tuple order: (run_id, result, assignment, stdout, stderr, error_type, error_message, runtime_s)."""
        mock_conn, mock_cursor = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        svc.insert_result(7, "SAT", None, "out", "err", "TypeError", "bad type", 3.14)

        params = mock_cursor.execute.call_args[0][1]
        assert params[0] == 7
        assert params[1] == "SAT"
        assert params[2] is None
        assert params[3] == "out"
        assert params[4] == "err"
        assert params[5] == "TypeError"
        assert params[6] == "bad type"
        assert params[7] == 3.14

    def test_returns_none(self):
        """insert_result should return None."""
        mock_conn, _ = make_mock_conn()
        svc, _, _ = make_db_service(mock_conn)

        result = svc.insert_result(1, "SAT", None, "", "", None, None, 0.0)

        assert result is None

    def test_release_conn_always_called(self):
        """release_conn must be called after insert_result."""
        mock_conn, _ = make_mock_conn()
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.insert_result(1, "SAT", None, "", "", None, None, 0.0)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_exception(self):
        """release_conn must be called even when execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("insert fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.insert_result(1, "SAT", None, "", "", None, None, 0.0)

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestGetResultByRunId
# ---------------------------------------------------------------------------

class TestGetResultByRunId:
    """Tests for DatabaseService.get_result_by_run_id."""

    def _make_result_row(self):
        """Return a 7-element tuple mimicking a results row."""
        return ("SAT", '{"x1": true}', "stdout text", "stderr text", None, None, 1.5)

    def test_returns_dict_with_seven_keys(self):
        """Should return dict with result, assignment, stdout, stderr, error_type, error_message, runtime_s."""
        row = self._make_result_row()
        mock_conn, _ = make_mock_conn(fetchone_return=row)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_result_by_run_id(run_id=1)

        assert set(result.keys()) == {
            "result", "assignment", "stdout", "stderr",
            "error_type", "error_message", "runtime_s"
        }

    def test_dict_values_mapped_correctly(self):
        """Each key must map to the correct tuple index."""
        row = self._make_result_row()
        mock_conn, _ = make_mock_conn(fetchone_return=row)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_result_by_run_id(run_id=1)

        assert result["result"] == row[0]
        assert result["assignment"] == row[1]
        assert result["stdout"] == row[2]
        assert result["stderr"] == row[3]
        assert result["error_type"] == row[4]
        assert result["error_message"] == row[5]
        assert result["runtime_s"] == row[6]

    def test_returns_none_when_fetchone_is_none(self):
        """Should return None when no result row is found."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_result_by_run_id(run_id=999)

        assert result is None

    def test_execute_called_with_correct_query_and_params(self):
        """execute should use GET_RESULT_BY_RUN_ID with (run_id,)."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=self._make_result_row())
        svc, _, _ = make_db_service(mock_conn)

        svc.get_result_by_run_id(run_id=22)

        mock_cursor.execute.assert_called_once_with(queries.GET_RESULT_BY_RUN_ID, (22,))

    def test_release_conn_always_called(self):
        """release_conn must be called after get_result_by_run_id."""
        mock_conn, _ = make_mock_conn(fetchone_return=self._make_result_row())
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_result_by_run_id(run_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_when_not_found(self):
        """release_conn must be called even when result is None."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_result_by_run_id(run_id=1)

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestGetActiveRun
# ---------------------------------------------------------------------------

class TestGetActiveRun:
    """Tests for DatabaseService.get_active_run."""

    def test_returns_tuple_from_fetchone(self):
        """Should return the raw tuple from fetchone."""
        expected = (10, "PROCESSING")
        mock_conn, _ = make_mock_conn(fetchone_return=expected)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_active_run(formula_id=3)

        assert result == expected

    def test_returns_none_when_no_active_run(self):
        """Should return None when fetchone returns None."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_active_run(formula_id=3)

        assert result is None

    def test_execute_called_with_correct_query_and_params(self):
        """execute should use GET_PENDING_RUN_BY_FORMULA with (formula_id,)."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(5, "QUEUED"))
        svc, _, _ = make_db_service(mock_conn)

        svc.get_active_run(formula_id=11)

        mock_cursor.execute.assert_called_once_with(
            queries.GET_PENDING_RUN_BY_FORMULA, (11,)
        )

    def test_release_conn_always_called(self):
        """release_conn must be called after get_active_run."""
        mock_conn, _ = make_mock_conn(fetchone_return=(5, "QUEUED"))
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_active_run(formula_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_when_not_found(self):
        """release_conn must be called even when result is None."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_active_run(formula_id=1)

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestGetCompletedRun
# ---------------------------------------------------------------------------

class TestGetCompletedRun:
    """Tests for DatabaseService.get_completed_run."""

    def test_returns_tuple_from_fetchone(self):
        """Should return the raw tuple from fetchone."""
        expected = (20, "COMPLETED")
        mock_conn, _ = make_mock_conn(fetchone_return=expected)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_completed_run(formula_id=7)

        assert result == expected

    def test_returns_none_when_no_completed_run(self):
        """Should return None when no completed run exists."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, _, _ = make_db_service(mock_conn)

        result = svc.get_completed_run(formula_id=7)

        assert result is None

    def test_execute_called_with_correct_query_and_params(self):
        """execute should use GET_COMPLETED_RUN_BY_FORMULA with (formula_id,)."""
        mock_conn, mock_cursor = make_mock_conn(fetchone_return=(20, "COMPLETED"))
        svc, _, _ = make_db_service(mock_conn)

        svc.get_completed_run(formula_id=6)

        mock_cursor.execute.assert_called_once_with(
            queries.GET_COMPLETED_RUN_BY_FORMULA, (6,)
        )

    def test_release_conn_always_called(self):
        """release_conn must be called after get_completed_run."""
        mock_conn, _ = make_mock_conn(fetchone_return=(20, "COMPLETED"))
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_completed_run(formula_id=2)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_when_not_found(self):
        """release_conn must be called even when result is None."""
        mock_conn, _ = make_mock_conn(fetchone_return=None)
        svc, get_conn, release_conn = make_db_service(mock_conn)

        svc.get_completed_run(formula_id=2)

        release_conn.assert_called_once_with(mock_conn)


# ---------------------------------------------------------------------------
# TestConnectionPooling
# ---------------------------------------------------------------------------

class TestConnectionPooling:
    """Tests verifying the finally-clause connection release contract."""

    def test_release_conn_called_on_execute_exception_get_or_create_formula(self):
        """get_or_create_formula: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = RuntimeError("DB unavailable")
        svc, get_conn, release_conn = make_db_service(mock_conn)

        with pytest.raises(RuntimeError):
            svc.get_or_create_formula("x", "h", "n")

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_create_run(self):
        """create_run: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = RuntimeError("timeout")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(RuntimeError):
            svc.create_run(formula_id=1, mode="dpll")

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_update_run_status(self):
        """update_run_status: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("write fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.update_run_status(run_id=1, status="FAILED")

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_get_formula_by_id(self):
        """get_formula_by_id: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("read fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.get_formula_by_id(formula_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_get_run_by_id(self):
        """get_run_by_id: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("read fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.get_run_by_id(run_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_get_status_by_run_id(self):
        """get_status_by_run_id: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("read fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.get_status_by_run_id(run_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_insert_result(self):
        """insert_result: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("write fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.insert_result(1, "SAT", None, "", "", None, None, 0.0)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_get_result_by_run_id(self):
        """get_result_by_run_id: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("read fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.get_result_by_run_id(run_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_get_active_run(self):
        """get_active_run: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("read fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.get_active_run(formula_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_release_conn_called_on_execute_exception_get_completed_run(self):
        """get_completed_run: release_conn called even if execute raises."""
        mock_conn, mock_cursor = make_mock_conn()
        mock_cursor.execute.side_effect = Exception("read fail")
        svc, _, release_conn = make_db_service(mock_conn)

        with pytest.raises(Exception):
            svc.get_completed_run(formula_id=1)

        release_conn.assert_called_once_with(mock_conn)

    def test_get_conn_called_before_release_conn(self):
        """get_conn must be called before release_conn (connection acquired first)."""
        call_order = []
        mock_conn, _ = make_mock_conn(fetchone_return=(1,))

        def get_conn_side_effect():
            call_order.append("get")
            return mock_conn

        def release_conn_side_effect(conn):
            call_order.append("release")

        svc = DatabaseService(get_conn_side_effect, release_conn_side_effect)
        svc.get_formula_by_id(formula_id=1)

        assert call_order == ["get", "release"]
