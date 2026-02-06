# ABOUTME: Additional tests for flexible authentication and session creation
# ABOUTME: Tests for the consolidated /api/jobs endpoint

import pytest
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from database import Database


@pytest.fixture
def client(test_db, monkeypatch):
    """Flask test client with test database"""
    import app as app_module

    # Replace app's db with test_db
    monkeypatch.setattr(app_module, 'db', test_db)
    
    # Disable API token authentication by default (tests can override)
    monkeypatch.setattr(app_module, 'API_AUTH_TOKEN', None)

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestFlexibleAuthentication:
    """Tests for flexible authentication (OAuth OR API token)"""

    def test_create_job_without_auth_when_no_token_configured(self, client, test_db, monkeypatch):
        """Test that job creation works without auth when API_AUTH_TOKEN not configured"""
        import app as app_module
        monkeypatch.setattr(app_module, 'API_AUTH_TOKEN', None)

        response = client.post('/api/jobs',
            data=json.dumps({'type': 'test_screening', 'params': {}}),
            content_type='application/json')

        assert response.status_code == 200

    def test_create_job_with_oauth_session(self, client, test_db, monkeypatch):
        """Test that job creation works with OAuth session"""
        import app as app_module
        monkeypatch.setattr(app_module, 'API_AUTH_TOKEN', 'test-token')

        # Simulate OAuth session
        with client.session_transaction() as sess:
            sess['user_id'] = 123

        response = client.post('/api/jobs',
            data=json.dumps({'type': 'test_screening', 'params': {}}),
            content_type='application/json')

        assert response.status_code == 200

    def test_create_job_with_api_token(self, client, test_db, monkeypatch):
        """Test that job creation works with API token"""
        import app as app_module
        monkeypatch.setattr(app_module, 'API_AUTH_TOKEN', 'test-token')

        response = client.post('/api/jobs',
            data=json.dumps({'type': 'test_screening', 'params': {}}),
            content_type='application/json',
            headers={'Authorization': 'Bearer test-token'})

        assert response.status_code == 200

    def test_create_job_fails_without_auth_when_token_configured(self, client, test_db, monkeypatch):
        """Test that job creation fails without auth when API_AUTH_TOKEN is configured"""
        import app as app_module
        monkeypatch.setattr(app_module, 'API_AUTH_TOKEN', 'test-token')
        monkeypatch.setattr(app_module, 'DEV_AUTH_BYPASS', False)

        response = client.post('/api/jobs',
            data=json.dumps({'type': 'test_screening', 'params': {}}),
            content_type='application/json')

        assert response.status_code == 401


class TestJobCreation:
    """Tests for job creation via /api/jobs endpoint"""

    def test_create_screening_job(self, client, test_db):
        """Test that screening job returns job_id"""
        response = client.post('/api/jobs',
            data=json.dumps({
                'type': 'full_screening',
                'params': {'algorithm': 'weighted'}
            }),
            content_type='application/json')

        assert response.status_code == 200
        data = response.get_json()
        assert 'job_id' in data

    def test_create_non_screening_job(self, client, test_db):
        """Test that non-screening jobs return job_id"""
        response = client.post('/api/jobs',
            data=json.dumps({
                'type': 'sec_refresh',
                'params': {}
            }),
            content_type='application/json')

        assert response.status_code == 200
        data = response.get_json()
        assert 'job_id' in data
