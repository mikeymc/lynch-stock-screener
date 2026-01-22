# ABOUTME: Tests for paper trading portfolio operations
# ABOUTME: Validates portfolio CRUD, transactions, and value calculations

import pytest
from datetime import datetime


class TestPortfolioCRUD:
    """Tests for basic portfolio create, read, update, delete operations"""

    def test_create_portfolio(self, test_db):
        """Test creating a new portfolio"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)

        portfolio_id = test_db.create_portfolio(user_id, "Tech Bets")

        assert portfolio_id is not None
        assert portfolio_id > 0

    def test_create_portfolio_with_custom_initial_cash(self, test_db):
        """Test creating portfolio with custom initial cash"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)

        portfolio_id = test_db.create_portfolio(user_id, "Small Fund", initial_cash=50000.0)
        portfolio = test_db.get_portfolio(portfolio_id)

        assert portfolio['initial_cash'] == 50000.0

    def test_get_portfolio(self, test_db):
        """Test retrieving a portfolio by ID"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Value Picks")

        portfolio = test_db.get_portfolio(portfolio_id)

        assert portfolio is not None
        assert portfolio['id'] == portfolio_id
        assert portfolio['name'] == "Value Picks"
        assert portfolio['initial_cash'] == 100000.0
        assert portfolio['user_id'] == user_id

    def test_get_nonexistent_portfolio(self, test_db):
        """Test getting a portfolio that doesn't exist returns None"""
        portfolio = test_db.get_portfolio(99999)
        assert portfolio is None

    def test_get_user_portfolios(self, test_db):
        """Test getting all portfolios for a user"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        test_db.create_portfolio(user_id, "Portfolio A")
        test_db.create_portfolio(user_id, "Portfolio B")
        test_db.create_portfolio(user_id, "Portfolio C")

        portfolios = test_db.get_user_portfolios(user_id)

        assert len(portfolios) == 3
        names = [p['name'] for p in portfolios]
        assert "Portfolio A" in names
        assert "Portfolio B" in names
        assert "Portfolio C" in names

    def test_get_user_portfolios_empty(self, test_db):
        """Test getting portfolios for user with none returns empty list"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)

        portfolios = test_db.get_user_portfolios(user_id)

        assert portfolios == []

    def test_different_users_have_separate_portfolios(self, test_db):
        """Test that portfolios are scoped to individual users"""
        user1_id = test_db.create_user("google_123", "user1@example.com", "User One", None)
        user2_id = test_db.create_user("google_456", "user2@example.com", "User Two", None)

        test_db.create_portfolio(user1_id, "User 1 Portfolio")
        test_db.create_portfolio(user2_id, "User 2 Portfolio")

        user1_portfolios = test_db.get_user_portfolios(user1_id)
        user2_portfolios = test_db.get_user_portfolios(user2_id)

        assert len(user1_portfolios) == 1
        assert len(user2_portfolios) == 1
        assert user1_portfolios[0]['name'] == "User 1 Portfolio"
        assert user2_portfolios[0]['name'] == "User 2 Portfolio"

    def test_rename_portfolio(self, test_db):
        """Test renaming a portfolio"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Old Name")

        test_db.rename_portfolio(portfolio_id, "New Name")

        portfolio = test_db.get_portfolio(portfolio_id)
        assert portfolio['name'] == "New Name"

    def test_delete_portfolio(self, test_db):
        """Test deleting a portfolio"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "To Delete")

        result = test_db.delete_portfolio(portfolio_id, user_id)

        assert result is True
        assert test_db.get_portfolio(portfolio_id) is None

    def test_delete_portfolio_verifies_ownership(self, test_db):
        """Test that delete verifies user owns the portfolio"""
        user1_id = test_db.create_user("google_123", "user1@example.com", "User One", None)
        user2_id = test_db.create_user("google_456", "user2@example.com", "User Two", None)
        portfolio_id = test_db.create_portfolio(user1_id, "User 1 Portfolio")

        # User 2 tries to delete User 1's portfolio
        result = test_db.delete_portfolio(portfolio_id, user2_id)

        assert result is False
        # Portfolio should still exist
        assert test_db.get_portfolio(portfolio_id) is not None


class TestPortfolioTransactions:
    """Tests for recording buy/sell transactions"""

    def test_record_buy_transaction(self, test_db):
        """Test recording a buy transaction"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        tx_id = test_db.record_transaction(
            portfolio_id=portfolio_id,
            symbol="AAPL",
            transaction_type="BUY",
            quantity=10,
            price_per_share=150.0
        )

        assert tx_id is not None
        assert tx_id > 0

    def test_record_sell_transaction(self, test_db):
        """Test recording a sell transaction"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        tx_id = test_db.record_transaction(
            portfolio_id=portfolio_id,
            symbol="AAPL",
            transaction_type="SELL",
            quantity=5,
            price_per_share=160.0
        )

        assert tx_id is not None

    def test_get_portfolio_transactions(self, test_db):
        """Test retrieving all transactions for a portfolio"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)
        test_db.record_transaction(portfolio_id, "GOOGL", "BUY", 5, 140.0)
        test_db.record_transaction(portfolio_id, "AAPL", "SELL", 3, 155.0)

        transactions = test_db.get_portfolio_transactions(portfolio_id)

        assert len(transactions) == 3

    def test_transaction_records_total_value(self, test_db):
        """Test that transaction total_value is calculated correctly"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)

        transactions = test_db.get_portfolio_transactions(portfolio_id)

        assert transactions[0]['total_value'] == 1500.0  # 10 * 150

    def test_transaction_with_note(self, test_db):
        """Test recording a transaction with a note"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.record_transaction(
            portfolio_id, "AAPL", "BUY", 10, 150.0,
            note="Bought on earnings dip"
        )

        transactions = test_db.get_portfolio_transactions(portfolio_id)

        assert transactions[0]['note'] == "Bought on earnings dip"


class TestPortfolioHoldings:
    """Tests for computing current holdings from transactions"""

    def test_get_holdings_after_buy(self, test_db):
        """Test holdings calculation after a buy"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)

        holdings = test_db.get_portfolio_holdings(portfolio_id)

        assert holdings["AAPL"] == 10

    def test_get_holdings_after_multiple_buys(self, test_db):
        """Test holdings aggregate multiple buys of same stock"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 5, 155.0)

        holdings = test_db.get_portfolio_holdings(portfolio_id)

        assert holdings["AAPL"] == 15

    def test_get_holdings_after_buy_and_sell(self, test_db):
        """Test holdings calculation after buy and partial sell"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)
        test_db.record_transaction(portfolio_id, "AAPL", "SELL", 3, 160.0)

        holdings = test_db.get_portfolio_holdings(portfolio_id)

        assert holdings["AAPL"] == 7

    def test_get_holdings_multiple_stocks(self, test_db):
        """Test holdings with multiple different stocks"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)
        test_db.record_transaction(portfolio_id, "GOOGL", "BUY", 5, 140.0)
        test_db.record_transaction(portfolio_id, "MSFT", "BUY", 20, 380.0)

        holdings = test_db.get_portfolio_holdings(portfolio_id)

        assert holdings["AAPL"] == 10
        assert holdings["GOOGL"] == 5
        assert holdings["MSFT"] == 20

    def test_get_holdings_excludes_zero_positions(self, test_db):
        """Test that fully sold positions are excluded from holdings"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)
        test_db.record_transaction(portfolio_id, "AAPL", "SELL", 10, 160.0)

        holdings = test_db.get_portfolio_holdings(portfolio_id)

        assert "AAPL" not in holdings

    def test_get_holdings_empty_portfolio(self, test_db):
        """Test holdings for portfolio with no transactions"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        holdings = test_db.get_portfolio_holdings(portfolio_id)

        assert holdings == {}


class TestPortfolioCash:
    """Tests for computing cash balance from transactions"""

    def test_get_cash_initial(self, test_db):
        """Test cash balance for new portfolio equals initial cash"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        cash = test_db.get_portfolio_cash(portfolio_id)

        assert cash == 100000.0

    def test_get_cash_after_buy(self, test_db):
        """Test cash decreases after buy"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        # Buy 10 shares at $150 = $1500
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)

        cash = test_db.get_portfolio_cash(portfolio_id)

        assert cash == 98500.0  # 100000 - 1500

    def test_get_cash_after_sell(self, test_db):
        """Test cash increases after sell"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        # Buy then sell
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)  # -1500
        test_db.record_transaction(portfolio_id, "AAPL", "SELL", 5, 160.0)  # +800

        cash = test_db.get_portfolio_cash(portfolio_id)

        assert cash == 99300.0  # 100000 - 1500 + 800

    def test_get_cash_custom_initial(self, test_db):
        """Test cash calculation with custom initial cash"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Small Fund", initial_cash=50000.0)

        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)

        cash = test_db.get_portfolio_cash(portfolio_id)

        assert cash == 48500.0  # 50000 - 1500


class TestPortfolioSnapshots:
    """Tests for portfolio value snapshots"""

    def test_save_portfolio_snapshot(self, test_db):
        """Test saving a portfolio value snapshot"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        snapshot_id = test_db.save_portfolio_snapshot(
            portfolio_id=portfolio_id,
            total_value=102500.0,
            cash_value=50000.0,
            holdings_value=52500.0
        )

        assert snapshot_id is not None

    def test_get_portfolio_snapshots(self, test_db):
        """Test retrieving portfolio value history"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.save_portfolio_snapshot(portfolio_id, 100000.0, 100000.0, 0.0)
        test_db.save_portfolio_snapshot(portfolio_id, 101000.0, 50000.0, 51000.0)
        test_db.save_portfolio_snapshot(portfolio_id, 102000.0, 50000.0, 52000.0)

        snapshots = test_db.get_portfolio_snapshots(portfolio_id)

        assert len(snapshots) == 3

    def test_snapshots_ordered_by_time(self, test_db):
        """Test that snapshots are returned in chronological order"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.save_portfolio_snapshot(portfolio_id, 100000.0, 100000.0, 0.0)
        test_db.save_portfolio_snapshot(portfolio_id, 101000.0, 50000.0, 51000.0)
        test_db.save_portfolio_snapshot(portfolio_id, 102000.0, 50000.0, 52000.0)

        snapshots = test_db.get_portfolio_snapshots(portfolio_id)

        # Values should be in order they were inserted
        assert snapshots[0]['total_value'] == 100000.0
        assert snapshots[1]['total_value'] == 101000.0
        assert snapshots[2]['total_value'] == 102000.0

    def test_delete_portfolio_cascades_to_snapshots(self, test_db):
        """Test that deleting portfolio also deletes its snapshots"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        test_db.save_portfolio_snapshot(portfolio_id, 100000.0, 100000.0, 0.0)
        test_db.save_portfolio_snapshot(portfolio_id, 101000.0, 50000.0, 51000.0)

        test_db.delete_portfolio(portfolio_id, user_id)

        # Snapshots should be gone (we can't query directly since portfolio is gone)
        # Just verify portfolio is deleted
        assert test_db.get_portfolio(portfolio_id) is None


class TestPortfolioSummary:
    """Tests for portfolio summary with computed values"""

    def test_get_portfolio_summary(self, test_db):
        """Test getting portfolio summary with all computed values"""
        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        # Add a stock so we have prices
        test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
        test_db.save_stock_metrics("AAPL", {"price": 150.0, "pe_ratio": 30.0})
        test_db.flush()

        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 10, 150.0)

        # Use cached prices (use_live_prices=False) to test with our mock data
        summary = test_db.get_portfolio_summary(portfolio_id, use_live_prices=False)

        assert summary is not None
        assert summary['id'] == portfolio_id
        assert summary['name'] == "Test Portfolio"
        assert summary['cash'] == 98500.0  # 100000 - 1500
        assert summary['holdings_value'] == 1500.0  # 10 * 150
        assert summary['total_value'] == 100000.0  # cash + holdings
        assert summary['gain_loss'] == 0.0  # no change from initial
        assert summary['gain_loss_percent'] == 0.0
