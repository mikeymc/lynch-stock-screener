import pytest


def test_backtest_endpoint(test_client, mock_yfinance):
    """Test backtest API endpoint using Flask test client."""
    response = test_client.post('/api/backtest', json={
        'symbol': 'GOOGL',
        'years_back': 1
    })

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.data}"

    data = response.json

    # Verify response structure
    assert 'symbol' in data, "Response missing 'symbol' field"
    assert data['symbol'] == 'GOOGL', f"Expected symbol GOOGL, got {data['symbol']}"

    assert 'total_return' in data, "Response missing 'total_return' field"
    assert 'historical_score' in data, "Response missing 'historical_score' field"

    # Verify data types
    if data['total_return'] is not None:
        assert isinstance(data['total_return'], (int, float)), "total_return should be numeric"

    if data['historical_score'] is not None:
        assert isinstance(data['historical_score'], (int, float, dict)), "historical_score should be numeric or dict"


def test_backtest_missing_symbol(test_client):
    """Test backtest API returns 400 when symbol is missing."""
    response = test_client.post('/api/backtest', json={
        'years_back': 1
    })

    assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    data = response.json
    assert 'error' in data, "Error response should contain 'error' field"
