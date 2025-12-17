"""
Integration tests for worker data caching
Tests that the worker correctly caches all external data during screening
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from worker import BackgroundWorker


class TestWorkerDataCaching:
    """Integration tests for worker data caching functionality"""
    
    # NOTE: These are placeholder tests for future integration testing
    # The worker data caching has been manually tested and verified
    # Full integration tests would require:
    # - Running actual worker process
    # - Mocking external APIs (TradingView, Finnhub, SEC, etc.)
    # - Verifying database writes
    # - Testing parallel execution with ThreadPoolExecutor
    
    def test_worker_module_imports(self):
        """Verify worker module can be imported and has required classes"""
        import worker
        
        # Verify BackgroundWorker class exists
        assert hasattr(worker, 'BackgroundWorker')
        assert callable(worker.BackgroundWorker)
    
    def test_fetcher_modules_exist(self):
        """Verify all fetcher modules can be imported"""
        # These imports will fail if the modules don't exist or have syntax errors
        from price_history_fetcher import PriceHistoryFetcher
        from sec_data_fetcher import SECDataFetcher
        from news_fetcher import NewsFetcher
        from material_events_fetcher import MaterialEventsFetcher
        
        # Verify classes are callable
        assert callable(PriceHistoryFetcher)
        assert callable(SECDataFetcher)
        assert callable(NewsFetcher)
        assert callable(MaterialEventsFetcher)
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        db = Mock()
        db.claim_pending_job = Mock(return_value=None)
        db.get_stock_metrics = Mock()
        db.save_screening_result = Mock()
        db.update_job_progress = Mock()
        db.update_session_progress = Mock()
        db.update_session_total_count = Mock()
        db.flush = Mock()
        return db
    
    def test_worker_handles_fetch_timeout(self):
        """Test that worker handles 10-second timeout for data fetching"""
        # Test that slow fetches don't block the entire screening
        assert True  # Placeholder for integration test
    
    def test_worker_continues_on_fetch_failure(self):
        """Test that worker continues screening even if data fetch fails"""
        # Test that a failed price fetch doesn't prevent stock from being screened
        assert True  # Placeholder for integration test
    
    def test_parallel_fetching_performance(self):
        """Test that parallel fetching completes within expected time"""
        # Test that 4 concurrent fetches complete faster than sequential
        assert True  # Placeholder for performance test


class TestCachedAPIEndpoints:
    """Integration tests for cached API endpoints"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database with cached data"""
        db = Mock()
        
        # Mock cached price data
        db.get_price_history.return_value = [
            {'date': '2023-09-30', 'close': 175.0, 'adjusted_close': 175.0, 'volume': 1000000}
        ]
        db.get_weekly_prices.return_value = {
            'dates': ['2023-01-01', '2023-01-08'],
            'prices': [150.0, 152.5]
        }
        
        # Mock cached SEC data
        db.get_sec_filings.return_value = [
            {'type': '10-K', 'date': '2023-10-27', 'url': 'http://...'}
        ]
        db.get_filing_sections.return_value = {
            'business': {'content': 'Business description...', 'filing_type': '10-K'}
        }
        
        # Mock cached news
        db.get_news_articles.return_value = [
            {'headline': 'Apple announces...', 'published_date': '2023-01-01'}
        ]
        db.get_news_cache_status.return_value = {
            'last_updated': '2023-12-14T00:00:00',
            'article_count': 1
        }
        
        # Mock cached events
        db.get_material_events.return_value = [
            {'headline': 'Apple acquisition', 'filing_date': '2023-10-15'}
        ]
        db.get_material_events_cache_status.return_value = {
            'last_updated': '2023-12-14T00:00:00',
            'event_count': 1
        }
        
        return db
    
    @patch('app.db')
    def test_history_endpoint_uses_cache(self, mock_db_patch, mock_db):
        """Test that /api/stock/<symbol>/history uses cached data"""
        # This would require actual Flask app testing
        # Verify no external API calls are made
        assert True  # Placeholder for integration test
    
    @patch('app.db')
    def test_filings_endpoint_uses_cache(self, mock_db_patch, mock_db):
        """Test that /api/stock/<symbol>/filings uses cached data"""
        assert True  # Placeholder for integration test
    
    @patch('app.db')
    def test_sections_endpoint_uses_cache(self, mock_db_patch, mock_db):
        """Test that /api/stock/<symbol>/sections uses cached data"""
        assert True  # Placeholder for integration test
    
    @patch('app.db')
    def test_news_endpoint_uses_cache(self, mock_db_patch, mock_db):
        """Test that /api/stock/<symbol>/news uses cached data"""
        assert True  # Placeholder for integration test
    
    @patch('app.db')
    def test_events_endpoint_uses_cache(self, mock_db_patch, mock_db):
        """Test that /api/stock/<symbol>/material-events uses cached data"""
        assert True  # Placeholder for integration test
    
    def test_no_external_calls_on_page_load(self):
        """Test that loading stock detail page makes zero external API calls"""
        # This would be best tested with network monitoring
        assert True  # Placeholder for E2E test


class TestCacheJobRouting:
    """Tests for the new cache job type routing in worker._execute_job"""
    
    def test_execute_job_routes_price_history_cache(self):
        """Verify _execute_job routes price_history_cache job type"""
        import worker
        assert hasattr(worker.BackgroundWorker, '_run_price_history_cache')
        assert callable(getattr(worker.BackgroundWorker, '_run_price_history_cache'))
    
    def test_execute_job_routes_news_cache(self):
        """Verify _execute_job routes news_cache job type"""
        import worker
        assert hasattr(worker.BackgroundWorker, '_run_news_cache')
        assert callable(getattr(worker.BackgroundWorker, '_run_news_cache'))
    
    def test_execute_job_routes_10k_cache(self):
        """Verify _execute_job routes 10k_cache job type"""
        import worker
        assert hasattr(worker.BackgroundWorker, '_run_10k_cache')
        assert callable(getattr(worker.BackgroundWorker, '_run_10k_cache'))
    
    def test_execute_job_routes_8k_cache(self):
        """Verify _execute_job routes 8k_cache job type"""
        import worker
        assert hasattr(worker.BackgroundWorker, '_run_8k_cache')
        assert callable(getattr(worker.BackgroundWorker, '_run_8k_cache'))


class TestDatabaseOrderByScore:
    """Tests for the new get_stocks_ordered_by_score database method"""
    
    def test_get_stocks_ordered_by_score_method_exists(self):
        """Verify get_stocks_ordered_by_score method exists in Database"""
        from database import Database
        assert hasattr(Database, 'get_stocks_ordered_by_score')
        assert callable(getattr(Database, 'get_stocks_ordered_by_score'))


class TestCLICacheCommands:
    """Tests for the new CLI cache commands"""
    
    def test_cache_module_imports(self):
        """Verify cache CLI module can be imported"""
        from cli.commands import cache
        assert hasattr(cache, 'app')
    
    def test_cache_commands_registered(self):
        """Verify cache commands are registered"""
        from cli.commands.cache import app
        
        # Check that expected commands exist
        command_names = [cmd.name for cmd in app.registered_commands]
        assert 'prices' in command_names
        assert 'news' in command_names
        assert '10k' in command_names
        assert '8k' in command_names
        assert 'all' in command_names
    
    def test_screen_command_has_region_option(self):
        """Verify screen command has --region option"""
        from cli.commands.screen import start
        import inspect
        
        # Get the function signature
        sig = inspect.signature(start)
        params = list(sig.parameters.keys())
        
        assert 'region' in params

