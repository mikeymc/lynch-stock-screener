import pytest
import pandas as pd
from datetime import datetime, timedelta


@pytest.fixture
def mock_yfinance_history(mock_yfinance):
    """Extend shared mock with history support locally."""
    mock_instance = mock_yfinance.return_value

    def mock_history(start=None, end=None, **kwargs):
        # Default range if not specified
        if start is None:
            start_dt = datetime.now() - timedelta(days=365*2)
        else:
            start_dt = datetime.fromisoformat(start) if isinstance(start, str) else start
            
        if end is None:
            end_dt = datetime.now()
        else:
            end_dt = datetime.fromisoformat(end) if isinstance(end, str) else end

        # Generate dates
        dates = pd.date_range(start=start_dt, end=end_dt, freq='D')
        
        # Generate fake prices (flat with slight noise or just flat)
        prices = [150.0 + (i % 10) for i in range(len(dates))]
        
        df = pd.DataFrame({'Close': prices}, index=dates)
        return df

    mock_instance.history.side_effect = mock_history
    return mock_yfinance


def test_backtest_endpoint(test_client, mock_yfinance_history, test_db):
    """Test backtest API endpoint using Flask test client."""
    # Setup test data
    test_db.save_stock_basic('GOOGL', 'Alphabet Inc.', 'NASDAQ', 'Technology', 'USA')
    test_db.save_stock_metrics('GOOGL', {
        'price': 150.0,
        'pe_ratio': 25.0,
        'market_cap': 2000000000000,
        'debt_to_equity': 0.1,
        'institutional_ownership': 0.8,
        'revenue': 300000000000,
        'dividend_yield': 0.0,
        'sector': 'Technology',
        'country': 'USA'
    })

    # Add earnings history for the past 3 years
    from datetime import datetime
    current_year = datetime.now().year
    
    for i in range(1, 4):
        year = current_year - i
        test_db.save_earnings_history(
            symbol='GOOGL',
            year=year,
            eps=5.0 * (1.1 ** i),
            revenue=200000000000 * (1.1 ** i),
            fiscal_end=f'{year}-12-31',
            debt_to_equity=0.1,
            period='annual',
            net_income=50000000000 * (1.1 ** i)
        )
    
    test_db.flush()

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
