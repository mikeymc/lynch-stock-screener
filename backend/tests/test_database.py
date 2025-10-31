# ABOUTME: Tests for database operations including stock storage and retrieval
# ABOUTME: Validates caching logic and data integrity

import pytest
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Database


@pytest.fixture
def test_db():
    db_path = "test_stocks.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


def test_init_schema_creates_tables(test_db):
    conn = test_db.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_metrics'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='earnings_history'")
    assert cursor.fetchone() is not None

    conn.close()


def test_save_and_retrieve_stock_basic(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")

    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, company_name, exchange, sector FROM stocks WHERE symbol = ?", ("AAPL",))
    row = cursor.fetchone()
    conn.close()

    assert row[0] == "AAPL"
    assert row[1] == "Apple Inc."
    assert row[2] == "NASDAQ"
    assert row[3] == "Technology"


def test_save_and_retrieve_stock_metrics(test_db):
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

    retrieved = test_db.get_stock_metrics("AAPL")

    assert retrieved is not None
    assert retrieved['symbol'] == "AAPL"
    assert retrieved['price'] == 150.25
    assert retrieved['pe_ratio'] == 25.5
    assert retrieved['market_cap'] == 2500000000000
    assert retrieved['debt_to_equity'] == 0.35
    assert retrieved['institutional_ownership'] == 0.45
    assert retrieved['revenue'] == 394000000000
    assert retrieved['company_name'] == "Apple Inc."
    assert retrieved['exchange'] == "NASDAQ"
    assert retrieved['sector'] == "Technology"


def test_save_and_retrieve_earnings_history(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")

    test_db.save_earnings_history("AAPL", 2019, 2.97, 260000000000)
    test_db.save_earnings_history("AAPL", 2020, 3.28, 275000000000)
    test_db.save_earnings_history("AAPL", 2021, 5.61, 366000000000)
    test_db.save_earnings_history("AAPL", 2022, 6.11, 394000000000)
    test_db.save_earnings_history("AAPL", 2023, 6.13, 383000000000)

    history = test_db.get_earnings_history("AAPL")

    assert len(history) == 5
    assert history[0]['year'] == 2023
    assert history[0]['eps'] == 6.13
    assert history[4]['year'] == 2019
    assert history[4]['eps'] == 2.97


def test_cache_validity_fresh_data(test_db):
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

    assert test_db.is_cache_valid("AAPL", max_age_hours=24) is True


def test_cache_validity_nonexistent_stock(test_db):
    assert test_db.is_cache_valid("NONEXISTENT", max_age_hours=24) is False


def test_get_nonexistent_stock_returns_none(test_db):
    result = test_db.get_stock_metrics("NONEXISTENT")
    assert result is None


def test_get_earnings_history_empty(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    history = test_db.get_earnings_history("AAPL")
    assert history == []


def test_update_existing_metrics(test_db):
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

    metrics['price'] = 155.50
    test_db.save_stock_metrics("AAPL", metrics)

    retrieved = test_db.get_stock_metrics("AAPL")
    assert retrieved['price'] == 155.50


def test_get_all_cached_stocks(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_stock_basic("MSFT", "Microsoft Corp.", "NASDAQ", "Technology")
    test_db.save_stock_basic("GOOGL", "Alphabet Inc.", "NASDAQ", "Technology")

    stocks = test_db.get_all_cached_stocks()
    assert len(stocks) == 3
    assert "AAPL" in stocks
    assert "MSFT" in stocks
    assert "GOOGL" in stocks


def test_update_earnings_history(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")

    test_db.save_earnings_history("AAPL", 2023, 6.13, 383000000000)
    test_db.save_earnings_history("AAPL", 2023, 6.15, 385000000000)

    history = test_db.get_earnings_history("AAPL")
    assert len(history) == 1
    assert history[0]['eps'] == 6.15
