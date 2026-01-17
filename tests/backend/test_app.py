# ABOUTME: Tests for Flask API endpoints including health check and stock data retrieval
# ABOUTME: Validates endpoint responses, status codes, and data format

import pytest
import os
import sys
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from database import Database


@pytest.fixture
def client(test_db, monkeypatch):
    """Flask test client with test database"""
    import app as app_module

    # Replace app's db with test_db
    monkeypatch.setattr(app_module, 'db', test_db)

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

# test_db fixture is now provided by conftest.py

def test_health_endpoint(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'





def test_stock_history_endpoint_handles_missing_stock(client):
    """Test that /api/stock/<symbol>/history returns 404 for non-existent stock"""
    response = client.get('/api/stock/INVALID/history')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data


def test_stock_history_endpoint_handles_negative_eps(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/history handles years with negative EPS by setting P/E to None"""
    import app as app_module

    symbol = "WOOF"
    test_db.save_stock_basic(symbol, "Petco", "NASDAQ", "Consumer")

    # Add earnings with one negative EPS year
    earnings_data = [
        (2020, 0.50, 5000000000, "2020-12-31"),
        (2021, -0.13, 5200000000, "2021-12-31"),  # Negative EPS
        (2022, 0.75, 5500000000, "2022-12-31")
    ]

    for year, eps, revenue, fiscal_end in earnings_data:
        test_db.save_earnings_history(symbol, year, eps, revenue, fiscal_end=fiscal_end)

    test_db.flush()  # Ensure data is committed

    # Mock weekly prices to return empty (will fallback to yfinance in app)
    mock_weekly_prices = {'dates': [], 'prices': []}
    original_get_weekly_prices = test_db.get_weekly_prices
    test_db.get_weekly_prices = MagicMock(return_value=mock_weekly_prices)

    try:
        response = client.get(f'/api/stock/{symbol}/history')

        assert response.status_code == 200
        data = json.loads(response.data)

        # Verify P/E ratio is None for negative EPS year (index 1)
        assert data['pe_ratio'][1] is None  # Negative EPS -> None P/E
    finally:
        # Restore original method
        test_db.get_weekly_prices = original_get_weekly_prices


def test_lynch_analysis_endpoint_returns_cached_analysis(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/lynch-analysis returns cached analysis when available"""
    import app as app_module
    from lynch_analyst import LynchAnalyst

    monkeypatch.setattr(app_module, 'lynch_analyst', LynchAnalyst(test_db))

    # Set up test data
    symbol = "AAPL"
    # Create a test user
    user_id = test_db.create_user("google_test", "test_cached_analysis@example.com", "Test User", None)
    test_db.save_stock_basic(symbol, "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_stock_metrics(symbol, {
        'price': 150.25,
        'pe_ratio': 25.5,
        'market_cap': 2500000000000,
        'debt_to_equity': 0.35,
        'institutional_ownership': 0.62,
        'revenue': 394000000000
    })
    test_db.save_earnings_history(symbol, 2023, 6.13, 383000000000)

    test_db.flush()  # Ensure stock exists before saving analysis

    # Save a cached analysis
    cached_analysis = "This is a cached Peter Lynch analysis of Apple. Strong fundamentals and growth trajectory."
    test_db.save_lynch_analysis(user_id, symbol, cached_analysis, "gemini-pro")

    test_db.flush()  # Ensure data is committed

    # Set session user_id for authentication
    with client.session_transaction() as sess:
        sess['user_id'] = user_id

    # Request analysis
    response = client.get(f'/api/stock/{symbol}/lynch-analysis')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['analysis'] == cached_analysis
    assert data['cached'] is True
    assert 'generated_at' in data


@patch('lynch_analyst.genai.Client')
def test_lynch_analysis_endpoint_generates_fresh_analysis(mock_client_class, client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/lynch-analysis generates fresh analysis when cache is empty"""
    import app as app_module
    from lynch_analyst import LynchAnalyst

    # Setup mock Gemini response FIRST
    mock_chunk = MagicMock()
    mock_chunk.text = "Fresh Peter Lynch analysis: Apple shows strong growth with a PEG ratio of 1.2, suggesting reasonable valuation."
    mock_response_iterator = [mock_chunk]
    
    mock_models = MagicMock()
    mock_models.generate_content_stream.return_value = mock_response_iterator
    
    mock_client = MagicMock()
    mock_client.models = mock_models
    mock_client_class.return_value = mock_client

    # NOW create LynchAnalyst with the mocked client
    monkeypatch.setattr(app_module, 'lynch_analyst', LynchAnalyst(test_db))

    # Set up test stock and earnings data
    symbol = "AAPL"
    test_db.save_stock_basic(symbol, "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_stock_metrics(symbol, {
        'price': 150.25,
        'pe_ratio': 25.5,
        'market_cap': 2500000000000,
        'debt_to_equity': 0.35,
        'institutional_ownership': 0.62,
        'revenue': 394000000000
    })
    test_db.save_earnings_history(symbol, 2023, 6.13, 383000000000)

    test_db.flush()  # Ensure data is committed

    # Create a test user for authentication
    user_id = test_db.create_user("google_test", "test_fresh_analysis@example.com", "Test User", None)

    # Set session user_id for authentication
    with client.session_transaction() as sess:
        sess['user_id'] = user_id

    # Request analysis
    response = client.get(f'/api/stock/{symbol}/lynch-analysis')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert "Fresh Peter Lynch analysis" in data['analysis']
    assert data['cached'] is False
    assert 'generated_at' in data


@patch('lynch_analyst.genai.Client')
def test_lynch_analysis_refresh_endpoint(mock_client_class, client, test_db, monkeypatch):
    """Test that POST /api/stock/<symbol>/lynch-analysis/refresh forces regeneration"""
    import app as app_module
    from lynch_analyst import LynchAnalyst

    # Setup mock Gemini response FIRST
    mock_chunk = MagicMock()
    mock_chunk.text = "Updated Peter Lynch analysis with latest data."
    mock_response_iterator = [mock_chunk]
    
    mock_models = MagicMock()
    mock_models.generate_content_stream.return_value = mock_response_iterator
    
    mock_client = MagicMock()
    mock_client.models = mock_models
    mock_client_class.return_value = mock_client

    # NOW create LynchAnalyst with the mocked client
    monkeypatch.setattr(app_module, 'lynch_analyst', LynchAnalyst(test_db))

    # Set up test stock and earnings data
    symbol = "AAPL"
    # Create a test user
    user_id = test_db.create_user("google_test", "test_refresh@example.com", "Test User", None)
    test_db.save_stock_basic(symbol, "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_stock_metrics(symbol, {
        'price': 150.25,
        'pe_ratio': 25.5,
        'market_cap': 2500000000000,
        'debt_to_equity': 0.35,
        'institutional_ownership': 0.62,
        'revenue': 394000000000
    })
    test_db.save_earnings_history(symbol, 2023, 6.13, 383000000000)

    test_db.flush()  # Ensure stock exists before saving analysis

    # Save old cached analysis
    test_db.save_lynch_analysis(user_id, symbol, "Old cached analysis", "gemini-pro")

    test_db.flush()  # Ensure data is committed

    # Set session user_id for authentication
    with client.session_transaction() as sess:
        sess['user_id'] = user_id

    # Request refresh
    response = client.post(
        f'/api/stock/{symbol}/lynch-analysis/refresh',
        data=json.dumps({'model': 'gemini-2.5-flash'}),
        content_type='application/json'
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert "Updated Peter Lynch analysis" in data['analysis']
    assert data['cached'] is False
    assert 'generated_at' in data

    # Verify the cache was updated
    cached = test_db.get_lynch_analysis(user_id, symbol)
    assert cached['analysis_text'].endswith("Updated Peter Lynch analysis with latest data.")


def test_lynch_analysis_endpoint_returns_404_for_unknown_stock(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/lynch-analysis returns 404 for unknown stock"""

    # Create a test user for authentication
    user_id = test_db.create_user("google_test", "test_unknown_stock@example.com", "Test User", None)

    # Set session user_id for authentication
    with client.session_transaction() as sess:
        sess['user_id'] = user_id

    response = client.get('/api/stock/UNKNOWN/lynch-analysis')

    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data


# Screening Sessions Tests

def test_get_latest_session_returns_most_recent_screening(client, test_db, monkeypatch):
    """Test that GET /api/sessions/latest returns the most recent screening session"""

    # Create a session with results
    session_id = test_db.create_session("test_algo", 100, total_analyzed=2, pass_count=1, close_count=0, fail_count=1)

    result1 = {
        'symbol': 'AAPL', 'company_name': 'Apple Inc.', 'country': 'US',
        'market_cap': 2500000000000, 'sector': 'Technology', 'ipo_year': 1980,
        'price': 150.25, 'pe_ratio': 25.5, 'peg_ratio': 1.2, 'debt_to_equity': 0.35,
        'institutional_ownership': 0.45, 'earnings_cagr': 15.5, 'revenue_cagr': 12.3,
        'consistency_score': 85.0, 'peg_status': 'PASS', 'debt_status': 'PASS',
        'institutional_ownership_status': 'PASS', 'overall_status': 'PASS'
    }
    test_db.save_screening_result(session_id, result1)

    result2 = {
        'symbol': 'MSFT', 'company_name': 'Microsoft Corp.', 'country': 'US',
        'market_cap': 2000000000000, 'sector': 'Technology', 'ipo_year': 1986,
        'price': 300.00, 'pe_ratio': 30.0, 'peg_ratio': 2.5, 'debt_to_equity': 0.40,
        'institutional_ownership': 0.70, 'earnings_cagr': 10.0, 'revenue_cagr': 8.0,
        'consistency_score': 75.0, 'peg_status': 'FAIL', 'debt_status': 'PASS',
        'institutional_ownership_status': 'FAIL', 'overall_status': 'FAIL'
    }
    test_db.save_screening_result(session_id, result2)

    test_db.flush()  # Ensure data is committed

    response = client.get('/api/sessions/latest')

    assert response.status_code == 200
    data = json.loads(response.data)

    assert 'session_id' in data
    assert 'created_at' in data
    assert data['total_analyzed'] == 2
    assert data['pass_count'] == 1
    assert data['close_count'] == 0
    assert data['fail_count'] == 1
    assert len(data['results']) == 2
    assert data['results'][0]['symbol'] in ['AAPL', 'MSFT']
    assert data['results'][1]['symbol'] in ['AAPL', 'MSFT']


def test_get_latest_session_returns_404_when_no_sessions(client, test_db, monkeypatch):
    """Test that GET /api/sessions/latest returns 404 when no sessions exist"""

    response = client.get('/api/sessions/latest')

    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data


# Economy Link Feature Flag Tests

def test_economy_link_feature_flag_exists_in_settings(client, test_db):
    """Test that feature_economy_link_enabled exists in settings"""
    response = client.get('/api/settings')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'feature_economy_link_enabled' in data
    assert 'value' in data['feature_economy_link_enabled']
    assert 'description' in data['feature_economy_link_enabled']


def test_economy_link_feature_flag_can_be_toggled(client, test_db):
    """Test that feature_economy_link_enabled can be toggled on and off"""
    # Set to True
    response = client.post(
        '/api/settings',
        data=json.dumps({
            'feature_economy_link_enabled': {
                'value': True,
                'description': 'Toggle Economy link visibility in navigation'
            }
        }),
        content_type='application/json'
    )
    assert response.status_code == 200

    # Verify it's True
    response = client.get('/api/settings')
    data = json.loads(response.data)
    assert data['feature_economy_link_enabled']['value'] is True

    # Set to False
    response = client.post(
        '/api/settings',
        data=json.dumps({
            'feature_economy_link_enabled': {
                'value': False,
                'description': 'Toggle Economy link visibility in navigation'
            }
        }),
        content_type='application/json'
    )
    assert response.status_code == 200

    # Verify it's False
    response = client.get('/api/settings')
    data = json.loads(response.data)
    assert data['feature_economy_link_enabled']['value'] is False


def test_fred_api_accessible_regardless_of_ui_flag(client, test_db, monkeypatch):
    """Test that FRED API endpoints remain accessible even when UI link is hidden"""
    import app as app_module

    # Disable the UI link
    test_db.set_setting('feature_economy_link_enabled', False)

    # Enable FRED feature (so API works)
    test_db.set_setting('feature_fred_enabled', True)

    # Mock FRED service
    mock_fred_service = MagicMock()
    mock_fred_service.is_available.return_value = True
    mock_fred_service.get_economic_summary.return_value = {
        'gdp': {'value': 25000, 'date': '2024-01-01'},
        'unemployment': {'value': 3.7, 'date': '2024-01-01'}
    }

    with patch('app.get_fred_service', return_value=mock_fred_service):
        # FRED API endpoint should still work
        response = client.get('/api/fred/summary')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'gdp' in data
        assert 'unemployment' in data
