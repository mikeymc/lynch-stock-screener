# ABOUTME: Tests for database operations including stock storage and retrieval
# ABOUTME: Validates caching logic and data integrity

import pytest
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Database

# test_db fixture is now provided by conftest.py

def test_init_schema_creates_tables(test_db):
    conn = test_db.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='stocks'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='stock_metrics'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='earnings_history'")
    assert cursor.fetchone() is not None

    test_db.return_connection(conn)


def test_save_and_retrieve_stock_basic(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()

    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, company_name, exchange, sector FROM stocks WHERE symbol = %s", ("AAPL",))
    row = cursor.fetchone()
    test_db.return_connection(conn)

    assert row[0] == "AAPL"
    assert row[1] == "Apple Inc."
    assert row[2] == "NASDAQ"
    assert row[3] == "Technology"


def test_save_and_retrieve_stock_metrics(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_stock_metrics("AAPL", {
        'price': 150.25,
        'pe_ratio': 25.5,
        'market_cap': 2500000000000,
        'debt_to_equity': 0.35,
        'institutional_ownership': 0.45,
        'revenue': 394000000000,
        'dividend_yield': 2.79
    })
    test_db.flush()

    retrieved = test_db.get_stock_metrics("AAPL")

    assert retrieved is not None
    assert retrieved['symbol'] == "AAPL"
    assert retrieved['price'] == 150.25
    assert retrieved['pe_ratio'] == 25.5
    assert retrieved['market_cap'] == 2500000000000
    assert retrieved['debt_to_equity'] == 0.35
    assert retrieved['institutional_ownership'] == 0.45
    assert retrieved['revenue'] == 394000000000
    assert retrieved['dividend_yield'] == 2.79
    assert retrieved['company_name'] == "Apple Inc."
    assert retrieved['exchange'] == "NASDAQ"
    assert retrieved['sector'] == "Technology"


def test_stock_metrics_with_null_dividend_yield(test_db):
    """Test that stocks without dividends (None) are handled correctly"""
    test_db.save_stock_basic("TSLA", "Tesla Inc.", "NASDAQ", "Automotive")

    metrics = {
        'price': 250.50,
        'pe_ratio': 45.2,
        'market_cap': 800000000000,
        'debt_to_equity': 0.15,
        'institutional_ownership': 0.40,
        'revenue': 81000000000,
        'dividend_yield': None  # Growth stock with no dividend
    }
    test_db.save_stock_metrics("TSLA", metrics)

    test_db.flush()  # Ensure data is committed

    retrieved = test_db.get_stock_metrics("TSLA")

    assert retrieved is not None
    assert retrieved['symbol'] == "TSLA"
    assert retrieved['dividend_yield'] is None


def test_save_and_retrieve_earnings_history(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock is committed before earnings history

    test_db.save_earnings_history("AAPL", 2019, 2.97, 260000000000)
    test_db.save_earnings_history("AAPL", 2020, 3.28, 275000000000)
    test_db.save_earnings_history("AAPL", 2021, 5.61, 366000000000)
    test_db.save_earnings_history("AAPL", 2022, 6.11, 394000000000)
    test_db.save_earnings_history("AAPL", 2023, 6.13, 383000000000)
    test_db.flush()  # Ensure data is committed

    history = test_db.get_earnings_history("AAPL")

    assert len(history) == 5
    assert history[0]['year'] == 2023
    assert history[0]['eps'] == 6.13
    assert history[4]['year'] == 2019
    assert history[4]['eps'] == 2.97


def test_save_and_retrieve_earnings_with_fiscal_end(test_db):
    """Test that fiscal year-end dates are stored and retrieved correctly"""
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock is committed before earnings history

    # Save earnings with fiscal year-end dates (Apple's fiscal year ends in September)
    test_db.save_earnings_history("AAPL", 2023, 6.13, 383000000000, fiscal_end="2023-09-30")
    test_db.save_earnings_history("AAPL", 2022, 6.11, 394000000000, fiscal_end="2022-09-24")
    test_db.save_earnings_history("AAPL", 2021, 5.61, 366000000000, fiscal_end="2021-09-25")

    test_db.flush()  # Ensure data is committed

    history = test_db.get_earnings_history("AAPL")

    assert len(history) == 3
    assert history[0]['year'] == 2023
    assert history[0]['fiscal_end'] == "2023-09-30"
    assert history[1]['year'] == 2022
    assert history[1]['fiscal_end'] == "2022-09-24"
    assert history[2]['year'] == 2021
    assert history[2]['fiscal_end'] == "2021-09-25"


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

    test_db.flush()  # Ensure data is committed

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

    test_db.flush()  # Ensure data is committed

    retrieved = test_db.get_stock_metrics("AAPL")
    assert retrieved['price'] == 155.50


def test_get_all_cached_stocks(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_stock_basic("MSFT", "Microsoft Corp.", "NASDAQ", "Technology")
    test_db.save_stock_basic("GOOGL", "Alphabet Inc.", "NASDAQ", "Technology")

    test_db.flush()  # Ensure data is committed

    stocks = test_db.get_all_cached_stocks()
    assert len(stocks) == 3
    assert "AAPL" in stocks
    assert "MSFT" in stocks
    assert "GOOGL" in stocks


def test_update_earnings_history(test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock is committed before earnings history

    test_db.save_earnings_history("AAPL", 2023, 6.13, 383000000000)
    test_db.save_earnings_history("AAPL", 2023, 6.15, 385000000000)

    test_db.flush()  # Ensure data is committed

    history = test_db.get_earnings_history("AAPL")
    assert len(history) == 1
    assert history[0]['eps'] == 6.15


def test_lynch_analyses_table_exists(test_db):
    """Test that lynch_analyses table is created"""
    conn = test_db.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='lynch_analyses'")
    assert cursor.fetchone() is not None

    test_db.return_connection(conn)


def test_save_and_retrieve_lynch_analysis(test_db):
    """Test saving and retrieving a Lynch analysis"""
    # Create test user
    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (id, google_id, email, name) VALUES (1, 'test123', 'test@example.com', 'Test User') ON CONFLICT DO NOTHING")
    conn.commit()
    test_db.return_connection(conn)

    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()

    analysis_text = "Apple is a solid growth company with strong earnings momentum. The PEG ratio of 1.2 suggests it's reasonably valued for its growth rate. With low debt and high institutional ownership, this is a textbook Peter Lynch growth stock. The consistent earnings growth over the past 5 years demonstrates strong management execution."
    model_version = "gemini-pro"

    test_db.save_lynch_analysis(1, "AAPL", analysis_text, model_version)
    test_db.flush()

    retrieved = test_db.get_lynch_analysis(1, "AAPL")

    assert retrieved is not None
    assert retrieved['symbol'] == "AAPL"
    assert retrieved['analysis_text'] == analysis_text
    assert retrieved['model_version'] == model_version
    assert 'generated_at' in retrieved


def test_get_nonexistent_lynch_analysis(test_db):
    """Test retrieving analysis for stock that doesn't have one"""
    result = test_db.get_lynch_analysis(1, "NONEXISTENT")
    assert result is None


def test_update_lynch_analysis(test_db):
    """Test updating an existing Lynch analysis (refresh)"""
    # Create test user
    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (id, google_id, email, name) VALUES (1, 'test123', 'test@example.com', 'Test User') ON CONFLICT DO NOTHING")
    conn.commit()
    test_db.return_connection(conn)

    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before saving analysis

    # Save initial analysis
    initial_analysis = "Initial analysis text"
    test_db.save_lynch_analysis(1, "AAPL", initial_analysis, "gemini-pro")

    # Update with new analysis
    updated_analysis = "Updated analysis text with new insights"
    test_db.save_lynch_analysis(1, "AAPL", updated_analysis, "gemini-pro")

    test_db.flush()  # Ensure data is committed

    retrieved = test_db.get_lynch_analysis(1, "AAPL")
    assert retrieved['analysis_text'] == updated_analysis


def test_lynch_analysis_has_timestamp(test_db):
    """Test that generated_at timestamp is saved correctly"""
    # Create test user
    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (id, google_id, email, name) VALUES (1, 'test123', 'test@example.com', 'Test User') ON CONFLICT DO NOTHING")
    conn.commit()
    test_db.return_connection(conn)

    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock exists before saving analysis

    before_save = datetime.now()
    test_db.save_lynch_analysis(1, "AAPL", "Test analysis", "gemini-pro")
    test_db.flush()  # Ensure data is committed
    after_save = datetime.now()

    retrieved = test_db.get_lynch_analysis(1, "AAPL")

    assert retrieved is not None
    generated_at = retrieved['generated_at']

    # Check that timestamp is between before and after save
    assert before_save <= generated_at <= after_save


# Screening Sessions Tests

