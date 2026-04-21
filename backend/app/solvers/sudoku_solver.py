"""
Actual Sudoku fast CNF sat solver caller.
The solver takes rpn from endpoint and calls the sat solver, it has two modes one is normal sat solving and other is sudoko    
"""

import subprocess
import time
from backend.app.core.config import settings
from typing import Tuple, List
import logging 

logger = logging.getLogger(__name__)


def run_solver_sudoku(formula: str, timeout_s: int = 15) -> Tuple[subprocess.CompletedProcess, float]:
    """Execute the CNF solver on the formula.
    
    Args:
        formula: CNF formula string
        timeout_s: Timeout in seconds
        
    Returns:
        Tuple of (is_sat: bool, output_lines: List[str], elapsed_time_seconds: float)
        
    Raises:
        subprocess.TimeoutExpired: On timeout
        FileNotFoundError: If solver binary not found
        RuntimeError: On other execution errors
    """
    path = settings.SOLVER_PATH_FAST
    cmd = [path, "--cnf"]
    try:
        start = time.perf_counter()
        logger.info(f"Sudoku Solver is running with timeout {timeout_s}s")
        logger.debug(f"Solver binary: {path}")
        process = subprocess.run(
            cmd,
            input=formula,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        end = time.perf_counter()
        runtime = end - start
        logger.info(f"Solver completed in {runtime:.6f}s with return code {process.returncode}")
        return process, runtime        
    except subprocess.TimeoutExpired as e:
        logger.error(f"Solver timed out after {timeout_s}s")
        raise
    except FileNotFoundError as e:
        logger.error(f"Solver binary not found at: {path}")
        raise
    except Exception as e:
        logger.error(f"Solver execution failed: {type(e).__name__}: {e}")
        raise RuntimeError(f"Solver execution failed: {e}") from e