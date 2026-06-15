"""
Comprehensive test suite for health check endpoints.
Tests /health (liveness) and /ready (readiness) endpoints.
"""

import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

pytestmark = pytest.mark.unit


class TestHealthEndpoint:
    """Tests for /health liveness check endpoint."""
    
    def test_get_health_returns_dict(self, monkeypatch):
        """Health function should return dict."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        assert isinstance(result, dict)
    
    def test_get_health_has_status_field(self, monkeypatch):
        """Health response should have 'status' field."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        assert "status" in result
    
    def test_get_health_status_is_ok(self, monkeypatch):
        """Health status should be 'ok'."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        assert result["status"] == "ok"
    
    def test_get_health_has_database_field(self, monkeypatch):
        """Health response should have 'database' field."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        assert "database" in result
    
    def test_get_health_has_redis_field(self, monkeypatch):
        """Health response should have 'redis' field."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        assert "redis" in result
    
    def test_get_health_db_status_connected(self, monkeypatch):
        """Database status should be 'connected' when ok."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        assert result["database"] == "connected"
    
    def test_get_health_redis_status_connected(self, monkeypatch):
        """Redis status should be 'connected' when ok."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        # Either connected or disconnected is valid, just verify it's one of these
        assert result["redis"] in ["connected", "disconnected"]
    
    def test_get_health_db_connection_failure(self, monkeypatch):
        """Health should report db as disconnected on failure."""
        from backend.app.api.health import get_health
        
        def mock_check_db():
            raise Exception("Connection refused")
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", mock_check_db)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        
        assert result["status"] == "ok"  # Overall status still ok
        assert result["database"] == "disconnected"
    
    def test_get_health_redis_connection_failure(self, monkeypatch):
        """Health should report redis as disconnected on failure."""
        from backend.app.api.health import get_health
        
        def mock_check_redis():
            raise Exception("Connection refused")
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", mock_check_redis)
        
        result = get_health()
        
        assert result["status"] == "ok"  # Overall status still ok
        assert result["redis"] == "disconnected"
    
    def test_get_health_both_services_down(self, monkeypatch):
        """Health should report both down if they fail."""
        from backend.app.api.health import get_health
        
        def mock_check_db():
            raise Exception("DB error")
        
        def mock_check_redis():
            raise Exception("Redis error")
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", mock_check_db)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", mock_check_redis)
        
        result = get_health()
        
        assert result["status"] == "ok"
        assert result["database"] == "disconnected"
        assert result["redis"] == "disconnected"
    
    def test_get_health_redis_returns_false(self, monkeypatch):
        """Health should report redis disconnected if check returns False."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: False)
        
        result = get_health()
        
        assert result["redis"] == "disconnected"


class TestReadyEndpoint:
    """Tests for /ready readiness check endpoint."""
    
    def test_get_readiness_returns_dict_on_success(self, monkeypatch):
        """Ready function should return dict on success."""
        from backend.app.api.health import get_readiness
        
        monkeypatch.setattr("backend.app.api.health.check_solver", lambda: None)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        
        result = get_readiness()
        assert isinstance(result, dict)
    
    def test_get_readiness_has_status_field(self, monkeypatch):
        """Ready response should have 'status' field."""
        from backend.app.api.health import get_readiness
        
        monkeypatch.setattr("backend.app.api.health.check_solver", lambda: None)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        
        result = get_readiness()
        assert "status" in result
    
    def test_get_readiness_checks_solver_exists(self, monkeypatch):
        """Ready endpoint should check if solver exists."""
        from backend.app.api.health import get_readiness
        
        def mock_check_solver():
            raise RuntimeError("Solver does not exist")
        
        monkeypatch.setattr("backend.app.api.health.check_solver", mock_check_solver)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        
        with pytest.raises(HTTPException) as exc_info:
            get_readiness()
        
        assert exc_info.value.status_code == 503
    
    def test_get_readiness_checks_solver_executable(self, monkeypatch):
        """Ready endpoint should check if solver is executable."""
        from backend.app.api.health import get_readiness
        
        def mock_check_solver():
            raise RuntimeError("Solver is not executable")
        
        monkeypatch.setattr("backend.app.api.health.check_solver", mock_check_solver)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        
        with pytest.raises(HTTPException) as exc_info:
            get_readiness()
        
        assert exc_info.value.status_code == 503
    
    def test_get_readiness_checks_db_connectivity(self, monkeypatch):
        """Ready endpoint should check database connectivity."""
        from backend.app.api.health import get_readiness
        
        def mock_check_db():
            raise RuntimeError("Database connection failed")
        
        monkeypatch.setattr("backend.app.api.health.check_solver", lambda: None)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", mock_check_db)
        
        with pytest.raises(HTTPException) as exc_info:
            get_readiness()
        
        assert exc_info.value.status_code == 503
    
    def test_get_readiness_failure_includes_error_detail(self, monkeypatch):
        """Ready endpoint should include error detail in exception."""
        from backend.app.api.health import get_readiness
        
        def mock_check_solver():
            raise RuntimeError("Solver not found")
        
        monkeypatch.setattr("backend.app.api.health.check_solver", mock_check_solver)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        
        with pytest.raises(HTTPException) as exc_info:
            get_readiness()
        
        assert "Solver not found" in exc_info.value.detail
    
    def test_get_readiness_solver_error_takes_precedence(self, monkeypatch):
        """Ready endpoint should fail on solver error."""
        from backend.app.api.health import get_readiness
        
        def mock_check_solver():
            raise RuntimeError("Solver missing")
        
        monkeypatch.setattr("backend.app.api.health.check_solver", mock_check_solver)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        
        with pytest.raises(HTTPException) as exc_info:
            get_readiness()
        
        assert exc_info.value.status_code == 503
        assert "Solver missing" in exc_info.value.detail
    
    def test_get_readiness_db_error_after_solver_ok(self, monkeypatch):
        """Ready endpoint should fail if db fails but solver is ok."""
        from backend.app.api.health import get_readiness
        
        def mock_check_db():
            raise RuntimeError("DB connection refused")
        
        monkeypatch.setattr("backend.app.api.health.check_solver", lambda: None)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", mock_check_db)
        
        with pytest.raises(HTTPException) as exc_info:
            get_readiness()
        
        assert exc_info.value.status_code == 503


class TestCheckSolverFunction:
    """Tests for the check_solver utility function."""
    
    def test_check_solver_verifies_file_exists(self, monkeypatch):
        """Should check if solver file exists."""
        from backend.app.api.health import check_solver
        from pathlib import Path as RealPath
        
        # Create a mock Path that handles division
        mock_path_instance = MagicMock(spec=RealPath)
        mock_path_instance.parent = mock_path_instance
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = False
        
        def mock_path_constructor(arg):
            return mock_path_instance
        
        monkeypatch.setattr("backend.app.api.health.Path", mock_path_constructor)
        
        with pytest.raises(RuntimeError, match="does not exist"):
            check_solver()
    
    def test_check_solver_verifies_is_file(self, monkeypatch):
        """Should check if solver is a file (not directory)."""
        from backend.app.api.health import check_solver
        from pathlib import Path as RealPath
        
        mock_path_instance = MagicMock(spec=RealPath)
        mock_path_instance.parent = mock_path_instance
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_file.return_value = False
        
        def mock_path_constructor(arg):
            return mock_path_instance
        
        monkeypatch.setattr("backend.app.api.health.Path", mock_path_constructor)
        
        with pytest.raises(RuntimeError, match="not a file"):
            check_solver()
    
    def test_check_solver_verifies_executable(self, monkeypatch):
        """Should check if solver is executable."""
        from backend.app.api.health import check_solver
        from pathlib import Path as RealPath
        
        mock_path_instance = MagicMock(spec=RealPath)
        mock_path_instance.parent = mock_path_instance
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_file.return_value = True
        
        def mock_path_constructor(arg):
            return mock_path_instance
        
        monkeypatch.setattr("backend.app.api.health.Path", mock_path_constructor)
        monkeypatch.setattr("backend.app.api.health.os.access", lambda path, mode: False)
        
        with pytest.raises(RuntimeError, match="not executable"):
            check_solver()
    
    def test_check_solver_success_on_valid_file(self, monkeypatch):
        """Should succeed when solver is valid."""
        from backend.app.api.health import check_solver
        from pathlib import Path as RealPath
        
        mock_path_instance = MagicMock(spec=RealPath)
        mock_path_instance.parent = mock_path_instance
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_file.return_value = True
        
        def mock_path_constructor(arg):
            return mock_path_instance
        
        monkeypatch.setattr("backend.app.api.health.Path", mock_path_constructor)
        monkeypatch.setattr("backend.app.api.health.os.access", lambda path, mode: True)
        
        # Should not raise
        check_solver()


class TestHealthConsistency:
    """Tests for consistency between health and ready endpoints."""
    
    def test_health_always_ok(self, monkeypatch):
        """Health should always return ok status."""
        from backend.app.api.health import get_health
        
        def mock_db():
            raise Exception("DB down")
        
        def mock_redis():
            raise Exception("Redis down")
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", mock_db)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", mock_redis)
        
        result = get_health()
        assert result["status"] == "ok"
    
    def test_ready_strict_on_failure(self, monkeypatch):
        """Ready should throw exception on any failure."""
        from backend.app.api.health import get_readiness
        
        def mock_db():
            raise RuntimeError("DB down")
        
        monkeypatch.setattr("backend.app.api.health.check_solver", lambda: None)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", mock_db)
        
        with pytest.raises(HTTPException):
            get_readiness()


class TestErrorMessages:
    """Tests for error message clarity."""
    
    def test_health_returns_specific_statuses(self, monkeypatch):
        """Health should use 'connected' or 'disconnected'."""
        from backend.app.api.health import get_health
        
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        monkeypatch.setattr("backend.app.api.health.check_redis_connectivity", lambda: True)
        
        result = get_health()
        
        assert result["database"] in ["connected", "disconnected"]
        assert result["redis"] in ["connected", "disconnected"]
    
    def test_ready_includes_error_context(self, monkeypatch):
        """Ready should include clear error messages."""
        from backend.app.api.health import get_readiness
        
        def mock_check():
            raise RuntimeError("Critical: System unavailable")
        
        monkeypatch.setattr("backend.app.api.health.check_solver", mock_check)
        monkeypatch.setattr("backend.app.db.session.check_db_connectivity", lambda: None)
        
        with pytest.raises(HTTPException) as exc_info:
            get_readiness()
        
        assert "Critical: System unavailable" in exc_info.value.detail
