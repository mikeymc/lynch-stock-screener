# ABOUTME: Tests for stock split fetching and adjustment functionality
# ABOUTME: Validates split data retrieval, adjustment factor calculations, and P/E ratio corrections

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_fetcher import DataFetcher
from database import Database


@pytest.fixture
def test_db():
    db_path = "test_splits_stocks.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def fetcher(test_db):
    return DataFetcher(test_db)


def test_database_has_stock_splits_table(test_db):
    """Test that the stock_splits table exists in the schema"""
    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_splits'")
    result = cursor.fetchone()
    conn.close()

    assert result is not None, "stock_splits table should exist"


def test_save_and_retrieve_stock_splits(test_db):
    """Test saving and retrieving stock split data"""
    # First, create a stock entry (required for foreign key)
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")

    # Save splits
    splits = [
        {'date': '2014-06-09', 'ratio': 7.0},
        {'date': '2020-08-31', 'ratio': 4.0}
    ]
    test_db.save_stock_splits("AAPL", splits)

    # Retrieve splits
    retrieved_splits = test_db.get_stock_splits("AAPL")

    assert len(retrieved_splits) == 2
    assert retrieved_splits[0]['date'] == '2014-06-09'
    assert retrieved_splits[0]['ratio'] == 7.0
    assert retrieved_splits[1]['date'] == '2020-08-31'
    assert retrieved_splits[1]['ratio'] == 4.0


def test_get_stock_splits_returns_empty_for_unknown_symbol(test_db):
    """Test that retrieving splits for a non-existent symbol returns empty list"""
    splits = test_db.get_stock_splits("NONEXISTENT")
    assert splits == []


@patch('data_fetcher.yf.Ticker')
def test_fetch_stock_splits_with_splits(mock_ticker, fetcher, test_db):
    """Test fetching stock splits from yfinance when splits exist"""
    # Create stock entry first
    test_db.save_stock_basic("NVDA", "NVIDIA Corporation", "NASDAQ", "Technology")

    # Mock yfinance ticker with splits
    mock_stock = MagicMock()
    split_dates = pd.to_datetime(['2024-06-10'])
    split_ratios = pd.Series([10.0], index=split_dates)
    mock_stock.splits = split_ratios
    mock_ticker.return_value = mock_stock

    # Fetch splits
    splits = fetcher.fetch_stock_splits("NVDA")

    assert len(splits) == 1
    assert splits[0]['date'] == '2024-06-10'
    assert splits[0]['ratio'] == 10.0

    # Verify splits are stored in database
    db_splits = test_db.get_stock_splits("NVDA")
    assert len(db_splits) == 1


@patch('data_fetcher.yf.Ticker')
def test_fetch_stock_splits_with_no_splits(mock_ticker, fetcher, test_db):
    """Test fetching stock splits when none exist"""
    # Create stock entry first
    test_db.save_stock_basic("BRK.A", "Berkshire Hathaway", "NYSE", "Finance")

    # Mock yfinance ticker with no splits
    mock_stock = MagicMock()
    mock_stock.splits = pd.Series([], dtype=float)  # Empty series
    mock_ticker.return_value = mock_stock

    # Fetch splits
    splits = fetcher.fetch_stock_splits("BRK.A")

    assert splits == []

    # Verify no splits in database
    db_splits = test_db.get_stock_splits("BRK.A")
    assert db_splits == []


@patch('data_fetcher.yf.Ticker')
def test_fetch_stock_splits_with_multiple_splits(mock_ticker, fetcher, test_db):
    """Test fetching multiple historical stock splits"""
    # Create stock entry first
    test_db.save_stock_basic("TSLA", "Tesla Inc.", "NASDAQ", "Automotive")

    # Mock yfinance ticker with multiple splits
    mock_stock = MagicMock()
    split_dates = pd.to_datetime(['2020-08-31', '2022-08-25'])
    split_ratios = pd.Series([5.0, 3.0], index=split_dates)
    mock_stock.splits = split_ratios
    mock_ticker.return_value = mock_stock

    # Fetch splits
    splits = fetcher.fetch_stock_splits("TSLA")

    assert len(splits) == 2
    assert splits[0]['date'] == '2020-08-31'
    assert splits[0]['ratio'] == 5.0
    assert splits[1]['date'] == '2022-08-25'
    assert splits[1]['ratio'] == 3.0


def test_get_split_adjustment_factor_no_splits(fetcher, test_db):
    """Test adjustment factor when no splits exist"""
    # Create stock with no splits
    test_db.save_stock_basic("BRK.A", "Berkshire Hathaway", "NYSE", "Finance")

    factor = fetcher.get_split_adjustment_factor("BRK.A", "2010-01-01")

    assert factor == 1.0, "No splits should result in factor of 1.0"


def test_get_split_adjustment_factor_before_all_splits(fetcher, test_db):
    """Test adjustment factor for date before all splits"""
    # Create stock and add splits
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    splits = [
        {'date': '2014-06-09', 'ratio': 7.0},
        {'date': '2020-08-31', 'ratio': 4.0}
    ]
    test_db.save_stock_splits("AAPL", splits)

    # Date before all splits should have cumulative factor
    factor = fetcher.get_split_adjustment_factor("AAPL", "2010-01-01")

    assert factor == 28.0, "Should multiply all splits: 7.0 * 4.0 = 28.0"


def test_get_split_adjustment_factor_after_all_splits(fetcher, test_db):
    """Test adjustment factor for date after all splits"""
    # Create stock and add splits
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    splits = [
        {'date': '2014-06-09', 'ratio': 7.0},
        {'date': '2020-08-31', 'ratio': 4.0}
    ]
    test_db.save_stock_splits("AAPL", splits)

    # Date after all splits should have no adjustment
    factor = fetcher.get_split_adjustment_factor("AAPL", "2024-01-01")

    assert factor == 1.0, "Date after all splits should have factor of 1.0"


def test_get_split_adjustment_factor_between_splits(fetcher, test_db):
    """Test adjustment factor for date between multiple splits"""
    # Create stock and add splits
    test_db.save_stock_basic("TSLA", "Tesla Inc.", "NASDAQ", "Automotive")
    splits = [
        {'date': '2020-08-31', 'ratio': 5.0},
        {'date': '2022-08-25', 'ratio': 3.0}
    ]
    test_db.save_stock_splits("TSLA", splits)

    # Date after first split but before second
    factor = fetcher.get_split_adjustment_factor("TSLA", "2021-01-01")

    assert factor == 3.0, "Should only apply the 2022 split: 3.0"


def test_get_split_adjustment_factor_on_split_date(fetcher, test_db):
    """Test adjustment factor on the exact split date"""
    # Create stock and add splits
    test_db.save_stock_basic("NVDA", "NVIDIA Corporation", "NASDAQ", "Technology")
    splits = [{'date': '2024-06-10', 'ratio': 10.0}]
    test_db.save_stock_splits("NVDA", splits)

    # On the split date, the split has not yet occurred for that day's data
    factor = fetcher.get_split_adjustment_factor("NVDA", "2024-06-10")

    # The split is dated 2024-06-10, so data from that date should not be adjusted
    # Data from before that date should be adjusted
    assert factor == 1.0, "Split date itself should not be adjusted"

    # But data from before should be adjusted
    factor_before = fetcher.get_split_adjustment_factor("NVDA", "2024-06-09")
    assert factor_before == 10.0, "Day before split should be adjusted"


def test_eps_adjustment_calculation(fetcher, test_db):
    """Test that EPS adjustment produces correct values"""
    # Create stock and add splits
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    splits = [
        {'date': '2014-06-09', 'ratio': 7.0},
        {'date': '2020-08-31', 'ratio': 4.0}
    ]
    test_db.save_stock_splits("AAPL", splits)

    # Original EPS from 2010 (before all splits)
    original_eps = 10.0
    target_date = "2010-12-31"

    factor = fetcher.get_split_adjustment_factor("AAPL", target_date)
    adjusted_eps = original_eps / factor

    # After 7:1 and 4:1 splits, the $10 EPS should be adjusted to $10/28 = $0.357
    expected_adjusted = 10.0 / 28.0
    assert abs(adjusted_eps - expected_adjusted) < 0.001, f"Expected {expected_adjusted}, got {adjusted_eps}"


def test_reverse_split_adjustment(fetcher, test_db):
    """Test adjustment factor for reverse splits (ratio < 1.0)"""
    # Create stock and add a reverse split
    test_db.save_stock_basic("TEST", "Test Corp.", "NASDAQ", "Technology")
    splits = [
        {'date': '2020-01-01', 'ratio': 0.5}  # 1:2 reverse split
    ]
    test_db.save_stock_splits("TEST", splits)

    # Date before reverse split
    factor = fetcher.get_split_adjustment_factor("TEST", "2019-01-01")

    assert factor == 0.5, "Reverse split should have factor of 0.5"

    # EPS adjustment for reverse split
    original_eps = 2.0
    adjusted_eps = original_eps / factor
    assert adjusted_eps == 4.0, "Reverse split should increase adjusted EPS"


@patch('data_fetcher.yf.Ticker')
def test_splits_fetched_during_stock_data_fetch(mock_ticker, fetcher, test_db):
    """Test that splits are automatically fetched when fetching stock data"""
    from edgar_fetcher import EdgarFetcher
    with patch.object(EdgarFetcher, 'fetch_stock_fundamentals', return_value=None):
        # Mock yfinance to return stock info and splits
        mock_stock = MagicMock()
        mock_stock.info = {
            'symbol': 'NVDA',
            'longName': 'NVIDIA Corporation',
            'exchange': 'NASDAQ',
            'sector': 'Technology',
            'currentPrice': 50.0,
            'trailingPE': 15.0,
            'marketCap': 500000000000,
            'heldPercentInstitutions': 0.40,
            'totalRevenue': 50000000000
        }

        # Mock splits
        split_dates = pd.to_datetime(['2024-06-10'])
        split_ratios = pd.Series([10.0], index=split_dates)
        mock_stock.splits = split_ratios

        mock_stock.financials = MagicMock()
        mock_stock.financials.to_dict.return_value = {}
        mock_ticker.return_value = mock_stock

        # Fetch stock data (should also fetch splits)
        result = fetcher.fetch_stock_data("NVDA")

        assert result is not None

        # Verify splits were stored
        splits = test_db.get_stock_splits("NVDA")
        assert len(splits) == 1
        assert splits[0]['ratio'] == 10.0


def test_split_adjustment_factor_with_missing_stock(fetcher, test_db):
    """Test that missing stock returns factor of 1.0"""
    # Don't create any stock entry
    factor = fetcher.get_split_adjustment_factor("NONEXISTENT", "2020-01-01")

    assert factor == 1.0, "Missing stock should return factor of 1.0"


def test_stock_splits_ordered_by_date(test_db):
    """Test that stock splits are returned in chronological order"""
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")

    # Add splits in non-chronological order
    splits = [
        {'date': '2020-08-31', 'ratio': 4.0},
        {'date': '2014-06-09', 'ratio': 7.0},
        {'date': '2000-06-21', 'ratio': 2.0}
    ]
    test_db.save_stock_splits("AAPL", splits)

    # Retrieve and check order
    retrieved = test_db.get_stock_splits("AAPL")

    assert len(retrieved) == 3
    assert retrieved[0]['date'] == '2000-06-21', "Should be ordered chronologically"
    assert retrieved[1]['date'] == '2014-06-09'
    assert retrieved[2]['date'] == '2020-08-31'


def test_cumulative_factor_with_many_splits(fetcher, test_db):
    """Test cumulative factor calculation with multiple splits"""
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")

    # Apple's actual historical splits
    splits = [
        {'date': '1987-06-16', 'ratio': 2.0},
        {'date': '2000-06-21', 'ratio': 2.0},
        {'date': '2005-02-28', 'ratio': 2.0},
        {'date': '2014-06-09', 'ratio': 7.0},
        {'date': '2020-08-31', 'ratio': 4.0}
    ]
    test_db.save_stock_splits("AAPL", splits)

    # Calculate factor for data from 1985
    factor = fetcher.get_split_adjustment_factor("AAPL", "1985-01-01")

    # Total: 2 * 2 * 2 * 7 * 4 = 224
    expected = 2.0 * 2.0 * 2.0 * 7.0 * 4.0
    assert factor == expected, f"Expected {expected}, got {factor}"
