# ABOUTME: Tests for briefings API endpoints
# ABOUTME: Validates GET /api/portfolios/<id>/briefings and GET /api/briefings/<id>

import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def authenticated_client(test_client):
    """Test client with mocked authentication."""
    with test_client.session_transaction() as sess:
        sess['user_id'] = 1
    return test_client


@pytest.fixture
def seed_briefing_data(authenticated_client):
    """Seed the database with briefing test data via the app's db."""
    from app import db

    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (id, email, name, google_id)
        VALUES (1, 'test@test.com', 'Test User', 'g1')
        ON CONFLICT (id) DO NOTHING
    """)
    cursor.execute("""
        INSERT INTO portfolios (id, user_id, name, initial_cash)
        VALUES (1, 1, 'Test Portfolio', 100000.0)
        ON CONFLICT (id) DO NOTHING
    """)
    cursor.execute("""
        INSERT INTO investment_strategies (id, user_id, portfolio_id, name, conditions)
        VALUES (1, 1, 1, 'Test Strategy', '{}')
        ON CONFLICT (id) DO NOTHING
    """)
    cursor.execute("""
        INSERT INTO strategy_runs (id, strategy_id, status)
        VALUES (1, 1, 'completed')
        ON CONFLICT (id) DO NOTHING
    """)
    cursor.execute("""
        INSERT INTO strategy_briefings
        (id, run_id, strategy_id, portfolio_id, stocks_screened, stocks_scored,
         theses_generated, trades_executed, portfolio_value, portfolio_return_pct,
         spy_return_pct, alpha, buys_json, sells_json, holds_json, watchlist_json,
         executive_summary, generated_at)
        VALUES (1, 1, 1, 1, 500, 25, 10, 3, 102500.0, 2.5, 1.2, 1.3,
                '[]', '[]', '[]', '[]', 'Test summary.', NOW())
        ON CONFLICT (run_id) DO NOTHING
    """)

    conn.commit()
    db.return_connection(conn)

    return authenticated_client


def test_get_portfolio_briefings(seed_briefing_data):
    """Test GET /api/portfolios/<id>/briefings returns briefings."""
    client = seed_briefing_data
    response = client.get('/api/portfolios/1/briefings')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]['stocks_screened'] == 500
    assert data[0]['executive_summary'] == 'Test summary.'


def test_get_portfolio_briefings_empty(authenticated_client):
    """Test GET /api/portfolios/<id>/briefings returns empty list for no briefings."""
    response = authenticated_client.get('/api/portfolios/999/briefings')
    assert response.status_code == 200
    data = response.get_json()
    assert data == []


def test_get_single_briefing(seed_briefing_data):
    """Test GET /api/briefings/<id> returns a single briefing."""
    client = seed_briefing_data
    response = client.get('/api/briefings/1')
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == 1
    assert data['executive_summary'] == 'Test summary.'


def test_get_single_briefing_not_found(authenticated_client):
    """Test GET /api/briefings/<id> returns 404 for non-existent briefing."""
    response = authenticated_client.get('/api/briefings/999')
    assert response.status_code == 404
