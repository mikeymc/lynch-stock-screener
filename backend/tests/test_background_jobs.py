# ABOUTME: Tests for background job queue functionality
# ABOUTME: Validates job creation, claiming, progress updates, and status management

import pytest
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Database


# Module-level database instance to avoid connection pool exhaustion
_db_instance = None


@pytest.fixture
def db():
    """Get shared database connection for testing"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=int(os.environ.get('DB_PORT', 5432)),
            database=os.environ.get('DB_NAME', 'lynch_stocks'),
            user=os.environ.get('DB_USER', 'lynch'),
            password=os.environ.get('DB_PASSWORD', 'lynch_dev_password')
        )

    # Clean up any test jobs before each test
    conn = _db_instance.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM background_jobs WHERE job_type LIKE 'test_%'")
    conn.commit()
    _db_instance.return_connection(conn)

    yield _db_instance

    # Cleanup after test
    conn = _db_instance.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM background_jobs WHERE job_type LIKE 'test_%'")
    conn.commit()
    _db_instance.return_connection(conn)


class TestBackgroundJobsTable:
    """Tests for background_jobs table schema"""

    def test_background_jobs_table_exists(self, db):
        """Test that background_jobs table is created"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'background_jobs'
            )
        """)
        exists = cursor.fetchone()[0]
        db.return_connection(conn)
        assert exists is True


class TestJobCreation:
    """Tests for creating background jobs"""

    def test_create_job_returns_id(self, db):
        """Test that creating a job returns an integer ID"""
        job_id = db.create_background_job('test_screening', {'algorithm': 'weighted'})
        assert job_id is not None
        assert isinstance(job_id, int)

    def test_create_job_stores_params(self, db):
        """Test that job params are stored correctly"""
        params = {'algorithm': 'weighted', 'session_id': 123}
        job_id = db.create_background_job('test_screening', params)

        job = db.get_background_job(job_id)
        assert job['params'] == params

    def test_create_job_initial_status_is_pending(self, db):
        """Test that new jobs have status 'pending'"""
        job_id = db.create_background_job('test_screening', {})

        job = db.get_background_job(job_id)
        assert job['status'] == 'pending'

    def test_create_job_has_created_at_timestamp(self, db):
        """Test that job has created_at timestamp"""
        job_id = db.create_background_job('test_screening', {})

        job = db.get_background_job(job_id)
        assert job['created_at'] is not None
        assert isinstance(job['created_at'], datetime)


class TestJobClaiming:
    """Tests for atomic job claiming"""

    def test_claim_job_returns_job(self, db):
        """Test that claiming a pending job returns the job"""
        job_id = db.create_background_job('test_screening', {'test': True})

        claimed = db.claim_pending_job('worker-1')
        assert claimed is not None
        assert claimed['id'] == job_id
        assert claimed['status'] == 'claimed'

    def test_claim_job_sets_claimed_by(self, db):
        """Test that claiming sets the claimed_by field"""
        db.create_background_job('test_screening', {})

        claimed = db.claim_pending_job('worker-123')
        assert claimed['claimed_by'] == 'worker-123'

    def test_claim_job_sets_claimed_at(self, db):
        """Test that claiming sets the claimed_at timestamp"""
        db.create_background_job('test_screening', {})

        claimed = db.claim_pending_job('worker-1')

        assert claimed['claimed_at'] is not None
        assert isinstance(claimed['claimed_at'], datetime)

    def test_claim_job_sets_expiry(self, db):
        """Test that claiming sets claim_expires_at"""
        db.create_background_job('test_screening', {})

        claimed = db.claim_pending_job('worker-1')
        assert claimed['claim_expires_at'] is not None
        # Default 10 minute expiry
        assert claimed['claim_expires_at'] > claimed['claimed_at']

    def test_claim_returns_none_when_no_pending_jobs(self, db):
        """Test that claiming returns None when no pending jobs"""
        claimed = db.claim_pending_job('worker-1')
        assert claimed is None

    def test_claim_is_atomic(self, db):
        """Test that only one worker can claim a job"""
        db.create_background_job('test_screening', {})

        claimed1 = db.claim_pending_job('worker-1')
        claimed2 = db.claim_pending_job('worker-2')

        assert claimed1 is not None
        assert claimed2 is None  # Second claim should fail


class TestJobProgress:
    """Tests for job progress updates"""

    def test_update_job_progress(self, db):
        """Test updating job progress percentage"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')

        db.update_job_progress(job_id, progress_pct=50, progress_message='Processing...')

        job = db.get_background_job(job_id)
        assert job['progress_pct'] == 50
        assert job['progress_message'] == 'Processing...'

    def test_update_job_progress_counts(self, db):
        """Test updating processed/total counts"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')

        db.update_job_progress(job_id, processed_count=100, total_count=1000)

        job = db.get_background_job(job_id)
        assert job['processed_count'] == 100
        assert job['total_count'] == 1000

    def test_update_job_status_to_running(self, db):
        """Test updating job status to running"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')

        db.update_job_status(job_id, 'running')

        job = db.get_background_job(job_id)
        assert job['status'] == 'running'


class TestJobCompletion:
    """Tests for completing and failing jobs"""

    def test_complete_job(self, db):
        """Test marking a job as completed"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')

        result = {'pass_count': 10, 'fail_count': 90}
        db.complete_job(job_id, result)

        job = db.get_background_job(job_id)
        assert job['status'] == 'completed'
        assert job['result'] == result
        assert job['completed_at'] is not None

    def test_fail_job(self, db):
        """Test marking a job as failed"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')

        db.fail_job(job_id, 'Connection timeout')

        job = db.get_background_job(job_id)
        assert job['status'] == 'failed'
        assert job['error_message'] == 'Connection timeout'

    def test_cancel_job(self, db):
        """Test cancelling a job"""
        job_id = db.create_background_job('test_screening', {})

        db.cancel_job(job_id)

        job = db.get_background_job(job_id)
        assert job['status'] == 'cancelled'


class TestJobHeartbeat:
    """Tests for worker heartbeat/claim extension"""

    def test_extend_job_claim(self, db):
        """Test extending a job's claim expiry"""
        job_id = db.create_background_job('test_screening', {})
        claimed = db.claim_pending_job('worker-1')
        original_expiry = claimed['claim_expires_at']

        # Small delay to ensure time difference
        time.sleep(0.1)

        db.extend_job_claim(job_id, minutes=10)

        job = db.get_background_job(job_id)
        assert job['claim_expires_at'] > original_expiry


class TestJobRetrieval:
    """Tests for retrieving job information"""

    def test_get_job_by_id(self, db):
        """Test retrieving a job by ID"""
        job_id = db.create_background_job('test_screening', {'key': 'value'})

        job = db.get_background_job(job_id)

        assert job is not None
        assert job['id'] == job_id
        assert job['job_type'] == 'test_screening'
        assert job['params'] == {'key': 'value'}

    def test_get_nonexistent_job_returns_none(self, db):
        """Test that getting a nonexistent job returns None"""
        job = db.get_background_job(99999)
        assert job is None

    def test_get_pending_jobs_count(self, db):
        """Test counting pending jobs"""
        db.create_background_job('test_screening', {})
        db.create_background_job('test_screening', {})
        db.create_background_job('test_sec_refresh', {})

        count = db.get_pending_jobs_count()
        assert count >= 3


class TestJobRelease:
    """Tests for releasing claimed jobs"""

    def test_release_job(self, db):
        """Test releasing a claimed job back to pending"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')

        db.release_job(job_id)

        job = db.get_background_job(job_id)
        assert job['status'] == 'pending'
        assert job['claimed_by'] is None
        assert job['claimed_at'] is None
