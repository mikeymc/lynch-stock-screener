# ABOUTME: Tests for paper trading portfolio API endpoints
# ABOUTME: Validates authentication, CRUD operations, and trade execution via HTTP

import pytest
import os
import sys
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend')))

from app import app


@pytest.fixture
def client(test_db, monkeypatch):
    """Flask test client with test database"""
    import app as app_module
    import auth

    # Replace app's db with test_db
    monkeypatch.setattr(app_module.deps, 'db', test_db)

    # Disable dev auth bypass so auth tests work correctly
    monkeypatch.setattr(auth, 'DEV_AUTH_BYPASS', False)

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_client(client, test_db):
    """Authenticated client with test user"""
    user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
    return client, user_id


class TestPortfolioListEndpoint:
    """Tests for GET /api/portfolios"""

    def test_list_portfolios_requires_auth(self, client):
        """Test that listing portfolios requires authentication"""
        response = client.get('/api/portfolios')
        assert response.status_code == 401

    def test_list_portfolios_empty(self, auth_client):
        """Test listing portfolios when user has none"""
        client, user_id = auth_client

        response = client.get('/api/portfolios')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['portfolios'] == []

    def test_list_portfolios_with_data(self, auth_client, test_db):
        """Test listing portfolios returns user's portfolios"""
        client, user_id = auth_client

        test_db.create_portfolio(user_id, "Tech Portfolio")
        test_db.create_portfolio(user_id, "Value Portfolio")

        response = client.get('/api/portfolios')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data['portfolios']) == 2


class TestCreatePortfolioEndpoint:
    """Tests for POST /api/portfolios"""

    def test_create_portfolio_requires_auth(self, client):
        """Test that creating portfolio requires authentication"""
        response = client.post('/api/portfolios',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json')
        assert response.status_code == 401

    def test_create_portfolio_success(self, auth_client):
        """Test creating a new portfolio"""
        client, user_id = auth_client

        response = client.post('/api/portfolios',
            data=json.dumps({'name': 'My Portfolio'}),
            content_type='application/json')
        assert response.status_code == 201

        data = json.loads(response.data)
        assert data['id'] is not None
        assert data['name'] == 'My Portfolio'
        assert data['initial_cash'] == 100000.0

    def test_create_portfolio_custom_cash(self, auth_client):
        """Test creating portfolio with custom initial cash"""
        client, user_id = auth_client

        response = client.post('/api/portfolios',
            data=json.dumps({'name': 'Small Fund', 'initial_cash': 50000.0}),
            content_type='application/json')
        assert response.status_code == 201

        data = json.loads(response.data)
        assert data['initial_cash'] == 50000.0

    def test_create_portfolio_requires_name(self, auth_client):
        """Test creating portfolio without name fails"""
        client, user_id = auth_client

        response = client.post('/api/portfolios',
            data=json.dumps({}),
            content_type='application/json')
        assert response.status_code == 400


class TestGetPortfolioEndpoint:
    """Tests for GET /api/portfolios/<id>"""

    def test_get_portfolio_requires_auth(self, client, test_db):
        """Test that getting portfolio requires authentication"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test")

        response = client.get(f'/api/portfolios/{portfolio_id}')
        assert response.status_code == 401

    def test_get_portfolio_success(self, auth_client, test_db):
        """Test getting portfolio details with computed values"""
        client, user_id = auth_client

        # Create stock and portfolio
        test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
        test_db.save_stock_metrics("AAPL", {"price": 150.0})
        test_db.flush()

        portfolio_id = test_db.create_portfolio(user_id, "Tech Portfolio")
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)

        # Mock batch price fetching to return our test price
        with patch('portfolio_service.fetch_current_prices_batch', return_value={'AAPL': 150.0}):
            response = client.get(f'/api/portfolios/{portfolio_id}')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['name'] == "Tech Portfolio"
        assert data['cash'] == 98500.0
        assert data['holdings']['AAPL'] == 10
        assert data['holdings_value'] == 1500.0

    def test_get_portfolio_not_found(self, auth_client):
        """Test getting non-existent portfolio returns 404"""
        client, user_id = auth_client

        response = client.get('/api/portfolios/99999')
        assert response.status_code == 404

    def test_get_portfolio_ownership(self, auth_client, test_db):
        """Test user can only get their own portfolios"""
        client, user_id = auth_client

        # Create another user's portfolio
        other_user_id = test_db.create_user("google_456", "other@example.com", "Other User", None)
        other_portfolio_id = test_db.create_portfolio(other_user_id, "Other Portfolio")

        response = client.get(f'/api/portfolios/{other_portfolio_id}')
        assert response.status_code == 404  # Should not see other user's portfolio


class TestUpdatePortfolioEndpoint:
    """Tests for PUT /api/portfolios/<id>"""

    def test_rename_portfolio(self, auth_client, test_db):
        """Test renaming a portfolio"""
        client, user_id = auth_client

        portfolio_id = test_db.create_portfolio(user_id, "Old Name")

        response = client.put(f'/api/portfolios/{portfolio_id}',
            data=json.dumps({'name': 'New Name'}),
            content_type='application/json')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['name'] == 'New Name'


class TestDeletePortfolioEndpoint:
    """Tests for DELETE /api/portfolios/<id>"""

    def test_delete_portfolio_success(self, auth_client, test_db):
        """Test deleting own portfolio"""
        client, user_id = auth_client

        portfolio_id = test_db.create_portfolio(user_id, "To Delete")

        response = client.delete(f'/api/portfolios/{portfolio_id}')
        assert response.status_code == 200

        # Verify deleted
        assert test_db.get_portfolio(portfolio_id) is None

    def test_delete_portfolio_not_owner(self, auth_client, test_db):
        """Test cannot delete another user's portfolio"""
        client, user_id = auth_client

        other_user_id = test_db.create_user("google_456", "other@example.com", "Other User", None)
        other_portfolio_id = test_db.create_portfolio(other_user_id, "Other Portfolio")

        response = client.delete(f'/api/portfolios/{other_portfolio_id}')
        assert response.status_code == 404  # Not found (ownership check)

        # Verify NOT deleted
        assert test_db.get_portfolio(other_portfolio_id) is not None


class TestTransactionsEndpoint:
    """Tests for GET /api/portfolios/<id>/transactions"""

    def test_get_transactions(self, auth_client, test_db):
        """Test getting portfolio transaction history"""
        client, user_id = auth_client

        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)
        test_db.record_transaction(portfolio_id, "GOOGL", "BUY", 5, 140.0)

        response = client.get(f'/api/portfolios/{portfolio_id}/transactions')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data['transactions']) == 2


class TestTradeEndpoint:
    """Tests for POST /api/portfolios/<id>/trade"""

    def test_execute_trade_buy(self, auth_client, test_db):
        """Test executing a buy trade"""
        client, user_id = auth_client

        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        with patch('portfolio_service.is_market_open', return_value=True):
            with patch('portfolio_service.fetch_current_price', return_value=150.0):
                response = client.post(f'/api/portfolios/{portfolio_id}/trade',
                    data=json.dumps({
                        'symbol': 'AAPL',
                        'transaction_type': 'BUY',
                        'quantity': 10
                    }),
                    content_type='application/json')

        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['success'] is True
        assert data['price_per_share'] == 150.0
        assert data['total_value'] == 1500.0

    def test_execute_trade_sell(self, auth_client, test_db):
        """Test executing a sell trade"""
        client, user_id = auth_client

        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 20, 150.0)

        with patch('portfolio_service.is_market_open', return_value=True):
            with patch('portfolio_service.fetch_current_price', return_value=160.0):
                response = client.post(f'/api/portfolios/{portfolio_id}/trade',
                    data=json.dumps({
                        'symbol': 'AAPL',
                        'transaction_type': 'SELL',
                        'quantity': 10
                    }),
                    content_type='application/json')

        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['success'] is True

    def test_execute_trade_market_closed(self, auth_client, test_db):
        """Test trade fails when market is closed"""
        client, user_id = auth_client

        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        with patch('portfolio_service.is_market_open', return_value=False):
            response = client.post(f'/api/portfolios/{portfolio_id}/trade',
                data=json.dumps({
                    'symbol': 'AAPL',
                    'transaction_type': 'BUY',
                    'quantity': 10
                }),
                content_type='application/json')

        assert response.status_code == 400

        data = json.loads(response.data)
        assert data['success'] is False
        assert 'market' in data['error'].lower()

    def test_execute_trade_insufficient_cash(self, auth_client, test_db):
        """Test buy fails with insufficient cash"""
        client, user_id = auth_client

        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")  # $100K

        with patch('portfolio_service.is_market_open', return_value=True):
            with patch('portfolio_service.fetch_current_price', return_value=200.0):
                response = client.post(f'/api/portfolios/{portfolio_id}/trade',
                    data=json.dumps({
                        'symbol': 'AAPL',
                        'transaction_type': 'BUY',
                        'quantity': 1000  # $200K worth
                    }),
                    content_type='application/json')

        assert response.status_code == 400

        data = json.loads(response.data)
        assert data['success'] is False
        assert 'insufficient' in data['error'].lower()


class TestValueHistoryEndpoint:
    """Tests for GET /api/portfolios/<id>/value-history"""

    def test_get_value_history(self, auth_client, test_db):
        """Test getting portfolio value history"""
        client, user_id = auth_client

        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")
        test_db.save_portfolio_snapshot(portfolio_id, 100000.0, 100000.0, 0.0)
        test_db.save_portfolio_snapshot(portfolio_id, 101000.0, 50000.0, 51000.0)

        response = client.get(f'/api/portfolios/{portfolio_id}/value-history')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data['snapshots']) == 2
        assert data['snapshots'][0]['total_value'] == 100000.0
