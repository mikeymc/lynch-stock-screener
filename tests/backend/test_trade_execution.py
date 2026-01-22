# ABOUTME: Tests for paper trading trade execution logic
# ABOUTME: Validates market hours, price fetching, and trade validation

import pytest
from datetime import datetime, time
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo


class TestMarketHours:
    """Tests for market hours validation (extended hours: 4 AM - 8 PM ET)"""

    def test_market_open_during_extended_hours_morning(self):
        """Test market is open at 6 AM ET (extended hours)"""
        from portfolio_service import is_market_open

        # 6 AM ET on a Tuesday
        et_time = datetime(2026, 1, 20, 6, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is True

    def test_market_open_during_regular_hours(self):
        """Test market is open at 10 AM ET (regular hours)"""
        from portfolio_service import is_market_open

        # 10 AM ET on a Tuesday
        et_time = datetime(2026, 1, 20, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is True

    def test_market_open_during_extended_hours_evening(self):
        """Test market is open at 7 PM ET (extended hours)"""
        from portfolio_service import is_market_open

        # 7 PM ET on a Tuesday
        et_time = datetime(2026, 1, 20, 19, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is True

    def test_market_closed_before_extended_hours(self):
        """Test market is closed at 3 AM ET"""
        from portfolio_service import is_market_open

        # 3 AM ET on a Tuesday
        et_time = datetime(2026, 1, 20, 3, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is False

    def test_market_closed_after_extended_hours(self):
        """Test market is closed at 9 PM ET"""
        from portfolio_service import is_market_open

        # 9 PM ET on a Tuesday
        et_time = datetime(2026, 1, 20, 21, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is False

    def test_market_closed_on_saturday(self):
        """Test market is closed on weekends"""
        from portfolio_service import is_market_open

        # 10 AM ET on Saturday
        et_time = datetime(2026, 1, 24, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is False

    def test_market_closed_on_sunday(self):
        """Test market is closed on Sunday"""
        from portfolio_service import is_market_open

        # 10 AM ET on Sunday
        et_time = datetime(2026, 1, 25, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is False

    def test_market_boundary_4am_is_open(self):
        """Test 4 AM ET is within extended hours"""
        from portfolio_service import is_market_open

        # Exactly 4 AM ET on Tuesday
        et_time = datetime(2026, 1, 20, 4, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is True

    def test_market_boundary_8pm_is_open(self):
        """Test 8 PM ET is within extended hours"""
        from portfolio_service import is_market_open

        # Exactly 8 PM ET on Tuesday
        et_time = datetime(2026, 1, 20, 20, 0, tzinfo=ZoneInfo("America/New_York"))
        assert is_market_open(et_time) is True


class TestPriceFetching:
    """Tests for fetching current price (yfinance with fallback)"""

    def test_fetch_price_from_yfinance(self):
        """Test fetching price from yfinance"""
        from portfolio_service import fetch_current_price

        with patch('portfolio_service.yf') as mock_yf:
            mock_ticker = Mock()
            mock_ticker.fast_info = {'lastPrice': 150.50}
            mock_yf.Ticker.return_value = mock_ticker

            price = fetch_current_price("AAPL", db=None)

            assert price == 150.50
            mock_yf.Ticker.assert_called_with("AAPL")

    def test_fetch_price_fallback_to_db(self, test_db):
        """Test fallback to stock_metrics when yfinance fails"""
        from portfolio_service import fetch_current_price

        # Setup stock in database
        test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
        test_db.save_stock_metrics("AAPL", {"price": 145.00})
        test_db.flush()

        with patch('portfolio_service.yf') as mock_yf:
            # Make yfinance fail
            mock_ticker = Mock()
            mock_ticker.fast_info = {}  # No lastPrice
            mock_yf.Ticker.return_value = mock_ticker

            price = fetch_current_price("AAPL", db=test_db)

            assert price == 145.00

    def test_fetch_price_returns_none_when_unavailable(self, test_db):
        """Test returns None when price unavailable everywhere"""
        from portfolio_service import fetch_current_price

        with patch('portfolio_service.yf') as mock_yf:
            mock_ticker = Mock()
            mock_ticker.fast_info = {}
            mock_yf.Ticker.return_value = mock_ticker

            price = fetch_current_price("FAKE", db=test_db)

            assert price is None


class TestTradeValidation:
    """Tests for validating trades before execution"""

    def test_validate_buy_with_sufficient_cash(self, test_db):
        """Test buy validation passes with enough cash"""
        from portfolio_service import validate_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")  # $100K initial

        result = validate_trade(
            db=test_db,
            portfolio_id=portfolio_id,
            symbol="AAPL",
            transaction_type="BUY",
            quantity=10,
            price_per_share=150.0
        )

        assert result['valid'] is True

    def test_validate_buy_with_insufficient_cash(self, test_db):
        """Test buy validation fails without enough cash"""
        from portfolio_service import validate_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")  # $100K initial

        # Try to buy $200K worth
        result = validate_trade(
            db=test_db,
            portfolio_id=portfolio_id,
            symbol="AAPL",
            transaction_type="BUY",
            quantity=1000,
            price_per_share=200.0
        )

        assert result['valid'] is False
        assert 'insufficient' in result['error'].lower()

    def test_validate_sell_with_sufficient_holdings(self, test_db):
        """Test sell validation passes with enough shares"""
        from portfolio_service import validate_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        # First buy some shares
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 20, 150.0)

        # Now try to sell some
        result = validate_trade(
            db=test_db,
            portfolio_id=portfolio_id,
            symbol="AAPL",
            transaction_type="SELL",
            quantity=10,
            price_per_share=160.0
        )

        assert result['valid'] is True

    def test_validate_sell_with_insufficient_holdings(self, test_db):
        """Test sell validation fails without enough shares"""
        from portfolio_service import validate_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        # Buy only 5 shares
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 5, 150.0)

        # Try to sell 10
        result = validate_trade(
            db=test_db,
            portfolio_id=portfolio_id,
            symbol="AAPL",
            transaction_type="SELL",
            quantity=10,
            price_per_share=160.0
        )

        assert result['valid'] is False
        assert 'insufficient' in result['error'].lower()

    def test_validate_sell_with_no_holdings(self, test_db):
        """Test sell validation fails when no shares owned"""
        from portfolio_service import validate_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        result = validate_trade(
            db=test_db,
            portfolio_id=portfolio_id,
            symbol="AAPL",
            transaction_type="SELL",
            quantity=10,
            price_per_share=160.0
        )

        assert result['valid'] is False

    def test_validate_requires_positive_quantity(self, test_db):
        """Test validation rejects zero or negative quantity"""
        from portfolio_service import validate_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        result = validate_trade(
            db=test_db,
            portfolio_id=portfolio_id,
            symbol="AAPL",
            transaction_type="BUY",
            quantity=0,
            price_per_share=150.0
        )

        assert result['valid'] is False


class TestExecuteTrade:
    """Tests for full trade execution flow"""

    def test_execute_buy_success(self, test_db):
        """Test successful buy execution"""
        from portfolio_service import execute_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        with patch('portfolio_service.is_market_open', return_value=True):
            with patch('portfolio_service.fetch_current_price', return_value=150.0):
                result = execute_trade(
                    db=test_db,
                    portfolio_id=portfolio_id,
                    symbol="AAPL",
                    transaction_type="BUY",
                    quantity=10
                )

        assert result['success'] is True
        assert result['transaction_id'] is not None
        assert result['price_per_share'] == 150.0
        assert result['total_value'] == 1500.0

        # Verify holdings updated
        holdings = test_db.get_portfolio_holdings(portfolio_id)
        assert holdings["AAPL"] == 10

        # Verify cash updated
        cash = test_db.get_portfolio_cash(portfolio_id)
        assert cash == 98500.0

    def test_execute_trade_fails_when_market_closed(self, test_db):
        """Test trade execution fails when market is closed"""
        from portfolio_service import execute_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        with patch('portfolio_service.is_market_open', return_value=False):
            result = execute_trade(
                db=test_db,
                portfolio_id=portfolio_id,
                symbol="AAPL",
                transaction_type="BUY",
                quantity=10
            )

        assert result['success'] is False
        assert 'market' in result['error'].lower()

    def test_execute_trade_fails_when_price_unavailable(self, test_db):
        """Test trade execution fails when price can't be fetched"""
        from portfolio_service import execute_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        with patch('portfolio_service.is_market_open', return_value=True):
            with patch('portfolio_service.fetch_current_price', return_value=None):
                result = execute_trade(
                    db=test_db,
                    portfolio_id=portfolio_id,
                    symbol="FAKE",
                    transaction_type="BUY",
                    quantity=10
                )

        assert result['success'] is False
        assert 'price' in result['error'].lower()

    def test_execute_sell_success(self, test_db):
        """Test successful sell execution"""
        from portfolio_service import execute_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        # First buy some shares
        test_db.record_transaction(portfolio_id, "AAPL", "BUY", 20, 150.0)

        with patch('portfolio_service.is_market_open', return_value=True):
            with patch('portfolio_service.fetch_current_price', return_value=160.0):
                result = execute_trade(
                    db=test_db,
                    portfolio_id=portfolio_id,
                    symbol="AAPL",
                    transaction_type="SELL",
                    quantity=10
                )

        assert result['success'] is True
        assert result['price_per_share'] == 160.0

        # Verify holdings updated
        holdings = test_db.get_portfolio_holdings(portfolio_id)
        assert holdings["AAPL"] == 10

    def test_execute_trade_with_note(self, test_db):
        """Test trade execution with optional note"""
        from portfolio_service import execute_trade

        user_id = test_db.create_user("google_123", "test@example.com", "Test User", None)
        portfolio_id = test_db.create_portfolio(user_id, "Test Portfolio")

        with patch('portfolio_service.is_market_open', return_value=True):
            with patch('portfolio_service.fetch_current_price', return_value=150.0):
                result = execute_trade(
                    db=test_db,
                    portfolio_id=portfolio_id,
                    symbol="AAPL",
                    transaction_type="BUY",
                    quantity=10,
                    note="Bought on dip"
                )

        assert result['success'] is True

        # Verify note was saved
        transactions = test_db.get_portfolio_transactions(portfolio_id)
        assert transactions[0]['note'] == "Bought on dip"
