from fastapi import APIRouter, HTTPException, status
from pathlib import Path
import os
from backend.app.db import session
from backend.app.redis.redis_session import check_redis_connectivity

health_router = APIRouter()

@health_router.get("/health", status_code=status.HTTP_200_OK) #liveness check
def get_health():
    """Health check endpoint that verifies database and Redis connectivity."""
    db_status = "connected"
    redis_status = "connected"
    
    # Check database connectivity
    try:
        session.check_db_connectivity()
    except Exception:
        db_status = "disconnected"
    
    # Check Redis connectivity
    try:
        if not check_redis_connectivity():
            redis_status = "disconnected"
    except Exception:
        redis_status = "disconnected"
    
    return {
        "status": "ok",
        "database": db_status,
        "redis": redis_status
    }

@health_router.get("/ready") #readiness check
def get_readiness():
    """Readiness check, solver existence check and db readiness check."""
    try:
        check_solver()
        session.check_db_connectivity()
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail = str(error),
        )
    return {"status": "Solver exists, is a file and is executable and DB is connectable."}

def check_solver():
    here = Path(__file__)
    project_root = here.parent.parent.parent.parent
    sat_solver_path = project_root / "bin" / "satsolver"
    if not sat_solver_path.exists():
        raise RuntimeError("Solver does not exist")
    if not sat_solver_path.is_file():
        raise RuntimeError("Solver is not a file")
    if not os.access(sat_solver_path,os.X_OK):
        raise RuntimeError("Solver is not executable")
