# ABOUTME: Tests for strategy briefings database operations
# ABOUTME: Validates save, retrieve by portfolio, and retrieve by run_id

import pytest
import json
from datetime import datetime


@pytest.fixture
def setup_briefing_prereqs(test_db):
    """Create user, portfolio, strategy, and run needed for briefing tests."""
    db = test_db
    conn = db.get_connection()
    cursor = conn.cursor()

    # Create user
    cursor.execute("""
        INSERT INTO users (id, email, name, google_id)
        VALUES (1, 'test@test.com', 'Test User', 'google_1')
    """)

    # Create portfolio
    cursor.execute("""
        INSERT INTO portfolios (id, user_id, name, initial_cash)
        VALUES (1, 1, 'Test Portfolio', 100000.0)
    """)

    # Create strategy
    cursor.execute("""
        INSERT INTO investment_strategies (id, user_id, portfolio_id, name, conditions)
        VALUES (1, 1, 1, 'Test Strategy', '{}')
    """)

    # Create strategy run
    cursor.execute("""
        INSERT INTO strategy_runs (id, strategy_id, status)
        VALUES (1, 1, 'completed')
    """)

    conn.commit()
    db.return_connection(conn)

    return db


def test_save_briefing(setup_briefing_prereqs):
    """Test saving a briefing and retrieving it."""
    db = setup_briefing_prereqs

    briefing_data = {
        'run_id': 1,
        'strategy_id': 1,
        'portfolio_id': 1,
        'stocks_screened': 500,
        'stocks_scored': 25,
        'theses_generated': 10,
        'trades_executed': 3,
        'portfolio_value': 102500.0,
        'portfolio_return_pct': 2.5,
        'spy_return_pct': 1.2,
        'alpha': 1.3,
        'buys_json': json.dumps([
            {'symbol': 'AAPL', 'shares': 10, 'price': 180.0, 'reasoning': 'Strong growth'}
        ]),
        'sells_json': json.dumps([]),
        'holds_json': json.dumps([
            {'symbol': 'MSFT', 'verdict': 'HOLD', 'reasoning': 'Still on track'}
        ]),
        'watchlist_json': json.dumps([]),
        'executive_summary': 'The strategy screened 500 stocks and executed 3 trades.',
    }

    briefing_id = db.save_briefing(briefing_data)
    assert briefing_id is not None
    assert briefing_id > 0


def test_get_briefings_for_portfolio(setup_briefing_prereqs):
    """Test retrieving briefings for a portfolio."""
    db = setup_briefing_prereqs

    # Save a briefing
    briefing_data = {
        'run_id': 1,
        'strategy_id': 1,
        'portfolio_id': 1,
        'stocks_screened': 500,
        'stocks_scored': 25,
        'theses_generated': 10,
        'trades_executed': 3,
        'portfolio_value': 102500.0,
        'portfolio_return_pct': 2.5,
        'spy_return_pct': 1.2,
        'alpha': 1.3,
        'buys_json': json.dumps([]),
        'sells_json': json.dumps([]),
        'holds_json': json.dumps([]),
        'watchlist_json': json.dumps([]),
        'executive_summary': 'Test summary.',
    }
    db.save_briefing(briefing_data)

    # Retrieve
    briefings = db.get_briefings_for_portfolio(1)
    assert len(briefings) == 1
    assert briefings[0]['stocks_screened'] == 500
    assert briefings[0]['trades_executed'] == 3
    assert briefings[0]['executive_summary'] == 'Test summary.'
    assert briefings[0]['portfolio_value'] == 102500.0


def test_get_briefing_by_run(setup_briefing_prereqs):
    """Test retrieving a briefing by run_id."""
    db = setup_briefing_prereqs

    briefing_data = {
        'run_id': 1,
        'strategy_id': 1,
        'portfolio_id': 1,
        'stocks_screened': 100,
        'stocks_scored': 10,
        'theses_generated': 5,
        'trades_executed': 2,
        'portfolio_value': 101000.0,
        'portfolio_return_pct': 1.0,
        'spy_return_pct': 0.5,
        'alpha': 0.5,
        'buys_json': json.dumps([]),
        'sells_json': json.dumps([]),
        'holds_json': json.dumps([]),
        'watchlist_json': json.dumps([]),
        'executive_summary': 'Run 1 summary.',
    }
    db.save_briefing(briefing_data)

    briefing = db.get_briefing_by_run(1)
    assert briefing is not None
    assert briefing['run_id'] == 1
    assert briefing['executive_summary'] == 'Run 1 summary.'


def test_get_briefing_by_run_not_found(setup_briefing_prereqs):
    """Test retrieving a briefing for a non-existent run returns None."""
    db = setup_briefing_prereqs
    briefing = db.get_briefing_by_run(999)
    assert briefing is None


def test_save_briefing_unique_run_id(setup_briefing_prereqs):
    """Test that saving two briefings for the same run_id raises an error."""
    db = setup_briefing_prereqs

    briefing_data = {
        'run_id': 1,
        'strategy_id': 1,
        'portfolio_id': 1,
        'stocks_screened': 100,
        'stocks_scored': 10,
        'theses_generated': 5,
        'trades_executed': 2,
        'portfolio_value': 101000.0,
        'buys_json': json.dumps([]),
        'sells_json': json.dumps([]),
        'holds_json': json.dumps([]),
        'watchlist_json': json.dumps([]),
        'executive_summary': 'First briefing.',
    }
    db.save_briefing(briefing_data)

    # Second save for same run should fail
    with pytest.raises(Exception):
        db.save_briefing(briefing_data)
