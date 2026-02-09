
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock dependencies
sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()
sys.modules["price_history_fetcher"] = MagicMock()
sys.modules["sec_data_fetcher"] = MagicMock()
sys.modules["news_fetcher"] = MagicMock()
sys.modules["material_events_fetcher"] = MagicMock()
sys.modules["sec_rate_limiter"] = MagicMock()
sys.modules["yfinance.cache"] = MagicMock()
sys.modules["portfolio_service"] = MagicMock()

from backend.strategy_executor.executor import StrategyExecutor

@pytest.fixture
def mock_db():
    db = MagicMock()
    return db

@pytest.fixture
def executor(mock_db):
    with patch('backend.strategy_executor.executor.PositionSizer'):
        exe = StrategyExecutor(mock_db)
        return exe

def test_execute_trades_idempotency_market_closed(executor, mock_db):
    """Test that duplicate alerts are not created when market is closed."""
    import portfolio_service
    
    # Setup mocks
    portfolio_service.is_market_open.return_value = False
    
    portfolio_id = 1
    user_id = 42
    run_id = 100
    
    strategy = {
        'id': 1,
        'portfolio_id': portfolio_id,
        'position_sizing': {'method': 'fixed_pct'}
    }
    
    mock_db.get_portfolio.return_value = {'user_id': user_id}
    mock_db.get_portfolio_summary.return_value = {'cash': 10000}
    
    # Mock existing alerts: Symbol 'AAPL' already has a BUY queued
    mock_db.get_alerts.return_value = [
        {
            'symbol': 'AAPL',
            'action_type': 'market_buy',
            'status': 'active',
            'portfolio_id': portfolio_id
        }
    ]
    
    # Decisions: AAPL (duplicate) and GOOG (new)
    buy_decisions = [
        {'symbol': 'AAPL', 'consensus_score': 80, 'id': 201, 'position_type': 'new'},
        {'symbol': 'GOOG', 'consensus_score': 85, 'id': 202, 'position_type': 'new'}
    ]
    
    # Mock position sizing (shares > 0)
    mock_pos_sizer = executor.position_sizer
    mock_pos_sizer.calculate_position.side_effect = [
        MagicMock(shares=10, estimated_value=1500.0, position_pct=1.5, status='queued', reasoning="Test"),
        MagicMock(shares=5, estimated_value=2000.0, position_pct=2.0, status='queued', reasoning="Test")
    ]
    
    # Run execution
    executor._execute_trades(
        buy_decisions=buy_decisions,
        exits=[],
        strategy=strategy,
        run_id=run_id
    )
    
    # Verify results
    # AAPL should be skipped (duplicate)
    # GOOG should be created
    
    # create_alert should only be called ONCE for GOOG
    assert mock_db.create_alert.call_count == 1
    args, kwargs = mock_db.create_alert.call_args
    assert kwargs['symbol'] == 'GOOG'
    assert kwargs['action_type'] == 'market_buy'
    
    # Verify AAPL was not called
    for call in mock_db.create_alert.call_args_list:
        assert call.kwargs['symbol'] != 'AAPL'

def test_execute_trades_idempotency_sells(executor, mock_db):
    """Test that duplicate SELL alerts are not created."""
    import portfolio_service
    from backend.strategy_executor.models import ExitSignal
    
    portfolio_service.is_market_open.return_value = False
    
    portfolio_id = 1
    user_id = 42
    run_id = 100
    
    strategy = {'portfolio_id': portfolio_id}
    mock_db.get_portfolio.return_value = {'user_id': user_id}
    mock_db.get_portfolio_summary.return_value = {'cash': 10000}
    
    # Mock existing alerts: TSLA already has a SELL queued
    mock_db.get_alerts.return_value = [
        {
            'symbol': 'TSLA',
            'action_type': 'market_sell',
            'status': 'active',
            'portfolio_id': portfolio_id
        }
    ]
    
    exits = [
        ExitSignal(symbol='TSLA', quantity=50, reason='Profit taking', current_value=5000.0, gain_pct=10.0),
        ExitSignal(symbol='MSFT', quantity=20, reason='Stop loss', current_value=6000.0, gain_pct=-5.0)
    ]
    
    # Run execution
    executor._execute_trades(
        buy_decisions=[],
        exits=exits,
        strategy=strategy,
        run_id=run_id
    )
    
    # Verify: create_alert called only for MSFT
    assert mock_db.create_alert.call_count == 1
    assert mock_db.create_alert.call_args.kwargs['symbol'] == 'MSFT'
    assert mock_db.create_alert.call_args.kwargs['action_type'] == 'market_sell'

