import pytest
import os
import sys
import json
from flask import session

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from database import Database

@pytest.fixture
def client(test_db, monkeypatch):
    """Flask test client with test database - same as test_job_api.py"""
    import app as app_module
    
    # Replace app's db with test_db
    monkeypatch.setattr(app_module.deps, 'db', test_db)
    monkeypatch.setattr(app_module.deps, 'API_AUTH_TOKEN', None)
    
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def admin_client(test_db, client):
    """Fixture to provide an authenticated admin client"""
    # Create a user
    user_id = test_db.create_user("google_id_123", "admin@example.com", "Admin User")
    
    # Manually promote to admin
    conn = test_db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET user_type = 'admin' WHERE id = %s", (user_id,))
        conn.commit()
    except Exception as e:
        print(f"Failed to set admin role: {e}")
        # Even if this fails, we want to try the test to see the 403 if it fails
    finally:
        test_db.return_connection(conn)
        
    # Login as this user
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        
    return client

class TestAdminJobFiltering:
    """Tests for filtering background jobs in admin dashboard"""

    def test_get_all_jobs(self, admin_client, test_db):
        """Test getting all jobs without filter"""
        # Create some mixed jobs
        test_db.create_background_job('type_A', {'id': 1})
        test_db.create_background_job('type_B', {'id': 2})
        test_db.create_background_job('type_A', {'id': 3})
        
        response = admin_client.get('/api/admin/background_jobs')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'jobs' in data
        # Should get all 3 (plus any others if db wasn't clean, but test_db fixture cleans)
        # Note: test_db fixture cleans 'test_%' jobs, but we created valid looking ones?
        # modify test_db fixture or use specific types. 
        # Actually test_db fixture cleans everything in tables_to_clear.
        
        jobs = data['jobs']
        assert len(jobs) >= 3
        
        types = set(j['job_type'] for j in jobs)
        assert 'type_A' in types
        assert 'type_B' in types

    def test_filter_by_job_type(self, admin_client, test_db):
        """Test filtering jobs by specific type"""
        test_db.create_background_job('type_A', {'id': 1})
        test_db.create_background_job('type_B', {'id': 2})
        test_db.create_background_job('type_A', {'id': 3})
        
        # Filter for type_A
        response = admin_client.get('/api/admin/background_jobs?job_type=type_A')
        assert response.status_code == 200
        
        data = response.get_json()
        jobs = data['jobs']
        
        assert len(jobs) == 2
        for job in jobs:
            assert job['job_type'] == 'type_A'

    def test_filter_by_nonexistent_type(self, admin_client, test_db):
        """Test filtering by a type that has no jobs"""
        test_db.create_background_job('type_A', {'id': 1})
        
        response = admin_client.get('/api/admin/background_jobs?job_type=non_existent')
        assert response.status_code == 200
        
        data = response.get_json()
        jobs = data['jobs']
        assert len(jobs) == 0

    def test_filter_sql_injection_prevention(self, admin_client, test_db):
        """Test that filter input is sanitized"""
        # This checks if the backend blindly puts the string in SQL
        response = admin_client.get("/api/admin/background_jobs?job_type=' OR '1'='1")
        assert response.status_code == 200
        
        data = response.get_json()
        jobs = data['jobs']
        # If injection worked, it might return all jobs. If properly parameterized, it looks for literal string.
        assert len(jobs) == 0
