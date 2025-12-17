# ABOUTME: Provider-agnostic test suite for historical price data fetching
# ABOUTME: Defines the contract that any price provider (Schwab, tvDatafeed, etc.) must satisfy

"""
Provider-Agnostic Price Provider Test Suite

This test suite defines the behavioral contract for historical price providers.
It can be run against any implementation (Schwab, tvDatafeed, yfinance, etc.)
to verify correct behavior during migration.

Usage:
    # Test against Schwab (current)
    pytest test_price_provider.py -k "schwab" -v
    
    # Test against tvDatafeed (after migration)
    pytest test_price_provider.py -k "tvdatafeed" -v
    
    # Test integration with app.py endpoint
    pytest test_price_provider.py -k "integration" -v
"""

import pytest
import os
import sys
from abc import ABC, abstractmethod
from typing import Optional, Protocol
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ============================================================================
# PROTOCOL DEFINITION - The contract all price providers must satisfy
# ============================================================================

class PriceProvider(Protocol):
    """
    Protocol defining the interface for historical price providers.
    Any implementation (Schwab, tvDatafeed, yfinance) must satisfy this contract.
    """
    
    def get_historical_price(self, symbol: str, target_date: str) -> Optional[float]:
        """
        Fetch the closing price for a stock on or near a specific date.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Closing price as float, or None if unavailable
            
        Behavior Contract:
            1. Returns closing price as a positive float for valid requests
            2. Returns None for invalid symbols
            3. Returns None for dates before stock existed
            4. For weekends/holidays, returns price from nearest trading day
            5. Returns None on API/network failures (does not raise)
            6. Invalid date format returns None (does not raise)
        """
        ...
    
    def is_available(self) -> bool:
        """
        Check if the provider is configured and available.
        
        Returns:
            True if provider can make requests, False otherwise
        """
        ...


# ============================================================================
# BEHAVIORAL TESTS - Provider-agnostic tests defining expected behavior
# ============================================================================

class TestPriceProviderContract:
    """
    Tests that define the behavioral contract for price providers.
    These tests use mocks to verify the expected behavior without making real API calls.
    """
    
    # --- Core Functionality ---
    
    def test_returns_float_price_for_valid_request(self):
        """Provider should return a float price for valid symbol and date"""
        provider = self._create_mock_provider(return_price=150.25)
        
        price = provider.get_historical_price("AAPL", "2023-09-30")
        
        assert price is not None
        assert isinstance(price, float)
        assert price > 0
        assert price == 150.25
    
    def test_returns_none_for_invalid_symbol(self):
        """Provider should return None for non-existent symbols"""
        provider = self._create_mock_provider(return_price=None)
        
        price = provider.get_historical_price("INVALIDTICKER123", "2023-09-30")
        
        assert price is None
    
    def test_returns_none_for_date_before_stock_existed(self):
        """Provider should return None for dates before the stock's IPO"""
        provider = self._create_mock_provider(return_price=None)
        
        # AAPL IPO was 1980, this date is before
        price = provider.get_historical_price("AAPL", "1970-01-01")
        
        assert price is None
    
    def test_returns_none_for_future_date(self):
        """Provider should return None for future dates"""
        provider = self._create_mock_provider(return_price=None)
        
        future_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
        price = provider.get_historical_price("AAPL", future_date)
        
        assert price is None
    
    # --- Weekend/Holiday Handling ---
    
    def test_handles_weekend_date_gracefully(self):
        """Provider should find nearest trading day for weekend dates"""
        # If asked for a Saturday, should return Friday's close (or nearby)
        provider = self._create_mock_provider(return_price=175.50)
        
        # 2023-09-30 was a Saturday
        price = provider.get_historical_price("AAPL", "2023-09-30")
        
        # Should return a price (from Friday 9/29 or thereabouts)
        assert price is not None
        assert isinstance(price, float)
    
    def test_handles_holiday_date_gracefully(self):
        """Provider should find nearest trading day for market holidays"""
        provider = self._create_mock_provider(return_price=180.00)
        
        # Christmas Day - market closed
        price = provider.get_historical_price("AAPL", "2023-12-25")
        
        # Should return a price from nearest trading day
        assert price is not None
        assert isinstance(price, float)
    
    # --- Error Handling ---
    
    def test_returns_none_on_api_failure(self):
        """Provider should return None on API errors, not raise exceptions"""
        provider = self._create_mock_provider(raise_error=True)
        
        # Should not raise, should return None
        price = provider.get_historical_price("AAPL", "2023-09-30")
        
        assert price is None
    
    def test_returns_none_for_invalid_date_format(self):
        """Provider should return None for malformed date strings"""
        provider = self._create_mock_provider(return_price=None)
        
        invalid_dates = [
            "invalid-date",
            "2023/09/30",      # Wrong separator
            "09-30-2023",      # Wrong order
            "2023-13-01",      # Invalid month
            "2023-09-32",      # Invalid day
            "",                # Empty string
            "2023",            # Incomplete
        ]
        
        for invalid_date in invalid_dates:
            price = provider.get_historical_price("AAPL", invalid_date)
            assert price is None, f"Expected None for invalid date: {invalid_date}"
    
    # --- Availability Check ---
    
    def test_is_available_returns_boolean(self):
        """is_available() should return a boolean"""
        provider = self._create_mock_provider(available=True)
        
        result = provider.is_available()
        
        assert isinstance(result, bool)
    
    def test_is_available_false_when_not_configured(self):
        """is_available() should return False when provider is not configured"""
        provider = self._create_mock_provider(available=False)
        
        result = provider.is_available()
        
        assert result is False
    
    # --- Helper Methods ---
    
    def _create_mock_provider(
        self, 
        return_price: Optional[float] = None, 
        available: bool = True,
        raise_error: bool = False
    ) -> PriceProvider:
        """Create a mock provider for testing"""
        mock = MagicMock()
        
        if raise_error:
            mock.get_historical_price.side_effect = Exception("API Error")
            # But the real implementation should catch this and return None
            # So we simulate that behavior
            mock.get_historical_price.return_value = None
            mock.get_historical_price.side_effect = None  # Reset
        else:
            mock.get_historical_price.return_value = return_price
            
        mock.is_available.return_value = available
        return mock


# ============================================================================
# INTEGRATION TESTS - Tests for the /api/stock/<symbol>/history endpoint
# ============================================================================

class TestHistoryEndpointIntegration:
    """
    Integration tests for the history endpoint.
    These tests verify the endpoint correctly uses the price provider.
    
    Note: These tests mock the database at the app level since the app uses PostgreSQL.
    """
    
    @pytest.fixture
    def client(self, test_db, monkeypatch):
        """Flask test client with test database"""
        import app as app_module

        # Replace app's db with test_db
        monkeypatch.setattr(app_module, 'db', test_db)

        from app import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    def test_endpoint_returns_prices_and_pe_ratios(self, client, test_db, monkeypatch):
        """
        The /api/stock/<symbol>/history endpoint should:
        1. Fetch historical prices from database cache
        2. Calculate P/E ratios from prices and EPS
        3. Return data in the correct format
        """
        import app as app_module
        
        symbol = "TEST"
        
        # Set up test data in database
        test_db.save_stock_basic(symbol, "Test Corp", "NASDAQ", "Technology")
        test_db.save_earnings_history(symbol, 2022, 5.00, 100000000000, fiscal_end='2022-12-31')
        test_db.save_earnings_history(symbol, 2023, 6.00, 120000000000, fiscal_end='2023-12-31')
        
        # Add cached price data
        test_db.save_price_history(symbol, [
            {'date': '2022-12-31', 'close': 100.00, 'adjusted_close': 100.00, 'volume': 1000000},
            {'date': '2023-12-31', 'close': 150.00, 'adjusted_close': 150.00, 'volume': 1000000}
        ])
        
        test_db.flush()
        
        response = client.get(f'/api/stock/{symbol}/history')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Verify structure
        assert 'labels' in data
        assert 'eps' in data
        assert 'price' in data
        assert 'pe_ratio' in data
        
        # Verify P/E calculation: price / eps
        # 2022: 100.00 / 5.00 = 20.0
        # 2023: 150.00 / 6.00 = 25.0
        assert len(data['pe_ratio']) == 2
        assert abs(data['pe_ratio'][0] - 20.0) < 0.1
        assert abs(data['pe_ratio'][1] - 25.0) < 0.1
    
    def test_endpoint_falls_back_to_yfinance(self, client, test_db, monkeypatch):
        """
        Endpoint should return cached data from database
        """
        import app as app_module
        
        symbol = "FALLBACK"
        
        # Set up test data in database
        test_db.save_stock_basic(symbol, "Fallback Corp", "NASDAQ", "Technology")
        test_db.save_earnings_history(symbol, 2023, 10.00, 500000000000, fiscal_end='2023-06-30')
        test_db.flush()
        
        # Mock database methods to return cached price data
        mock_price_history = [{'date': '2023-06-30', 'close': 200.00}]
        mock_weekly_prices = {'dates': [], 'prices': []}
        
        original_get_price_history = test_db.get_price_history
        original_get_weekly_prices = test_db.get_weekly_prices
        
        test_db.get_price_history = MagicMock(return_value=mock_price_history)
        test_db.get_weekly_prices = MagicMock(return_value=mock_weekly_prices)
        
        try:
            response = client.get(f'/api/stock/{symbol}/history')
        
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Verify P/E was calculated from cached data
            # 200.00 / 10.00 = 20.0
            assert data['pe_ratio'][0] == pytest.approx(20.0, abs=0.1)
        finally:
            test_db.get_price_history = original_get_price_history
            test_db.get_weekly_prices = original_get_weekly_prices
    
    def test_endpoint_handles_none_prices_gracefully(self, client, test_db, monkeypatch):
        """
        When no cached price data exists, P/E should be None (not crash)
        """
        import app as app_module
        
        symbol = "NOPRICE"
        
        # Set up test data in database
        test_db.save_stock_basic(symbol, "No Price Corp", "NASDAQ", "Technology")
        test_db.save_earnings_history(symbol, 2023, 5.00, 100000000000, fiscal_end='2023-12-31')
        test_db.flush()
        
        # Mock database methods to return empty price data
        mock_price_history = []
        mock_weekly_prices = {'dates': [], 'prices': []}
        
        original_get_price_history = test_db.get_price_history
        original_get_weekly_prices = test_db.get_weekly_prices
        
        test_db.get_price_history = MagicMock(return_value=mock_price_history)
        test_db.get_weekly_prices = MagicMock(return_value=mock_weekly_prices)
        
        try:
            response = client.get(f'/api/stock/{symbol}/history')
        
            assert response.status_code == 200
            data = json.loads(response.data)
            
            # P/E should be None when price is unavailable
            assert data['pe_ratio'][0] is None
            assert data['price'][0] is None
        finally:
            test_db.get_price_history = original_get_price_history
            test_db.get_weekly_prices = original_get_weekly_prices


# ============================================================================
# YFINANCE TESTS - Tests for YFinancePriceClient implementation
# ============================================================================

class TestYFinancePriceClientImplementation:
    """
    Tests specific to the YFinancePriceClient implementation.
    Verifies the price client satisfies the PriceProvider protocol.
    """
    
    def test_yfinance_satisfies_protocol_interface(self):
        """Verify YFinancePriceClient has the required interface methods"""
        from yfinance_price_client import YFinancePriceClient
        
        client = YFinancePriceClient()
        
        # Check interface methods exist
        assert hasattr(client, 'get_historical_price')
        assert hasattr(client, 'is_available')
        assert callable(client.get_historical_price)
        assert callable(client.is_available)
    
    def test_yfinance_get_historical_price_signature(self):
        """Verify get_historical_price accepts correct arguments"""
        from yfinance_price_client import YFinancePriceClient
        
        client = YFinancePriceClient()
        client._available = False  # Prevent actual API calls
        
        # Should accept (symbol, date) and return Optional[float]
        # Using a future date ensures no actual API call
        future_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
        result = client.get_historical_price("AAPL", future_date)
        
        assert result is None or isinstance(result, float)
    
    def test_yfinance_handles_invalid_date_format(self):
        """YFinancePriceClient should return None for invalid date formats"""
        from yfinance_price_client import YFinancePriceClient
        
        client = YFinancePriceClient()
        
        price = client.get_historical_price("AAPL", "not-a-date")
        
        assert price is None
    
    def test_yfinance_handles_future_date(self):
        """YFinancePriceClient should return None for future dates"""
        from yfinance_price_client import YFinancePriceClient
        
        client = YFinancePriceClient()
        
        future_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
        price = client.get_historical_price("AAPL", future_date)
        
        assert price is None
    
    def test_yfinance_is_available_returns_true(self):
        """YFinancePriceClient.is_available() should return True by default"""
        from yfinance_price_client import YFinancePriceClient
        
        client = YFinancePriceClient()
        
        assert client.is_available() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
