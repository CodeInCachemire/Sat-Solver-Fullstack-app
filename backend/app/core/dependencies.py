# backend/app/core/dependencies.py
from typing import Optional

from fastapi import Depends
from backend.app.db.session import get_connection, release_connection
from backend.app.services.database_service import DatabaseService
from backend.app.services.job_service import JobService
from backend.app.services.queue_service import QueueService
from backend.app.redis.redis_session import get_redis_client

# Singletons
_queue_service: Optional[QueueService] = None

def init_queue_service() -> None:
    """Initialize QueueService singleton at app startup."""
    global _queue_service
    _queue_service = QueueService(get_redis_client())

def get_db():
    """Provide DatabaseService with connection pool functions."""
    yield DatabaseService(get_connection, release_connection)

def get_job_service(db: DatabaseService = Depends(get_db)) -> JobService:
    """Dependency injection for JobService."""
    if _queue_service is None:
        raise RuntimeError("QueueService not initialized. Call init_queue_service() at startup.")
    return JobService(db, _queue_service)