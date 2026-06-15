#!/usr/bin/env python3
"""Worker process startup script.

This script initializes and runs a worker that processes solver jobs from the queue.
"""
import logging
import sys
import sentry_sdk

from backend.app.core.config import settings
from backend.app.db.session import init_db_pool, get_connection, release_connection
from backend.app.redis.redis_session import init_redis_pool, get_redis_client
from backend.app.services.database_service import DatabaseService
from backend.app.services.queue_service import QueueService
from backend.app.worker import Worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    environment=settings.SENTRY_ENVIRONMENT,
    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    send_default_pii=True,
)


def main():
    """Initialize dependencies and start the worker."""
    logger.info("Initializing worker dependencies...")
    
    # Initialize connection pools
    init_db_pool()
    init_redis_pool()
    
    # Create service instances with proper dependency injection
    redis_client = get_redis_client()
    queue_service = QueueService(redis_client)
    
    # DatabaseService now takes connection pool functions, not a connection!
    db_service = DatabaseService(get_connection, release_connection)
    
    # Create and start worker
    worker = Worker(
        queue=queue_service,
        db=db_service,
        poll_timeout_s=5
    )
    
    logger.info("Starting worker process...")
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception:
        logger.exception("Worker crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
