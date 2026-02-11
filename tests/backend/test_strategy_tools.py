# ABOUTME: Tests for strategy management tool executors (get, list, update, activity, decisions)
# ABOUTME: Follows the same mock-DB pattern as test_portfolio_tools.py

import json
import pytest
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()
sys.modules["fred_service"] = MagicMock()
sys.modules["characters"] = MagicMock()
sys.modules["stock_context"] = MagicMock()

from database import Database
from agent_tools import ToolExecutor


@pytest.fixture
def mock_db():
    db = MagicMock(spec=Database)
    return db


@pytest.fixture
def executor(mock_db):
    return ToolExecutor(mock_db)


# =========================================================================
# get_my_strategies
# =========================================================================

def test_get_my_strategies_returns_list(executor, mock_db):
    mock_db.get_user_strategies.return_value = [
        {
            'id': 1, 'name': 'Growth Play', 'enabled': True,
            'alpha': 5.2, 'last_run_date': '2026-02-10', 'last_run_status': 'success',
            'portfolio_name': 'My Portfolio',
        },
        {
            'id': 2, 'name': 'Value Hunt', 'enabled': False,
            'alpha': None, 'last_run_date': None, 'last_run_status': None,
            'portfolio_name': 'Value Portfolio',
        },
    ]

    result = executor._get_my_strategies(user_id=1)

    assert result['success'] is True
    assert len(result['strategies']) == 2
    mock_db.get_user_strategies.assert_called_once_with(1)


def test_get_my_strategies_empty(executor, mock_db):
    mock_db.get_user_strategies.return_value = []

    result = executor._get_my_strategies(user_id=99)

    assert result['success'] is True
    assert result['strategies'] == []


def test_get_my_strategies_db_error(executor, mock_db):
    mock_db.get_user_strategies.side_effect = Exception("DB down")

    result = executor._get_my_strategies(user_id=1)

    assert result['success'] is False
    assert 'DB down' in result['error']


# =========================================================================
# get_strategy
# =========================================================================

def test_get_strategy_success(executor, mock_db):
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'My Strategy',
        'conditions': json.dumps({'filters': []}),
        'position_sizing': json.dumps({'method': 'equal_weight', 'max_position_pct': 5.0}),
        'exit_conditions': json.dumps({'profit_target_pct': 50}),
        'enabled': True,
    }

    result = executor._get_strategy(strategy_id=5, user_id=1)

    assert result['success'] is True
    assert result['strategy']['name'] == 'My Strategy'
    mock_db.get_strategy.assert_called_once_with(5)


def test_get_strategy_not_found(executor, mock_db):
    mock_db.get_strategy.return_value = None

    result = executor._get_strategy(strategy_id=999, user_id=1)

    assert result['success'] is False
    assert 'not found' in result['error'].lower()


def test_get_strategy_unauthorized(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 2, 'name': 'Other User'}

    result = executor._get_strategy(strategy_id=5, user_id=1)

    assert result['success'] is False
    assert 'unauthorized' in result['error'].lower()


def test_get_strategy_parses_json_strings(executor, mock_db):
    """JSON string fields from DB should be parsed into dicts."""
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'S',
        'conditions': '{"filters": []}',
        'position_sizing': '{"method": "equal_weight"}',
        'exit_conditions': '{"stop_loss_pct": -20}',
    }

    result = executor._get_strategy(strategy_id=5, user_id=1)

    assert result['success'] is True
    strat = result['strategy']
    assert isinstance(strat['conditions'], dict)
    assert isinstance(strat['position_sizing'], dict)
    assert isinstance(strat['exit_conditions'], dict)


# =========================================================================
# update_strategy
# =========================================================================

def test_update_strategy_name_only(executor, mock_db):
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'Old Name',
        'position_sizing': {'method': 'equal_weight', 'max_position_pct': 5.0},
        'exit_conditions': {},
    }
    mock_db.update_strategy.return_value = True

    result = executor._update_strategy(strategy_id=5, user_id=1, name='New Name')

    assert result['success'] is True
    mock_db.update_strategy.assert_called_once_with(1, 5, name='New Name')


def test_update_strategy_unauthorized(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 2, 'name': 'Other'}

    result = executor._update_strategy(strategy_id=5, user_id=1, name='Hacked')

    assert result['success'] is False
    assert 'unauthorized' in result['error'].lower()
    mock_db.update_strategy.assert_not_called()


def test_update_strategy_position_sizing_merge(executor, mock_db):
    """Updating max_position_pct should preserve other position_sizing fields."""
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'S',
        'position_sizing': {'method': 'equal_weight', 'max_position_pct': 5.0},
        'exit_conditions': {},
    }
    mock_db.update_strategy.return_value = True

    result = executor._update_strategy(strategy_id=5, user_id=1, max_position_pct=10.0)

    assert result['success'] is True
    call_kwargs = mock_db.update_strategy.call_args[1]
    assert call_kwargs['position_sizing']['method'] == 'equal_weight'
    assert call_kwargs['position_sizing']['max_position_pct'] == 10.0


def test_update_strategy_position_sizing_method_merge(executor, mock_db):
    """Updating method should preserve max_position_pct."""
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'S',
        'position_sizing': {'method': 'equal_weight', 'max_position_pct': 5.0},
        'exit_conditions': {},
    }
    mock_db.update_strategy.return_value = True

    result = executor._update_strategy(strategy_id=5, user_id=1, position_sizing_method='kelly_criterion')

    call_kwargs = mock_db.update_strategy.call_args[1]
    assert call_kwargs['position_sizing']['method'] == 'kelly_criterion'
    assert call_kwargs['position_sizing']['max_position_pct'] == 5.0


def test_update_strategy_exit_conditions_merge(executor, mock_db):
    """Updating stop_loss_pct should preserve profit_target_pct."""
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'S',
        'position_sizing': {'method': 'equal_weight', 'max_position_pct': 5.0},
        'exit_conditions': {'profit_target_pct': 50.0},
    }
    mock_db.update_strategy.return_value = True

    result = executor._update_strategy(strategy_id=5, user_id=1, stop_loss_pct=-20.0)

    call_kwargs = mock_db.update_strategy.call_args[1]
    assert call_kwargs['exit_conditions']['stop_loss_pct'] == -20.0
    assert call_kwargs['exit_conditions']['profit_target_pct'] == 50.0


def test_update_strategy_filters_replaces(executor, mock_db):
    """Updating filters fully replaces conditions.filters."""
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'S',
        'conditions': {'filters': [{'field': 'pe_ratio', 'operator': '<', 'value': 20}]},
        'position_sizing': {'method': 'equal_weight', 'max_position_pct': 5.0},
        'exit_conditions': {},
    }
    mock_db.update_strategy.return_value = True
    new_filters = [{'field': 'revenue_growth', 'operator': '>', 'value': 10}]

    result = executor._update_strategy(strategy_id=5, user_id=1, filters=new_filters)

    call_kwargs = mock_db.update_strategy.call_args[1]
    conditions = call_kwargs['conditions']
    assert conditions['filters'] == new_filters


def test_update_strategy_json_string_position_sizing(executor, mock_db):
    """position_sizing returned as JSON string should be parsed before merging."""
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'S',
        'position_sizing': '{"method": "equal_weight", "max_position_pct": 5.0}',
        'exit_conditions': '{}',
    }
    mock_db.update_strategy.return_value = True

    result = executor._update_strategy(strategy_id=5, user_id=1, max_position_pct=8.0)

    assert result['success'] is True
    call_kwargs = mock_db.update_strategy.call_args[1]
    assert call_kwargs['position_sizing']['max_position_pct'] == 8.0


def test_update_strategy_enabled(executor, mock_db):
    mock_db.get_strategy.return_value = {
        'id': 5, 'user_id': 1, 'name': 'S',
        'position_sizing': {'method': 'equal_weight', 'max_position_pct': 5.0},
        'exit_conditions': {},
    }
    mock_db.update_strategy.return_value = True

    result = executor._update_strategy(strategy_id=5, user_id=1, enabled=False)

    assert result['success'] is True
    mock_db.update_strategy.assert_called_once_with(1, 5, enabled=False)


# =========================================================================
# get_strategy_activity
# =========================================================================

def test_get_strategy_activity_success(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1, 'name': 'S'}
    mock_db.get_strategy_runs.return_value = [
        {'id': 10, 'strategy_id': 5, 'started_at': '2026-02-10', 'status': 'success',
         'trades_executed': 3, 'stocks_screened': 100},
    ]
    mock_db.get_strategy_performance.return_value = [
        {'snapshot_date': '2026-02-10', 'portfolio_return_pct': 2.5, 'alpha': 1.1},
    ]

    result = executor._get_strategy_activity(strategy_id=5, user_id=1)

    assert result['success'] is True
    assert len(result['runs']) == 1
    mock_db.get_strategy_runs.assert_called_once_with(5, 5)  # default limit=5


def test_get_strategy_activity_custom_limit(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1, 'name': 'S'}
    mock_db.get_strategy_runs.return_value = []
    mock_db.get_strategy_performance.return_value = []

    executor._get_strategy_activity(strategy_id=5, user_id=1, limit=10)

    mock_db.get_strategy_runs.assert_called_once_with(5, 10)


def test_get_strategy_activity_unauthorized(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 2}

    result = executor._get_strategy_activity(strategy_id=5, user_id=1)

    assert result['success'] is False
    assert 'unauthorized' in result['error'].lower()


def test_get_strategy_activity_performance_sliced(executor, mock_db):
    """Performance history should be limited to match run count."""
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1, 'name': 'S'}
    mock_db.get_strategy_runs.return_value = [
        {'id': i, 'strategy_id': 5, 'started_at': f'2026-02-0{i}', 'status': 'success',
         'trades_executed': 0, 'stocks_screened': 10}
        for i in range(1, 4)
    ]
    # Return more performance records than runs
    mock_db.get_strategy_performance.return_value = [
        {'snapshot_date': f'2026-02-0{i}', 'portfolio_return_pct': float(i), 'alpha': 0.1}
        for i in range(1, 10)
    ]

    result = executor._get_strategy_activity(strategy_id=5, user_id=1, limit=3)

    assert result['success'] is True
    assert len(result['performance']) <= 3


# =========================================================================
# get_strategy_decisions
# =========================================================================

SAMPLE_DECISIONS = [
    {'id': 1, 'symbol': 'AAPL', 'final_decision': 'BUY', 'lynch_score': 75.0,
     'buffett_score': 80.0, 'thesis_summary': 'Strong growth', 'shares_traded': 10},
    {'id': 2, 'symbol': 'MSFT', 'final_decision': 'SKIP', 'lynch_score': 55.0,
     'buffett_score': 60.0, 'thesis_summary': 'Too expensive', 'shares_traded': None},
    {'id': 3, 'symbol': 'TSLA', 'final_decision': 'SELL', 'lynch_score': 40.0,
     'buffett_score': 45.0, 'thesis_summary': 'Declining metrics', 'shares_traded': 5},
]


def test_get_strategy_decisions_defaults_to_latest_run(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1}
    mock_db.get_strategy_runs.return_value = [
        {'id': 42, 'strategy_id': 5, 'started_at': '2026-02-10'},
        {'id': 41, 'strategy_id': 5, 'started_at': '2026-02-09'},
    ]
    mock_db.get_run_decisions.return_value = SAMPLE_DECISIONS

    result = executor._get_strategy_decisions(strategy_id=5, user_id=1)

    assert result['success'] is True
    mock_db.get_run_decisions.assert_called_once_with(42)  # latest run


def test_get_strategy_decisions_explicit_run_id(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1}
    mock_db.get_run_decisions.return_value = SAMPLE_DECISIONS

    result = executor._get_strategy_decisions(strategy_id=5, user_id=1, run_id=41)

    mock_db.get_run_decisions.assert_called_once_with(41)
    mock_db.get_strategy_runs.assert_not_called()


def test_get_strategy_decisions_filter_buys(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1}
    mock_db.get_strategy_runs.return_value = [{'id': 42}]
    mock_db.get_run_decisions.return_value = SAMPLE_DECISIONS

    result = executor._get_strategy_decisions(strategy_id=5, user_id=1, filter='buys')

    assert result['success'] is True
    assert all(d['final_decision'] == 'BUY' for d in result['decisions'])
    assert len(result['decisions']) == 1


def test_get_strategy_decisions_filter_sells(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1}
    mock_db.get_strategy_runs.return_value = [{'id': 42}]
    mock_db.get_run_decisions.return_value = SAMPLE_DECISIONS

    result = executor._get_strategy_decisions(strategy_id=5, user_id=1, filter='sells')

    assert all(d['final_decision'] == 'SELL' for d in result['decisions'])
    assert len(result['decisions']) == 1


def test_get_strategy_decisions_filter_trades(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1}
    mock_db.get_strategy_runs.return_value = [{'id': 42}]
    mock_db.get_run_decisions.return_value = SAMPLE_DECISIONS

    result = executor._get_strategy_decisions(strategy_id=5, user_id=1, filter='trades')

    # trades = BUY + SELL, not SKIP
    assert all(d['final_decision'] in ('BUY', 'SELL') for d in result['decisions'])
    assert len(result['decisions']) == 2


def test_get_strategy_decisions_filter_all(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1}
    mock_db.get_strategy_runs.return_value = [{'id': 42}]
    mock_db.get_run_decisions.return_value = SAMPLE_DECISIONS

    result = executor._get_strategy_decisions(strategy_id=5, user_id=1, filter='all')

    assert len(result['decisions']) == 3


def test_get_strategy_decisions_no_runs(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 1}
    mock_db.get_strategy_runs.return_value = []

    result = executor._get_strategy_decisions(strategy_id=5, user_id=1)

    assert result['success'] is False
    assert 'no runs' in result['error'].lower()


def test_get_strategy_decisions_unauthorized(executor, mock_db):
    mock_db.get_strategy.return_value = {'id': 5, 'user_id': 2}

    result = executor._get_strategy_decisions(strategy_id=5, user_id=1)

    assert result['success'] is False
    assert 'unauthorized' in result['error'].lower()
