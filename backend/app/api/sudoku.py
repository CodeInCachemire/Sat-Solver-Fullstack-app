import logging
import subprocess
from typing import List
from fastapi import APIRouter, HTTPException, File, UploadFile
from backend.app.schemas.sudoku_schema import SudokuGrid, NYDiffEnum
from backend.app.solvers.sudoku_solver import run_solver_sudoku
from backend.app.utils.sudoku_helper import decode_solution, encode_sudoku, propagate
from backend.app.core.constants import NYT_SUDOKU_URL_BASE
from backend.app.utils.sudoku_ny import parse_nyt_sudoku

sudoku_router = APIRouter(prefix="/sudoku", tags=["sudoku-solver"])
logger = logging.getLogger(__name__)

def print_grid(grid: List[List[int]]):
    for row in grid:
        print(" ".join(str(x) for x in row))
"""@sudoku_router.post("/image-upload")
def image_upload(file: UploadFile = File(...)):
    #TODO nothing done yet
    pass"""

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