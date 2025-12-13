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

def test_screening_sessions_table_exists(test_db):
    """Test that screening_sessions table is created"""
    conn = test_db.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='screening_sessions'")
    assert cursor.fetchone() is not None

    test_db.return_connection(conn)


def test_screening_results_table_exists(test_db):
    """Test that screening_results table is created"""
    conn = test_db.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='screening_results'")
    assert cursor.fetchone() is not None

    test_db.return_connection(conn)


def test_create_session(test_db):
    """Test creating a new screening session"""
    session_id = test_db.create_session("test_algo", 100, total_analyzed=50, pass_count=5, close_count=10, fail_count=35)

    assert session_id is not None
    assert isinstance(session_id, int)

    # Verify session was saved
    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, total_analyzed, pass_count, close_count, fail_count FROM screening_sessions WHERE id = %s", (session_id,))
    row = cursor.fetchone()
    test_db.return_connection(conn)

    assert row is not None
    assert row[0] == session_id
    assert row[1] == 50
    assert row[2] == 5
    assert row[3] == 10
    assert row[4] == 35


def test_save_screening_result(test_db):
    """Test saving a stock result to a screening session"""
    session_id = test_db.create_session("test_algo", 100, total_analyzed=1, pass_count=1, close_count=0, fail_count=0)

    result_data = {
        'symbol': 'AAPL',
        'company_name': 'Apple Inc.',
        'country': 'United States',
        'market_cap': 2500000000000,
        'sector': 'Technology',
        'ipo_year': 1980,
        'price': 150.25,
        'pe_ratio': 25.5,
        'peg_ratio': 1.2,
        'debt_to_equity': 0.35,
        'institutional_ownership': 0.45,
        'earnings_cagr': 15.5,
        'revenue_cagr': 12.3,
        'consistency_score': 85.0,
        'peg_status': 'PASS',
        'debt_status': 'PASS',
        'institutional_ownership_status': 'PASS',
        'overall_status': 'PASS'
    }

    test_db.save_screening_result(session_id, result_data)

    test_db.flush()  # Ensure data is committed

    # Verify result was saved
    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, company_name, overall_status FROM screening_results WHERE session_id = %s", (session_id,))
    row = cursor.fetchone()
    test_db.return_connection(conn)

    assert row is not None
    assert row[0] == 'AAPL'
    assert row[1] == 'Apple Inc.'
    assert row[2] == 'PASS'


def test_get_latest_session_with_results(test_db):
    """Test retrieving the latest screening session with all results"""
    # Create first session
    session1_id = test_db.create_session("test_algo", 100, total_analyzed=2, pass_count=1, close_count=1, fail_count=0)
    result1 = {
        'symbol': 'AAPL', 'company_name': 'Apple Inc.', 'country': 'United States',
        'market_cap': 2500000000000, 'sector': 'Technology', 'ipo_year': 1980,
        'price': 150.25, 'pe_ratio': 25.5, 'peg_ratio': 1.2, 'debt_to_equity': 0.35,
        'institutional_ownership': 0.45, 'earnings_cagr': 15.5, 'revenue_cagr': 12.3,
        'consistency_score': 85.0, 'peg_status': 'PASS', 'debt_status': 'PASS',
        'institutional_ownership_status': 'PASS', 'overall_status': 'PASS'
    }
    test_db.save_screening_result(session1_id, result1)

    # Create second session (most recent)
    session2_id = test_db.create_session("test_algo", 100, total_analyzed=1, pass_count=0, close_count=0, fail_count=1)
    result2 = {
        'symbol': 'MSFT', 'company_name': 'Microsoft Corp.', 'country': 'United States',
        'market_cap': 2000000000000, 'sector': 'Technology', 'ipo_year': 1986,
        'price': 300.00, 'pe_ratio': 30.0, 'peg_ratio': 2.5, 'debt_to_equity': 0.40,
        'institutional_ownership': 0.70, 'earnings_cagr': 10.0, 'revenue_cagr': 8.0,
        'consistency_score': 75.0, 'peg_status': 'FAIL', 'debt_status': 'PASS',
        'institutional_ownership_status': 'FAIL', 'overall_status': 'FAIL'
    }
    test_db.save_screening_result(session2_id, result2)

    test_db.flush()  # Ensure data is committed

    # Retrieve latest session
    latest = test_db.get_latest_session()

    assert latest is not None
    assert latest['session_id'] == session2_id
    assert latest['total_analyzed'] == 1
    assert latest['pass_count'] == 0
    assert latest['fail_count'] == 1
    assert len(latest['results']) == 1
    assert latest['results'][0]['symbol'] == 'MSFT'
    assert latest['results'][0]['company_name'] == 'Microsoft Corp.'


def test_get_latest_session_when_none_exists(test_db):
    """Test retrieving latest session when no sessions exist"""
    result = test_db.get_latest_session()
    assert result is None


def test_cleanup_old_sessions(test_db):
    """Test that cleanup_old_sessions keeps only the most recent N sessions"""
    # Create 5 sessions
    session_ids = []
    for i in range(5):
        session_id = test_db.create_session("test_algo", 100, total_analyzed=i, pass_count=0, close_count=0, fail_count=i)
        session_ids.append(session_id)

    # Keep only 2 most recent
    test_db.cleanup_old_sessions(keep_count=2)

    # Verify only 2 sessions remain
    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM screening_sessions ORDER BY created_at DESC")
    remaining_sessions = cursor.fetchall()
    test_db.return_connection(conn)

    assert len(remaining_sessions) == 2
    # Most recent 2 should be kept
    assert remaining_sessions[0][0] == session_ids[4]
    assert remaining_sessions[1][0] == session_ids[3]


def test_cleanup_cascades_to_results(test_db):
    """Test that deleting a session also deletes its results"""
    # Create session with results
    session_id = test_db.create_session("test_algo", 100, total_analyzed=1, pass_count=1, close_count=0, fail_count=0)
    result_data = {
        'symbol': 'AAPL', 'company_name': 'Apple Inc.', 'country': 'United States',
        'market_cap': 2500000000000, 'sector': 'Technology', 'ipo_year': 1980,
        'price': 150.25, 'pe_ratio': 25.5, 'peg_ratio': 1.2, 'debt_to_equity': 0.35,
        'institutional_ownership': 0.45, 'earnings_cagr': 15.5, 'revenue_cagr': 12.3,
        'consistency_score': 85.0, 'peg_status': 'PASS', 'debt_status': 'PASS',
        'institutional_ownership_status': 'PASS', 'overall_status': 'PASS'
    }
    test_db.save_screening_result(session_id, result_data)

    # Create a newer session
    test_db.create_session("test_algo", 100, total_analyzed=0, pass_count=0, close_count=0, fail_count=0)

    # Cleanup, keeping only 1
    test_db.cleanup_old_sessions(keep_count=1)

    # Verify old session's results were deleted
    conn = test_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM screening_results WHERE session_id = %s", (session_id,))
    count = cursor.fetchone()[0]
    test_db.return_connection(conn)

    assert count == 0
