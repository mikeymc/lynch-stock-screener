# ABOUTME: Tests for dashboard and market data endpoints
# ABOUTME: Verifies /api/market/index, /api/market/movers, and /api/dashboard work correctly

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

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
