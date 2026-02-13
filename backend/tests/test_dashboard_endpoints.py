# ABOUTME: Tests for dashboard and market data endpoints
# ABOUTME: Verifies /api/market/index, /api/market/movers, and /api/dashboard work correctly

import pytest
from unittest.mock import MagicMock, patch
import sys
import os
from datetime import date

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock google.genai before importing app
mock_genai = MagicMock()
sys.modules["google.genai"] = mock_genai
sys.modules["google.genai.types"] = MagicMock()


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    db.get_connection.return_value = MagicMock()
    db.return_connection = MagicMock()
    db.get_watchlist.return_value = ['AAPL', 'GOOGL']
    db.get_user_portfolios.return_value = []
    db.get_alerts.return_value = []
    db.get_user_strategies.return_value = []
    db.get_portfolio_holdings.return_value = {}
    return db


@pytest.fixture
def app(mock_db):
    """Create test Flask app."""
    with patch.dict(os.environ, {
        'FINNHUB_API_KEY': 'test_key',
        'SESSION_SECRET_KEY': 'test_secret'
    }):
        with patch('backend.database.Database', return_value=mock_db):
            # Import app after patching
            from backend import app as flask_app
            flask_app.app.config['TESTING'] = True
            yield flask_app.app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestMarketIndexEndpoint:
    """Tests for GET /api/market/index/<symbol>"""

    def test_unsupported_index_returns_400(self, client):
        """Test that unsupported index symbols return 400."""
        response = client.get('/api/market/index/INVALID?period=1mo')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_invalid_period_returns_400(self, client):
        """Test that invalid periods return 400."""
        response = client.get('/api/market/index/^GSPC?period=invalid')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data


class TestMarketMoversEndpoint:
    """Tests for GET /api/market/movers"""

    def test_get_movers_default(self, client, mock_db):
        """Test getting market movers with defaults."""
        # Mock cursor with dict_row behavior
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'symbol': 'AAPL', 'company_name': 'Apple', 'current_price': 150.0, 'change_pct': 2.5}
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        response = client.get('/api/market/movers')
        assert response.status_code == 200
        data = response.get_json()
        assert 'gainers' in data
        assert 'losers' in data
        assert 'period' in data
        assert data['period'] == '1d'


class TestDashboardEndpoint:
    """Tests for GET /api/dashboard"""

    def test_dashboard_requires_auth(self, client):
        """Test that dashboard endpoint requires authentication."""
        response = client.get('/api/dashboard')
        assert response.status_code == 401


class TestMarketIndexPartialData:
    """Tests for partial data handling in GET /api/market/index"""

    def test_get_market_index_partial_data(self, client):
        """Test that the endpoint handles missing symbols in yfinance download."""
        import pandas as pd
        from unittest.mock import patch

        # MultiIndex columns simulating ^GSPC and ^IXIC returned, but ^DJI missing
        columns = pd.MultiIndex.from_tuples([
            ('^GSPC', 'Close'), ('^GSPC', 'High'), ('^GSPC', 'Low'), ('^GSPC', 'Open'), ('^GSPC', 'Volume'),
            ('^IXIC', 'Close'), ('^IXIC', 'High'), ('^IXIC', 'Low'), ('^IXIC', 'Open'), ('^IXIC', 'Volume')
        ])

        # Mock DataFrame
        mock_df = pd.DataFrame({
            ('^GSPC', 'Close'): [100.0, 105.0],
            ('^GSPC', 'High'): [101.0, 106.0],
            ('^GSPC', 'Low'): [99.0, 104.0],
            ('^GSPC', 'Open'): [99.5, 104.5],
            ('^GSPC', 'Volume'): [1000, 1100],
            ('^IXIC', 'Close'): [200.0, 210.0],
            ('^IXIC', 'High'): [201.0, 211.0],
            ('^IXIC', 'Low'): [199.0, 209.0],
            ('^IXIC', 'Open'): [199.5, 209.5],
            ('^IXIC', 'Volume'): [2000, 2200]
        }, index=pd.to_datetime(['2024-01-01', '2024-01-02']))
        mock_df.columns = columns

        with patch('yfinance.download', return_value=mock_df):
            response = client.get('/api/market/index/^GSPC,^IXIC,^DJI?period=1mo')
            assert response.status_code == 200
            data = response.get_json()

            assert '^GSPC' in data
            assert '^IXIC' in data
            assert '^DJI' in data

            assert 'data' in data['^GSPC']
            assert'current_price' in data['^GSPC']
            assert data['^GSPC']['current_price'] == 105.0

            assert 'data' in data['^IXIC']
            
            assert 'error' in data['^DJI']
            assert 'No data available for ^DJI' in data['^DJI']['error']


class TestDashboardEarningsEndpoint:
    """Tests for GET /api/dashboard/earnings"""

    def test_get_earnings_days_param(self, client, mock_db):
        """Test getting earnings with custom days parameter."""
        mock_cursor = MagicMock()
        # First call is for total count, second for results, others for potential auth/8k status
        mock_cursor.fetchone.side_effect = [{'total': 5}]
        mock_cursor.fetchall.return_value = [
            {'symbol': 'AAPL', 'company_name': 'Apple', 'next_earnings_date': date(2026, 3, 1)}
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        mock_db.get_earnings_8k_status_batch.return_value = {}
        mock_db.get_user_by_id.return_value = {"id": 1, "user_type": "regular"}
        
        # Test with days=30
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            
        with patch('app.deps.db', mock_db):
            response = client.get('/api/dashboard/earnings?days=30')
            assert response.status_code == 200
            data = response.get_json()
            assert 'upcoming_earnings' in data
            assert data['upcoming_earnings']['total_count'] == 5
            
            # Verify the SQL matches our expectation (parameterized interval)
            execute_calls = [call for call in mock_cursor.execute.call_args_list]
            found_interval_logic = False
            for call in execute_calls:
                sql = call[0][0]
                params = call[0][1]
                if "%s * INTERVAL '1 day'" in sql:
                    found_interval_logic = True
                    # Check parameter order: days should be first, symbols second
                    assert params[0] == 30
                    assert isinstance(params[1], list)
                    assert "sm.symbol = ANY(%s)" in sql
                    break
            assert found_interval_logic

    def test_get_earnings_scope_all(self, client, mock_db):
        """Test getting earnings with scope=all parameter."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'total': 100}
        mock_cursor.fetchall.return_value = [
            {'symbol': 'MSFT', 'company_name': 'Microsoft', 'next_earnings_date': date(2026, 3, 1)}
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        mock_db.get_earnings_8k_status_batch.return_value = {}
        mock_db.get_user_by_id.return_value = {"id": 1, "user_type": "regular"}
        
        # Test with scope=all
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            
        with patch('app.deps.db', mock_db):
            response = client.get('/api/dashboard/earnings?scope=all')
            assert response.status_code == 200
            data = response.get_json()
            assert data['upcoming_earnings']['total_count'] == 100
            
            # Verify the SQL DOES NOT contain the watchlist filtering
            execute_calls = [call for call in mock_cursor.execute.call_args_list]
            for call in execute_calls:
                sql = call[0][0]
                assert "sm.symbol = ANY(%s)" not in sql
