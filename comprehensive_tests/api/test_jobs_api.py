"""
Comprehensive API test suite for the /jobs router.
Tests POST /jobs/submit, GET /jobs/status/{run_id}, GET /jobs/result/{run_id}.

All external services (DB, Redis) are replaced by mocks via FastAPI dependency
overrides declared in conftest.py. The mock_job_service fixture is shared between
test_client and the test function — both receive the exact same MagicMock instance,
so return values and side_effect set in the test body affect what the endpoint sees.

Run only API tests:
    pytest backend/tests/test_jobs_api.py -m api
"""

import pytest
from fastapi import HTTPException

from backend.app.schemas.job import JobSubmitResponse, StatusSchema, SolverResult

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_submit_response(
    msg="Job submitted successfully",
    formula="a && b",
    formula_id=1,
    run_id=42,
    status="QUEUED",
):
    """Build a valid JobSubmitResponse for use as a mock return value."""
    return JobSubmitResponse(
        msg=msg,
        formula=formula,
        formula_id=formula_id,
        run_id=run_id,
        status=status,
    )


def make_status_schema(msg="Status retrieved.", run_id=7, status="QUEUED"):
    """Build a valid StatusSchema for use as a mock return value."""
    return StatusSchema(msg=msg, run_id=run_id, status=status)


def make_solver_result(
    run_id=1,
    result="SAT",
    assignment=None,
    runtime=0.042,
    formula="a && b",
    formula_id=1,
):
    """Build a valid SolverResult for use as a mock return value."""
    return SolverResult(
        msg="Here is the result for your run_id.",
        status="COMPLETED",
        run_id=run_id,
        formula_id=formula_id,
        formula=formula,
        result=result,
        assignment=assignment,
        runtime=runtime,
    )


# ---------------------------------------------------------------------------
# POST /jobs/submit
# ---------------------------------------------------------------------------

class TestSubmitEndpoint:
    """Tests for POST /jobs/submit."""

    def test_valid_formula_returns_200(self, test_client, mock_job_service):
        """A well-formed request with a valid formula should return HTTP 200."""
        mock_job_service.submit_job.return_value = make_submit_response()

        response = test_client.post(
            "/jobs/submit",
            json={"formula": "a && b", "notation": "RPN", "mode": "RPN"},
        )

        assert response.status_code == 200

    def test_response_has_all_required_fields(self, test_client, mock_job_service):
        """Response body must contain msg, formula, formula_id, run_id, and status."""
        mock_job_service.submit_job.return_value = make_submit_response()

        response = test_client.post(
            "/jobs/submit",
            json={"formula": "a && b", "notation": "RPN", "mode": "RPN"},
        )

        data = response.json()
        assert "msg" in data
        assert "formula" in data
        assert "formula_id" in data
        assert "run_id" in data
        assert "status" in data

    def test_run_id_in_response_matches_service_return(self, test_client, mock_job_service):
        """run_id in JSON response must equal the value returned by submit_job."""
        mock_job_service.submit_job.return_value = make_submit_response(run_id=42)

        response = test_client.post(
            "/jobs/submit",
            json={"formula": "a && b", "notation": "RPN", "mode": "RPN"},
        )

        assert response.json()["run_id"] == 42

    def test_status_is_queued_on_success(self, test_client, mock_job_service):
        """Newly submitted jobs should carry status='QUEUED'."""
        mock_job_service.submit_job.return_value = make_submit_response(status="QUEUED")

        response = test_client.post(
            "/jobs/submit",
            json={"formula": "a && b", "notation": "RPN", "mode": "RPN"},
        )

        assert response.json()["status"] == "QUEUED"

    def test_missing_formula_field_returns_422(self, test_client, mock_job_service):
        """A request body with no formula key at all should be rejected with 422."""
        response = test_client.post("/jobs/submit", json={})

        assert response.status_code == 422

    def test_empty_formula_returns_422(self, test_client, mock_job_service):
        """An empty string formula violates min_length=1 and must return 422."""
        response = test_client.post(
            "/jobs/submit",
            json={"formula": "", "notation": "RPN", "mode": "RPN"},
        )

        assert response.status_code == 422

    def test_submit_job_called_with_correct_args(self, test_client, mock_job_service):
        """The endpoint must forward formula, notation, and mode to submit_job."""
        mock_job_service.submit_job.return_value = make_submit_response()

        test_client.post(
            "/jobs/submit",
            json={"formula": "a && b", "notation": "RPN", "mode": "RPN"},
        )

        mock_job_service.submit_job.assert_called_once_with(
            "a && b", notation="RPN", mode="RPN"
        )

    def test_service_raises_http_400_client_gets_400(self, test_client, mock_job_service):
        """When submit_job raises HTTPException(400), the client must receive 400."""
        mock_job_service.submit_job.side_effect = HTTPException(
            status_code=400, detail="bad formula"
        )

        response = test_client.post(
            "/jobs/submit",
            json={"formula": "a && b", "notation": "RPN", "mode": "RPN"},
        )

        assert response.status_code == 400

    def test_service_raises_http_503_client_gets_503(self, test_client, mock_job_service):
        """When submit_job raises HTTPException(503), the client must receive 503."""
        mock_job_service.submit_job.side_effect = HTTPException(
            status_code=503, detail="queue unavailable"
        )

        response = test_client.post(
            "/jobs/submit",
            json={"formula": "a && b", "notation": "RPN", "mode": "RPN"},
        )

        assert response.status_code == 503

    def test_notation_and_mode_forwarded_to_service(self, test_client, mock_job_service):
        """Non-default mode value must be forwarded to submit_job unchanged."""
        mock_job_service.submit_job.return_value = make_submit_response()

        test_client.post(
            "/jobs/submit",
            json={"formula": "a", "notation": "RPN", "mode": "CNF_SUDOKU"},
        )

        _args, _kwargs = mock_job_service.submit_job.call_args
        assert _kwargs["mode"] == "CNF_SUDOKU"


# ---------------------------------------------------------------------------
# GET /jobs/status/{run_id}
# ---------------------------------------------------------------------------

class TestStatusEndpoint:
    """Tests for GET /jobs/status/{run_id}."""

    def test_existing_run_returns_200(self, test_client, mock_job_service):
        """A valid run_id for an existing run should return HTTP 200."""
        mock_job_service.get_run_status.return_value = make_status_schema(
            msg="Status retrieved.", run_id=7, status="QUEUED"
        )

        response = test_client.get("/jobs/status/7")

        assert response.status_code == 200

    def test_response_has_msg_run_id_status_fields(self, test_client, mock_job_service):
        """Response body must contain exactly msg, run_id, and status."""
        mock_job_service.get_run_status.return_value = make_status_schema(run_id=7)

        response = test_client.get("/jobs/status/7")
        data = response.json()

        assert "msg" in data
        assert "run_id" in data
        assert "status" in data

    def test_status_value_matches_service_return(self, test_client, mock_job_service):
        """status field in response must equal the value returned by get_run_status."""
        mock_job_service.get_run_status.return_value = make_status_schema(
            run_id=7, status="PROCESSING"
        )

        response = test_client.get("/jobs/status/7")

        assert response.json()["status"] == "PROCESSING"

    def test_run_id_in_response_matches_path_param(self, test_client, mock_job_service):
        """run_id in the response body must reflect the value from the service."""
        mock_job_service.get_run_status.return_value = make_status_schema(run_id=7)

        response = test_client.get("/jobs/status/7")

        assert response.json()["run_id"] == 7

    def test_service_raises_404_client_gets_404(self, test_client, mock_job_service):
        """When get_run_status raises HTTPException(404), the client must receive 404."""
        mock_job_service.get_run_status.side_effect = HTTPException(
            status_code=404, detail="not found"
        )

        response = test_client.get("/jobs/status/9999")

        assert response.status_code == 404

    def test_invalid_run_id_type_returns_422(self, test_client, mock_job_service):
        """A non-integer run_id in the path must be rejected with 422."""
        response = test_client.get("/jobs/status/abc")

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /jobs/result/{run_id}
# ---------------------------------------------------------------------------

class TestResultEndpoint:
    """Tests for GET /jobs/result/{run_id}."""

    def test_completed_run_returns_200(self, test_client, mock_job_service):
        """A completed run with a stored result should return HTTP 200."""
        mock_job_service.get_run_result.return_value = make_solver_result()

        response = test_client.get("/jobs/result/1")

        assert response.status_code == 200

    def test_response_has_all_solver_result_fields(self, test_client, mock_job_service):
        """Response must contain every field defined in the SolverResult schema."""
        mock_job_service.get_run_result.return_value = make_solver_result()

        response = test_client.get("/jobs/result/1")
        data = response.json()

        for field in ("msg", "status", "run_id", "formula_id", "formula", "result", "assignment", "runtime"):
            assert field in data, f"Missing field: {field}"

    def test_result_is_sat_with_assignment(self, test_client, mock_job_service):
        """When the formula is satisfiable the result field should be 'SAT' and assignment non-null."""
        mock_job_service.get_run_result.return_value = make_solver_result(
            result="SAT", assignment={"x1": True}
        )

        response = test_client.get("/jobs/result/1")
        data = response.json()

        assert data["result"] == "SAT"
        assert data["assignment"] == {"x1": True}

    def test_result_is_unsat_with_null_assignment(self, test_client, mock_job_service):
        """When the formula is unsatisfiable assignment should be null."""
        mock_job_service.get_run_result.return_value = make_solver_result(
            result="UNSAT", assignment=None
        )

        response = test_client.get("/jobs/result/1")
        data = response.json()

        assert data["result"] == "UNSAT"
        assert data["assignment"] is None

    def test_service_raises_404_client_gets_404(self, test_client, mock_job_service):
        """When get_run_result raises HTTPException(404), the client must receive 404."""
        mock_job_service.get_run_result.side_effect = HTTPException(
            status_code=404, detail="run not found"
        )

        response = test_client.get("/jobs/result/9999")

        assert response.status_code == 404

    def test_service_raises_400_for_incomplete_run(self, test_client, mock_job_service):
        """When the run is still in progress, a 400 from the service must reach the client."""
        mock_job_service.get_run_result.side_effect = HTTPException(
            status_code=400, detail="not complete yet"
        )

        response = test_client.get("/jobs/result/5")

        assert response.status_code == 400

    def test_runtime_in_response_is_float(self, test_client, mock_job_service):
        """The runtime field must be serialised as a JSON number equal to the service value."""
        mock_job_service.get_run_result.return_value = make_solver_result(runtime=0.042)

        response = test_client.get("/jobs/result/1")

        assert response.json()["runtime"] == 0.042
