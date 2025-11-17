# ABOUTME: Tests for yfinance data fetcher with caching behavior
# ABOUTME: Validates data retrieval, parsing, and cache management

import pytest
import os
import sys
import logging
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
    # Price will be current live price since AAPL data is always fetched fresh from EDGAR
    assert result['price'] > 0
    assert result['pe_ratio'] > 0


@patch('data_fetcher.yf.Ticker')
def test_fetch_stock_data_not_cached(mock_ticker, fetcher):
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals', return_value=None):
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
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals', return_value=None):
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
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals', return_value=None):
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
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals', return_value=None):
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


@patch('data_fetcher.yf.Ticker')
def test_hybrid_fetch_uses_edgar_for_fundamentals(mock_ticker, test_db):
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        # Provide >= 5 years for EDGAR to be used
        mock_edgar.return_value = {
            'ticker': 'AAPL',
            'cik': '0000320193',
            'company_name': 'Apple Inc.',
            'calculated_eps_history': [
                {'year': 2023, 'eps': 6.13, 'net_income': 96995000000},
                {'year': 2022, 'eps': 6.11, 'net_income': 99803000000},
                {'year': 2021, 'eps': 5.61, 'net_income': 94680000000},
                {'year': 2020, 'eps': 3.28, 'net_income': 57411000000},
                {'year': 2019, 'eps': 2.97, 'net_income': 55256000000}
            ],
            'net_income_annual': [
                {'year': 2023, 'net_income': 96995000000},
                {'year': 2022, 'net_income': 99803000000},
                {'year': 2021, 'net_income': 94680000000},
                {'year': 2020, 'net_income': 57411000000},
                {'year': 2019, 'net_income': 55256000000}
            ],
            'revenue_history': [
                {'year': 2023, 'revenue': 383285000000},
                {'year': 2022, 'revenue': 394328000000},
                {'year': 2021, 'revenue': 365817000000},
                {'year': 2020, 'revenue': 274515000000},
                {'year': 2019, 'revenue': 260174000000}
            ],
            'debt_to_equity_history': [],
            'debt_to_equity': 4.67
        }

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'AAPL',
            'longName': 'Apple Inc.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 180.50,
            'trailingPE': 29.5,
            'marketCap': 2800000000000,
            'heldPercentInstitutions': 0.60,
            'totalRevenue': 383000000000
        }
        mock_ticker.return_value = mock_stock

        fetcher = DataFetcher(test_db)
        result = fetcher.fetch_stock_data("AAPL")

        assert result is not None

        earnings = test_db.get_earnings_history("AAPL")
        assert len(earnings) == 5
        assert earnings[0]['eps'] == 6.13
        assert earnings[0]['year'] == 2023

        metrics = test_db.get_stock_metrics("AAPL")
        assert metrics['price'] == 180.50
        assert metrics['debt_to_equity'] == 4.67


@patch('data_fetcher.yf.Ticker')
def test_hybrid_fallback_to_yfinance_when_edgar_fails(mock_ticker, test_db):
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        mock_edgar.return_value = None

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'NEWSTOCK',
            'longName': 'New Stock Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'debtToEquity': 30.0,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 50000000000
        }
        mock_stock.financials = MagicMock()
        mock_stock.financials.to_dict.return_value = {}
        mock_ticker.return_value = mock_stock

        fetcher = DataFetcher(test_db)
        result = fetcher.fetch_stock_data("NEWSTOCK")

        assert result is not None
        assert result['price'] == 50.0
        assert result['debt_to_equity'] == 0.3


@patch('data_fetcher.yf.Ticker')
def test_logging_edgar_attempt(mock_ticker, test_db, caplog):
    """Test that EDGAR fetch attempts are logged"""
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        mock_edgar.return_value = None

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'TEST',
            'longName': 'Test Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 50000000000
        }
        mock_stock.financials = MagicMock()
        mock_stock.financials.to_dict.return_value = {}
        mock_ticker.return_value = mock_stock

        with caplog.at_level(logging.INFO):
            fetcher = DataFetcher(test_db)
            result = fetcher.fetch_stock_data("TEST")

        assert result is not None
        assert any("Attempting EDGAR fetch" in record.message for record in caplog.records)


@patch('data_fetcher.yf.Ticker')
def test_logging_edgar_success_with_year_counts(mock_ticker, test_db, caplog):
    """Test that successful EDGAR fetch logs the number of years retrieved"""
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        mock_edgar.return_value = {
            'ticker': 'TEST',
            'cik': '0000123456',
            'company_name': 'Test Corp.',
            'calculated_eps_history': [
                {'year': 2023, 'eps': 5.0, 'net_income': 50000000000},
                {'year': 2022, 'eps': 4.5, 'net_income': 45000000000},
                {'year': 2021, 'eps': 4.0, 'net_income': 40000000000},
                {'year': 2020, 'eps': 3.5, 'net_income': 35000000000},
                {'year': 2019, 'eps': 3.0, 'net_income': 30000000000},
                {'year': 2018, 'eps': 2.8, 'net_income': 28000000000},
                {'year': 2017, 'eps': 2.5, 'net_income': 25000000000},
                {'year': 2016, 'eps': 2.3, 'net_income': 23000000000},
                {'year': 2015, 'eps': 2.0, 'net_income': 20000000000},
                {'year': 2014, 'eps': 1.8, 'net_income': 18000000000}
            ],
            'revenue_history': [
                {'year': 2023, 'revenue': 100000000000},
                {'year': 2022, 'revenue': 95000000000},
                {'year': 2021, 'revenue': 90000000000},
                {'year': 2020, 'revenue': 85000000000},
                {'year': 2019, 'revenue': 80000000000},
                {'year': 2018, 'revenue': 75000000000},
                {'year': 2017, 'revenue': 70000000000},
                {'year': 2016, 'revenue': 65000000000},
                {'year': 2015, 'revenue': 60000000000},
                {'year': 2014, 'revenue': 55000000000}
            ],
            'debt_to_equity_history': [],
            'debt_to_equity': 0.5
        }

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'TEST',
            'longName': 'Test Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 100000000000
        }
        mock_ticker.return_value = mock_stock

        with caplog.at_level(logging.INFO):
            fetcher = DataFetcher(test_db)
            result = fetcher.fetch_stock_data("TEST")

        assert result is not None
        assert any("EDGAR returned" in record.message and "10" in record.message for record in caplog.records)


@patch('data_fetcher.yf.Ticker')
def test_logging_fallback_to_yfinance_with_reason(mock_ticker, test_db, caplog):
    """Test that fallback to yfinance is logged with the reason"""
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        mock_edgar.return_value = None

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'TEST',
            'longName': 'Test Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 50000000000
        }
        mock_stock.financials = MagicMock()
        mock_stock.financials.to_dict.return_value = {}
        mock_ticker.return_value = mock_stock

        with caplog.at_level(logging.INFO):
            fetcher = DataFetcher(test_db)
            result = fetcher.fetch_stock_data("TEST")

        assert result is not None
        assert any("EDGAR fetch failed" in record.message or "Using yfinance" in record.message for record in caplog.records)


@patch('data_fetcher.yf.Ticker')
def test_logging_yfinance_data_completeness_warning(mock_ticker, test_db, caplog):
    """Test that warnings are logged when yfinance returns limited years"""
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        mock_edgar.return_value = None

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'TEST',
            'longName': 'Test Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 50000000000
        }
        # Mock financials to return only 3 years (which should trigger warning)
        mock_stock.financials = MagicMock()
        mock_stock.financials.empty = False
        mock_stock.financials.columns = ['2023-12-31', '2022-12-31', '2021-12-31']
        mock_stock.financials.to_dict.return_value = {
            ('Total Revenue', '2023-12-31'): 50000000000,
            ('Total Revenue', '2022-12-31'): 48000000000,
            ('Total Revenue', '2021-12-31'): 45000000000
        }
        mock_ticker.return_value = mock_stock

        with caplog.at_level(logging.WARNING):
            fetcher = DataFetcher(test_db)
            result = fetcher.fetch_stock_data("TEST")

        assert result is not None
        assert any("only 3 years" in record.message or "limited" in record.message.lower() for record in caplog.records)


@patch('data_fetcher.yf.Ticker')
def test_hybrid_partial_edgar_data_uses_available_years(mock_ticker, test_db):
    """Test that when EDGAR has mismatched EPS/revenue years, we store what we can"""
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        # EDGAR returns 10 EPS years but only 8 revenue years
        mock_edgar.return_value = {
            'ticker': 'TEST',
            'cik': '0000123456',
            'company_name': 'Test Corp.',
            'calculated_eps_history': [
                {'year': 2023, 'eps': 10.0, 'net_income': 100000000000},
                {'year': 2022, 'eps': 9.5, 'net_income': 95000000000},
                {'year': 2021, 'eps': 9.0, 'net_income': 90000000000},
                {'year': 2020, 'eps': 8.5, 'net_income': 85000000000},
                {'year': 2019, 'eps': 8.0, 'net_income': 80000000000},
                {'year': 2018, 'eps': 7.5, 'net_income': 75000000000},
                {'year': 2017, 'eps': 7.0, 'net_income': 70000000000},
                {'year': 2016, 'eps': 6.5, 'net_income': 65000000000},
                {'year': 2015, 'eps': 6.0, 'net_income': 60000000000},
                {'year': 2014, 'eps': 5.5, 'net_income': 55000000000}
            ],
            'net_income_annual': [
                {'year': 2023, 'net_income': 100000000000},
                {'year': 2022, 'net_income': 95000000000},
                {'year': 2021, 'net_income': 90000000000},
                {'year': 2020, 'net_income': 85000000000},
                {'year': 2019, 'net_income': 80000000000},
                {'year': 2018, 'net_income': 75000000000},
                {'year': 2017, 'net_income': 70000000000},
                {'year': 2016, 'net_income': 65000000000},
                {'year': 2015, 'net_income': 60000000000},
                {'year': 2014, 'net_income': 55000000000}
            ],
            'revenue_history': [
                {'year': 2023, 'revenue': 100000000000},
                {'year': 2022, 'revenue': 95000000000},
                {'year': 2021, 'revenue': 90000000000},
                {'year': 2020, 'revenue': 85000000000},
                {'year': 2019, 'revenue': 80000000000},
                {'year': 2018, 'revenue': 75000000000},
                {'year': 2017, 'revenue': 70000000000},
                {'year': 2016, 'revenue': 65000000000}
                # Missing 2015 and 2014
            ],
            'debt_to_equity_history': [],
            'debt_to_equity': 0.5
        }

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'TEST',
            'longName': 'Test Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 100000000000
        }
        mock_ticker.return_value = mock_stock

        fetcher = DataFetcher(test_db)
        result = fetcher.fetch_stock_data("TEST")

        assert result is not None
        # Should have stored 8 years (where both EPS and revenue match)
        earnings = test_db.get_earnings_history("TEST")
        assert len(earnings) == 8
        assert earnings[0]['year'] == 2023
        assert earnings[7]['year'] == 2016


@patch('data_fetcher.yf.Ticker')
def test_hybrid_uses_edgar_when_sufficient_years(mock_ticker, test_db):
    """Test that EDGAR is used when it has >= 5 years of matched data"""
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        # EDGAR returns exactly 5 years
        mock_edgar.return_value = {
            'ticker': 'TEST',
            'cik': '0000123456',
            'company_name': 'Test Corp.',
            'calculated_eps_history': [
                {'year': 2023, 'eps': 5.0, 'net_income': 50000000000},
                {'year': 2022, 'eps': 4.5, 'net_income': 45000000000},
                {'year': 2021, 'eps': 4.0, 'net_income': 40000000000},
                {'year': 2020, 'eps': 3.5, 'net_income': 35000000000},
                {'year': 2019, 'eps': 3.0, 'net_income': 30000000000}
            ],
            'net_income_annual': [
                {'year': 2023, 'net_income': 50000000000},
                {'year': 2022, 'net_income': 45000000000},
                {'year': 2021, 'net_income': 40000000000},
                {'year': 2020, 'net_income': 35000000000},
                {'year': 2019, 'net_income': 30000000000}
            ],
            'revenue_history': [
                {'year': 2023, 'revenue': 50000000000},
                {'year': 2022, 'revenue': 48000000000},
                {'year': 2021, 'revenue': 45000000000},
                {'year': 2020, 'revenue': 42000000000},
                {'year': 2019, 'revenue': 40000000000}
            ],
            'debt_to_equity_history': [],
            'debt_to_equity': 0.5
        }

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'TEST',
            'longName': 'Test Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 50000000000
        }
        mock_ticker.return_value = mock_stock

        fetcher = DataFetcher(test_db)
        result = fetcher.fetch_stock_data("TEST")

        assert result is not None
        earnings = test_db.get_earnings_history("TEST")
        assert len(earnings) == 5


@patch('data_fetcher.yf.Ticker')
def test_hybrid_falls_back_when_insufficient_edgar_years(mock_ticker, test_db):
    """Test that we fall back to yfinance when EDGAR has < 5 years"""
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals') as mock_edgar:
        # EDGAR returns only 3 years
        mock_edgar.return_value = {
            'ticker': 'TEST',
            'cik': '0000123456',
            'company_name': 'Test Corp.',
            'calculated_eps_history': [
                {'year': 2023, 'eps': 5.0, 'net_income': 50000000000},
                {'year': 2022, 'eps': 4.5, 'net_income': 45000000000},
                {'year': 2021, 'eps': 4.0, 'net_income': 40000000000}
            ],
            'revenue_history': [
                {'year': 2023, 'revenue': 50000000000},
                {'year': 2022, 'revenue': 48000000000},
                {'year': 2021, 'revenue': 45000000000}
            ],
            'debt_to_equity_history': [],
            'debt_to_equity': 0.5
        }

        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'TEST',
            'longName': 'Test Corp.',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 50000000000
        }
        # Mock yfinance to return 4 years - properly simulate pandas DataFrame
        import pandas as pd
        from datetime import datetime

        dates = [
            pd.Timestamp('2023-12-31'),
            pd.Timestamp('2022-12-31'),
            pd.Timestamp('2021-12-31'),
            pd.Timestamp('2020-12-31')
        ]

        mock_financials = pd.DataFrame({
            dates[0]: {'Total Revenue': 50000000000, 'Diluted EPS': 5.0},
            dates[1]: {'Total Revenue': 48000000000, 'Diluted EPS': 4.5},
            dates[2]: {'Total Revenue': 45000000000, 'Diluted EPS': 4.0},
            dates[3]: {'Total Revenue': 42000000000, 'Diluted EPS': 3.5}
        })

        mock_stock.financials = mock_financials
        mock_ticker.return_value = mock_stock

        fetcher = DataFetcher(test_db)
        result = fetcher.fetch_stock_data("TEST")

        assert result is not None
        # Should use yfinance (4 years) instead of EDGAR (3 years)
        earnings = test_db.get_earnings_history("TEST")
        assert len(earnings) >= 4  # yfinance should provide 4 years
