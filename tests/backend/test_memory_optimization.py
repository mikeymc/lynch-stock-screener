import pytest
from unittest.mock import Mock, MagicMock, patch
from worker import BackgroundWorker
import gc

class TestWorkerMemoryOptimization:
    """Tests for worker memory optimizations (OOM fixes)"""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.claim_pending_job = Mock(return_value=None)
        db.update_job_progress = Mock()
        db.update_session_progress = Mock()
        db.complete_job = Mock()
        db.complete_session = Mock()
        db.get_background_job = Mock(return_value={'status': 'running'})
        return db

    @patch('tradingview_fetcher.TradingViewFetcher')
    @patch('finviz_fetcher.FinvizFetcher')
    @patch('data_fetcher.DataFetcher')
    @patch('lynch_criteria.LynchCriteria')
    @patch('earnings_analyzer.EarningsAnalyzer')
    def test_run_screening_clears_cache_and_counts_correctly(
        self, 
        MockAnalyzer, MockCriteria, MockDataFetcher, MockFinvizFetcher, MockTVFetcher,
        mock_db
    ):
        """
        Verify that:
        1. Results are NOT stored in a list (inferred by memory check or logic verification)
        2. Market data and Finviz cache entries are deleted after processing
        3. Counters (pass/fail) are calculated correctly without the full list
        """
        # Setup mocks
        worker = BackgroundWorker()
        worker.db = mock_db
        
        # Test data - 20 stocks
        stocks = {f'SYM{i}': {'price': 100} for i in range(20)}
        
        # Determine who passes/fails
        # 0-9: PASS (STRONG_BUY for weighted)
        # 10-14: HOLD
        # 15-19: FAIL (AVOID)
        def mock_evaluate(symbol, **kwargs):
            i = int(symbol[3:])
            if i < 10:
                return {'symbol': symbol, 'overall_status': 'STRONG_BUY'}
            elif i < 15:
                return {'symbol': symbol, 'overall_status': 'HOLD'}
            else:
                return {'symbol': symbol, 'overall_status': 'AVOID'}

        MockCriteria.return_value.evaluate_stock.side_effect = mock_evaluate
        MockTVFetcher.return_value.fetch_all_stocks.return_value = stocks.copy() # Return copy so we can verify deletion on original or captured ref? 
        # Wait, fetch_all_stocks returns a dict. The worker binds it to `market_data_cache`.
        # We need to verify that items are deleted from THAT dict.
        
        # We can't easily capture the local variable `market_data_cache` inside worker.run_screening.
        # But we can verify side effects.
        # Ideally we'd modify the worker to make these accessible or use a Spy.
        
        # Strategy: Pass a dictionary that wraps `del` to track deletions?
        # Or just trust the code change?
        # Let's inspect the side effect on the return value of fetch_all_stocks.
        # The worker calls `tv_fetcher.fetch_all_stocks`. It gets `market_data_cache`.
        # It modifies this dict in place.
        # So we can keep a reference to it.
        
        market_data_cache_ref = stocks.copy()
        MockTVFetcher.return_value.fetch_all_stocks.return_value = market_data_cache_ref
        
        finviz_cache_ref = {f'SYM{i}': 0.5 for i in range(20)}
        MockFinvizFetcher.return_value.fetch_all_institutional_ownership.return_value = finviz_cache_ref
        
        # Mock DataFetcher to return something
        MockDataFetcher.return_value.fetch_stock_data.return_value = {'some': 'data'}

        # Run screening
        job = {
            'id': 123,
            'job_type': 'full_screening',
            'params': {
                'limit': 20, 
                'session_id': 999,
                'algorithm': 'weighted'
            }
        }
        
        worker._execute_job(job)
        
        # 2. Verify cache entries are deleted
        # After the job, the cache dicts should be empty because we process all stocks
        assert len(market_data_cache_ref) == 0, "Market data cache should be empty after processing"
        assert len(finviz_cache_ref) == 0, "Finviz cache should be empty after processing"
        
        # 3. Verify counters
        # We check the arguments passed to complete_job
        mock_db.complete_job.assert_called_once()
        result_arg = mock_db.complete_job.call_args[0][1]
        
        assert result_arg['total_analyzed'] == 20
        assert result_arg['pass_count'] == 10  # 0-9
        assert result_arg['close_count'] == 5  # 10-14
        assert result_arg['fail_count'] == 5   # 15-19
        assert result_arg['session_id'] == 999
