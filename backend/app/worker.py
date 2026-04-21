import logging
import signal
import subprocess
import time
import json
from typing import Optional, List

from backend.app.schemas.sudoku_schema import SudokuGrid
from backend.app.services.queue_service import QueueService
from backend.app.services.database_service import DatabaseService
from backend.app.core.constants import TIMEOUT_S_SAT, TIMEOUT_S_SUDOKU, JobStatus, SolverMode
from backend.app.solvers.satsolver import run_solver, parse_solver_output
from backend.app.core.constants import SolverExitCodes
from backend.app.solvers.sudoku_solver import run_solver_sudoku
from backend.app.utils.sudoku_helper import decode_solution, encode_sudoku, propagate

logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        queue: QueueService,
        db: DatabaseService,
        poll_timeout_s: int = 5,
    ):
        self.queue = queue
        self.db = db
        self.poll_timeout_s = poll_timeout_s
        self.running = True
        self._current_run_id: Optional[int] = None

    def _handle_shutdown_signal(self, signum, frame):
        logger.info("Worker received shutdown signal (%s)", signum)
        self.running = False

    def install_signal_handlers(self):
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

    """Main loop run forever for workers.
    
    """
    def run_forever(self):
        logger.info("Worker starting")
        self.install_signal_handlers()

        while self.running:
            try:
                job = self.queue.claim(timeout_s=self.poll_timeout_s)
            except Exception:
                logger.exception("Queue claim failed")
                time.sleep(2)
                continue

            if job is None:
                # no job available, loop again (idle, no CPU)
                continue

            run_id, payload = job
            self._current_run_id = run_id
            logger.info("Claimed run_id=%s", run_id)

            try:
                self._process_job(run_id, payload)
            finally:
                self._current_run_id = None

        logger.info("Worker shutting down cleanly")

    #process a run
    def _process_job(self, run_id: int, payload: dict):
        try:
            self.db.update_run_status(run_id, JobStatus.PROCESSING)
            
            formula = payload["formula"]
            formula_id = payload.get("formula_id")
            mode = payload["mode"]
            if mode == SolverMode.CNF_SUDOKU:
                timeout_s = TIMEOUT_S_SUDOKU
                # Parse puzzle grid from JSON string if needed
                if isinstance(formula, str):
                    try:
                        puzzle_grid = json.loads(formula)
                    except (json.JSONDecodeError, ValueError):
                        # If not JSON, assume it's already a list
                        puzzle_grid = formula
                else:
                    puzzle_grid = formula
                process, runtime_s = sudoku_helper(puzzle_grid)
            else: 
                timeout_s = TIMEOUT_S_SAT
                process, runtime_s = run_solver(
                formula=formula, 
                run_id=run_id, 
                formula_id=formula_id, 
                timeout_s=timeout_s
                )
            
            # Extract process results
            rc = process.returncode
            stdout = process.stdout or ""
            stderr = process.stderr or ""
            runtime_s = runtime_s
            
            # Parse output based on return code
            if rc == SolverExitCodes.PARSE_ERROR:
                # Parse error - store as failed result
                self.db.insert_result(
                    run_id=run_id,
                    result="PARSE_ERROR",
                    assignment=None,
                    stdout=stdout,
                    stderr=stderr,
                    error_type="PARSE_ERROR",
                    error_message=stderr or "Formula parsing failed",
                    runtime_s=runtime_s,
                )
                self.db.update_run_status(run_id, JobStatus.FAILED)
                self.queue.ack(run_id)
                logger.info("Parse error for run_id=%s", run_id)
                
            elif rc in {SolverExitCodes.SAT, SolverExitCodes.UNSAT}:
                # SAT/UNSAT - parse and store result
                if mode == SolverMode.CNF_SUDOKU:
                    if rc == 10:
                        result = "SAT"
                    elif rc == 20:
                        result = "UNSAT"
                    assignment = decode_solution(stdout.splitlines())
                elif mode == "RPN":
                    result, assignment = parse_solver_output(stdout)
                self.db.insert_result(
                    run_id=run_id,
                    result=result,
                    assignment=assignment,
                    stdout=stdout,
                    stderr=stderr,
                    error_type=None,
                    error_message=None,
                    runtime_s=runtime_s,
                )
                self.db.update_run_status(run_id, JobStatus.COMPLETED)
                self.queue.ack(run_id)
                logger.info("Completed run_id=%s with result=%s", run_id, result)
                
            else:
                # Unexpected return code
                self.db.insert_result(
                    run_id=run_id,
                    result="UNEXPECTED_RETURNCODE",
                    assignment=None,
                    stdout=stdout,
                    stderr=stderr,
                    error_type="UNEXPECTED_RC",
                    error_message=f"Unexpected solver return code {rc}",
                    runtime_s=runtime_s,
                )
                self.db.update_run_status(run_id, JobStatus.FAILED)
                self.queue.ack(run_id)
                logger.warning("Unexpected return code %s for run_id=%s", rc, run_id)

        except subprocess.TimeoutExpired:
            logger.warning("Solver timeout for run_id=%s", run_id)
            try:
                self.db.insert_result(
                    run_id=run_id,
                    result="TIMEOUT",
                    assignment=None,
                    stdout="",
                    stderr="",
                    error_type="TIMEOUT",
                    error_message=f"Solver execution timed out after {timeout_s}s",
                    runtime_s= timeout_s,
                )
                self.db.update_run_status(run_id, JobStatus.TIMEOUT)
                self.queue.ack(run_id)
            except Exception:
                logger.exception("Failed to record timeout for run_id=%s", run_id)
                try:
                    self.queue.fail(run_id, reason="Timeout")
                except Exception:
                    logger.exception("Failed queue cleanup after timeout run_id=%s", run_id)
                    
        except FileNotFoundError:
            logger.error("Solver binary not found for run_id=%s", run_id)
            try:
                self.db.insert_result(
                    run_id=run_id,
                    result="ERROR",
                    assignment=None,
                    stdout="",
                    stderr="",
                    error_type="BINARY_NOT_FOUND",
                    error_message="Solver binary not available",
                    runtime_s=0,
                )
                self.db.update_run_status(run_id, JobStatus.FAILED)
                self.queue.ack(run_id)
            except Exception:
                logger.exception("Failed to record binary error for run_id=%s", run_id)
                try:
                    self.queue.fail(run_id, reason="Binary not found")
                except Exception:
                    logger.exception("Failed queue cleanup run_id=%s", run_id)
                    
        except Exception as e:
            logger.exception("Job failed run_id=%s", run_id)
            try:
                self.db.insert_result(
                    run_id=run_id,
                    result="EXEC_ERROR",
                    assignment=None,
                    stdout="",
                    stderr="",
                    error_type="EXECUTION_ERROR",
                    error_message=str(e),
                    runtime_s=0,
                )
                self.db.update_run_status(run_id, JobStatus.FAILED)
                self.queue.ack(run_id)
            except Exception:
                logger.exception("Failed DB update for run_id=%s", run_id)
                try:
                    self.queue.fail(run_id, reason=str(e))
                except Exception:
                    logger.exception("Failed queue cleanup run_id=%s", run_id)

def sudoku_helper(puzzle: List[List[int]]):
    """Helper to solve sudoku: propagate -> encode -> solve -> decode"""
    logger.debug("Input Sudoku puzzle received")
    
    try:
        logger.info("Starting propagation (constraint propagation)")
        puzzle = propagate(puzzle)
        logger.debug("Propagation complete")
        
        logger.info("Encoding Sudoku to CNF formula")
        formula = encode_sudoku(puzzle)
        logger.debug(f"CNF formula generated, {len(formula.splitlines())} clauses")
        
        logger.info("Invoking SAT solver")
        process, runtime_s = run_solver_sudoku(formula, timeout_s=TIMEOUT_S_SUDOKU)
        logger.info(f"SAT solver returned: rc={process.returncode}, elapsed={runtime_s:.6f}s")
        
        return process, runtime_s
    except Exception as e:
        logger.exception("Error in sudoku_helper")
        raise

        