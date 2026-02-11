import pytest
import sys
import os
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from strategy_executor.position_sizing import PositionSizer
from strategy_executor.models import TargetAllocation, ExitSignal, PositionSize

@pytest.fixture
def mock_db():
    db = MagicMock()
    return db

@pytest.fixture
def sizer(mock_db):
    sizer = PositionSizer(mock_db)
    # Mock _fetch_price to avoid DB calls
    sizer._fetch_price = MagicMock(return_value=100.0) 
    return sizer

def test_calculate_target_allocations_equal_weight(sizer):
    """Test basic equal weight allocation."""
    candidates = [
        {'symbol': 'AAPL', 'conviction': 90, 'price': 150},
        {'symbol': 'MSFT', 'conviction': 80, 'price': 250},
    ]
    portfolio_value = 10000
    
    allocations = sizer._calculate_ideal_allocation(
        candidates, portfolio_value, 'equal_weight', {'max_positions': 5}
    )
    
    assert len(allocations) == 2
    assert allocations[0].symbol == 'AAPL'
    assert allocations[0].target_value == 5000  # 10000 / 2
    assert allocations[1].symbol == 'MSFT'
    assert allocations[1].target_value == 5000

def test_fully_invested_swap(sizer):
    """
    Scenario: User holds 2 stocks (A, B). 
    New candidate C appears with higher conviction than B.
    Max positions = 2.
    Expectation: Sell B, Buy C. Keep A.
    """
    # Current Holdings: A ($5000), B ($5000)
    holdings = {'A': 50, 'B': 50} # Price $100
    portfolio_value = 10000
    
    # Candidates: A (90), C (85), B (50)
    candidates = [
        {'symbol': 'A', 'conviction': 90, 'price': 100},
        {'symbol': 'C', 'conviction': 85, 'price': 100},
        {'symbol': 'B', 'conviction': 50, 'price': 100},
    ]
    
    rules = {'max_positions': 2}
    
    sells, buys = sizer.calculate_target_orders(
        1, candidates, portfolio_value, holdings, 'equal_weight', rules
    )
    
    # Verify Sells
    # B should be sold fully (displaced)
    assert len(sells) == 1
    assert sells[0].symbol == 'B'
    assert sells[0].exit_type == 'full'
    assert sells[0].quantity == 50
    
    # Verify Buys
    # C should be bought
    assert len(buys) == 1
    assert buys[0]['symbol'] == 'C'
    # Target for C is 5000 (10000 / 2)
    # Price 100 -> 50 shares
    assert buys[0]['position'].shares == 50

def test_cash_trap_rebalance(sizer):
    """
    Scenario: Fully invested in A (100%).
    New candidate B appears (equal conviction).
    Expectation: Trim A to 50%, Buy B to 50%.
    """
    holdings = {'A': 100} # $100 * 100 = $10,000
    portfolio_value = 10000
    
    candidates = [
        {'symbol': 'A', 'conviction': 90, 'price': 100},
        {'symbol': 'B', 'conviction': 90, 'price': 100},
    ]
    
    rules = {'max_positions': 2, 'min_trade_amount': 100}
    
    sells, buys = sizer.calculate_target_orders(
        1, candidates, portfolio_value, holdings, 'equal_weight', rules
    )
    
    # Target for A: $5000. Current: $10,000. Drift: -$5000.
    # Sell A: 50 shares.
    assert len(sells) == 1
    assert sells[0].symbol == 'A'
    assert sells[0].exit_type == 'trim'
    assert sells[0].quantity == 50
    
    # Target for B: $5000. Current: 0. Drift: $5000.
    # Buy B: 50 shares.
    assert len(buys) == 1
    assert buys[0]['symbol'] == 'B'
    assert buys[0]['position'].shares == 50

def test_drift_tolerance(sizer):
    """
    Scenario: Holding A ($5100). Target ($5000).
    Drift is -$100. Min trade amount is $200.
    Expectation: No trade.
    """
    holdings = {'A': 51} # $5100
    portfolio_value = 10000
    
    candidates = [
        {'symbol': 'A', 'conviction': 90, 'price': 100},
        {'symbol': 'B', 'conviction': 90, 'price': 100},
    ]
    
    # Target per stock = $5000
    
    rules = {'max_positions': 2, 'min_trade_amount': 200}
    
    sells, buys = sizer.calculate_target_orders(
        1, candidates, portfolio_value, holdings, 'equal_weight', rules
    )
    
    # A drift is -100 (abs < 200) -> No Sell
    # B drift is +5000 -> Buy B
    
    # Check Sells
    assert len(sells) == 0
    
    # Check Buys
    assert len(buys) == 1
    assert buys[0]['symbol'] == 'B'

def test_fixed_pct_sizing(sizer):
    """Test fixed percentage sizing ignores portfolio count and uses strict %."""
    candidates = [{'symbol': 'A', 'price': 100, 'conviction': 90}]
    portfolio_value = 100000

    rules = {'fixed_position_pct': 5.0} # Target $5000

    allocations = sizer._calculate_ideal_allocation(
        candidates, portfolio_value, 'fixed_pct', rules
    )

    assert len(allocations) == 1
    assert allocations[0].target_value == 5000


def test_candidate_prices_fetched_before_position_sizing():
    """
    Regression test: candidates built with price=0 must have prices populated
    before reaching PositionSizer, or _calculate_ideal_allocation silently returns
    empty list, causing all holdings to be sold.

    Verifies that _execute_trades fetches prices for candidates via
    fetch_current_prices_batch and populates them before calling calculate_target_orders.
    """
    from unittest.mock import patch, MagicMock
    from strategy_executor.trading import TradingMixin

    mixin = TradingMixin.__new__(TradingMixin)
    mock_db = MagicMock()
    mixin.db = mock_db

    mock_db.get_portfolio_summary.return_value = {'cash': 2500, 'total_value': 10000}
    mock_db.get_portfolio_holdings.return_value = {'AAPL': 50}
    mock_db.get_alerts.return_value = []

    buy_decisions = [{'symbol': 'MSFT', 'consensus_score': 85}]
    held_verdicts = [{'symbol': 'AAPL', 'consensus_score': 90}]

    captured_candidates = []

    def fake_calculate_target_orders(section_id, candidates, portfolio_value, holdings, method, rules, cash_available=0):
        captured_candidates.extend(candidates)
        return [], []

    mock_position_sizer = MagicMock()
    mock_position_sizer.calculate_target_orders.side_effect = fake_calculate_target_orders
    mixin.position_sizer = mock_position_sizer

    strategy = {
        'portfolio_id': 1,
        'position_sizing': {'method': 'equal_weight', 'max_positions': 5},
    }

    with patch('portfolio_service.is_market_open', return_value=False), \
         patch('strategy_executor.trading.fetch_current_prices_batch') as mock_fetch_prices:
        mock_fetch_prices.return_value = {'AAPL': 150.0, 'MSFT': 320.0}

        mixin._execute_trades(
            buy_decisions=buy_decisions,
            exits=[],
            strategy=strategy,
            run_id=42,
            held_verdicts=held_verdicts,
        )

    # Prices must be populated — not zero
    assert len(captured_candidates) == 2
    prices_by_symbol = {c['symbol']: c['price'] for c in captured_candidates}
    assert prices_by_symbol['AAPL'] == 150.0, "AAPL price should be fetched, not 0"
    assert prices_by_symbol['MSFT'] == 320.0, "MSFT price should be fetched, not 0"
