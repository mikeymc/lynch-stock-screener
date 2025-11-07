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
    assert 'years' in data
    assert 'eps' in data
    assert 'revenue' in data
    assert 'pe_ratio' in data

    # Verify data length matches
    assert len(data['years']) == 4
    assert len(data['eps']) == 4
    assert len(data['revenue']) == 4
    assert len(data['pe_ratio']) == 4

    # Verify years are sorted in ascending order for charting
    assert data['years'] == [2020, 2021, 2022, 2023]

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
    assert 'years' in data
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
