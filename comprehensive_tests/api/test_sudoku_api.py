"""
Comprehensive API tests for the /sudoku router.

External solver calls and helper functions are mocked via monkeypatch so no
real SAT binary, image-extraction library, or NYT network request is required.

Run with:
    pytest backend/tests/test_sudoku_api.py -v -m api
"""

import subprocess
import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.api

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

VALID_GRID = [
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

# A completed 9x9 grid used as a fake decoded solution.
SOLVED_GRID = [
    [5, 3, 4, 6, 7, 8, 9, 1, 2],
    [6, 7, 2, 1, 9, 5, 3, 4, 8],
    [1, 9, 8, 3, 4, 2, 5, 6, 7],
    [8, 5, 9, 7, 6, 1, 4, 2, 3],
    [4, 2, 6, 8, 5, 3, 7, 9, 1],
    [7, 1, 3, 9, 2, 4, 8, 5, 6],
    [9, 6, 1, 5, 3, 7, 2, 8, 4],
    [2, 8, 7, 4, 1, 9, 6, 3, 5],
    [3, 4, 5, 2, 8, 6, 1, 7, 9],
]

FAKE_CNF = "p cnf 1 1\n1 0\n"
FAKE_SAT_OUTPUT = "SAT\nv 1 0\n"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_mock_process(returncode: int = 10, stdout: str = "", stderr: str = "") -> MagicMock:
    """Return a MagicMock that mimics a finished subprocess.CompletedProcess."""
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def _patch_solve_helpers(monkeypatch, *, returncode: int = 10, runtime: float = 0.05):
    """
    Patch all four helpers used by POST /sudoku/solve.

    propagate  → identity (returns the grid unchanged)
    encode_sudoku → returns a fake CNF string
    run_solver_sudoku → returns (mock_process, runtime)
    decode_solution → returns SOLVED_GRID

    Individual tests may override specific patches by calling
    monkeypatch.setattr again *after* calling this helper.
    """
    monkeypatch.setattr("backend.app.api.sudoku.propagate", lambda g: g)
    monkeypatch.setattr("backend.app.api.sudoku.encode_sudoku", lambda g: FAKE_CNF)
    monkeypatch.setattr(
        "backend.app.api.sudoku.run_solver_sudoku",
        lambda formula, **kw: (make_mock_process(returncode, FAKE_SAT_OUTPUT), runtime),
    )
    monkeypatch.setattr("backend.app.api.sudoku.decode_solution", lambda lines: SOLVED_GRID)


# ---------------------------------------------------------------------------
# POST /sudoku/solve
# ---------------------------------------------------------------------------

class TestSudokuSolveEndpoint:
    """Tests for POST /sudoku/solve."""

    # --- Happy-path: SAT result ---

    def test_valid_grid_sat_returns_200(self, test_client, monkeypatch):
        """Valid 9×9 grid with SAT result returns HTTP 200."""
        _patch_solve_helpers(monkeypatch, returncode=10)

        response = test_client.post("/sudoku/solve", json={"grid": VALID_GRID})

        assert response.status_code == 200

    def test_solved_true_when_sat(self, test_client, monkeypatch):
        """solved field is True when the SAT solver returns rc=10."""
        _patch_solve_helpers(monkeypatch, returncode=10)

        data = test_client.post("/sudoku/solve", json={"grid": VALID_GRID}).json()

        assert data["solved"] is True

    def test_time_seconds_is_float(self, test_client, monkeypatch):
        """time_seconds is present and is a numeric value."""
        _patch_solve_helpers(monkeypatch, returncode=10, runtime=0.123456)

        data = test_client.post("/sudoku/solve", json={"grid": VALID_GRID}).json()

        assert "time_seconds" in data
        assert isinstance(data["time_seconds"], float)

    def test_solution_grid_present_when_sat(self, test_client, monkeypatch):
        """solution is not None when the puzzle is satisfiable."""
        _patch_solve_helpers(monkeypatch, returncode=10)

        data = test_client.post("/sudoku/solve", json={"grid": VALID_GRID}).json()

        assert data["solution"] is not None

    # --- UNSAT result ---

    def test_unsat_returns_solved_false(self, test_client, monkeypatch):
        """solved is False when the SAT solver returns rc=20 (UNSAT)."""
        _patch_solve_helpers(monkeypatch, returncode=20)

        data = test_client.post("/sudoku/solve", json={"grid": VALID_GRID}).json()

        assert data["solved"] is False
        assert data["solution"] is None

    def test_error_message_present_on_unsat(self, test_client, monkeypatch):
        """An 'error' key is included in the UNSAT response body."""
        _patch_solve_helpers(monkeypatch, returncode=20)

        data = test_client.post("/sudoku/solve", json={"grid": VALID_GRID}).json()

        assert "error" in data
        assert data["error"]  # non-empty string

    # --- Input validation ---

    def test_invalid_grid_shape_returns_422(self, test_client, monkeypatch):
        """A grid that is not 9×9 is rejected with HTTP 422 before hitting solver."""
        # No solver patches needed — Pydantic rejects before the handler runs.
        response = test_client.post("/sudoku/solve", json={"grid": [[1, 2, 3]]})

        assert response.status_code == 422

    def test_missing_grid_field_returns_422(self, test_client, monkeypatch):
        """Omitting the 'grid' field entirely returns HTTP 422."""
        response = test_client.post("/sudoku/solve", json={})

        assert response.status_code == 422

    # --- Solver error codes / exceptions ---

    def test_unexpected_returncode_raises_500(self, test_client, monkeypatch):
        """An unexpected solver return code (not 10 or 20) surfaces as HTTP 500."""
        _patch_solve_helpers(monkeypatch, returncode=99)
        # Override run_solver_sudoku specifically for rc=99.
        monkeypatch.setattr(
            "backend.app.api.sudoku.run_solver_sudoku",
            lambda formula, **kw: (make_mock_process(99, ""), 0.01),
        )

        response = test_client.post("/sudoku/solve", json={"grid": VALID_GRID})

        assert response.status_code == 500

    def test_timeout_expired_returns_408(self, test_client, monkeypatch):
        """subprocess.TimeoutExpired raised inside the solver maps to HTTP 408."""
        monkeypatch.setattr("backend.app.api.sudoku.propagate", lambda g: g)
        monkeypatch.setattr("backend.app.api.sudoku.encode_sudoku", lambda g: FAKE_CNF)

        def _timeout(formula, **kw):
            raise subprocess.TimeoutExpired("minisat", 5)

        monkeypatch.setattr("backend.app.api.sudoku.run_solver_sudoku", _timeout)

        response = test_client.post("/sudoku/solve", json={"grid": VALID_GRID})

        assert response.status_code == 408

    def test_file_not_found_returns_500(self, test_client, monkeypatch):
        """FileNotFoundError (missing solver binary) maps to HTTP 500."""
        monkeypatch.setattr("backend.app.api.sudoku.propagate", lambda g: g)
        monkeypatch.setattr("backend.app.api.sudoku.encode_sudoku", lambda g: FAKE_CNF)

        def _missing(formula, **kw):
            raise FileNotFoundError("minisat: command not found")

        monkeypatch.setattr("backend.app.api.sudoku.run_solver_sudoku", _missing)

        response = test_client.post("/sudoku/solve", json={"grid": VALID_GRID})

        assert response.status_code == 500

    # --- Propagate called correctly ---

    def test_propagate_called_with_grid(self, test_client, monkeypatch):
        """propagate() is invoked with the incoming 9×9 grid."""
        propagate_mock = MagicMock(return_value=VALID_GRID)
        monkeypatch.setattr("backend.app.api.sudoku.propagate", propagate_mock)
        monkeypatch.setattr("backend.app.api.sudoku.encode_sudoku", lambda g: FAKE_CNF)
        monkeypatch.setattr(
            "backend.app.api.sudoku.run_solver_sudoku",
            lambda formula, **kw: (make_mock_process(10, FAKE_SAT_OUTPUT), 0.05),
        )
        monkeypatch.setattr("backend.app.api.sudoku.decode_solution", lambda lines: SOLVED_GRID)

        test_client.post("/sudoku/solve", json={"grid": VALID_GRID})

        propagate_mock.assert_called_once_with(VALID_GRID)


# ---------------------------------------------------------------------------
# GET /sudoku/ny-puzzle/{difficulty}
# ---------------------------------------------------------------------------

class TestNYPuzzleEndpoint:
    """Tests for GET /sudoku/ny-puzzle/{difficulty}."""

    def _patch_parser(self, monkeypatch, return_value=None):
        """Patch parse_nyt_sudoku to avoid real HTTP requests."""
        if return_value is None:
            return_value = {"grid": VALID_GRID}
        monkeypatch.setattr(
            "backend.app.api.sudoku.parse_nyt_sudoku",
            lambda url: return_value,
        )

    def test_easy_difficulty_returns_200(self, test_client, monkeypatch):
        """GET /sudoku/ny-puzzle/easy returns HTTP 200."""
        self._patch_parser(monkeypatch)

        response = test_client.get("/sudoku/ny-puzzle/easy")

        assert response.status_code == 200

    def test_medium_difficulty_returns_200(self, test_client, monkeypatch):
        """GET /sudoku/ny-puzzle/medium returns HTTP 200."""
        self._patch_parser(monkeypatch)

        response = test_client.get("/sudoku/ny-puzzle/medium")

        assert response.status_code == 200

    def test_hard_difficulty_returns_200(self, test_client, monkeypatch):
        """GET /sudoku/ny-puzzle/hard returns HTTP 200."""
        self._patch_parser(monkeypatch)

        response = test_client.get("/sudoku/ny-puzzle/hard")

        assert response.status_code == 200

    def test_invalid_difficulty_returns_422(self, test_client, monkeypatch):
        """An enum value not in {easy, medium, hard} is rejected with HTTP 422."""
        # No patch needed — FastAPI rejects before the handler.
        response = test_client.get("/sudoku/ny-puzzle/extreme")

        assert response.status_code == 422

    def test_parse_nyt_sudoku_called_with_correct_url(self, test_client, monkeypatch):
        """parse_nyt_sudoku receives a URL that contains the requested difficulty."""
        captured_urls: list[str] = []

        def _capture(url: str):
            captured_urls.append(url)
            return {"grid": VALID_GRID}

        monkeypatch.setattr("backend.app.api.sudoku.parse_nyt_sudoku", _capture)

        test_client.get("/sudoku/ny-puzzle/hard")

        assert len(captured_urls) == 1
        assert "hard" in captured_urls[0]


# ---------------------------------------------------------------------------
# POST /sudoku/image-upload
# ---------------------------------------------------------------------------

class TestImageUploadEndpoint:
    """Tests for POST /sudoku/image-upload."""

    def _patch_extractor(self, monkeypatch, return_value=None):
        """Replace extract_sudoku_from_image with a no-op async stub."""
        if return_value is None:
            return_value = VALID_GRID

        async def mock_extract(file_bytes: bytes, content_type: str):
            return return_value

        monkeypatch.setattr(
            "backend.app.api.sudoku.extract_sudoku_from_image", mock_extract
        )

    # --- Happy path ---

    def test_valid_jpeg_upload_returns_200(self, test_client, monkeypatch):
        """A valid JPEG upload with a filename returns HTTP 200 and extracted=True."""
        self._patch_extractor(monkeypatch)

        response = test_client.post(
            "/sudoku/image-upload",
            files={"file": ("test.jpg", b"fake-jpeg-bytes", "image/jpeg")},
        )

        assert response.status_code == 200
        assert response.json()["extracted"] is True

    def test_response_contains_grid_and_filename(self, test_client, monkeypatch):
        """Successful upload response includes both 'grid' and 'filename' keys."""
        self._patch_extractor(monkeypatch)

        data = test_client.post(
            "/sudoku/image-upload",
            files={"file": ("puzzle.png", b"fake-png-bytes", "image/png")},
        ).json()

        assert "grid" in data
        assert "filename" in data
        assert data["filename"] == "puzzle.png"

    # --- Validation failures ---

    def test_no_filename_returns_400(self, test_client, monkeypatch):
        """Upload with an empty filename string returns HTTP 400."""
        self._patch_extractor(monkeypatch)

        # Starlette/requests sends an empty string when filename is omitted.
        response = test_client.post(
            "/sudoku/image-upload",
            files={"file": ("", b"fake-jpeg-bytes", "image/jpeg")},
        )

        # 400 if the handler checks filename; 422 if multipart layer rejects it first
        assert response.status_code in (400, 422)

    def test_wrong_mime_type_returns_400(self, test_client, monkeypatch):
        """Uploading a PDF (not an image) returns HTTP 400."""
        self._patch_extractor(monkeypatch)

        response = test_client.post(
            "/sudoku/image-upload",
            files={"file": ("document.pdf", b"%PDF-fake", "application/pdf")},
        )

        assert response.status_code == 400

    def test_empty_file_returns_400(self, test_client, monkeypatch):
        """A zero-byte upload returns HTTP 400."""
        self._patch_extractor(monkeypatch)

        response = test_client.post(
            "/sudoku/image-upload",
            files={"file": ("empty.jpg", b"", "image/jpeg")},
        )

        assert response.status_code == 400
