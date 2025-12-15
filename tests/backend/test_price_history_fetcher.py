"""
Unit tests for PriceHistoryFetcher
Tests the fetching and caching of price history data
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from price_history_fetcher import PriceHistoryFetcher


class TestPriceHistoryFetcher:
    """Test suite for PriceHistoryFetcher"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        db = Mock()
        db.save_weekly_prices = Mock()
        db.save_price_point = Mock()
        db.get_earnings_history = Mock()
        return db
    
    @pytest.fixture
    def mock_price_client(self):
        """Create a mock price client"""
        client = Mock()
        client.get_weekly_price_history = Mock()
        client.get_historical_price = Mock()
        return client
    
    @pytest.fixture
    def fetcher(self, mock_db, mock_price_client):
        """Create a PriceHistoryFetcher instance"""
        return PriceHistoryFetcher(mock_db, mock_price_client)
    
    def test_fetch_weekly_prices_success(self, fetcher, mock_db, mock_price_client):
        """Test successful weekly price fetching"""
        # Setup
        symbol = "AAPL"
        weekly_data = {
            'dates': ['2023-01-01', '2023-01-08', '2023-01-15'],
            'prices': [150.0, 152.5, 155.0]
        }
        mock_price_client.get_weekly_price_history.return_value = weekly_data
        mock_db.get_earnings_history.return_value = []
        
        # Execute
        fetcher.fetch_and_cache_prices(symbol)
        
        # Verify
        mock_price_client.get_weekly_price_history.assert_called_once_with(symbol)
        mock_db.save_weekly_prices.assert_called_once_with(symbol, weekly_data)
    
    def test_fetch_weekly_prices_no_data(self, fetcher, mock_db, mock_price_client):
        """Test handling of no weekly price data"""
        # Setup
        symbol = "AAPL"
        mock_price_client.get_weekly_price_history.return_value = None
        mock_db.get_earnings_history.return_value = []
        
        # Execute
        fetcher.fetch_and_cache_prices(symbol)
        
        # Verify - should not save if no data
        mock_db.save_weekly_prices.assert_not_called()
    
    def test_fetch_fiscal_year_end_prices(self, fetcher, mock_db, mock_price_client):
        """Test fetching fiscal year-end prices"""
        # Setup
        symbol = "AAPL"
        earnings = [
            {'fiscal_end': '2023-09-30', 'eps': 6.0},
            {'fiscal_end': '2022-09-30', 'eps': 5.5},
            {'fiscal_end': '2021-09-30', 'eps': 5.0}
        ]
        mock_db.get_earnings_history.return_value = earnings
        mock_price_client.get_weekly_price_history.return_value = {'dates': [], 'prices': []}
        mock_price_client.get_historical_price.side_effect = [175.0, 155.0, 145.0]
        
        # Execute
        fetcher.fetch_and_cache_prices(symbol)
        
        # Verify
        assert mock_price_client.get_historical_price.call_count == 3
        assert mock_db.save_price_point.call_count == 3
        mock_db.save_price_point.assert_any_call(symbol, '2023-09-30', 175.0)
        mock_db.save_price_point.assert_any_call(symbol, '2022-09-30', 155.0)
        mock_db.save_price_point.assert_any_call(symbol, '2021-09-30', 145.0)
    
    def test_fetch_handles_missing_fiscal_end(self, fetcher, mock_db, mock_price_client):
        """Test handling of earnings without fiscal_end"""
        # Setup
        symbol = "AAPL"
        earnings = [
            {'fiscal_end': None, 'eps': 6.0},
            {'fiscal_end': '2022-09-30', 'eps': 5.5}
        ]
        mock_db.get_earnings_history.return_value = earnings
        mock_price_client.get_weekly_price_history.return_value = {'dates': [], 'prices': []}
        mock_price_client.get_historical_price.return_value = 155.0
        
        # Execute
        fetcher.fetch_and_cache_prices(symbol)
        
        # Verify - should only fetch for entries with fiscal_end
        assert mock_price_client.get_historical_price.call_count == 1
        mock_db.save_price_point.assert_called_once_with(symbol, '2022-09-30', 155.0)
    
    def test_fetch_handles_price_fetch_error(self, fetcher, mock_db, mock_price_client):
        """Test handling of price fetch errors"""
        # Setup
        symbol = "AAPL"
        earnings = [{'fiscal_end': '2023-09-30', 'eps': 6.0}]
        mock_db.get_earnings_history.return_value = earnings
        mock_price_client.get_weekly_price_history.return_value = {'dates': [], 'prices': []}
        mock_price_client.get_historical_price.side_effect = Exception("API Error")
        
        # Execute - should not raise exception
        fetcher.fetch_and_cache_prices(symbol)
        
        # Verify - should not save if fetch failed
        mock_db.save_price_point.assert_not_called()
    
    def test_fetch_handles_no_earnings_history(self, fetcher, mock_db, mock_price_client):
        """Test handling when stock has no earnings history"""
        # Setup
        symbol = "NEWCO"
        mock_db.get_earnings_history.return_value = []
        mock_price_client.get_weekly_price_history.return_value = {'dates': [], 'prices': []}
        
        # Execute
        fetcher.fetch_and_cache_prices(symbol)
        
        # Verify - should not attempt to fetch fiscal year-end prices
        mock_price_client.get_historical_price.assert_not_called()
        mock_db.save_price_point.assert_not_called()
