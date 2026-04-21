import json

import redis
import logging
from redis.exceptions import ConnectionError, TimeoutError, RedisError
from fastapi import HTTPException
from backend.app.services.database_service import DatabaseService
from backend.app.services.queue_service import QueueService
from backend.app.utils.formula import normalize_and_hash
from backend.app.core.constants import JobStatus, TIMEOUT_S_SUDOKU, TIMEOUT_S_SAT, SolverMode
from backend.app.schemas.job import JobSubmitResponse, StatusSchema, SolverResult

logger = logging.getLogger(__name__)

class JobService: 
    """Run submissions follow an async job based exec.
    Responsibilites of this class:
    1. JobService initialization.
    2. Submitting a run and returning run_id.
    3. Get the status of a run if it exists in db.
    4. Get the result of a completed run."""
    
    def __init__(self, db_service: DatabaseService, queue_service: QueueService):
        """DI"""
        self.db = db_service
        self.queue = queue_service
    
    def submit_job(self, formula_raw: str, notation: str = 'RPN', timeout_s: int = 5, mode: str = 'RPN'):
        """
        DATABASE is source of truth.
        1.Validate formula
        2.Deduplicate and check if it exists in Postgressql.
        3.Create Job
        4.Try enqueue, if fails then DB is FAILED, else QUEUED.
        Return: JobSubmitSchema
        """
        try:
            normalized_rpn, normalized_hash = normalize_and_hash(formula_raw, "RPN", mode)
            logger.debug(f"Normalized_rpn: {normalized_rpn} and normalized_hash {normalized_hash}")
        except ValueError as e:
            logger.error(f"Formula entered needs to be checked.")
            raise HTTPException(
            status_code=400,
            detail= "Re check your input as it may be wrong, error is: " + str(e)
            )
        formula_id = self.db.get_or_create_formula(normalized_rpn, normalized_hash, notation)
        logger.debug(f"For formula_id{formula_id}, formula has been checked or created.")
        
        # For sudoku, always create a new run (no caching/dedup)
        if mode != SolverMode.CNF_SUDOKU:
            # First check for completed runs (cached results)
            completed_job = self.db.get_completed_run(formula_id)
            if completed_job:
                existing_run_id, status = completed_job
                logger.info(f"Cached result found for formula_id {formula_id}, run_id is {existing_run_id}")
                return JobSubmitResponse(
                    msg = "Cached result found. Returning existing run_id.",
                    formula = normalized_rpn,
                    formula_id = formula_id,
                    run_id = existing_run_id,
                    status = status             
                )
            
            # Then check if there are already pending/processing jobs against said formula
            pending_job = self.db.get_active_run(formula_id)
            if pending_job:
                existing_run_id, status = pending_job
                logger.info(f"Run pending against formula_id{formula_id}, run_id is {existing_run_id}")
                logger.info(f"Returning run_id:{existing_run_id}")
                return JobSubmitResponse(
                    msg = "A run already exists for said formula, run_id is returned.",
                    formula = normalized_rpn,
                    formula_id = formula_id,
                    run_id = existing_run_id,
                    status =  status             
                )
        
        new_run_id = None
        timeout_s = 5
        if mode == SolverMode.CNF_SUDOKU:
            new_run_id = self.db.create_run(formula_id, mode, TIMEOUT_S_SUDOKU)
            timeout_s =  TIMEOUT_S_SUDOKU
        else:
            new_run_id = self.db.create_run(formula_id, mode, TIMEOUT_S_SAT)
            timeout_s =  TIMEOUT_S_SAT
        logger.info(f"For formula_id{formula_id} run_id {new_run_id} has been created.")
        payload = {
            "formula" : normalized_rpn,
            "run_id": new_run_id,
            "formula_id": formula_id,
            "mode": mode,
            "timeout_s": timeout_s
        }
        try:
            self.queue.enqueue(new_run_id, payload)
            logger.info(f"Run with id{new_run_id} has been queued on Redis.")
            #REDIS ENQUEUED LOGGER
        except redis.RedisError as exc:
            self.db.update_run_status(new_run_id, JobStatus.FAILED)
            logger.exception(
                "Failed to enqueue run to Redis",
                extra={"run_id": new_run_id, "formula_id": formula_id},
            )
            raise HTTPException(
                status_code=503,
                detail="Job queue temporarily unavailable"
            ) from exc

        self.db.update_run_status(new_run_id, JobStatus.QUEUED)
        logger.info(f"Run with id{new_run_id} has successfully queued on Redis, status change to QUEUED.")
        return JobSubmitResponse(
                msg = "Job submitted successfully",
                formula = normalized_rpn,
                formula_id = formula_id,
                run_id = new_run_id,
                status = JobStatus.QUEUED
            ) 
            
    def get_run_status(self, run_id: int):
        run = self.db.get_status_by_run_id(run_id)
        if run:
            logger.info(f"Run with id {run_id} does exists.")
            return StatusSchema(
                msg="Here is the status of your run.",
                run_id=run_id,
                status=run["status"]
            )
        else:
            logger.error(f"Run with id {run_id} does not exist. Cannot get_job_status")
            raise HTTPException(
                status_code=404, 
                detail=f"Run ID {run_id} not found. Please check the run_id from your job submission."
            )

    def get_run_result(self, run_id: int):
        run = self.db.get_run_by_id(run_id)
        if not run:
            logger.error(f"Run with id {run_id} does not exist. Cannot get_job_result.")
            raise HTTPException(
                status_code=404, 
                detail=f"Run ID {run_id} not found. Please check the run_id from your job submission."
            )
        
        if run["status"] not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMEOUT):
            logger.warning(f"Run {run_id} is not yet complete. Status: {run['status']}")
            raise HTTPException(
                status_code=400, 
                detail=f"Run is not complete yet. Current status: {run['status']}. Use 'status {run_id}' to check progress."
            )
        
        result = self.db.get_result_by_run_id(run_id)
        if not result:
            logger.error(f"No result found for run_id {run_id}")
            raise HTTPException(
                status_code=404, 
                detail=f"Result not found for run_id {run_id}. The job may have failed or timed out."
            )
            
        formula = self.db.get_formula_by_id(run["formula_id"])
        
        # Handle assignment: could be JSON string (RPN) or already parsed (sudoku)
        assignment = None
        if result["assignment"]:
            if isinstance(result["assignment"], str):
                # RPN formula result - parse JSON string
                assignment = json.loads(result["assignment"])
            else:
                # Sudoku result - already parsed (list)
                assignment = result["assignment"]
        
        return SolverResult(
            msg="Here is the result for your run_id.",
            status=run["status"],
            run_id=run_id,
            formula_id=run["formula_id"],
            formula=formula,
            result=result["result"],
            assignment=assignment,
            runtime=result["runtime_s"]
        )