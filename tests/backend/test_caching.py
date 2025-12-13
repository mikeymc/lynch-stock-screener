# ABOUTME: Tests for chart analysis caching functionality
# ABOUTME: Validates that chart analysis results are cached and retrieved correctly

import pytest
import json
import time
from unittest.mock import patch, MagicMock

from app import app


@pytest.fixture
def client(test_db, monkeypatch):
    """Flask test client with test database"""
    import app as app_module

    # Replace app's db with test_db
    monkeypatch.setattr(app_module, 'db', test_db)

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_caching(client, test_db, monkeypatch):
    """Test that unified chart analysis caching works correctly"""
    import app as app_module
    from lynch_analyst import LynchAnalyst

    symbol = "AMZN"

    # Create a test user
    user_id = test_db.create_user("google_test", "test@example.com", "Test User", None)

    # Set up test stock data
    test_db.save_stock_basic(symbol, "Amazon.com Inc.", "NASDAQ", "Technology")
    test_db.save_stock_metrics(symbol, {
        'price': 150.00,
        'pe_ratio': 50.0,
        'market_cap': 1500000000000,
        'debt_to_equity': 0.5,
        'institutional_ownership': 0.65,
        'revenue': 500000000000
    })

    # Add earnings history for multiple years (needed for evaluation)
    for year in range(2019, 2024):
        test_db.save_earnings_history(symbol, year, 10.50 + year - 2019, 400000000000 + (year - 2019) * 20000000000)

    test_db.flush()

    # Mock the LynchAnalyst to return predictable responses
    mock_analyst = MagicMock()
    mock_analyst.generate_unified_chart_analysis.return_value = {
        'growth': 'Test growth analysis',
        'cash': 'Test cash analysis',
        'valuation': 'Test valuation analysis'
    }
    mock_analyst.model_version = "test-model"
    monkeypatch.setattr(app_module, 'lynch_analyst', mock_analyst)

    # Set session user_id
    with client.session_transaction() as sess:
        sess['user_id'] = user_id

    print(f"\n1. Generating unified analysis for {symbol} - Force Refresh...")
    start = time.time()
    resp = client.post(f'/api/stock/{symbol}/unified-chart-analysis',
                       data=json.dumps({
                           "force_refresh": True
                       }),
                       content_type='application/json')
    print(f"   Status: {resp.status_code}")
    data = json.loads(resp.data)
    print(f"   Cached: {data.get('cached')}")
    print(f"   Time: {time.time() - start:.2f}s")

    assert resp.status_code == 200
    assert 'sections' in data
    assert 'growth' in data['sections']
    assert 'cash' in data['sections']
    assert 'valuation' in data['sections']
    assert data.get('cached') is False  # First call should not be cached

    print("\n2. Fetching analysis again - Should be Cached...")
    start = time.time()
    resp = client.post(f'/api/stock/{symbol}/unified-chart-analysis',
                       data=json.dumps({
                           "force_refresh": False
                       }),
                       content_type='application/json')
    print(f"   Status: {resp.status_code}")
    data = json.loads(resp.data)
    print(f"   Cached: {data.get('cached')}")
    print(f"   Time: {time.time() - start:.2f}s")

    assert resp.status_code == 200
    assert 'sections' in data
    assert data.get('cached') is True  # Second call should be cached

    print("\n✅ SUCCESS: Caching is working via API.")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
