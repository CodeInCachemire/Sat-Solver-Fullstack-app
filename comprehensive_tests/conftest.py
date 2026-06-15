"""
Shared fixtures for unit and API tests.
All fixtures here use mocks — no external services required.
"""

import pytest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from backend.app.services.database_service import DatabaseService
from backend.app.services.job_service import JobService
from backend.app.services.queue_service import QueueService


@pytest.fixture
def mock_queue_service():
    """MagicMock for QueueService — no Redis required."""
    svc = MagicMock(spec=QueueService)
    svc.enqueue.return_value = None
    svc.claim.return_value = None
    svc.ack.return_value = None
    svc.fail.return_value = None
    return svc


@pytest.fixture
def mock_database_service():
    """MagicMock for DatabaseService — no PostgreSQL required."""
    svc = MagicMock(spec=DatabaseService)
    svc.get_or_create_formula.return_value = 1
    svc.create_run.return_value = 1
    svc.update_run_status.return_value = None
    svc.insert_result.return_value = None
    svc.get_status_by_run_id.return_value = None
    svc.get_run_by_id.return_value = None
    svc.get_result_by_run_id.return_value = None
    svc.get_active_run.return_value = None
    svc.get_completed_run.return_value = None
    svc.get_formula_by_id.return_value = "a && b"
    return svc


@pytest.fixture
def mock_job_service(mock_database_service, mock_queue_service):
    """MagicMock for JobService — returns configurable mock for API tests."""
    return MagicMock(spec=JobService)


@pytest.fixture
def test_client(mock_job_service, mock_database_service):
    """
    FastAPI TestClient with all external dependencies replaced by mocks.

    Patches startup/shutdown hooks so no real DB or Redis pool is opened.
    Overrides both get_job_service (jobs router) and get_db (dependencies)
    so injected services are fully controlled by the test.

    Both mock_job_service and mock_database_service are available to
    the test function alongside this fixture — pytest gives the same
    instance to all fixtures/tests within one function scope.
    """
    from backend.app.main import app
    from backend.app.core.dependencies import get_job_service, get_db

    app.dependency_overrides[get_job_service] = lambda: mock_job_service
    app.dependency_overrides[get_db] = lambda: mock_database_service

    # Patch names as they appear in main.py's global namespace (module-level imports)
    # and in the session.py / redis_session.py modules (inline imports in shutdown)
    with patch("backend.app.main.init_db_pool"), \
         patch("backend.app.main.init_redis_pool"), \
         patch("backend.app.main.init_queue_service"), \
         patch("backend.app.db.session.close_pool"), \
         patch("backend.app.redis.redis_session.close_redis_pool"):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client

    app.dependency_overrides.clear()
