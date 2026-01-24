
import pytest
from unittest.mock import MagicMock, patch
import datetime
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock dependencies
sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()
sys.modules["fred_service"] = MagicMock()
sys.modules["characters"] = MagicMock()
sys.modules["stock_context"] = MagicMock()

import backend.database
sys.modules['database'] = backend.database
from backend.database import Database
from backend.agent_tools import ToolExecutor
from backend.smart_chat_agent import SmartChatAgent

@pytest.fixture
def mock_db():
    db = MagicMock(spec=Database)
    db.get_connection = MagicMock()
    db.return_connection = MagicMock()
    return db

@pytest.fixture
def mock_portfolio_service():
    with patch('backend.agent_tools.portfolio_service') as mock:
        yield mock

def test_create_portfolio_tool(mock_db):
    executor = ToolExecutor(mock_db)
    mock_db.create_portfolio.return_value = 123
    
    result = executor._create_portfolio(name="Test Portfolio", user_id=1, initial_cash=50000.0)
    
    assert result["success"] is True
    assert result["portfolio_id"] == 123
    assert "created successfully" in result["message"]
    mock_db.create_portfolio.assert_called_with(user_id=1, name="Test Portfolio", initial_cash=50000.0)

def test_get_my_portfolios_tool(mock_db):
    executor = ToolExecutor(mock_db)
    
    # Mock list of portfolios
    mock_db.get_user_portfolios.return_value = [{'id': 1}, {'id': 2}]
    # Mock summaries
    mock_db.get_portfolio_summary.side_effect = [
        {'id': 1, 'name': 'P1', 'total_value': 1000},
        {'id': 2, 'name': 'P2', 'total_value': 2000}
    ]
    
    result = executor._get_my_portfolios(user_id=1)
    
    assert result["success"] is True
    assert len(result["portfolios"]) == 2
    assert result["portfolios"][0]['name'] == 'P1'
    assert result["portfolios"][1]['name'] == 'P2'

def test_get_portfolio_status_unauthorized(mock_db):
    executor = ToolExecutor(mock_db)
    
    # Portfolio exists but owned by user 2
    mock_db.get_portfolio.return_value = {'id': 100, 'user_id': 2}
    
    result = executor._get_portfolio_status(portfolio_id=100, user_id=1)
    
    assert result["success"] is False
    assert "unauthorized" in result["error"]

def test_get_portfolio_status_success(mock_db):
    executor = ToolExecutor(mock_db)
    
    mock_db.get_portfolio.return_value = {'id': 100, 'user_id': 1}
    mock_db.get_portfolio_summary.return_value = {'id': 100, 'total_value': 1500}
    
    result = executor._get_portfolio_status(portfolio_id=100, user_id=1)
    
    assert result["success"] is True
    assert result["status"]['total_value'] == 1500

def test_buy_stock_tool(mock_db, mock_portfolio_service):
    executor = ToolExecutor(mock_db)
    
    mock_db.get_portfolio.return_value = {'id': 100, 'user_id': 1}
    mock_portfolio_service.execute_trade.return_value = {'success': True, 'transaction_id': 500}
    
    result = executor._buy_stock(portfolio_id=100, ticker="AAPL", quantity=10, user_id=1, note="Testing")
    
    assert result["success"] is True
    assert result["transaction_id"] == 500
    mock_portfolio_service.execute_trade.assert_called_with(
        db=mock_db,
        portfolio_id=100,
        symbol="AAPL",
        transaction_type='BUY',
        quantity=10,
        note="Testing"
    )

def test_sell_stock_tool(mock_db, mock_portfolio_service):
    executor = ToolExecutor(mock_db)
    
    mock_db.get_portfolio.return_value = {'id': 100, 'user_id': 1}
    mock_portfolio_service.execute_trade.return_value = {'success': True, 'transaction_id': 501}
    
    result = executor._sell_stock(portfolio_id=100, ticker="NVDA", quantity=5, user_id=1)
    
    assert result["success"] is True
    assert result["transaction_id"] == 501
    mock_portfolio_service.execute_trade.assert_called_with(
        db=mock_db,
        portfolio_id=100,
        symbol="NVDA",
        transaction_type='SELL',
        quantity=5,
        note=None
    )

def test_smart_chat_agent_injection(mock_db):
    # Mock some data for the agent
    mock_db.get_user_character.return_value = "lynch"
    mock_db.get_setting.return_value = False # alerts disabled
    
    agent = SmartChatAgent(mock_db)
    
    # Mock the tool executor
    agent.tool_executor = MagicMock()
    agent.tool_executor.execute.return_value = {"success": True}
    
    # Mock the Gemini client and generate_content
    mock_response = MagicMock()
    
    # Use a real-looking object for the function call
    class MockFunctionCall:
        def __init__(self, name, args):
            self.name = name
            self.args = args
            
    mock_fc = MockFunctionCall("buy_stock", {"portfolio_id": 1, "ticker": "AAPL", "quantity": 10})
    
    class MockPart:
        def __init__(self, function_call=None, text=None):
            self.function_call = function_call
            self.text = text
            
    mock_part = MockPart(function_call=mock_fc)
    
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[0].content.parts = [mock_part]
    
    # Second call for the final answer
    mock_final_part = MockPart(text="Bought the stock!")
    mock_final_response = MagicMock()
    mock_final_response.candidates = [MagicMock()]
    mock_final_response.candidates[0].content.parts = [mock_final_part]
    
    # Use a function for side_effect to avoid StopIteration and handle retries/fallbacks
    responses = [mock_response, mock_final_response]
    def side_effect_func(*args, **kwargs):
        if responses:
            return responses.pop(0)
        return mock_final_response

    agent.client.models.generate_content.side_effect = side_effect_func
    
    agent.chat(primary_symbol="AAPL", user_message="Buy 10 AAPL for me", user_id=42)
    
    # Verify execution with injected user_id
    agent.tool_executor.execute.assert_called_with(
        "buy_stock",
        {"portfolio_id": 1, "ticker": "AAPL", "quantity": 10, "user_id": 42}
    )
