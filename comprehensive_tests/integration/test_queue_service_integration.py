"""
Integration tests for backend.app.services.queue_service module.
Tests with real Redis instance to verify actual queue behavior.

Prerequisites:
- Redis server running on localhost:6379
- Can be started with: docker run -d -p 6379:6379 redis:latest

Run only integration tests with:
    pytest backend/tests/integration/ -m integration

Skip integration tests with:
    pytest -m "not integration"
"""

import json
import pytest
import time
import redis
from redis.exceptions import ConnectionError

from backend.app.services.queue_service import QueueService
from backend.app.core.constants import JobStatus

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="function")
def redis_client():
    """Create a Redis client connection for testing."""
    try:
        client = redis.Redis(
            host="localhost",
            port=6379,
            db=15,  # Use db 15 to avoid interfering with production
            decode_responses=False,  # Keep raw bytes for proper testing
            socket_connect_timeout=5
        )
        # Test connection
        client.ping()
        yield client
    except ConnectionError:
        pytest.skip("Redis server not available on localhost:6379")
    finally:
        try:
            client.close()
        except:
            pass


@pytest.fixture(scope="function")
def clean_redis(redis_client):
    """Clear all test data from Redis before and after test."""
    # Clear before test
    redis_client.flushdb()
    yield redis_client
    # Clear after test
    redis_client.flushdb()


@pytest.fixture(scope="function")
def queue_service(clean_redis):
    """Create QueueService instance with real Redis."""
    return QueueService(clean_redis, max_attempts=3, job_ttl=3600)


class TestEnqueueIntegration:
    """Integration tests for enqueue operation with real Redis."""
    
    def test_enqueue_creates_all_keys_in_redis(self, queue_service, clean_redis):
        """Verify enqueue creates payload, metadata, and status in Redis."""
        payload = {"formula": "a b &&", "run_id": 1, "formula_id": 10}
        
        queue_service.enqueue(run_id=1, payload=payload)
        
        # Verify payload exists
        stored_payload = clean_redis.get("job:1:payload")
        assert stored_payload is not None
        assert json.loads(stored_payload) == payload
        
        # Verify metadata exists
        metadata = clean_redis.hgetall("job:1:meta")
        assert b"attempts" in metadata
        assert metadata[b"attempts"] == b"0"
        assert b"created_at" in metadata
        assert b"last_claimed_at" in metadata
        
        # Verify status exists
        status = clean_redis.get("job:1:status")
        assert status == JobStatus.QUEUED.encode()
    
    def test_enqueue_adds_to_pending_queue(self, queue_service, clean_redis):
        """Verify enqueue adds run_id to pending queue."""
        payload = {"formula": "test"}
        
        queue_service.enqueue(run_id=42, payload=payload)
        
        # Check pending queue
        pending = clean_redis.lrange("q:pending", 0, -1)
        assert b"42" in pending
    
    def test_enqueue_multiple_jobs(self, queue_service, clean_redis):
        """Verify multiple jobs can be enqueued."""
        for i in range(5):
            payload = {"formula": f"formula_{i}"}
            queue_service.enqueue(run_id=i, payload=payload)
        
        # Verify all in pending queue
        pending = clean_redis.lrange("q:pending", 0, -1)
        assert len(pending) == 5
        
        # Verify all have payloads
        for i in range(5):
            stored = clean_redis.get(f"job:{i}:payload")
            assert stored is not None
    
    def test_enqueue_ttl_is_respected(self, clean_redis):
        """Verify TTL is set correctly on keys."""
        service = QueueService(clean_redis, job_ttl=10)
        payload = {"formula": "test"}
        
        service.enqueue(run_id=1, payload=payload)
        
        # Check TTL on payload
        ttl = clean_redis.ttl("job:1:payload")
        assert ttl > 0 and ttl <= 10
        
        # Check TTL on status
        ttl = clean_redis.ttl("job:1:status")
        assert ttl > 0 and ttl <= 10
    
    def test_enqueue_different_run_ids_separate_keys(self, queue_service, clean_redis):
        """Verify different run_ids create separate keys."""
        payload1 = {"formula": "a b &&"}
        payload2 = {"formula": "c d ||"}
        
        queue_service.enqueue(run_id=1, payload=payload1)
        queue_service.enqueue(run_id=2, payload=payload2)
        
        # Verify separate payloads
        stored1 = json.loads(clean_redis.get("job:1:payload"))
        stored2 = json.loads(clean_redis.get("job:2:payload"))
        
        assert stored1 == payload1
        assert stored2 == payload2
        assert stored1 != stored2
    
    def test_enqueue_complex_nested_payload(self, queue_service, clean_redis):
        """Verify complex nested JSON payloads are correctly serialized."""
        payload = {
            "formula": "complex",
            "metadata": {
                "nested": {
                    "deep": {
                        "value": 123,
                        "list": [1, 2, 3]
                    }
                }
            },
            "timeout_s": 10
        }
        
        queue_service.enqueue(run_id=99, payload=payload)
        
        stored = json.loads(clean_redis.get("job:99:payload"))
        assert stored == payload
        assert stored["metadata"]["nested"]["deep"]["value"] == 123


class TestClaimIntegration:
    """Integration tests for claim operation with real Redis."""
    
    def test_claim_moves_job_from_pending_to_processing(self, queue_service, clean_redis):
        """Verify claim moves job from pending to processing queue."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        
        # Verify in pending
        pending = clean_redis.lrange("q:pending", 0, -1)
        assert b"1" in pending
        assert b"1" not in clean_redis.lrange("q:processing", 0, -1)
        
        # Claim job
        result = queue_service.claim(timeout_s=0.1)
        
        # Verify moved to processing
        pending = clean_redis.lrange("q:pending", 0, -1)
        processing = clean_redis.lrange("q:processing", 0, -1)
        assert b"1" not in pending
        assert b"1" in processing
    
    def test_claim_returns_correct_payload(self, queue_service, clean_redis):
        """Verify claim returns the correct payload."""
        payload = {"formula": "a b &&", "run_id": 5}
        queue_service.enqueue(run_id=5, payload=payload)
        
        result = queue_service.claim(timeout_s=0.1)
        
        assert result is not None
        run_id, claimed_payload = result
        assert run_id == 5
        assert claimed_payload == payload
    
    def test_claim_returns_none_on_empty_queue(self, queue_service):
        """Verify claim returns None when queue is empty."""
        result = queue_service.claim(timeout_s=0.1)
        assert result is None
    
    def test_claim_increments_attempts(self, queue_service, clean_redis):
        """Verify claim increments attempt counter."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        
        # Initial attempts should be 0
        attempts = clean_redis.hget("job:1:meta", "attempts")
        assert int(attempts) == 0
        
        # Claim once
        queue_service.claim(timeout_s=0.1)
        attempts = clean_redis.hget("job:1:meta", "attempts")
        assert int(attempts) == 1
        
        # Claim again (requeue, move back to pending manually for testing)
        clean_redis.rpush("q:pending", 1)
        queue_service.claim(timeout_s=0.1)
        attempts = clean_redis.hget("job:1:meta", "attempts")
        assert int(attempts) == 2
    
    def test_claim_updates_last_claimed_at(self, queue_service, clean_redis):
        """Verify claim updates last_claimed_at timestamp."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        
        before = int(time.time())
        queue_service.claim(timeout_s=0.1)
        after = int(time.time())
        
        last_claimed = int(clean_redis.hget("job:1:meta", "last_claimed_at"))
        assert before <= last_claimed <= after
    
    def test_claim_returns_none_on_missing_payload(self, queue_service, clean_redis):
        """Verify claim returns None if payload is missing from Redis."""
        # Manually create queue entry without payload
        clean_redis.rpush("q:pending", 1)
        
        result = queue_service.claim(timeout_s=0.1)
        
        assert result is None
        # Job should be removed from processing
        processing = clean_redis.lrange("q:processing", 0, -1)
        assert b"1" not in processing
    
    def test_claim_returns_none_on_corrupted_json(self, queue_service, clean_redis):
        """Verify claim returns None if payload JSON is corrupted."""
        # Manually create corrupted payload
        clean_redis.set("job:1:payload", "invalid json {")
        clean_redis.rpush("q:pending", 1)
        
        result = queue_service.claim(timeout_s=0.1)
        
        assert result is None
        # Job should be removed from processing
        processing = clean_redis.lrange("q:processing", 0, -1)
        assert b"1" not in processing
    
    def test_claim_lifo_order(self, queue_service, clean_redis):
        """Verify jobs are claimed in LIFO order (rpush + brpoplpush = LIFO)."""
        # Enqueue multiple jobs
        for i in range(1, 6):
            queue_service.enqueue(run_id=i, payload={"formula": f"test_{i}"})
        
        # Verify they're all in pending queue
        pending = clean_redis.lrange("q:pending", 0, -1)
        assert len(pending) == 5
        
        # Claim them all and verify LIFO order (Last enqueued claimed first)
        claimed = []
        for i in range(5):
            result = queue_service.claim(timeout_s=0.1)
            assert result is not None, f"Expected claim {i+1} to succeed"
            run_id, _ = result
            claimed.append(run_id)
        
        # RPUSH + BRPOPLPUSH gives LIFO: last enqueued (5) is claimed first
        assert claimed == [5, 4, 3, 2, 1]


class TestAckIntegration:
    """Integration tests for ack operation with real Redis."""
    
    def test_ack_removes_from_processing_queue(self, queue_service, clean_redis):
        """Verify ack removes job from processing queue."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        queue_service.claim(timeout_s=0.1)
        
        # Verify in processing
        assert b"1" in clean_redis.lrange("q:processing", 0, -1)
        
        # Ack
        queue_service.ack(run_id=1)
        
        # Verify removed from processing
        assert b"1" not in clean_redis.lrange("q:processing", 0, -1)
    
    def test_ack_deletes_payload(self, queue_service, clean_redis):
        """Verify ack deletes the job payload."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        queue_service.claim(timeout_s=0.1)
        
        # Verify payload exists
        assert clean_redis.exists("job:1:payload")
        
        # Ack
        queue_service.ack(run_id=1)
        
        # Verify payload is deleted
        assert not clean_redis.exists("job:1:payload")
    
    def test_ack_deletes_metadata(self, queue_service, clean_redis):
        """Verify ack deletes the job metadata."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        queue_service.claim(timeout_s=0.1)
        
        # Verify metadata exists
        assert clean_redis.exists("job:1:meta")
        
        # Ack
        queue_service.ack(run_id=1)
        
        # Verify metadata is deleted
        assert not clean_redis.exists("job:1:meta")
    
    def test_ack_multiple_jobs(self, queue_service, clean_redis):
        """Verify acking multiple jobs."""
        for i in range(1, 4):
            queue_service.enqueue(run_id=i, payload={"formula": f"test_{i}"})
            queue_service.claim(timeout_s=0.1)
        
        # Verify all in processing
        processing = clean_redis.lrange("q:processing", 0, -1)
        assert len(processing) == 3
        
        # Ack all
        for i in range(1, 4):
            queue_service.ack(run_id=i)
        
        # Verify processing queue is empty
        processing = clean_redis.lrange("q:processing", 0, -1)
        assert len(processing) == 0
    
    def test_ack_idempotent(self, queue_service, clean_redis):
        """Verify acking same job multiple times is safe."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        queue_service.claim(timeout_s=0.1)
        
        # Ack twice
        queue_service.ack(run_id=1)
        queue_service.ack(run_id=1)  # Should not raise
        
        # Should be clean
        assert not clean_redis.exists("job:1:payload")
        assert not clean_redis.exists("job:1:meta")


class TestFailIntegration:
    """Integration tests for fail operation with real Redis."""
    
    def test_fail_removes_from_processing_queue(self, queue_service, clean_redis):
        """Verify fail removes job from processing queue."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        queue_service.claim(timeout_s=0.1)
        
        # Verify in processing
        assert b"1" in clean_redis.lrange("q:processing", 0, -1)
        
        # Fail
        queue_service.fail(run_id=1, reason="Test failure")
        
        # Verify removed
        assert b"1" not in clean_redis.lrange("q:processing", 0, -1)
    
    def test_fail_records_error_metadata(self, queue_service, clean_redis):
        """Verify fail records error reason and timestamp."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        queue_service.claim(timeout_s=0.1)
        
        before = int(time.time())
        queue_service.fail(run_id=1, reason="Solver crashed")
        after = int(time.time())
        
        # Verify metadata
        metadata = clean_redis.hgetall("job:1:meta")
        assert metadata[b"last_error"] == b"Solver crashed"
        failed_at = int(metadata[b"failed_at"])
        assert before <= failed_at <= after
    
    def test_fail_keeps_payload_and_metadata(self, queue_service, clean_redis):
        """Verify fail keeps payload and metadata for investigation."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        queue_service.claim(timeout_s=0.1)
        
        # Fail
        queue_service.fail(run_id=1, reason="Error")
        
        # Payload and metadata should still exist
        assert clean_redis.exists("job:1:payload")
        assert clean_redis.exists("job:1:meta")
    
    def test_fail_multiple_jobs(self, queue_service, clean_redis):
        """Verify failing multiple jobs."""
        for i in range(1, 4):
            queue_service.enqueue(run_id=i, payload={"formula": f"test_{i}"})
            queue_service.claim(timeout_s=0.1)
        
        # Fail all
        for i in range(1, 4):
            queue_service.fail(run_id=i, reason=f"Error {i}")
        
        # Verify all removed from processing
        processing = clean_redis.lrange("q:processing", 0, -1)
        assert len(processing) == 0
        
        # Verify all have error metadata
        for i in range(1, 4):
            error = clean_redis.hget(f"job:{i}:meta", "last_error")
            assert error == f"Error {i}".encode()
    
    def test_fail_different_reasons(self, queue_service, clean_redis):
        """Verify different failure reasons are recorded."""
        reasons = [
            "Timeout exceeded",
            "Memory exhausted",
            "Invalid formula",
            "Solver crashed"
        ]
        
        for i, reason in enumerate(reasons, 1):
            queue_service.enqueue(run_id=i, payload={"formula": "test"})
            queue_service.claim(timeout_s=0.1)
            queue_service.fail(run_id=i, reason=reason)
        
        # Verify each has correct reason
        for i, reason in enumerate(reasons, 1):
            stored_reason = clean_redis.hget(f"job:{i}:meta", "last_error").decode()
            assert stored_reason == reason


class TestWorkflowIntegration:
    """End-to-end workflow tests with real Redis."""
    
    def test_enqueue_claim_ack_workflow(self, queue_service, clean_redis):
        """Test complete happy path: enqueue -> claim -> ack."""
        # Enqueue
        payload = {"formula": "a b &&", "run_id": 1}
        queue_service.enqueue(run_id=1, payload=payload)
        
        pending = clean_redis.lrange("q:pending", 0, -1)
        assert b"1" in pending
        
        # Claim
        result = queue_service.claim(timeout_s=0.1)
        assert result is not None
        run_id, claimed_payload = result
        assert run_id == 1
        assert claimed_payload == payload
        
        # Verify in processing
        processing = clean_redis.lrange("q:processing", 0, -1)
        assert b"1" in processing
        
        # Ack
        queue_service.ack(run_id=1)
        
        # Verify cleaned up
        assert not clean_redis.exists("job:1:payload")
        assert not clean_redis.exists("job:1:meta")
        assert b"1" not in clean_redis.lrange("q:processing", 0, -1)
    
    def test_enqueue_claim_fail_workflow(self, queue_service, clean_redis):
        """Test failure path: enqueue -> claim -> fail."""
        # Enqueue
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        
        # Claim
        result = queue_service.claim(timeout_s=0.1)
        assert result is not None
        
        # Fail
        queue_service.fail(run_id=1, reason="Processing failed")
        
        # Verify in failed state
        assert clean_redis.exists("job:1:payload")
        metadata = clean_redis.hgetall("job:1:meta")
        assert metadata[b"last_error"] == b"Processing failed"
        assert b"1" not in clean_redis.lrange("q:processing", 0, -1)
    
    def test_multiple_jobs_concurrent_workflow(self, queue_service, clean_redis):
        """Test multiple jobs in different states simultaneously."""
        # Enqueue 5 jobs
        for i in range(1, 6):
            queue_service.enqueue(run_id=i, payload={"formula": f"test_{i}"})
        
        # Claim 3 jobs
        claimed = []
        for _ in range(3):
            result = queue_service.claim(timeout_s=0.1)
            if result:
                claimed.append(result[0])
        
        # Ack first one
        queue_service.ack(run_id=claimed[0])
        
        # Fail second one
        queue_service.fail(run_id=claimed[1], reason="Error")
        
        # Leave third one in processing
        
        # Verify states
        pending = clean_redis.lrange("q:pending", 0, -1)
        processing = clean_redis.lrange("q:processing", 0, -1)
        
        # 2 jobs still pending (weren't claimed)
        assert len(pending) == 2
        
        # 1 job still processing (claimed but not acked)
        assert len(processing) == 1
    
    def test_rapid_enqueue_claim_cycles(self, queue_service, clean_redis):
        """Test rapid cycles of enqueue and claim."""
        # Rapidly enqueue and claim
        for i in range(1, 21):
            queue_service.enqueue(run_id=i, payload={"formula": f"test_{i}"})
            result = queue_service.claim(timeout_s=0.1)
            assert result is not None
            queue_service.ack(run_id=i)
        
        # Verify clean state
        assert clean_redis.llen("q:pending") == 0
        assert clean_redis.llen("q:processing") == 0


class TestRedisStateConsistency:
    """Tests verifying Redis state consistency and atomicity."""
    
    def test_enqueue_atomic_operations(self, queue_service, clean_redis):
        """Verify all enqueue operations complete atomically."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=100, payload=payload)
        
        # All keys should exist together
        assert clean_redis.exists("job:100:payload")
        assert clean_redis.exists("job:100:meta")
        assert clean_redis.exists("job:100:status")
        
        # Queue should have the ID
        pending = clean_redis.lrange("q:pending", 0, -1)
        assert b"100" in pending
    
    def test_claim_updates_metadata_atomically(self, queue_service, clean_redis):
        """Verify claim metadata updates are atomic."""
        payload = {"formula": "test"}
        queue_service.enqueue(run_id=1, payload=payload)
        
        # Claim multiple times, verify consistency
        for _ in range(3):
            queue_service.claim(timeout_s=0.1)
            metadata = clean_redis.hgetall("job:1:meta")
            
            # All expected fields should exist
            assert b"attempts" in metadata
            assert b"created_at" in metadata
            assert b"last_claimed_at" in metadata
            
            # Re-add to queue for next claim
            clean_redis.rpush("q:pending", 1)
    
    def test_no_data_loss_on_operations(self, queue_service, clean_redis):
        """Verify no data loss during queue operations."""
        payloads = {}
        for i in range(1, 6):
            payload = {"formula": f"complex_{i}", "data": list(range(100))}
            payloads[i] = payload
            queue_service.enqueue(run_id=i, payload=payload)
        
        # Claim all, verify data intact
        for _ in range(5):
            result = queue_service.claim(timeout_s=0.1)
            if result:
                run_id, claimed = result
                assert claimed == payloads[run_id]
                queue_service.ack(run_id=run_id)


class TestErrorRecovery:
    """Tests for error handling and recovery."""
    
    def test_recover_from_missing_payload(self, queue_service, clean_redis):
        """Verify service recovers from missing payload."""
        # Manually create broken job
        clean_redis.hset("job:1:meta", mapping={"attempts": 0})
        clean_redis.rpush("q:pending", 1)
        
        # Claim should handle gracefully
        result = queue_service.claim(timeout_s=0.1)
        assert result is None
        
        # Queue should be clean
        assert b"1" not in clean_redis.lrange("q:processing", 0, -1)
    
    def test_recover_from_corrupted_payload(self, queue_service, clean_redis):
        """Verify service recovers from corrupted JSON."""
        # Manually create corrupted job
        clean_redis.set("job:1:payload", "{{invalid")
        clean_redis.hset("job:1:meta", mapping={"attempts": 0})
        clean_redis.rpush("q:pending", 1)
        
        # Claim should handle gracefully
        result = queue_service.claim(timeout_s=0.1)
        assert result is None
        
        # Queue should be clean
        assert b"1" not in clean_redis.lrange("q:processing", 0, -1)
    
    def test_large_payload_handling(self, queue_service, clean_redis):
        """Verify service handles large payloads."""
        large_payload = {
            "formula": "x" * 10000,
            "data": list(range(1000))
        }
        
        queue_service.enqueue(run_id=1, payload=large_payload)
        result = queue_service.claim(timeout_s=0.1)
        
        assert result is not None
        _, claimed = result
        assert claimed == large_payload
