# ABOUTME: Verbose test for chart analysis caching with detailed output
# ABOUTME: Provides debugging information for caching behavior

import pytest
import json
from unittest.mock import MagicMock

from app import app


@pytest.fixture
def client(test_db, monkeypatch):
    """Flask test client with test database"""
    import app as app_module

    # Replace app's db with test_db
    monkeypatch.setattr(app_module.deps, 'db', test_db)

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_caching(client, test_db, monkeypatch):
    """Test chart analysis caching with verbose output"""
    import app as app_module

    symbol = "AMZN"

    print(f"\nTesting unified chart analysis caching for {symbol}...")

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

    # Mock the StockAnalyst to return predictable responses
    mock_analyst = MagicMock()
    mock_analyst.generate_unified_chart_analysis.return_value = {
        'narrative': 'Test unified narrative analysis for Amazon'
    }
    mock_analyst.model_version = "test-model"
    monkeypatch.setattr(app_module.deps, 'stock_analyst', mock_analyst)

    # Set session user_id
    with client.session_transaction() as sess:
        sess['user_id'] = user_id

    print("\n1. Force refresh request...")
    resp = client.post(f'/api/stock/{symbol}/unified-chart-analysis',
                       data=json.dumps({
                           "force_refresh": True,
                           "character": "lynch"
                       }),
                       content_type='application/json')

    print(f"Status: {resp.status_code}")
    data = resp.get_json()
    print(f"Response keys: {list(data.keys())}")
    print(f"Full response: {json.dumps(data, indent=2)[:500]}...")

    assert resp.status_code == 200
    assert data.get('cached') is False

    print("\n2. Normal request (should be cached)...")
    resp2 = client.post(f'/api/stock/{symbol}/unified-chart-analysis',
                        data=json.dumps({
                            "force_refresh": False,
                            "character": "lynch"
                        }),
                        content_type='application/json')

    print(f"Status: {resp2.status_code}")
    data2 = resp2.get_json()
    print(f"Response keys: {list(data2.keys())}")
    print(f"Cached field: {data2.get('cached')}")

    assert resp2.status_code == 200
    assert data2.get('cached') is True

    print("\n Caching test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
