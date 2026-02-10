# ABOUTME: Unit tests for the three-phase trade execution methods
# ABOUTME: Tests _process_exits, _calculate_all_positions, and _execute_buys independently

import pytest
from unittest.mock import MagicMock, patch, call
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()
sys.modules["price_history_fetcher"] = MagicMock()
sys.modules["sec_data_fetcher"] = MagicMock()
sys.modules["news_fetcher"] = MagicMock()
sys.modules["material_events_fetcher"] = MagicMock()
sys.modules["sec_rate_limiter"] = MagicMock()
sys.modules["yfinance.cache"] = MagicMock()
sys.modules["portfolio_service"] = MagicMock()

from strategy_executor import StrategyExecutor
from strategy_executor.models import ExitSignal


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_portfolio_summary.return_value = {'cash': 10000.0, 'total_value': 50000.0}
    db.get_portfolio.return_value = {'user_id': 42}
    db.get_alerts.return_value = []
    return db


@pytest.fixture
def executor(mock_db):
    with patch('strategy_executor.PositionSizer'):
        exe = StrategyExecutor(mock_db)
        return exe


def make_exit(symbol, quantity=10, current_value=1000.0):
    return ExitSignal(symbol=symbol, quantity=quantity, reason='Test reason',
                      current_value=current_value, gain_pct=5.0)


# ---------------------------------------------------------------------------
# _process_exits tests
# ---------------------------------------------------------------------------

def test_process_exits_market_open(executor, mock_db):
    """Market open: sells execute via execute_trade, returns (count, proceeds)."""
    import portfolio_service
    portfolio_service.execute_trade.return_value = {'success': True}

    exits = [make_exit('AAPL', quantity=5, current_value=750.0),
              make_exit('TSLA', quantity=10, current_value=2000.0)]

    count, proceeds = executor._process_exits(
        exits=exits,
        portfolio_id=1,
        is_market_open=True,
        user_id=42,
        existing_alerts=[],
        run_id=1
    )

    assert count == 2
    assert proceeds == 2750.0
    assert portfolio_service.execute_trade.call_count == 2


def test_process_exits_market_closed(executor, mock_db):
    """Market closed: creates sell alerts, returns (count, anticipated_proceeds)."""
    mock_db.create_alert.side_effect = [101, 102]

    exits = [make_exit('AAPL', quantity=5, current_value=750.0),
              make_exit('TSLA', quantity=10, current_value=2000.0)]

    count, proceeds = executor._process_exits(
        exits=exits,
        portfolio_id=1,
        is_market_open=False,
        user_id=42,
        existing_alerts=[],
        run_id=1
    )

    assert count == 2
    assert proceeds == 2750.0
    assert mock_db.create_alert.call_count == 2
    # Verify it created market_sell alerts
    call_kwargs = [c.kwargs for c in mock_db.create_alert.call_args_list]
    assert all(kw['action_type'] == 'market_sell' for kw in call_kwargs)


def test_process_exits_skips_duplicates(executor, mock_db):
    """Idempotency: already-queued sell alerts are skipped."""
    existing_alerts = [
        {'symbol': 'AAPL', 'action_type': 'market_sell', 'portfolio_id': 1}
    ]
    exits = [make_exit('AAPL'), make_exit('TSLA')]
    mock_db.create_alert.return_value = 101

    count, proceeds = executor._process_exits(
        exits=exits,
        portfolio_id=1,
        is_market_open=False,
        user_id=42,
        existing_alerts=existing_alerts,
        run_id=1
    )

    # Only TSLA should be queued
    assert mock_db.create_alert.call_count == 1
    assert mock_db.create_alert.call_args.kwargs['symbol'] == 'TSLA'
    # But count still includes the duplicate (was already queued)
    assert count == 2


# ---------------------------------------------------------------------------
# _execute_buys tests
# ---------------------------------------------------------------------------

def _make_position(shares=10, estimated_value=1500.0):
    pos = MagicMock()
    pos.shares = shares
    pos.estimated_value = estimated_value
    pos.position_pct = 1.5
    pos.reasoning = 'Test'
    return pos


def test_execute_buys_market_open(executor, mock_db):
    """Market open: buys execute via execute_trade, decision records updated."""
    import portfolio_service
    portfolio_service.execute_trade.reset_mock()
    portfolio_service.execute_trade.return_value = {'success': True, 'transaction_id': 999}

    prioritized = [
        {'symbol': 'MSFT', 'decision': {'id': 10, 'position_type': 'new', 'consensus_reasoning': ''},
         'position': _make_position(shares=5, estimated_value=1000.0)},
    ]

    count = executor._execute_buys(
        prioritized_positions=prioritized,
        portfolio_id=1,
        is_market_open=True,
        user_id=42,
        existing_alerts=[],
        run_id=1
    )

    assert count == 1
    portfolio_service.execute_trade.assert_called_once()
    mock_db.update_strategy_decision.assert_called_once()


def test_execute_buys_market_closed(executor, mock_db):
    """Market closed: creates buy alerts, skips duplicates."""
    mock_db.create_alert.side_effect = [201, 202]

    # AAPL already queued, GOOG is new
    existing_alerts = [
        {'symbol': 'AAPL', 'action_type': 'market_buy', 'portfolio_id': 1}
    ]

    prioritized = [
        {'symbol': 'AAPL', 'decision': {'id': 11, 'position_type': 'new', 'consensus_reasoning': ''},
         'position': _make_position(shares=10, estimated_value=1500.0)},
        {'symbol': 'GOOG', 'decision': {'id': 12, 'position_type': 'new', 'consensus_reasoning': ''},
         'position': _make_position(shares=5, estimated_value=2000.0)},
    ]

    count = executor._execute_buys(
        prioritized_positions=prioritized,
        portfolio_id=1,
        is_market_open=False,
        user_id=42,
        existing_alerts=existing_alerts,
        run_id=1
    )

    # Both count (one duplicate, one new)
    assert count == 2
    # Only one alert created (GOOG)
    assert mock_db.create_alert.call_count == 1
    assert mock_db.create_alert.call_args.kwargs['symbol'] == 'GOOG'


# ---------------------------------------------------------------------------
# _execute_trades integration: cash anticipation
# ---------------------------------------------------------------------------

def test_execute_trades_uses_anticipated_cash(executor, mock_db):
    """When market closed, position sizing uses db_cash + anticipated_proceeds and excludes exited holdings."""
    import portfolio_service
    portfolio_service.is_market_open.return_value = False

    # DB cash is 5000, we will sell 2000 worth of stock off-hours
    mock_db.get_portfolio_summary.return_value = {'cash': 5000.0, 'total_value': 20000.0}
    mock_db.create_alert.return_value = 999
    mock_db.get_portfolio_holdings.return_value = {'TSLA': 10, 'MSFT': 5}

    exits = [make_exit('TSLA', quantity=10, current_value=2000.0)]
    buy_decisions = [{'symbol': 'MSFT', 'consensus_score': 80, 'id': 300, 'position_type': 'new'}]

    captured = {}

    def spy_prioritize(buy_decisions, available_cash, portfolio_value, portfolio_id,
                       method, rules, holdings=None, **kwargs):
        captured['available_cash'] = available_cash
        captured['holdings'] = holdings
        return []

    executor.position_sizer.prioritize_positions = spy_prioritize

    strategy = {
        'portfolio_id': 1,
        'position_sizing': {'method': 'equal_weight'}
    }

    executor._execute_trades(
        buy_decisions=buy_decisions,
        exits=exits,
        strategy=strategy,
        run_id=1
    )

    # Should be db_cash (5000) + anticipated_proceeds (2000) = 7000
    assert captured['available_cash'] == 7000.0
    # TSLA was exited, should not appear in holdings passed to prioritize_positions
    assert 'TSLA' not in captured['holdings']


# ---------------------------------------------------------------------------
# Deliberation exit tests
# ---------------------------------------------------------------------------

def test_deliberation_exits_on_held_positions(executor, mock_db):
    """AVOID verdict on a held position produces an ExitSignal."""
    held_symbols = {'AAPL'}
    mock_db.create_strategy_decision.return_value = 1

    # A held stock that gets AVOID
    enriched = [
        {
            'symbol': 'AAPL',
            'lynch_thesis': 'Some thesis',
            'buffett_thesis': 'Some thesis',
            'lynch_thesis_verdict': 'AVOID',
            'buffett_thesis_verdict': 'AVOID',
            'lynch_score': 40,
            'lynch_status': 'poor',
            'buffett_score': 35,
            'buffett_status': 'poor',
        }
    ]

    with patch.object(executor, '_conduct_deliberation', return_value=('Avoid text', 'AVOID')):
        buy_decisions, deliberation_exits = executor._deliberate(
            enriched=enriched,
            run_id=1,
            conditions={},
            held_symbols=held_symbols
        )

    assert len(buy_decisions) == 0
    assert len(deliberation_exits) == 1
    assert deliberation_exits[0].symbol == 'AAPL'
    assert deliberation_exits[0].reason.startswith('Deliberation')


def test_deliberation_watch_does_not_exit(executor, mock_db):
    """WATCH verdict on a held position produces no ExitSignal."""
    held_symbols = {'AAPL'}
    mock_db.create_strategy_decision.return_value = 1

    enriched = [
        {
            'symbol': 'AAPL',
            'lynch_thesis': 'Some thesis',
            'buffett_thesis': 'Some thesis',
            'lynch_thesis_verdict': 'WATCH',
            'buffett_thesis_verdict': 'WATCH',
            'lynch_score': 60,
            'lynch_status': 'ok',
            'buffett_score': 55,
            'buffett_status': 'ok',
        }
    ]

    with patch.object(executor, '_conduct_deliberation', return_value=('Watch text', 'WATCH')):
        buy_decisions, deliberation_exits = executor._deliberate(
            enriched=enriched,
            run_id=1,
            conditions={},
            held_symbols=held_symbols
        )

    assert len(deliberation_exits) == 0
