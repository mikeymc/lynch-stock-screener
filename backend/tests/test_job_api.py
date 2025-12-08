# ABOUTME: Tests for background job API endpoints
# ABOUTME: Validates job creation, status retrieval, and cancellation endpoints

import pytest
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
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


@pytest.fixture
def client():
    """Flask test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestCreateJobEndpoint:
    """Tests for POST /api/jobs endpoint"""

    def test_create_job_returns_job_id(self, client, db):
        """Test that creating a job returns a job ID"""
        response = client.post('/api/jobs',
            data=json.dumps({'type': 'test_screening', 'params': {}}),
            content_type='application/json')

        assert response.status_code == 200
        data = response.get_json()
        assert 'job_id' in data
        assert isinstance(data['job_id'], int)

    def test_create_job_returns_pending_status(self, client, db):
        """Test that new job has pending status"""
        response = client.post('/api/jobs',
            data=json.dumps({'type': 'test_screening', 'params': {}}),
            content_type='application/json')

        data = response.get_json()
        assert data['status'] == 'pending'

    def test_create_job_stores_params(self, client, db):
        """Test that job params are stored correctly"""
        params = {'algorithm': 'weighted', 'session_id': 123}
        response = client.post('/api/jobs',
            data=json.dumps({'type': 'test_screening', 'params': params}),
            content_type='application/json')

        job_id = response.get_json()['job_id']

        # Verify params in database
        job = db.get_background_job(job_id)
        assert job['params'] == params

    def test_create_job_requires_type(self, client, db):
        """Test that job type is required"""
        response = client.post('/api/jobs',
            data=json.dumps({'params': {}}),
            content_type='application/json')

        assert response.status_code == 400

    def test_create_job_accepts_empty_params(self, client, db):
        """Test that empty params are allowed"""
        response = client.post('/api/jobs',
            data=json.dumps({'type': 'test_screening'}),
            content_type='application/json')

        assert response.status_code == 200
        job_id = response.get_json()['job_id']

        job = db.get_background_job(job_id)
        assert job['params'] == {}


class TestGetJobEndpoint:
    """Tests for GET /api/jobs/<id> endpoint"""

    def test_get_job_returns_job_data(self, client, db):
        """Test that getting a job returns its data"""
        job_id = db.create_background_job('test_screening', {'test': True})

        response = client.get(f'/api/jobs/{job_id}')

        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == job_id
        assert data['job_type'] == 'test_screening'
        assert data['params'] == {'test': True}

    def test_get_job_returns_status(self, client, db):
        """Test that job status is returned"""
        job_id = db.create_background_job('test_screening', {})

        response = client.get(f'/api/jobs/{job_id}')

        data = response.get_json()
        assert data['status'] == 'pending'

    def test_get_job_returns_progress(self, client, db):
        """Test that job progress is returned"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')
        db.update_job_progress(job_id, progress_pct=50, progress_message='Halfway done')

        response = client.get(f'/api/jobs/{job_id}')

        data = response.get_json()
        assert data['progress_pct'] == 50
        assert data['progress_message'] == 'Halfway done'

    def test_get_nonexistent_job_returns_404(self, client, db):
        """Test that getting a nonexistent job returns 404"""
        response = client.get('/api/jobs/99999')

        assert response.status_code == 404

    def test_get_job_returns_result_when_complete(self, client, db):
        """Test that completed job includes result"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')
        result = {'pass_count': 10, 'fail_count': 90}
        db.complete_job(job_id, result)

        response = client.get(f'/api/jobs/{job_id}')

        data = response.get_json()
        assert data['status'] == 'completed'
        assert data['result'] == result


class TestCancelJobEndpoint:
    """Tests for POST /api/jobs/<id>/cancel endpoint"""

    def test_cancel_job_sets_cancelled_status(self, client, db):
        """Test that cancelling a job sets its status to cancelled"""
        job_id = db.create_background_job('test_screening', {})

        response = client.post(f'/api/jobs/{job_id}/cancel')

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'cancelled'

        # Verify in database
        job = db.get_background_job(job_id)
        assert job['status'] == 'cancelled'

    def test_cancel_nonexistent_job_returns_404(self, client, db):
        """Test that cancelling a nonexistent job returns 404"""
        response = client.post('/api/jobs/99999/cancel')

        assert response.status_code == 404

    def test_cancel_completed_job_still_works(self, client, db):
        """Test that cancelling a completed job still succeeds"""
        job_id = db.create_background_job('test_screening', {})
        db.claim_pending_job('worker-1')
        db.complete_job(job_id, {'result': 'done'})

        response = client.post(f'/api/jobs/{job_id}/cancel')

        # Should still work (idempotent operation)
        assert response.status_code == 200
