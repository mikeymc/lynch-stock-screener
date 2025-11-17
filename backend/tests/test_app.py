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
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def test_db():
    db_path = "test_app_stocks.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    test_database = Database(db_path)
    yield test_database
    if os.path.exists(db_path):
        os.remove(db_path)


def test_health_endpoint(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'


def test_stock_history_endpoint_returns_historical_data(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/history returns historical EPS, revenue, and calculated P/E ratios"""

    # Replace app's db with test_db
    import app as app_module
    monkeypatch.setattr(app_module, 'db', test_db)

    # Set up test data in database
    symbol = "AAPL"
    test_db.save_stock_basic(symbol, "Apple Inc.", "NASDAQ", "Technology")

    # Add earnings history for multiple years
    earnings_data = [
        (2020, 3.28, 274515000000),
        (2021, 5.61, 365817000000),
        (2022, 6.11, 394328000000),
        (2023, 6.13, 383285000000)
    ]

    for year, eps, revenue in earnings_data:
        test_db.save_earnings_history(symbol, year, eps, revenue)

    # Mock yfinance to return historical prices
    mock_ticker = MagicMock()
    mock_history = MagicMock()

    # Return different closing prices for each year
    # These would be the price on the last day of each fiscal year
    mock_history_data = {
        2020: 132.69,
        2021: 177.57,
        2022: 129.93,
        2023: 191.45
    }

    def mock_get_history(start, end):
        # Extract year from start date string
        year = int(start.split('-')[0])
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.iloc = MagicMock()
        mock_df.iloc.__getitem__ = MagicMock(return_value={'Close': mock_history_data.get(year, 100.0)})
        return mock_df

    mock_ticker.history.side_effect = mock_get_history

    with patch('yfinance.Ticker', return_value=mock_ticker):
        response = client.get(f'/api/stock/{symbol}/history')

    assert response.status_code == 200
    data = json.loads(response.data)

    # Verify response structure
    assert 'labels' in data
    assert 'eps' in data
    assert 'revenue' in data
    assert 'pe_ratio' in data

    # Verify data length matches
    assert len(data['labels']) == 4
    assert len(data['eps']) == 4
    assert len(data['revenue']) == 4
    assert len(data['pe_ratio']) == 4

    # Verify labels are sorted in ascending order for charting
    assert data['labels'] == ['2020', '2021', '2022', '2023']

    # Verify EPS values
    assert data['eps'][0] == 3.28
    assert data['eps'][1] == 5.61
    assert data['eps'][2] == 6.11
    assert data['eps'][3] == 6.13

    # Verify revenue values
    assert data['revenue'][0] == 274515000000

    # Verify P/E ratios are calculated correctly (price / eps)
    # 2020: 132.69 / 3.28 = 40.45
    assert abs(data['pe_ratio'][0] - 40.45) < 0.1
    # 2021: 177.57 / 5.61 = 31.65
    assert abs(data['pe_ratio'][1] - 31.65) < 0.1
    # 2022: 129.93 / 6.11 = 21.26
    assert abs(data['pe_ratio'][2] - 21.26) < 0.1
    # 2023: 191.45 / 6.13 = 31.24
    assert abs(data['pe_ratio'][3] - 31.24) < 0.1


def test_stock_history_endpoint_handles_missing_stock(client):
    """Test that /api/stock/<symbol>/history returns 404 for non-existent stock"""
    response = client.get('/api/stock/INVALID/history')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data


def test_stock_history_endpoint_handles_negative_eps(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/history handles years with negative EPS by setting P/E to None"""

    import app as app_module
    monkeypatch.setattr(app_module, 'db', test_db)

    symbol = "WOOF"
    test_db.save_stock_basic(symbol, "Petco", "NASDAQ", "Consumer")

    # Add earnings with one negative EPS year
    earnings_data = [
        (2020, 0.50, 5000000000),
        (2021, -0.13, 5200000000),  # Negative EPS
        (2022, 0.75, 5500000000)
    ]

    for year, eps, revenue in earnings_data:
        test_db.save_earnings_history(symbol, year, eps, revenue)

    # Mock yfinance
    mock_ticker = MagicMock()
    mock_history = MagicMock()

    def mock_get_history(start, end):
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.iloc = MagicMock()
        mock_df.iloc.__getitem__ = MagicMock(return_value={'Close': 25.0})
        return mock_df

    mock_ticker.history.side_effect = mock_get_history

    with patch('yfinance.Ticker', return_value=mock_ticker):
        response = client.get(f'/api/stock/{symbol}/history')

    assert response.status_code == 200
    data = json.loads(response.data)

    # Verify P/E ratio is None for negative EPS year
    assert data['pe_ratio'][0] == 50.0  # 25.0 / 0.50
    assert data['pe_ratio'][1] is None  # Negative EPS -> None P/E
    assert data['pe_ratio'][2] == pytest.approx(33.33, abs=0.1)  # 25.0 / 0.75


def test_stock_history_uses_schwab_api_when_available(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/history uses Schwab API when available"""

    import app as app_module
    monkeypatch.setattr(app_module, 'db', test_db)

    # Set up test data with fiscal year-end dates (Apple's fiscal year ends in September)
    symbol = "AAPL"
    test_db.save_stock_basic(symbol, "Apple Inc.", "NASDAQ", "Technology")

    earnings_data = [
        (2020, 3.28, 274515000000, "2020-09-26"),
        (2021, 5.61, 365817000000, "2021-09-25"),
        (2022, 6.11, 394328000000, "2022-09-24"),
        (2023, 6.13, 383285000000, "2023-09-30")
    ]

    for year, eps, revenue, fiscal_end in earnings_data:
        test_db.save_earnings_history(symbol, year, eps, revenue, fiscal_end=fiscal_end)

    # Mock SchwabClient to return historical prices
    mock_schwab_client = MagicMock()
    mock_schwab_client.is_available.return_value = True

    # Return different prices for each fiscal year-end date
    price_data = {
        "2020-09-26": 108.77,
        "2021-09-25": 141.50,
        "2022-09-24": 150.43,
        "2023-09-30": 171.21
    }

    def mock_get_price(sym, date):
        return price_data.get(date)

    mock_schwab_client.get_historical_price.side_effect = mock_get_price

    # Replace app's schwab_client instance with our mock
    monkeypatch.setattr(app_module, 'schwab_client', mock_schwab_client)

    response = client.get(f'/api/stock/{symbol}/history')

    assert response.status_code == 200
    data = json.loads(response.data)

    # Verify response structure
    assert 'labels' in data
    assert 'eps' in data
    assert 'revenue' in data
    assert 'pe_ratio' in data
    assert 'price' in data

    # Verify Schwab API was called with correct fiscal year-end dates
    assert mock_schwab_client.get_historical_price.call_count == 4
    mock_schwab_client.get_historical_price.assert_any_call(symbol, "2020-09-26")
    mock_schwab_client.get_historical_price.assert_any_call(symbol, "2021-09-25")
    mock_schwab_client.get_historical_price.assert_any_call(symbol, "2022-09-24")
    mock_schwab_client.get_historical_price.assert_any_call(symbol, "2023-09-30")

    # Verify P/E ratios are calculated from Schwab prices
    # 2020: 108.77 / 3.28 = 33.16
    assert abs(data['pe_ratio'][0] - 33.16) < 0.1
    # 2021: 141.50 / 5.61 = 25.22
    assert abs(data['pe_ratio'][1] - 25.22) < 0.1
    # 2022: 150.43 / 6.11 = 24.62
    assert abs(data['pe_ratio'][2] - 24.62) < 0.1
    # 2023: 171.21 / 6.13 = 27.93
    assert abs(data['pe_ratio'][3] - 27.93) < 0.1

    # Verify prices are included in response
    assert data['price'][0] == 108.77
    assert data['price'][1] == 141.50
    assert data['price'][2] == 150.43
    assert data['price'][3] == 171.21


def test_stock_history_falls_back_to_yfinance_when_schwab_fails(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/history falls back to yfinance when Schwab API fails"""

    import app as app_module
    monkeypatch.setattr(app_module, 'db', test_db)

    symbol = "MSFT"
    test_db.save_stock_basic(symbol, "Microsoft", "NASDAQ", "Technology")

    # Microsoft's fiscal year ends in June
    earnings_data = [
        (2021, 8.05, 168088000000, "2021-06-30"),
        (2022, 9.21, 198270000000, "2022-06-30"),
        (2023, 9.68, 211915000000, "2023-06-30")
    ]

    for year, eps, revenue, fiscal_end in earnings_data:
        test_db.save_earnings_history(symbol, year, eps, revenue, fiscal_end=fiscal_end)

    # Mock SchwabClient to be unavailable
    mock_schwab_client = MagicMock()
    mock_schwab_client.is_available.return_value = False

    # Mock yfinance to return fallback prices
    mock_ticker = MagicMock()

    def mock_get_history(start, end):
        # Extract date from start to determine which price to return
        year = int(start.split('-')[0])
        prices = {
            2021: 265.51,
            2022: 256.83,
            2023: 339.96
        }
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.iloc = MagicMock()
        mock_df.iloc.__getitem__ = MagicMock(return_value={'Close': prices.get(year, 100.0)})
        return mock_df

    mock_ticker.history.side_effect = mock_get_history

    monkeypatch.setattr(app_module, 'schwab_client', mock_schwab_client)

    with patch('yfinance.Ticker', return_value=mock_ticker):
        response = client.get(f'/api/stock/{symbol}/history')

    assert response.status_code == 200
    data = json.loads(response.data)

    # Verify yfinance was used as fallback
    assert mock_ticker.history.call_count == 3

    # Verify P/E ratios are calculated from yfinance prices
    # 2021: 265.51 / 8.05 = 32.98
    assert abs(data['pe_ratio'][0] - 32.98) < 0.1
    # 2022: 256.83 / 9.21 = 27.88
    assert abs(data['pe_ratio'][1] - 27.88) < 0.1
    # 2023: 339.96 / 9.68 = 35.12
    assert abs(data['pe_ratio'][2] - 35.12) < 0.1


def test_stock_history_uses_fiscal_year_end_dates(client, test_db, monkeypatch):
    """Test that history endpoint uses fiscal year-end dates instead of calendar year-end"""

    import app as app_module
    monkeypatch.setattr(app_module, 'db', test_db)

    symbol = "WMT"
    test_db.save_stock_basic(symbol, "Walmart", "NYSE", "Retail")

    # Walmart's fiscal year ends in January
    earnings_data = [
        (2021, 4.77, 559151000000, "2021-01-31"),
        (2022, 6.47, 572754000000, "2022-01-31"),
        (2023, 6.29, 611289000000, "2023-01-31")
    ]

    for year, eps, revenue, fiscal_end in earnings_data:
        test_db.save_earnings_history(symbol, year, eps, revenue, fiscal_end=fiscal_end)

    # Mock SchwabClient
    mock_schwab_client = MagicMock()
    mock_schwab_client.is_available.return_value = True

    price_data = {
        "2021-01-31": 139.49,
        "2022-01-31": 135.90,
        "2023-01-31": 141.70
    }

    def mock_get_price(sym, date):
        return price_data.get(date)

    mock_schwab_client.get_historical_price.side_effect = mock_get_price

    monkeypatch.setattr(app_module, 'schwab_client', mock_schwab_client)

    response = client.get(f'/api/stock/{symbol}/history')

    assert response.status_code == 200

    # Verify Schwab was called with fiscal year-end dates (January 31), not calendar year-end (December 31)
    mock_schwab_client.get_historical_price.assert_any_call(symbol, "2021-01-31")
    mock_schwab_client.get_historical_price.assert_any_call(symbol, "2022-01-31")
    mock_schwab_client.get_historical_price.assert_any_call(symbol, "2023-01-31")

    # Verify it was NOT called with December 31 dates
    for year in [2021, 2022, 2023]:
        assert not any(
            call[0][1] == f"{year}-12-31"
            for call in mock_schwab_client.get_historical_price.call_args_list
        )


def test_lynch_analysis_endpoint_returns_cached_analysis(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/lynch-analysis returns cached analysis when available"""
    import app as app_module
    from lynch_analyst import LynchAnalyst

    monkeypatch.setattr(app_module, 'db', test_db)
    monkeypatch.setattr(app_module, 'lynch_analyst', LynchAnalyst(test_db))

    # Set up test data
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

    # Save a cached analysis
    cached_analysis = "This is a cached Peter Lynch analysis of Apple. Strong fundamentals and growth trajectory."
    test_db.save_lynch_analysis(symbol, cached_analysis, "gemini-pro")

    # Request analysis
    response = client.get(f'/api/stock/{symbol}/lynch-analysis')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['analysis'] == cached_analysis
    assert data['cached'] is True
    assert 'generated_at' in data


@patch('lynch_analyst.genai.GenerativeModel')
def test_lynch_analysis_endpoint_generates_fresh_analysis(mock_model_class, client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/lynch-analysis generates fresh analysis when cache is empty"""
    import app as app_module
    from lynch_analyst import LynchAnalyst

    monkeypatch.setattr(app_module, 'db', test_db)
    monkeypatch.setattr(app_module, 'lynch_analyst', LynchAnalyst(test_db))

    # Setup mock Gemini response
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Fresh Peter Lynch analysis: Apple shows strong growth with a PEG ratio of 1.2, suggesting reasonable valuation."
    mock_model.generate_content.return_value = mock_response
    mock_model_class.return_value = mock_model

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

    # Request analysis
    response = client.get(f'/api/stock/{symbol}/lynch-analysis')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert "Fresh Peter Lynch analysis" in data['analysis']
    assert data['cached'] is False
    assert 'generated_at' in data


@patch('lynch_analyst.genai.GenerativeModel')
def test_lynch_analysis_refresh_endpoint(mock_model_class, client, test_db, monkeypatch):
    """Test that POST /api/stock/<symbol>/lynch-analysis/refresh forces regeneration"""
    import app as app_module
    from lynch_analyst import LynchAnalyst

    monkeypatch.setattr(app_module, 'db', test_db)
    monkeypatch.setattr(app_module, 'lynch_analyst', LynchAnalyst(test_db))

    # Setup mock Gemini response
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Updated Peter Lynch analysis with latest data."
    mock_model.generate_content.return_value = mock_response
    mock_model_class.return_value = mock_model

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

    # Save old cached analysis
    test_db.save_lynch_analysis(symbol, "Old cached analysis", "gemini-pro")

    # Request refresh
    response = client.post(f'/api/stock/{symbol}/lynch-analysis/refresh')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert "Updated Peter Lynch analysis" in data['analysis']
    assert data['cached'] is False
    assert 'generated_at' in data

    # Verify the cache was updated
    cached = test_db.get_lynch_analysis(symbol)
    assert cached['analysis_text'] == "Updated Peter Lynch analysis with latest data."


def test_lynch_analysis_endpoint_returns_404_for_unknown_stock(client, test_db, monkeypatch):
    """Test that /api/stock/<symbol>/lynch-analysis returns 404 for unknown stock"""
    import app as app_module
    monkeypatch.setattr(app_module, 'db', test_db)

    response = client.get('/api/stock/UNKNOWN/lynch-analysis')

    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data


# Screening Sessions Tests

def test_get_latest_session_returns_most_recent_screening(client, test_db, monkeypatch):
    """Test that GET /api/sessions/latest returns the most recent screening session"""
    import app as app_module
    monkeypatch.setattr(app_module, 'db', test_db)

    # Create a session with results
    session_id = test_db.create_session(total_analyzed=2, pass_count=1, close_count=0, fail_count=1)

    result1 = {
        'symbol': 'AAPL', 'company_name': 'Apple Inc.', 'country': 'United States',
        'market_cap': 2500000000000, 'sector': 'Technology', 'ipo_year': 1980,
        'price': 150.25, 'pe_ratio': 25.5, 'peg_ratio': 1.2, 'debt_to_equity': 0.35,
        'institutional_ownership': 0.45, 'earnings_cagr': 15.5, 'revenue_cagr': 12.3,
        'consistency_score': 85.0, 'peg_status': 'PASS', 'debt_status': 'PASS',
        'institutional_ownership_status': 'PASS', 'overall_status': 'PASS'
    }
    test_db.save_screening_result(session_id, result1)

    result2 = {
        'symbol': 'MSFT', 'company_name': 'Microsoft Corp.', 'country': 'United States',
        'market_cap': 2000000000000, 'sector': 'Technology', 'ipo_year': 1986,
        'price': 300.00, 'pe_ratio': 30.0, 'peg_ratio': 2.5, 'debt_to_equity': 0.40,
        'institutional_ownership': 0.70, 'earnings_cagr': 10.0, 'revenue_cagr': 8.0,
        'consistency_score': 75.0, 'peg_status': 'FAIL', 'debt_status': 'PASS',
        'institutional_ownership_status': 'FAIL', 'overall_status': 'FAIL'
    }
    test_db.save_screening_result(session_id, result2)

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
    import app as app_module
    monkeypatch.setattr(app_module, 'db', test_db)

    response = client.get('/api/sessions/latest')

    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data
