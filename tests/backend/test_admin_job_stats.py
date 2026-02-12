
import pytest
import os
import sys
from datetime import datetime, timedelta

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

from app import app

@pytest.fixture
def client(test_db, monkeypatch):
    """Flask test client with test database"""
    import app as app_module
    monkeypatch.setattr(app_module.deps, 'db', test_db)
    
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def admin_client(test_db, client):
    """Authenticated admin client"""
    user_id = test_db.create_user("google_id_123", "admin@example.com", "Admin User")
    
    conn = test_db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET user_type = 'admin' WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        test_db.return_connection(conn)
        
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        
    return client

def test_get_job_stats(admin_client, test_db):
    """Test the /api/admin/job_stats endpoint"""
    # 1. Create a sample job
    test_db.create_background_job(
        job_type='test_job',
        params={'foo': 'bar'}
    )
    
    # Manually update it to running and then completed to have duration data
    conn = test_db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM background_jobs WHERE job_type = 'test_job' LIMIT 1")
        job_id = cursor.fetchone()[0]
        
        # Start the job
        test_db.claim_pending_job('test_worker')
        
        # Finish the job with a simulated duration
        test_db.update_job_progress(job_id, 100, "Done")
        cursor.execute("""
            UPDATE background_jobs 
            SET status = 'completed', 
                started_at = NOW() - INTERVAL '10 seconds',
                completed_at = NOW()
            WHERE id = %s
        """, (job_id,))
        conn.commit()
    finally:
        test_db.return_connection(conn)

    # 2. Call the endpoint
    response = admin_client.get('/api/admin/job_stats?hours=1')
    assert response.status_code == 200
    
    data = response.get_json()
    assert 'stats' in data
    assert 'jobs' in data
    assert 'time_range' in data
    
    # 3. Verify stats aggregation
    stats = data['stats']
    test_job_stats = next((s for s in stats if s['job_type'] == 'test_job'), None)
    assert test_job_stats is not None
    assert test_job_stats['total_runs'] >= 1
    assert test_job_stats['completed_runs'] >= 1
    assert test_job_stats['tier'] == 'light'
    assert test_job_stats['avg_duration_seconds'] is not None
    assert float(test_job_stats['avg_duration_seconds']) >= 9 # Roughly 10s
    
    # 4. Verify jobs list
    jobs = data['jobs']
    assert len(jobs) >= 1
    assert any(j['job_type'] == 'test_job' for j in jobs)
    
    # 5. Verify params are included
    test_job = next(j for j in jobs if j['job_type'] == 'test_job')
    assert 'params' in test_job
    assert test_job['params'] == {'foo': 'bar'}
