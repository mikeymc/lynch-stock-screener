# ABOUTME: Tests for consolidated exit detection (Phase 5)
# ABOUTME: Covers universe compliance exits, scoring fallback, and phase consolidation

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

from strategy_executor.exit_conditions import ExitConditionChecker
from strategy_executor.models import ExitSignal


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_portfolio_holdings_detailed.return_value = []
    db.get_position_entry_dates.return_value = {}
    return db


@pytest.fixture
def checker(mock_db):
    return ExitConditionChecker(mock_db)


# ---------------------------------------------------------------------------
# Universe compliance via set arithmetic
# ---------------------------------------------------------------------------

def test_universe_compliance_exit(checker):
    """Held symbol absent from filtered_candidates produces an ExitSignal."""
    held_symbols = {'AAPL', 'MSFT'}
    filtered_candidates = ['MSFT', 'GOOG']  # AAPL is missing
    holdings = {'AAPL': {'quantity': 10}, 'MSFT': {'quantity': 5}}

    exits = checker.check_universe_compliance(held_symbols, filtered_candidates, holdings)

    assert len(exits) == 1
    assert exits[0].symbol == 'AAPL'
    assert exits[0].quantity == 10
    assert 'universe' in exits[0].reason.lower()


def test_universe_compliance_no_exit_for_passing(checker):
    """Held symbol present in filtered_candidates produces no exit."""
    held_symbols = {'AAPL', 'MSFT'}
    filtered_candidates = ['AAPL', 'MSFT', 'GOOG']
    holdings = {'AAPL': {'quantity': 10}, 'MSFT': {'quantity': 5}}

    exits = checker.check_universe_compliance(held_symbols, filtered_candidates, holdings)

    assert exits == []


def test_universe_compliance_empty_holdings(checker):
    """No holdings means no exits."""
    exits = checker.check_universe_compliance(set(), ['AAPL', 'MSFT'], {})
    assert exits == []


# ---------------------------------------------------------------------------
# Default score degradation (applied when score_degradation not configured)
# ---------------------------------------------------------------------------

def _make_scoring_func(lynch_score, buffett_score):
    """Returns a scoring function that returns fixed scores."""
    def scoring_func(symbol):
        return {'lynch_score': lynch_score, 'buffett_score': buffett_score}
    return scoring_func


def test_default_score_degradation_applied_when_not_configured(mock_db, checker):
    """When no score_degradation configured, default (lynch_below=50, buffett_below=50) is used."""
    mock_db.get_portfolio_holdings_detailed.return_value = [
        {'symbol': 'AAPL', 'quantity': 10, 'current_value': 1200.0, 'total_cost': 1000.0}
    ]
    mock_db.get_position_entry_dates.return_value = {}

    # Both scores at 15 — below the default threshold of 50 (AND logic: both must fail)
    scoring_func = _make_scoring_func(lynch_score=15, buffett_score=15)

    # No score_degradation in exit_conditions
    exits = checker.check_exits(1, {}, scoring_func=scoring_func)

    assert len(exits) == 1
    assert exits[0].symbol == 'AAPL'
    assert 'degraded' in exits[0].reason.lower()


def test_explicit_score_degradation_overrides_default(mock_db, checker):
    """Explicit score_degradation config overrides the default thresholds."""
    mock_db.get_portfolio_holdings_detailed.return_value = [
        {'symbol': 'AAPL', 'quantity': 10, 'current_value': 1200.0, 'total_cost': 1000.0}
    ]
    mock_db.get_position_entry_dates.return_value = {}

    # Both scores at 35 — above default (50 AND) but below explicit threshold (40 AND)
    scoring_func = _make_scoring_func(lynch_score=35, buffett_score=35)

    exits = checker.check_exits(
        1,
        {'score_degradation': {'lynch_below': 40, 'buffett_below': 40}},
        scoring_func=scoring_func
    )

    assert len(exits) == 1
    assert exits[0].symbol == 'AAPL'


# ---------------------------------------------------------------------------
# Phase 5 consolidation: 3 sources merge into exits list (no scoring fallback)
# ---------------------------------------------------------------------------

def test_phase5_consolidation_all_sources_merged():
    """Integration: universe compliance + price/degradation exits + deliberation exits all reach _process_exits."""
    from strategy_executor import StrategyExecutor

    mock_db = MagicMock()
    mock_db.get_portfolio_summary.return_value = {'cash': 10000.0, 'total_value': 50000.0}
    mock_db.get_portfolio.return_value = {'user_id': 1}
    mock_db.get_alerts.return_value = []
    mock_db.get_strategy.return_value = {
        'id': 1,
        'name': 'Test',
        'enabled': True,
        'portfolio_id': 10,
        'conditions': {
            'scoring_requirements': [
                {'character': 'lynch', 'min_score': 60},
                {'character': 'buffett', 'min_score': 60},
            ]
        },
        'exit_conditions': {},
    }
    mock_db.create_strategy_run.return_value = 99
    mock_db.get_portfolio_holdings.return_value = {
        'AAPL': {'quantity': 10},  # will fail universe
        'MSFT': {'quantity': 5},
    }

    with patch('strategy_executor.PositionSizer'):
        executor = StrategyExecutor(mock_db)

    # Track all exits passed to _execute_trades
    captured_exits = {}

    def spy_execute_trades(buy_decisions, exits, strategy, run_id, **kwargs):
        captured_exits['exits'] = exits
        return 0

    executor._execute_trades = spy_execute_trades

    # Universe filter returns only MSFT (AAPL fails)
    universe_exits = [
        ExitSignal(symbol='AAPL', quantity=10, reason='No longer passes universe filters',
                   current_value=0.0, gain_pct=0.0)
    ]

    # Deliberation exit (from Phase 4)
    deliberation_exit = ExitSignal(
        symbol='NVDA', quantity=8, reason='Deliberation: AVOID verdict',
        current_value=900.0, gain_pct=2.0
    )

    with patch.object(executor.universe_filter, 'filter_universe', return_value=['MSFT']):
        with patch.object(executor.exit_checker, 'check_exits', return_value=[]):
            with patch.object(executor.exit_checker, 'check_universe_compliance',
                              return_value=universe_exits):
                with patch.object(executor, '_deliberate',
                                  return_value=([], [deliberation_exit], [])):
                    with patch.object(executor, '_score_candidates', return_value=([], [])):
                        with patch.object(executor, '_generate_theses', return_value=[]):
                            with patch('strategy_executor.core.get_spy_price', return_value=500.0):
                                executor.benchmark_tracker = MagicMock()
                                executor.benchmark_tracker.record_strategy_performance.return_value = {}
                                executor.execute_strategy(1)

    assert 'exits' in captured_exits, "_execute_trades was not called"
    exit_symbols = {e.symbol for e in captured_exits['exits']}
    assert 'AAPL' in exit_symbols, "Universe compliance exit missing"
    assert 'NVDA' in exit_symbols, "Deliberation exit missing"


# ---------------------------------------------------------------------------
# held_declined stocks routed through deliberation
# ---------------------------------------------------------------------------

def test_held_declined_get_deliberated():
    """Held stocks that fail addition scoring reach _deliberate as exit_only candidates."""
    from strategy_executor import StrategyExecutor

    mock_db = MagicMock()
    mock_db.get_portfolio_summary.return_value = {'cash': 10000.0, 'total_value': 50000.0}
    mock_db.get_portfolio.return_value = {'user_id': 1}
    mock_db.get_alerts.return_value = []
    mock_db.get_strategy.return_value = {
        'id': 1,
        'name': 'Test',
        'enabled': True,
        'portfolio_id': 10,
        'conditions': {},
        'exit_conditions': {},
    }
    mock_db.create_strategy_run.return_value = 99
    mock_db.get_portfolio_holdings.return_value = {'MSFT': {'quantity': 5}}

    with patch('strategy_executor.PositionSizer'):
        executor = StrategyExecutor(mock_db)

    executor._execute_trades = MagicMock(return_value=0)

    msft_declined = {'symbol': 'MSFT', 'lynch_score': 45, 'buffett_score': 40,
                     'lynch_status': 'FAIR', 'buffett_status': 'FAIR', 'position_type': 'held_exit_evaluation'}

    captured_deliberate_calls = {}

    def spy_deliberate(enriched, run_id, conditions=None, user_id=None, job_id=None,
                       held_symbols=None, holdings=None,
                       symbols_of_held_stocks_with_failing_scores=None):
        captured_deliberate_calls['exit_only_symbols'] = symbols_of_held_stocks_with_failing_scores
        captured_deliberate_calls['enriched_symbols'] = {s['symbol'] for s in enriched}
        return [], [], []

    executor._deliberate = spy_deliberate

    with patch.object(executor.universe_filter, 'filter_universe', return_value=['MSFT']):
        with patch.object(executor.exit_checker, 'check_exits', return_value=[]):
            with patch.object(executor.exit_checker, 'check_universe_compliance', return_value=[]):
                # _score_candidates for additions returns ([], [msft_declined])
                with patch.object(executor, '_score_candidates', return_value=([], [msft_declined])):
                    with patch.object(executor, '_generate_theses', side_effect=lambda stocks, *a, **kw: stocks):
                        with patch('strategy_executor.core.get_spy_price', return_value=500.0):
                            executor.benchmark_tracker = MagicMock()
                            executor.benchmark_tracker.record_strategy_performance.return_value = {}
                            executor.execute_strategy(1)

    assert 'MSFT' in captured_deliberate_calls.get('enriched_symbols', set()), \
        "MSFT should be in enriched for deliberation"
    assert 'MSFT' in captured_deliberate_calls.get('exit_only_symbols', set()), \
        "MSFT should be in exit_only_symbols"


def test_held_declined_avoid_exits():
    """Held declined stock with AVOID verdict → ExitSignal emitted."""
    from strategy_executor.deliberation import DeliberationMixin
    from strategy_executor.models import ExitSignal

    class TestExecutor(DeliberationMixin):
        def __init__(self):
            self.db = MagicMock()
            self.db.create_strategy_decision.return_value = 1

    executor = TestExecutor()

    msft = {
        'symbol': 'MSFT',
        'lynch_score': 45, 'lynch_status': 'FAIR',
        'buffett_score': 40, 'buffett_status': 'FAIR',
        'lynch_thesis': 'Lynch thesis text',
        'buffett_thesis': 'Buffett thesis text',
        'lynch_thesis_verdict': 'AVOID',
        'buffett_thesis_verdict': 'AVOID',
    }

    with patch.object(executor, '_conduct_deliberation', return_value=('deliberation text', 'AVOID')):
        decisions, exits, held_verdicts = executor._deliberate(
            enriched=[msft],
            run_id=1,
            held_symbols={'MSFT'},
            holdings={'MSFT': {'quantity': 5, 'current_value': 500.0, 'gain_pct': -5.0}},
            symbols_of_held_stocks_with_failing_scores={'MSFT'}
        )

    assert decisions == [], "AVOID should not produce a buy decision"
    assert len(exits) == 1
    assert exits[0].symbol == 'MSFT'


def test_held_declined_buy_does_not_add_position():
    """Held declined stock with BUY verdict → not added to buy decisions (treated as HOLD)."""
    from strategy_executor.deliberation import DeliberationMixin

    class TestExecutor(DeliberationMixin):
        def __init__(self):
            self.db = MagicMock()
            self.db.create_strategy_decision.return_value = 1

    executor = TestExecutor()

    msft = {
        'symbol': 'MSFT',
        'lynch_score': 45, 'lynch_status': 'FAIR',
        'buffett_score': 40, 'buffett_status': 'FAIR',
        'lynch_thesis': 'Lynch thesis text',
        'buffett_thesis': 'Buffett thesis text',
        'lynch_thesis_verdict': 'BUY',
        'buffett_thesis_verdict': 'BUY',
    }

    with patch.object(executor, '_conduct_deliberation', return_value=('deliberation text', 'BUY')):
        decisions, exits, held_verdicts = executor._deliberate(
            enriched=[msft],
            run_id=1,
            held_symbols={'MSFT'},
            holdings={'MSFT': {'quantity': 5, 'current_value': 500.0, 'gain_pct': 2.0}},
            symbols_of_held_stocks_with_failing_scores={'MSFT'}
        )

    assert decisions == [], "BUY on held_declined should not add to buy decisions"
    assert exits == [], "BUY on held_declined should not exit either"
