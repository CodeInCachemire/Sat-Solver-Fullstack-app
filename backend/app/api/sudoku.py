import logging
import subprocess
from fastapi import APIRouter, HTTPException, File, UploadFile
from backend.app.schemas.sudoku_schema import SudokuGrid, NYDiffEnum
from backend.app.services.image_service import extract_sudoku_from_image, ImageExtractionError
from backend.app.solvers.sudoku_solver import run_solver_sudoku
from backend.app.utils.sudoku_helper import decode_solution, encode_sudoku, propagate
from backend.app.core.constants import NYT_SUDOKU_URL_BASE, ALLOWED_MIME_TYPES, MAX_FILE_SIZE
from backend.app.utils.sudoku_ny import parse_nyt_sudoku

sudoku_router = APIRouter(prefix="/sudoku", tags=["sudoku-solver"])
logger = logging.getLogger(__name__)

@sudoku_router.post("/image-upload")
async def image_upload(file: UploadFile = File(...)):
    """
    Upload a sudoku puzzle image (JPG, JPEG, or PNG) and extract the puzzle.
    
    Returns:
        SudokuGrid: Extracted 9x9 sudoku grid with 0 for empty cells and 1-9 for filled cells
        
    Raises:
        HTTPException: If file is invalid or extraction fails
    """
    logger.info(f"Image upload endpoint called with file: {file.filename}")
    
    try:
        # Validate filename and MIME type
        if not file.filename:
            logger.warning("Upload attempt with no filename")
            raise HTTPException(status_code=400, detail="No filename provided")
        
        if file.content_type not in ALLOWED_MIME_TYPES:
            logger.warning(f"Invalid MIME type: {file.content_type}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
            )
        
        # Read file content
        file_bytes = await file.read()
        
        # Validate file size
        if len(file_bytes) == 0:
            logger.warning("Empty file uploaded")
            raise HTTPException(status_code=400, detail="File is empty")
        
        if len(file_bytes) > MAX_FILE_SIZE:
            logger.warning(f"File too large: {len(file_bytes)} bytes > {MAX_FILE_SIZE} bytes")
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024):.1f} MB"
            )
        
        logger.debug(f"File validated: {file.filename} ({len(file_bytes)} bytes, {file.content_type})")
        
        # Extract sudoku grid from image using service
        try:
            grid = await extract_sudoku_from_image(file_bytes, file.content_type)
        except ImageExtractionError as e:
            error_msg = str(e)
            if "not installed" in error_msg or "not configured" in error_msg:
                logger.error(f"Service configuration error: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Image extraction service unavailable - {error_msg}")
            else:
                logger.error(f"Grid extraction/validation error: {error_msg}")
                raise HTTPException(status_code=422, detail=f"Failed to extract puzzle: {error_msg}")
        
        # Return extracted grid
        return {
            "extracted": True,
            "grid": grid,
            "filename": file.filename,
            "message": "Puzzle successfully extracted from image"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in image_upload: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {type(e).__name__}"
        )

@sudoku_router.get("/ny-puzzle/{difficulty}")
def get_ny_puzzle(difficulty: NYDiffEnum):
    """Get the NY Times puzzle given the difficulty from the user."""
    return parse_nyt_sudoku(f"{NYT_SUDOKU_URL_BASE}{difficulty.value}")
    
@sudoku_router.post("/solve")
def sudoku(request: SudokuGrid):

    logger.info("Sudoku solve endpoint called")
    puzzle = request.grid

    try:
        logger.debug("Input Sudoku puzzle received")
        
        logger.info("Starting propagation (constraint propagation)")
        puzzle = propagate(puzzle)
        logger.debug("Propagation complete")
        
        logger.info("Encoding Sudoku to CNF formula")
        formula = encode_sudoku(puzzle)
        logger.debug(f"CNF formula generated, {len(formula.splitlines())} clauses")
        
        logger.info("Invoking SAT solver with timeout 5s")
        process, runtime  = run_solver_sudoku(formula)
        if process.returncode == 20:
            logger.info("Result: UNSAT (no solution)")
            sat = False
        elif process.returncode == 10:
            logger.info(f"Result: SAT (solution found with {len(process.stdout.splitlines())} output lines)")
            sat = True
        else:
            logger.error(f"Unexpected solver return code: {process.returncode}")
            logger.error(f"stdout: {process.stdout[:200]}")
            logger.error(f"stderr: {process.stderr[:200]}")
            raise HTTPException(status_code=500, detail=f"Solver returned unexpected code {process.returncode}")
        logger.info(f"SAT solver returned: sat={sat}, elapsed={runtime:.6f}s")
        
        if not sat:
            logger.warning("Puzzle is UNSATISFIABLE (no solution exists)")
            return {
                "solved": False,
                "solution": None,
                "time_seconds": round(runtime, 6),
                "error": "No solution exists for this puzzle"
            }

        logger.info("Solution found, decoding SAT output")
        solution = decode_solution(process.stdout.splitlines())
        logger.debug(f"Solution decoded successfully")
        
        logger.info("Sudoku solved successfully")
        response_data = {
            "solved": True,
            "solution": SudokuGrid(grid=solution),
            "time_seconds": round(runtime, 6),
        }
        return response_data
        
    except ValueError as e:
        logger.error(f"Validation error during sudoku solve: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except subprocess.TimeoutExpired as e:
        logger.error(f"SAT solver timeout after 5s")
        raise HTTPException(status_code=408, detail="Solver timeout - puzzle too complex")
    except FileNotFoundError as e:
        logger.error(f"Solver binary not found: {str(e)}")
        raise HTTPException(status_code=500, detail="Solver binary unavailable")
    except Exception as e:
        logger.exception(f"Unexpected error during sudoku solve: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=f"Internal error: {type(e).__name__}")