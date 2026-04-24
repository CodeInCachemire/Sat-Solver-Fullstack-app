"""Database service layer for handling all database operations."""
import json
from typing import Optional, Dict, Any, Callable
from psycopg2.extensions import connection
from backend.app.db import queries
from backend.app.core.constants import JobStatus


class DatabaseService:
    """Class for database operations using connection pool."""
    
    def __init__(self, get_conn_func: Callable, release_conn_func: Callable):
        """Initialize with connection pool functions."""
        self.get_conn = get_conn_func
        self.release_conn = release_conn_func
 
    def get_or_create_formula(
        self, 
        normalized_input: str, 
        hash_value: str, 
        notation: str
    ) -> int: 
        """
        Get existing formula ID or create new formula.
        
        If formula with the same hash exists, returns its ID.
        Otherwise, creates a new formula and returns the new ID.
        """
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        queries.UPSERT_INTO_FORMULAS,
                        (normalized_input, hash_value, notation)
                    )
                    formula_id = cursor.fetchone()[0]  
                    return formula_id
        finally:
            self.release_conn(conn)          
                
    def create_run(self, formula_id: int, mode: str, timeout_s: int = 5) -> int:
        """Create a new solver run for the specified formula."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        queries.INSERT_INTO_RUNS,
                        (formula_id, JobStatus.CREATED, timeout_s, mode)
                    )
                    run_id = cursor.fetchone()[0]
                    return run_id
        finally:
            self.release_conn(conn)

    def update_run_status(self, run_id: int, status: str) -> None:
        """Update the status of a solver run."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(queries.UPDATE_RUN_STATUS, (status, status, status, run_id))
        finally:
            self.release_conn(conn)

    def get_formula_by_id(self, formula_id: int) -> Optional[str]:
        """Get normalized formula input by formula ID."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(queries.GET_FORMULA_BY_ID, (formula_id,))
                    result = cur.fetchone()
                    return result[0] if result else None
        finally:
            self.release_conn(conn)
            
    def get_run_by_id(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get run details by run ID."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(queries.GET_RUN_BY_ID, (run_id,))
                    result = cur.fetchone()
                    if result: 
                        return {
                            "id": result[0],
                            "formula_id": result[1],
                            "status": result[2],
                            "created_at": result[3],
                            "started_at": result[4],
                            "finished_at": result[5],
                            "timeout_s": result[6],
                            "mode": result[7]
                        } 
                    return None
        finally:
            self.release_conn(conn)
            
    def get_status_by_run_id(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get run details by run ID."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(queries.GET_RUN_STATUS_BY_ID, (run_id,))
                    result = cur.fetchone()
                    if result: 
                        return {
                            "id": result[0],
                            "status": result[1],
                        } 
                    return None
        finally:
            self.release_conn(conn) 
                   
    def insert_result(
        self,
        run_id: int,
        result: str,
        assignment: Optional[Dict],
        stdout: str,
        stderr: str,
        error_type: Optional[str],
        error_message: Optional[str],
        runtime_s: float
    ) -> None:
        """Store solver execution result."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        queries.INSERT_RESULT,
                        (
                            run_id, 
                            result, 
                            json.dumps(assignment) if assignment else None, 
                            stdout, 
                            stderr, 
                            error_type, 
                            error_message, 
                            runtime_s
                        )
                    )
        finally:
            self.release_conn(conn)

    def get_result_by_run_id(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get solver result by run ID."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(queries.GET_RESULT_BY_RUN_ID, (run_id,))
                    result = cur.fetchone()
                    if result: 
                        return {
                            "result": result[0],
                            "assignment": result[1],
                            "stdout": result[2],
                            "stderr": result[3],
                            "error_type": result[4],
                            "error_message": result[5],
                            "runtime_s": result[6],
                        }
                    return None
        finally:
            self.release_conn(conn)
        
    def get_active_run(self, formula_id: int) -> Optional[tuple]:
        """Get pending or processing job for a formula."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(queries.GET_PENDING_RUN_BY_FORMULA, (formula_id,))
                    return cur.fetchone()
        finally:
            self.release_conn(conn)
    
    def get_completed_run(self, formula_id: int) -> Optional[tuple]:
        """Get most recent completed run for a formula (cached result)."""
        conn = self.get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(queries.GET_COMPLETED_RUN_BY_FORMULA, (formula_id,))
                    return cur.fetchone()
        finally:
            self.release_conn(conn)