"""
Tests for smart incremental price caching in PriceHistoryFetcher
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from price_history_fetcher import PriceHistoryFetcher


class TestIncrementalPriceCaching:
    """Test suite for smart incremental price updates"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        db = Mock()
        db.get_weekly_prices = Mock()
        db.save_weekly_prices = Mock()
        return db
    
    @pytest.fixture
    def mock_price_client(self):
        """Mock yfinance price client"""
        client = Mock()
        client.get_weekly_price_history = Mock()
        client.get_weekly_price_history_since = Mock()
        return client
    
    @pytest.fixture
    def fetcher(self, mock_db, mock_price_client):
        """Create PriceHistoryFetcher instance"""
        return PriceHistoryFetcher(mock_db, mock_price_client, yf_semaphore=None)
    
    def test_full_history_when_no_cached_data(self, fetcher, mock_db, mock_price_client):
        """Test that full history is fetched when no cached data exists"""
        # Setup: No existing data
        mock_db.get_weekly_prices.return_value = None
        
        # Setup: Mock full history response
        mock_price_client.get_weekly_price_history.return_value = {
            'dates': ['2024-01-05', '2024-01-12', '2024-01-19'],
            'prices': [150.0, 152.0, 151.0]
        }
        
        # Execute
        fetcher.fetch_and_cache_prices('AAPL')
        
        # Verify: Full history was fetched
        mock_price_client.get_weekly_price_history.assert_called_once_with('AAPL')
        mock_price_client.get_weekly_price_history_since.assert_not_called()
        
        # Verify: Data was saved
        mock_db.save_weekly_prices.assert_called_once()
        saved_data = mock_db.save_weekly_prices.call_args[0][1]
        assert len(saved_data['dates']) == 3
    
    def test_incremental_update_when_cached_data_exists(self, fetcher, mock_db, mock_price_client):
        """Test that only new data is fetched when cached data exists"""
        # Setup: Existing data in cache
        mock_db.get_weekly_prices.return_value = {
            'dates': ['2024-01-05', '2024-01-12', '2024-01-19'],
            'prices': [150.0, 152.0, 151.0]
        }
        
        # Setup: Mock incremental response (2 new weeks)
        mock_price_client.get_weekly_price_history_since.return_value = {
            'dates': ['2024-01-26', '2024-02-02'],
            'prices': [153.0, 154.0]
        }
        
        # Execute
        fetcher.fetch_and_cache_prices('AAPL')
        
        # Verify: Incremental fetch was used
        mock_price_client.get_weekly_price_history_since.assert_called_once_with('AAPL', '2024-01-19')
        mock_price_client.get_weekly_price_history.assert_not_called()
        
        # Verify: New data was saved
        mock_db.save_weekly_prices.assert_called_once()
        saved_data = mock_db.save_weekly_prices.call_args[0][1]
        assert len(saved_data['dates']) == 2
        assert saved_data['dates'][0] == '2024-01-26'
    
    def test_empty_cached_data_triggers_full_fetch(self, fetcher, mock_db, mock_price_client):
        """Test that empty cached data triggers full history fetch"""
        # Setup: Empty cached data
        mock_db.get_weekly_prices.return_value = {'dates': [], 'prices': []}
        
        # Setup: Mock full history response
        mock_price_client.get_weekly_price_history.return_value = {
            'dates': ['2024-01-05'],
            'prices': [150.0]
        }
        
        # Execute
        fetcher.fetch_and_cache_prices('AAPL')
        
        # Verify: Full history was fetched (empty dates means no data)
        mock_price_client.get_weekly_price_history.assert_called_once()
    
    def test_no_new_data_available(self, fetcher, mock_db, mock_price_client):
        """Test handling when no new data is available"""
        # Setup: Existing data
        mock_db.get_weekly_prices.return_value = {
            'dates': ['2024-12-13'],
            'prices': [250.0]
        }
        
        # Setup: No new data available
        mock_price_client.get_weekly_price_history_since.return_value = {
            'dates': [],
            'prices': []
        }
        
        # Execute
        fetcher.fetch_and_cache_prices('AAPL')
        
        # Verify: Incremental fetch was attempted
        mock_price_client.get_weekly_price_history_since.assert_called_once()
        
        # Verify: Nothing saved because empty data means no new weeks
        # (The implementation treats empty arrays as "no data" and doesn't save)
        mock_db.save_weekly_prices.assert_not_called()
    
    def test_uses_most_recent_date_from_cache(self, fetcher, mock_db, mock_price_client):
        """Test that the most recent date is used as start date"""
        # Setup: Multiple weeks in cache
        mock_db.get_weekly_prices.return_value = {
            'dates': ['2024-01-05', '2024-01-12', '2024-01-19', '2024-01-26'],
            'prices': [150.0, 152.0, 151.0, 153.0]
        }
        
        mock_price_client.get_weekly_price_history_since.return_value = {
            'dates': ['2024-02-02'],
            'prices': [154.0]
        }
        
        # Execute
        fetcher.fetch_and_cache_prices('AAPL')
        
        # Verify: Most recent date was used
        mock_price_client.get_weekly_price_history_since.assert_called_once_with('AAPL', '2024-01-26')


class TestYFinancePriceClientIncremental:
    """Test suite for YFinancePriceClient.get_weekly_price_history_since()"""
    
    @pytest.fixture
    def price_client(self):
        """Create YFinancePriceClient instance"""
        from yfinance_price_client import YFinancePriceClient
        return YFinancePriceClient()
    
    @patch('yfinance.Ticker')
    def test_fetches_data_from_start_date(self, mock_ticker_class, price_client):
        """Test that data is fetched starting from the given date"""
        import pandas as pd
        
        # Setup: Mock yfinance response
        mock_ticker = Mock()
        mock_ticker_class.return_value = mock_ticker
        
        # Create mock DataFrame with weekly data
        dates = pd.date_range('2024-12-01', periods=5, freq='W-FRI')
        mock_df = pd.DataFrame({
            'Close': [250.0, 251.0, 252.0, 253.0, 254.0]
        }, index=dates)
        mock_ticker.history.return_value = mock_df
        
        # Execute
        result = price_client.get_weekly_price_history_since('AAPL', '2024-12-01')
        
        # Verify: yfinance was called with correct parameters
        mock_ticker.history.assert_called_once_with(start='2024-12-01', interval='1wk')
        
        # Verify: First row was skipped (to avoid duplicate)
        assert len(result['dates']) == 4  # 5 rows - 1 skipped
        assert result['dates'][0] != '2024-12-01'  # First date should be skipped
    
    @patch('yfinance.Ticker')
    def test_returns_empty_when_no_new_data(self, mock_ticker_class, price_client):
        """Test that empty arrays are returned when no new data exists"""
        import pandas as pd
        
        # Setup: Mock yfinance response with only 1 row (the start date)
        mock_ticker = Mock()
        mock_ticker_class.return_value = mock_ticker
        
        dates = pd.date_range('2024-12-13', periods=1, freq='W-FRI')
        mock_df = pd.DataFrame({
            'Close': [250.0]
        }, index=dates)
        mock_ticker.history.return_value = mock_df
        
        # Execute
        result = price_client.get_weekly_price_history_since('AAPL', '2024-12-13')
        
        # Verify: Empty arrays returned
        assert result['dates'] == []
        assert result['prices'] == []
    
    @patch('yfinance.Ticker')
    def test_handles_empty_response(self, mock_ticker_class, price_client):
        """Test handling of empty yfinance response"""
        import pandas as pd
        
        # Setup: Mock empty response
        mock_ticker = Mock()
        mock_ticker_class.return_value = mock_ticker
        mock_ticker.history.return_value = pd.DataFrame()
        
        # Execute
        result = price_client.get_weekly_price_history_since('AAPL', '2024-12-01')
        
        # Verify: None returned for error case
        assert result is None
    
    @patch('yfinance.Ticker')
    def test_handles_missing_close_column(self, mock_ticker_class, price_client):
        """Test handling when Close column is missing"""
        import pandas as pd
        
        # Setup: Mock response without Close column
        mock_ticker = Mock()
        mock_ticker_class.return_value = mock_ticker
        
        dates = pd.date_range('2024-12-01', periods=3, freq='W-FRI')
        mock_df = pd.DataFrame({
            'Open': [250.0, 251.0, 252.0]  # No Close column
        }, index=dates)
        mock_ticker.history.return_value = mock_df
        
        # Execute
        result = price_client.get_weekly_price_history_since('AAPL', '2024-12-01')
        
        # Verify: None returned for error case
        assert result is None


class TestPerformanceComparison:
    """Performance comparison tests (integration-style)"""
    
    @pytest.mark.slow
    @pytest.mark.integration
    def test_incremental_faster_than_full(self):
        """Verify that incremental fetch is faster than full history (integration test)"""
        import time
        from yfinance_price_client import YFinancePriceClient
        
        client = YFinancePriceClient()
        
        # Measure full history fetch
        start = time.time()
        full_data = client.get_weekly_price_history('AAPL')
        full_time = time.time() - start
        
        # Measure incremental fetch (last 3 months)
        start = time.time()
        incremental_data = client.get_weekly_price_history_since('AAPL', '2024-09-01')
        incremental_time = time.time() - start
        
        # Verify: Incremental is faster
        assert incremental_time < full_time, f"Incremental ({incremental_time:.2f}s) should be faster than full ({full_time:.2f}s)"
        
        # Verify: Both return valid data
        assert full_data is not None
        assert incremental_data is not None
        assert len(full_data['dates']) > len(incremental_data['dates'])
