"""
Comprehensive unit test suite for backend.app.services.queue_service module.
Tests Redis queue operations using mocks to verify business logic.

Run only unit tests with:
    pytest backend/tests/test_*.py -m unit

Run with integration tests:
    pytest -m ""
"""

import json
import pytest
import time
from unittest.mock import Mock, MagicMock, patch, call
from redis.exceptions import ConnectionError, TimeoutError, RedisError

from backend.app.services.queue_service import QueueService
from backend.app.core.constants import JobStatus

# Mark all tests in this file as unit tests
pytestmark = pytest.mark.unit


class TestQueueServiceInit:
    """Test suite for QueueService initialization."""
    
    def test_init_with_defaults(self):
        """Initialize with default parameters."""
        mock_redis = Mock()
        service = QueueService(mock_redis)
        
        assert service.redis is mock_redis
        assert service.max_attempts == 3
        assert service.job_ttl == 3600
    
    def test_init_with_custom_values(self):
        """Initialize with custom max_attempts and job_ttl."""
        mock_redis = Mock()
        service = QueueService(mock_redis, max_attempts=5, job_ttl=7200)
        
        assert service.redis is mock_redis
        assert service.max_attempts == 5
        assert service.job_ttl == 7200
    
    def test_queue_constants(self):
        """Verify queue constant names."""
        assert QueueService.PENDING_QUEUE == "q:pending"
        assert QueueService.PROCESSING_QUEUE == "q:processing"
        assert QueueService.DEAD_QUEUE == "q:dead"
    
    def test_key_format_constants(self):
        """Verify key format templates."""
        assert QueueService.JOB_PAYLOAD_KEY == "job:{run_id}:payload"
        assert QueueService.JOB_META_KEY == "job:{run_id}:meta"
        assert QueueService.JOB_STATUS_KEY == "job:{run_id}:status"


class TestEnqueue:
    """Test suite for QueueService.enqueue method."""
    
    def test_enqueue_creates_payload_key(self):
        """Should create job payload in Redis."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        payload = {"formula": "a b &&", "run_id": 1, "formula_id": 10}
        
        service.enqueue(run_id=1, payload=payload)
        
        # Verify pipeline was created
        mock_redis.pipeline.assert_called_once_with(transaction=True)
        
        # Verify set was called for payload
        mock_pipeline.set.assert_any_call(
            "job:1:payload",
            json.dumps(payload),
            ex=3600
        )
    
    def test_enqueue_creates_metadata(self):
        """Should create job metadata with attempts, created_at, last_claimed_at."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        payload = {"formula": "a b &&"}
        
        with patch('time.time', return_value=1000.0):
            service.enqueue(run_id=42, payload=payload)
        
        # Verify hset was called for metadata
        calls = mock_pipeline.hset.call_args_list
        meta_call = calls[0]  # First hset call
        
        assert meta_call[0][0] == "job:42:meta"
        assert meta_call[1]["mapping"]["attempts"] == 0
        assert meta_call[1]["mapping"]["created_at"] == 1000
        assert meta_call[1]["mapping"]["last_claimed_at"] == 0
    
    def test_enqueue_creates_status_key(self):
        """Should create job status key with QUEUED status."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        payload = {"formula": "test"}
        
        service.enqueue(run_id=5, payload=payload)
        
        # Verify set was called for status
        mock_pipeline.set.assert_any_call(
            "job:5:status",
            JobStatus.QUEUED,
            ex=3600
        )
    
    def test_enqueue_pushes_to_pending_queue(self):
        """Should push run_id to pending queue."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        payload = {"formula": "test"}
        
        service.enqueue(run_id=99, payload=payload)
        
        # Verify rpush was called
        mock_pipeline.rpush.assert_called_once_with("q:pending", 99)
    
    def test_enqueue_executes_pipeline(self):
        """Should execute the pipeline."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        payload = {"formula": "test"}
        
        service.enqueue(run_id=1, payload=payload)
        
        mock_pipeline.execute.assert_called_once()
    
    def test_enqueue_uses_custom_ttl(self):
        """Should use custom job_ttl when set."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis, job_ttl=7200)
        payload = {"formula": "test"}
        
        service.enqueue(run_id=1, payload=payload)
        
        # All set commands should use 7200 TTL
        for call_obj in mock_pipeline.set.call_args_list:
            assert call_obj[1]["ex"] == 7200
    
    def test_enqueue_json_serializes_payload(self):
        """Should JSON serialize the payload."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        payload = {"formula": "a b &&", "run_id": 1, "nested": {"key": "value"}}
        
        service.enqueue(run_id=100, payload=payload)
        
        # Verify JSON serialization
        mock_pipeline.set.assert_any_call(
            "job:100:payload",
            json.dumps(payload),
            ex=3600
        )
    
    def test_enqueue_with_complex_payload(self):
        """Should handle complex nested payloads."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        payload = {
            "formula": "complex formula",
            "run_id": 1,
            "formula_id": 42,
            "mode": "SAT",
            "timeout_s": 10,
            "metadata": {"solver": "dpll", "version": "1.0"}
        }
        
        service.enqueue(run_id=1, payload=payload)
        
        # Should successfully serialize
        mock_pipeline.execute.assert_called_once()


class TestClaim:
    """Test suite for QueueService.claim method."""
    
    def test_claim_moves_from_pending_to_processing(self):
        """Should move job from pending to processing queue."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"42"
        mock_redis.get.return_value = json.dumps({"formula": "test"}).encode()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        result = service.claim(timeout_s=1)
        
        # Verify BRPOPLPUSH was called correctly
        mock_redis.brpoplpush.assert_called_once_with(
            "q:pending",
            "q:processing",
            timeout=1
        )
    
    def test_claim_returns_none_on_empty_queue(self):
        """Should return None when no jobs in queue."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = None
        
        service = QueueService(mock_redis)
        result = service.claim(timeout_s=1)
        
        assert result is None
    
    def test_claim_returns_tuple_with_run_id_and_payload(self):
        """Should return (run_id, payload) tuple."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"42"
        payload = {"formula": "a b &&", "run_id": 42}
        mock_redis.get.return_value = json.dumps(payload).encode()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        result = service.claim()
        
        assert result is not None
        run_id, claimed_payload = result
        assert run_id == 42
        assert claimed_payload == payload
    
    def test_claim_fetches_payload_from_redis(self):
        """Should fetch payload from Redis."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"10"
        payload_dict = {"formula": "test formula"}
        mock_redis.get.return_value = json.dumps(payload_dict).encode()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        result = service.claim()
        
        mock_redis.get.assert_called_once_with("job:10:payload")
    
    def test_claim_returns_none_on_missing_payload(self):
        """Should return None when payload doesn't exist in Redis."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"10"
        mock_redis.get.return_value = None  # Payload doesn't exist
        
        service = QueueService(mock_redis)
        result = service.claim()
        
        assert result is None
        # Should remove from processing queue on missing payload
        mock_redis.lrem.assert_called_once_with("q:processing", 1, b"10")
    
    def test_claim_returns_none_on_invalid_json(self):
        """Should return None when payload is not valid JSON."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"15"
        mock_redis.get.return_value = b"invalid json {"
        
        service = QueueService(mock_redis)
        result = service.claim()
        
        assert result is None
        # Should remove from processing queue on JSON error
        mock_redis.lrem.assert_called_once_with("q:processing", 1, b"15")
    
    def test_claim_returns_none_on_non_integer_run_id(self):
        """Should return None when run_id is not an integer."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"not_a_number"
        
        service = QueueService(mock_redis)
        result = service.claim()
        
        assert result is None
        # Should remove from processing queue
        mock_redis.lrem.assert_called_once_with("q:processing", 1, b"not_a_number")
    
    def test_claim_updates_metadata_on_success(self):
        """Should update metadata with last_claimed_at and increment attempts."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"25"
        payload = {"formula": "test"}
        mock_redis.get.return_value = json.dumps(payload).encode()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        with patch('time.time', return_value=2000.0):
            service = QueueService(mock_redis)
            result = service.claim()
        
        assert result is not None
        
        # Verify metadata was updated
        mock_pipeline.hset.assert_called_once()
        hset_call = mock_pipeline.hset.call_args
        assert hset_call[0][0] == "job:25:meta"
        assert hset_call[1]["mapping"]["last_claimed_at"] == 2000
        
        # Verify attempts was incremented
        mock_pipeline.hincrby.assert_called_once_with(
            "job:25:meta",
            "attempts",
            1
        )
    
    def test_claim_continues_on_metadata_update_failure(self):
        """Should continue and return job even if metadata update fails."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"30"
        payload = {"formula": "test"}
        mock_redis.get.return_value = json.dumps(payload).encode()
        mock_pipeline = MagicMock()
        mock_pipeline.execute.side_effect = RedisError("Connection lost")
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        result = service.claim()
        
        # Should still return the job despite metadata failure
        assert result is not None
        run_id, claimed_payload = result
        assert run_id == 30
    
    def test_claim_raises_on_brpoplpush_error(self):
        """Should raise RedisError if BRPOPLPUSH fails."""
        mock_redis = Mock()
        mock_redis.brpoplpush.side_effect = RedisError("Redis connection failed")
        
        service = QueueService(mock_redis)
        
        with pytest.raises(RedisError):
            service.claim()
    
    def test_claim_raises_on_get_payload_error(self):
        """Should raise RedisError if getting payload fails."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"35"
        mock_redis.get.side_effect = RedisError("Redis connection failed")
        
        service = QueueService(mock_redis)
        
        with pytest.raises(RedisError):
            service.claim()
    
    def test_claim_cleans_processing_queue_on_get_error(self):
        """Should remove from processing queue if get fails."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"35"
        mock_redis.get.side_effect = RedisError("Connection failed")
        
        service = QueueService(mock_redis)
        
        with pytest.raises(RedisError):
            service.claim()
        
        # Should attempt to clean processing queue
        assert mock_redis.lrem.called
    
    def test_claim_default_timeout(self):
        """Should use default timeout of 1 second."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"40"
        mock_redis.get.return_value = json.dumps({"formula": "test"}).encode()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.claim()
        
        # Verify default timeout
        mock_redis.brpoplpush.assert_called_once()
        call_args = mock_redis.brpoplpush.call_args
        assert call_args[1]["timeout"] == 1


class TestAck:
    """Test suite for QueueService.ack method."""
    
    def test_ack_removes_from_processing_queue(self):
        """Should remove job from processing queue."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.ack(run_id=50)
        
        # Verify lrem was called
        mock_pipeline.lrem.assert_called_once_with("q:processing", 1, "50")
    
    def test_ack_deletes_payload(self):
        """Should delete job payload."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.ack(run_id=50)
        
        # Verify delete was called for payload
        delete_calls = mock_pipeline.delete.call_args_list
        assert call("job:50:payload") in delete_calls
    
    def test_ack_deletes_metadata(self):
        """Should delete job metadata."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.ack(run_id=50)
        
        # Verify delete was called for metadata
        delete_calls = mock_pipeline.delete.call_args_list
        assert call("job:50:meta") in delete_calls
    
    def test_ack_executes_pipeline(self):
        """Should execute the pipeline."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.ack(run_id=50)
        
        mock_pipeline.execute.assert_called_once()
    
    def test_ack_does_not_raise_on_redis_error(self):
        """Should not raise exception on Redis error."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_pipeline.execute.side_effect = RedisError("Connection lost")
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        
        # Should not raise
        service.ack(run_id=50)
    
    def test_ack_with_different_run_ids(self):
        """Should handle multiple different run_ids correctly."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        
        service.ack(run_id=1)
        service.ack(run_id=999)
        service.ack(run_id=42)
        
        # Verify each had correct calls
        assert mock_pipeline.lrem.call_count == 3
        assert mock_pipeline.delete.call_count == 6  # 2 deletes per ack


class TestFail:
    """Test suite for QueueService.fail method."""
    
    def test_fail_removes_from_processing_queue(self):
        """Should remove job from processing queue."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.fail(run_id=60, reason="Timeout")
        
        # Verify lrem was called
        mock_pipeline.lrem.assert_called_once_with("q:processing", 1, "60")
    
    def test_fail_stores_failure_metadata(self):
        """Should store failed_at timestamp and error reason."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        with patch('time.time', return_value=3000.0):
            service = QueueService(mock_redis)
            service.fail(run_id=60, reason="Solver crashed")
        
        # Verify metadata was set
        mock_pipeline.hset.assert_called_once()
        hset_call = mock_pipeline.hset.call_args
        assert hset_call[0][0] == "job:60:meta"
        assert hset_call[1]["mapping"]["failed_at"] == 3000
        assert hset_call[1]["mapping"]["last_error"] == "Solver crashed"
    
    def test_fail_executes_pipeline(self):
        """Should execute the pipeline."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.fail(run_id=60, reason="Test failure")
        
        mock_pipeline.execute.assert_called_once()
    
    def test_fail_does_not_raise_on_redis_error(self):
        """Should not raise exception on Redis error."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_pipeline.execute.side_effect = RedisError("Connection lost")
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        
        # Should not raise
        service.fail(run_id=60, reason="Error")
    
    def test_fail_with_different_reasons(self):
        """Should handle different failure reasons."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        
        service.fail(run_id=1, reason="Timeout")
        service.fail(run_id=2, reason="Memory exhausted")
        service.fail(run_id=3, reason="Formula invalid")
        
        # Should have 3 pipeline executions
        assert mock_pipeline.execute.call_count == 3


class TestIntegration:
    """Integration tests for QueueService workflows."""
    
    def test_enqueue_then_claim_workflow(self):
        """Test complete enqueue -> claim workflow."""
        mock_redis = Mock()
        payload = {"formula": "a b &&", "run_id": 1}
        
        # Setup enqueue
        mock_pipeline_enqueue = MagicMock()
        
        # Setup claim
        mock_redis.brpoplpush.return_value = b"1"
        mock_redis.get.return_value = json.dumps(payload).encode()
        mock_pipeline_claim = MagicMock()
        
        # Alternate between pipelines
        mock_redis.pipeline.side_effect = [
            mock_pipeline_enqueue,
            mock_pipeline_claim
        ]
        
        service = QueueService(mock_redis)
        
        # Enqueue job
        service.enqueue(run_id=1, payload=payload)
        assert mock_redis.pipeline.call_count == 1
        
        # Claim job
        result = service.claim()
        assert result is not None
        run_id, claimed_payload = result
        assert run_id == 1
        assert claimed_payload == payload
    
    def test_enqueue_claim_ack_workflow(self):
        """Test complete workflow: enqueue -> claim -> ack."""
        mock_redis = Mock()
        payload = {"formula": "test"}
        
        # Setup pipelines
        mock_pipeline_enqueue = MagicMock()
        mock_pipeline_claim = MagicMock()
        mock_pipeline_ack = MagicMock()
        
        mock_redis.pipeline.side_effect = [
            mock_pipeline_enqueue,
            mock_pipeline_claim,
            mock_pipeline_ack
        ]
        
        # Setup claim
        mock_redis.brpoplpush.return_value = b"1"
        mock_redis.get.return_value = json.dumps(payload).encode()
        
        service = QueueService(mock_redis)
        
        # Enqueue
        service.enqueue(run_id=1, payload=payload)
        
        # Claim
        result = service.claim()
        assert result is not None
        
        # Ack
        service.ack(run_id=1)
        assert mock_pipeline_ack.execute.called
    
    def test_enqueue_claim_fail_workflow(self):
        """Test workflow: enqueue -> claim -> fail."""
        mock_redis = Mock()
        payload = {"formula": "test"}
        
        # Setup pipelines
        pipelines = [MagicMock() for _ in range(3)]
        mock_redis.pipeline.side_effect = pipelines
        
        # Setup claim
        mock_redis.brpoplpush.return_value = b"1"
        mock_redis.get.return_value = json.dumps(payload).encode()
        
        service = QueueService(mock_redis)
        
        # Enqueue
        service.enqueue(run_id=1, payload=payload)
        
        # Claim
        result = service.claim()
        assert result is not None
        
        # Fail
        service.fail(run_id=1, reason="Processing error")
        assert pipelines[2].execute.called


class TestErrorHandling:
    """Test error handling and resilience."""
    
    def test_claim_handles_connection_error_gracefully(self):
        """Should handle connection errors appropriately."""
        mock_redis = Mock()
        mock_redis.brpoplpush.side_effect = ConnectionError("No connection")
        
        service = QueueService(mock_redis)
        
        with pytest.raises(ConnectionError):
            service.claim()
    
    def test_claim_handles_timeout_error(self):
        """Should handle timeout errors appropriately."""
        mock_redis = Mock()
        mock_redis.brpoplpush.side_effect = TimeoutError("Timeout waiting for job")
        
        service = QueueService(mock_redis)
        
        with pytest.raises(TimeoutError):
            service.claim()
    
    def test_multiple_failed_claims_dont_corrupt_state(self):
        """Multiple failed claims shouldn't corrupt queue state."""
        mock_redis = Mock()
        
        service = QueueService(mock_redis)
        
        # First claim succeeds
        mock_redis.brpoplpush.return_value = None
        result1 = service.claim()
        assert result1 is None
        
        # Second claim also succeeds (returns None)
        result2 = service.claim()
        assert result2 is None
        
        # Redis should still be in good state for other operations
        mock_redis.brpoplpush.return_value = b"1"
        mock_redis.get.return_value = json.dumps({"formula": "test"}).encode()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        result3 = service.claim()
        assert result3 is not None


class TestKeyFormatting:
    """Test key formatting for Redis operations."""
    
    def test_payload_key_formatting(self):
        """Test payload key formatting."""
        key = QueueService.JOB_PAYLOAD_KEY.format(run_id=42)
        assert key == "job:42:payload"
    
    def test_meta_key_formatting(self):
        """Test metadata key formatting."""
        key = QueueService.JOB_META_KEY.format(run_id=42)
        assert key == "job:42:meta"
    
    def test_status_key_formatting(self):
        """Test status key formatting."""
        key = QueueService.JOB_STATUS_KEY.format(run_id=42)
        assert key == "job:42:status"
    
    def test_different_run_ids_different_keys(self):
        """Different run_ids should produce different keys."""
        key1 = QueueService.JOB_PAYLOAD_KEY.format(run_id=1)
        key2 = QueueService.JOB_PAYLOAD_KEY.format(run_id=2)
        assert key1 != key2
        assert key1 == "job:1:payload"
        assert key2 == "job:2:payload"
    
    def test_large_run_ids(self):
        """Should handle large run_ids."""
        large_id = 999999999
        key = QueueService.JOB_PAYLOAD_KEY.format(run_id=large_id)
        assert key == f"job:{large_id}:payload"


class TestPipelineUsage:
    """Test that pipelines are used correctly for atomicity."""
    
    def test_enqueue_uses_pipeline(self):
        """Enqueue should use pipeline for atomic operations."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.enqueue(run_id=1, payload={"formula": "test"})
        
        # Should create pipeline with transaction=True
        mock_redis.pipeline.assert_called_once_with(transaction=True)
        
        # Should execute exactly once
        mock_pipeline.execute.assert_called_once()
    
    def test_claim_uses_pipeline_for_metadata(self):
        """Claim should use pipeline for metadata updates."""
        mock_redis = Mock()
        mock_redis.brpoplpush.return_value = b"1"
        mock_redis.get.return_value = json.dumps({"formula": "test"}).encode()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.claim()
        
        # Should use pipeline for metadata
        mock_redis.pipeline.assert_called_once_with(transaction=True)
    
    def test_ack_uses_pipeline(self):
        """Ack should use pipeline for atomic cleanup."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.ack(run_id=1)
        
        mock_redis.pipeline.assert_called_once_with(transaction=True)
        mock_pipeline.execute.assert_called_once()
    
    def test_fail_uses_pipeline(self):
        """Fail should use pipeline for atomic metadata update."""
        mock_redis = Mock()
        mock_pipeline = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        service = QueueService(mock_redis)
        service.fail(run_id=1, reason="Test")
        
        mock_redis.pipeline.assert_called_once_with(transaction=True)
        mock_pipeline.execute.assert_called_once()
