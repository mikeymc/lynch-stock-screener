# ABOUTME: Tests for the Smart Chat Agent tool definitions and ReAct loop
# ABOUTME: Validates tool execution and basic agent behavior

import pytest
from unittest.mock import MagicMock, patch
import os
import sys

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestToolExecutor:
    """Tests for the ToolExecutor class."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database with sample data."""
        db = MagicMock()
        
        # Mock get_stock_metrics
        db.get_stock_metrics.return_value = {
            'symbol': 'NVDA',
            'company_name': 'NVIDIA Corporation',
            'sector': 'Technology',
            'price': 140.50,
            'pe_ratio': 65.2,
            'market_cap': 3500000000000,
            'debt_to_equity': 0.41,
            'institutional_ownership': 0.68,
            'dividend_yield': 0.02,
            'forward_pe': 35.0,
            'beta': 1.65,
        }
        
        # Mock get_earnings_history
        db.get_earnings_history.return_value = [
            {'year': 2024, 'eps': 2.95, 'revenue': 60900000000, 'net_income': 29000000000, 'free_cash_flow': 25000000000},
            {'year': 2023, 'eps': 1.19, 'revenue': 26974000000, 'net_income': 4368000000, 'free_cash_flow': 3800000000},
            {'year': 2022, 'eps': 1.32, 'revenue': 26914000000, 'net_income': 9752000000, 'free_cash_flow': 8000000000},
        ]
        
        # Mock get_insider_trades
        db.get_insider_trades.return_value = [
            {
                'name': 'Jensen Huang',
                'position': 'CEO',
                'transaction_date': '2024-01-15',
                'transaction_type': 'S',
                'transaction_code': 'S',
                'shares': 50000,
                'value': 7000000,
            },
            {
                'name': 'Colette Kress',
                'position': 'CFO',
                'transaction_date': '2024-01-10',
                'transaction_type': 'P',
                'transaction_code': 'P',
                'shares': 5000,
                'value': 700000,
            },
        ]
        
        # Mock get_connection/return_connection for get_peers
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('AMD', 'Advanced Micro Devices', 250000000000),
            ('INTC', 'Intel Corporation', 180000000000),
            ('QCOM', 'Qualcomm', 200000000000),
        ]
        mock_conn.cursor.return_value = mock_cursor
        db.get_connection.return_value = mock_conn
        db.return_connection = MagicMock()
        
        return db
    
    @pytest.fixture
    def tool_executor(self, mock_db):
        """Create a ToolExecutor with mocked dependencies."""
        from agent_tools import ToolExecutor
        return ToolExecutor(mock_db, rag_context=None)
    
    def test_get_stock_metrics(self, tool_executor, mock_db):
        """Test get_stock_metrics tool returns expected data."""
        result = tool_executor.execute('get_stock_metrics', {'ticker': 'NVDA'})
        
        assert result['ticker'] == 'NVDA'
        assert result['company_name'] == 'NVIDIA Corporation'
        assert result['sector'] == 'Technology'
        assert result['price'] == 140.50
        assert result['pe_ratio'] == 65.2
        mock_db.get_stock_metrics.assert_called_once_with('NVDA')
    
    def test_get_stock_metrics_not_found(self, tool_executor, mock_db):
        """Test get_stock_metrics returns error for unknown ticker."""
        mock_db.get_stock_metrics.return_value = None
        result = tool_executor.execute('get_stock_metrics', {'ticker': 'FAKE'})
        
        assert 'error' in result
        assert 'FAKE' in result['error']
    
    def test_get_financials(self, tool_executor, mock_db):
        """Test get_financials tool returns filtered data."""
        result = tool_executor.execute('get_financials', {
            'ticker': 'NVDA',
            'metric': 'revenue',
            'years': [2023, 2024]
        })
        
        assert result['ticker'] == 'NVDA'
        assert result['metric'] == 'revenue'
        assert 2023 in result['data']
        assert 2024 in result['data']
        assert result['data'][2024] == 60900000000
    
    def test_get_peers(self, tool_executor, mock_db):
        """Test get_peers returns sector peers."""
        result = tool_executor.execute('get_peers', {'ticker': 'NVDA'})
        
        assert result['ticker'] == 'NVDA'
        assert result['sector'] == 'Technology'
        assert len(result['peers']) == 3
        assert result['peers'][0]['ticker'] == 'AMD'
    
    def test_get_insider_activity(self, tool_executor, mock_db):
        """Test get_insider_activity returns summarized trades."""
        result = tool_executor.execute('get_insider_activity', {'ticker': 'NVDA'})
        
        assert result['ticker'] == 'NVDA'
        assert result['summary']['total_buys'] == 1
        assert result['summary']['total_sells'] == 1
        assert result['summary']['buy_value'] == 700000
        assert result['summary']['sell_value'] == 7000000
    
    def test_unknown_tool(self, tool_executor):
        """Test that unknown tools return an error."""
        result = tool_executor.execute('unknown_tool', {'arg': 'value'})
        
        assert 'error' in result
        assert 'Unknown tool' in result['error']


class TestToolDeclarations:
    """Tests for the Gemini tool declarations."""
    
    def test_tool_declarations_exist(self):
        """Test that all expected tool declarations exist."""
        from agent_tools import TOOL_DECLARATIONS
        
        tool_names = [t.name for t in TOOL_DECLARATIONS]
        
        assert 'get_stock_metrics' in tool_names
        assert 'get_financials' in tool_names
        assert 'get_peers' in tool_names
        assert 'get_insider_activity' in tool_names
        assert 'search_news' in tool_names
        assert 'get_filing_section' in tool_names
    
    def test_agent_tools_object(self):
        """Test that AGENT_TOOLS is a valid Tool object."""
        from agent_tools import AGENT_TOOLS
        from google.genai.types import Tool
        
        assert isinstance(AGENT_TOOLS, Tool)
        assert len(AGENT_TOOLS.function_declarations) == 6


class TestSmartChatAgent:
    """Tests for the SmartChatAgent class."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a minimal mock database."""
        db = MagicMock()
        db.get_stock_metrics.return_value = {
            'symbol': 'NVDA',
            'company_name': 'NVIDIA',
            'sector': 'Technology',
            'price': 140.0,
        }
        return db
    
    def test_agent_initialization(self, mock_db):
        """Test that the agent initializes without errors."""
        from smart_chat_agent import SmartChatAgent
        
        agent = SmartChatAgent(mock_db, gemini_api_key='test_key')
        
        assert agent.db is mock_db
        assert agent.model_name == "gemini-2.5-flash"
    
    def test_build_system_prompt(self, mock_db):
        """Test that system prompt includes the stock symbol."""
        from smart_chat_agent import SmartChatAgent
        
        agent = SmartChatAgent(mock_db, gemini_api_key='test_key')
        prompt = agent._build_system_prompt('NVDA')
        
        assert 'NVDA' in prompt
        assert 'financial research' in prompt.lower()


class TestIntegration:
    """Integration tests that require database access."""
    
    @pytest.fixture
    def real_db(self):
        """Get a real database connection for integration tests."""
        from database import Database
        
        # Use test database settings
        db = Database(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=int(os.environ.get('DB_PORT', 5432)),
            database=os.environ.get('DB_NAME', 'lynch_stocks'),
            user=os.environ.get('DB_USER', 'lynch'),
            password=os.environ.get('DB_PASSWORD', 'lynch_dev_password'),
        )
        return db
    
    @pytest.mark.skipif(
        os.environ.get('RUN_INTEGRATION_TESTS') != 'true',
        reason="Integration tests disabled (set RUN_INTEGRATION_TESTS=true to run)"
    )
    def test_tool_executor_with_real_db(self, real_db):
        """Test ToolExecutor with real database."""
        from agent_tools import ToolExecutor
        
        executor = ToolExecutor(real_db)
        
        # Test with a stock that should exist
        result = executor.execute('get_stock_metrics', {'ticker': 'AAPL'})
        
        # Should either return data or an error, not crash
        assert 'ticker' in result or 'error' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
