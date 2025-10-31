# ABOUTME: Tests for yfinance data fetcher with caching behavior
# ABOUTME: Validates data retrieval, parsing, and cache management

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_fetcher import DataFetcher
from database import Database


@pytest.fixture
def test_db():
    db_path = "test_fetcher_stocks.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def fetcher(test_db):
    return DataFetcher(test_db)


def test_fetch_stock_data_from_cache(fetcher, test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    metrics = {
        'price': 150.25,
        'pe_ratio': 25.5,
        'market_cap': 2500000000000,
        'debt_to_equity': 0.35,
        'institutional_ownership': 0.45,
        'revenue': 394000000000
    }
    test_db.save_stock_metrics("AAPL", metrics)
    test_db.save_earnings_history("AAPL", 2023, 6.13, 383000000000)
    test_db.save_earnings_history("AAPL", 2022, 6.11, 394000000000)

    result = fetcher.fetch_stock_data("AAPL")

    assert result is not None
    assert result['symbol'] == "AAPL"
    assert result['price'] == 150.25
    assert result['pe_ratio'] == 25.5


@patch('data_fetcher.yf.Ticker')
def test_fetch_stock_data_not_cached(mock_ticker, fetcher):
    mock_stock = MagicMock()
    mock_stock.info = {
        'symbol': 'MSFT',
        'longName': 'Microsoft Corp.',
        'exchange': 'NASDAQ',
        'sector': 'Technology',
        'currentPrice': 380.50,
        'trailingPE': 35.2,
        'marketCap': 2800000000000,
        'debtToEquity': 42.5,
        'heldPercentInstitutions': 0.73,
        'totalRevenue': 211000000000
    }
    mock_stock.earnings_history = MagicMock()
    mock_stock.earnings_history.to_dict.return_value = {
        'EPS': {0: 9.72, 1: 10.15}
    }
    mock_stock.financials = MagicMock()
    mock_stock.financials.to_dict.return_value = {
        ('Total Revenue', '2023-12-31'): 211000000000,
        ('Total Revenue', '2022-12-31'): 198000000000
    }
    mock_ticker.return_value = mock_stock

    result = fetcher.fetch_stock_data("MSFT")

    assert result is not None
    assert result['symbol'] == 'MSFT'
    assert result['company_name'] == 'Microsoft Corp.'
    assert result['price'] == 380.50


@patch('data_fetcher.yf.Ticker')
def test_fetch_stock_data_force_refresh(mock_ticker, fetcher, test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    metrics = {
        'price': 150.25,
        'pe_ratio': 25.5,
        'market_cap': 2500000000000,
        'debt_to_equity': 0.35,
        'institutional_ownership': 0.45,
        'revenue': 394000000000
    }
    test_db.save_stock_metrics("AAPL", metrics)

    mock_stock = MagicMock()
    mock_stock.info = {
        'symbol': 'AAPL',
        'longName': 'Apple Inc.',
        'exchange': 'NASDAQ',
        'sector': 'Technology',
        'currentPrice': 155.75,
        'trailingPE': 26.0,
        'marketCap': 2600000000000,
        'debtToEquity': 38.0,
        'heldPercentInstitutions': 0.48,
        'totalRevenue': 400000000000
    }
    mock_stock.earnings_history = MagicMock()
    mock_stock.earnings_history.to_dict.return_value = {}
    mock_stock.financials = MagicMock()
    mock_stock.financials.to_dict.return_value = {}
    mock_ticker.return_value = mock_stock

    result = fetcher.fetch_stock_data("AAPL", force_refresh=True)

    assert result is not None
    assert result['price'] == 155.75


@patch('data_fetcher.yf.Ticker')
def test_fetch_stock_data_missing_info(mock_ticker, fetcher):
    mock_stock = MagicMock()
    mock_stock.info = {}
    mock_stock.earnings_history = MagicMock()
    mock_stock.earnings_history.to_dict.return_value = {}
    mock_stock.financials = MagicMock()
    mock_stock.financials.to_dict.return_value = {}
    mock_ticker.return_value = mock_stock

    result = fetcher.fetch_stock_data("INVALID")

    assert result is None


@patch('data_fetcher.yf.Ticker')
def test_fetch_multiple_stocks(mock_ticker, fetcher):
    def mock_ticker_factory(symbol):
        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': symbol,
            'longName': f'{symbol} Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 100.0,
            'trailingPE': 20.0,
            'marketCap': 1000000000000,
            'debtToEquity': 30.0,
            'heldPercentInstitutions': 0.50,
            'totalRevenue': 100000000000
        }
        mock_stock.earnings_history = MagicMock()
        mock_stock.earnings_history.to_dict.return_value = {}
        mock_stock.financials = MagicMock()
        mock_stock.financials.to_dict.return_value = {}
        return mock_stock

    mock_ticker.side_effect = mock_ticker_factory

    results = fetcher.fetch_multiple_stocks(["AAPL", "MSFT", "GOOGL"])

    assert len(results) == 3
    assert "AAPL" in results
    assert "MSFT" in results
    assert "GOOGL" in results
    assert results["AAPL"]['company_name'] == "AAPL Corp."


def test_fetch_stock_data_stores_in_db(fetcher, test_db):
    with patch('data_fetcher.yf.Ticker') as mock_ticker:
        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'TEST',
            'longName': 'Test Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'debtToEquity': 25.0,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 50000000000
        }
        mock_stock.earnings_history = MagicMock()
        mock_stock.earnings_history.to_dict.return_value = {}
        mock_stock.financials = MagicMock()
        mock_stock.financials.to_dict.return_value = {}
        mock_ticker.return_value = mock_stock

        fetcher.fetch_stock_data("TEST")

        cached = test_db.get_stock_metrics("TEST")
        assert cached is not None
        assert cached['symbol'] == "TEST"
        assert cached['price'] == 50.0


@patch('data_fetcher.pd.read_csv')
def test_get_nyse_nasdaq_symbols_returns_list(mock_read_csv, fetcher):
    mock_df_nyse = MagicMock()
    mock_df_nyse.__getitem__.return_value.tolist.return_value = ['AAPL', 'IBM', 'MSFT']

    mock_df_nasdaq = MagicMock()
    mock_df_nasdaq.__getitem__.return_value.tolist.return_value = ['GOOGL', 'AMZN', 'MSFT']

    mock_read_csv.side_effect = [mock_df_nyse, mock_df_nasdaq]

    symbols = fetcher.get_nyse_nasdaq_symbols()

    assert isinstance(symbols, list)
    assert len(symbols) > 0
    assert 'AAPL' in symbols
    assert 'GOOGL' in symbols
