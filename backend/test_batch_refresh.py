#!/usr/bin/env python3
"""
Tests for batch_refresh.py

Run with: pytest test_batch_refresh.py -v
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
import pytest

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from batch_refresh import BatchRefreshStats, BatchRefreshProcessor


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    temp = tempfile.mkdtemp()
    yield temp
    # Cleanup
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
def test_config_path(temp_dir):
    """Create a test configuration file"""
    config = {
        "enabled": True,
        "scheduling": {
            "run_time": "02:00",
            "timezone": "America/New_York"
        },
        "processing": {
            "batch_size": 10,
            "delay_between_batches_seconds": 0,
            "max_workers": 1,
            "force_refresh": True
        },
        "rate_limiting": {
            "edgar_requests_per_second": 9,
            "yfinance_delay_seconds": 0
        },
        "logging": {
            "log_directory": os.path.join(temp_dir, "logs"),
            "log_file": "test_batch.log",
            "max_log_size_mb": 10,
            "backup_count": 3,
            "log_level": "INFO",
            "console_output": False
        },
        "database": {
            "path": ":memory:",
            "backup_before_run": False,
            "backup_directory": os.path.join(temp_dir, "backups")
        },
        "error_handling": {
            "max_consecutive_failures": 5,
            "retry_failed_stocks": False,
            "max_retries_per_stock": 1,
            "continue_on_error": True
        },
        "reporting": {
            "generate_summary": True,
            "summary_directory": os.path.join(temp_dir, "reports"),
            "keep_last_n_reports": 5
        }
    }

    config_path = os.path.join(temp_dir, "test_config.json")
    with open(config_path, 'w') as f:
        json.dump(config, f)

    return config_path


@pytest.fixture
def mock_database():
    """Mock database"""
    db = MagicMock()
    return db


@pytest.fixture
def sample_stock_symbols():
    """Sample stock symbols for testing"""
    return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']


# ============================================================================
# Tests for BatchRefreshStats
# ============================================================================

class TestBatchRefreshStats:
    """Test the BatchRefreshStats class"""

    def test_initialization(self):
        """Test stats object initialization"""
        stats = BatchRefreshStats()

        assert stats.total_stocks == 0
        assert stats.successful == 0
        assert stats.failed == 0
        assert stats.skipped == 0
        assert stats.start_time is None
        assert stats.end_time is None
        assert stats.failed_symbols == []
        assert stats.error_counts == {}

    def test_record_success(self):
        """Test recording successful stock processing"""
        stats = BatchRefreshStats()

        stats.record_success('AAPL')
        assert stats.successful == 1

        stats.record_success('MSFT')
        assert stats.successful == 2

    def test_record_failure(self):
        """Test recording failed stock processing"""
        stats = BatchRefreshStats()

        stats.record_failure('AAPL', 'Network error')
        assert stats.failed == 1
        assert 'AAPL' in stats.failed_symbols
        assert stats.error_counts['str'] == 1

        # Test with exception
        error = ValueError('Invalid data')
        stats.record_failure('MSFT', error)
        assert stats.failed == 2
        assert 'MSFT' in stats.failed_symbols
        assert stats.error_counts['ValueError'] == 1

    def test_record_skip(self):
        """Test recording skipped stock"""
        stats = BatchRefreshStats()

        stats.record_skip('AAPL')
        assert stats.skipped == 1

        stats.record_skip('MSFT')
        assert stats.skipped == 2

    def test_get_duration(self):
        """Test duration calculation"""
        stats = BatchRefreshStats()

        # No times set
        assert stats.get_duration() == 0

        # Set times
        stats.start_time = datetime(2024, 1, 1, 2, 0, 0)
        stats.end_time = datetime(2024, 1, 1, 4, 30, 0)

        # 2.5 hours = 9000 seconds
        assert stats.get_duration() == 9000

    def test_get_summary(self):
        """Test summary generation"""
        stats = BatchRefreshStats()
        stats.total_stocks = 100
        stats.start_time = datetime(2024, 1, 1, 2, 0, 0)
        stats.end_time = datetime(2024, 1, 1, 4, 30, 0)

        # Record some results
        for i in range(95):
            stats.record_success(f'STOCK{i}')

        for i in range(5):
            stats.record_failure(f'FAIL{i}', 'Network error')

        summary = stats.get_summary()

        assert summary['total_stocks'] == 100
        assert summary['successful'] == 95
        assert summary['failed'] == 5
        assert summary['skipped'] == 0
        assert summary['success_rate'] == '95.00%'
        assert summary['duration_seconds'] == 9000
        assert len(summary['failed_symbols']) == 5
        assert 'str' in summary['error_types']

    def test_get_summary_zero_stocks(self):
        """Test summary with zero stocks"""
        stats = BatchRefreshStats()
        stats.total_stocks = 0

        summary = stats.get_summary()

        assert summary['total_stocks'] == 0
        assert summary['success_rate'] == '0.00%'

    def test_error_counts_aggregation(self):
        """Test that error types are properly counted"""
        stats = BatchRefreshStats()

        stats.record_failure('AAPL', ValueError('error1'))
        stats.record_failure('MSFT', ValueError('error2'))
        stats.record_failure('GOOGL', TypeError('error3'))
        stats.record_failure('AMZN', 'String error')

        assert stats.error_counts['ValueError'] == 2
        assert stats.error_counts['TypeError'] == 1
        assert stats.error_counts['str'] == 1

    def test_failed_symbols_limit(self):
        """Test that failed symbols are limited in summary"""
        stats = BatchRefreshStats()
        stats.total_stocks = 100

        # Record 60 failures
        for i in range(60):
            stats.record_failure(f'FAIL{i}', 'Error')

        summary = stats.get_summary()

        # Should only include first 50
        assert len(summary['failed_symbols']) == 50


# ============================================================================
# Tests for BatchRefreshProcessor
# ============================================================================

class TestBatchRefreshProcessor:
    """Test the BatchRefreshProcessor class"""

    def test_initialization(self, test_config_path):
        """Test processor initialization"""
        processor = BatchRefreshProcessor(test_config_path)

        assert processor.config is not None
        assert processor.logger is not None
        assert processor.db is not None
        assert processor.stats is not None

    def test_load_config_success(self, test_config_path):
        """Test successful configuration loading"""
        processor = BatchRefreshProcessor(test_config_path)

        assert processor.config['enabled'] is True
        assert processor.config['processing']['batch_size'] == 10

    def test_load_config_missing_file(self, temp_dir):
        """Test loading non-existent config file"""
        fake_path = os.path.join(temp_dir, "nonexistent.json")

        with pytest.raises(FileNotFoundError):
            BatchRefreshProcessor(fake_path)

    def test_load_config_invalid_json(self, temp_dir):
        """Test loading invalid JSON config"""
        config_path = os.path.join(temp_dir, "invalid.json")
        with open(config_path, 'w') as f:
            f.write("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            BatchRefreshProcessor(config_path)

    def test_logging_setup(self, test_config_path, temp_dir):
        """Test logging configuration"""
        processor = BatchRefreshProcessor(test_config_path)

        # Check log directory was created
        log_dir = os.path.join(temp_dir, "logs")
        assert os.path.exists(log_dir)

        # Check logger exists
        assert processor.logger.name == 'batch_refresh'

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    def test_get_stock_symbols(self, mock_get_symbols, test_config_path, sample_stock_symbols):
        """Test getting stock symbols"""
        mock_get_symbols.return_value = sample_stock_symbols

        processor = BatchRefreshProcessor(test_config_path)
        symbols = processor._get_stock_symbols()

        assert symbols == sample_stock_symbols
        assert len(symbols) == 5

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    def test_get_stock_symbols_with_limit(self, mock_get_symbols, test_config_path, sample_stock_symbols):
        """Test getting stock symbols with limit"""
        mock_get_symbols.return_value = sample_stock_symbols

        processor = BatchRefreshProcessor(test_config_path)
        symbols = processor._get_stock_symbols(limit=3)

        assert len(symbols) == 3
        assert symbols == sample_stock_symbols[:3]

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    def test_get_stock_symbols_error(self, mock_get_symbols, test_config_path):
        """Test error handling when fetching symbols"""
        mock_get_symbols.side_effect = Exception("API error")

        processor = BatchRefreshProcessor(test_config_path)

        with pytest.raises(Exception):
            processor._get_stock_symbols()

    @patch('batch_refresh.fetch_stock_data')
    def test_process_stock_success(self, mock_fetch, test_config_path):
        """Test successful stock processing"""
        mock_fetch.return_value = {'symbol': 'AAPL', 'price': 150.0}

        processor = BatchRefreshProcessor(test_config_path)
        success, error = processor._process_stock('AAPL')

        assert success is True
        assert error == ""
        mock_fetch.assert_called_once()

    @patch('batch_refresh.fetch_stock_data')
    def test_process_stock_no_data(self, mock_fetch, test_config_path):
        """Test stock processing with no data returned"""
        mock_fetch.return_value = None

        processor = BatchRefreshProcessor(test_config_path)
        success, error = processor._process_stock('AAPL')

        assert success is False
        assert error == "No data returned"

    @patch('batch_refresh.fetch_stock_data')
    def test_process_stock_exception(self, mock_fetch, test_config_path):
        """Test stock processing with exception"""
        mock_fetch.side_effect = ValueError("Invalid symbol")

        processor = BatchRefreshProcessor(test_config_path)
        success, error = processor._process_stock('INVALID')

        assert success is False
        assert "ValueError" in error

    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_process_batch(self, mock_sleep, mock_fetch, test_config_path, sample_stock_symbols):
        """Test batch processing"""
        mock_fetch.return_value = {'symbol': 'AAPL', 'price': 150.0}

        processor = BatchRefreshProcessor(test_config_path)
        processor._process_batch(sample_stock_symbols[:3], 1, 5)

        # Should have processed 3 stocks
        assert processor.stats.successful == 3
        assert processor.stats.failed == 0

        # Should have called fetch 3 times
        assert mock_fetch.call_count == 3

    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_process_batch_with_failures(self, mock_sleep, mock_fetch, test_config_path, sample_stock_symbols):
        """Test batch processing with some failures"""
        # First 2 succeed, last one fails
        mock_fetch.side_effect = [
            {'symbol': 'AAPL'},
            {'symbol': 'MSFT'},
            None
        ]

        processor = BatchRefreshProcessor(test_config_path)
        processor._process_batch(sample_stock_symbols[:3], 1, 1)

        assert processor.stats.successful == 2
        assert processor.stats.failed == 1

    def test_check_max_failures_under_limit(self, test_config_path):
        """Test max failures check when under limit"""
        processor = BatchRefreshProcessor(test_config_path)
        processor.stats.successful = 100
        processor.stats.failed = 3

        assert processor._check_max_failures() is False

    def test_check_max_failures_over_limit(self, test_config_path):
        """Test max failures check when over limit with low success rate"""
        processor = BatchRefreshProcessor(test_config_path)
        processor.stats.successful = 5
        processor.stats.failed = 50

        assert processor._check_max_failures() is True

    def test_check_max_failures_high_success_rate(self, test_config_path):
        """Test max failures check with high success rate"""
        processor = BatchRefreshProcessor(test_config_path)
        processor.stats.successful = 500
        processor.stats.failed = 50

        # Even with high failure count, success rate is high
        assert processor._check_max_failures() is False

    def test_save_report(self, test_config_path, temp_dir):
        """Test report saving"""
        processor = BatchRefreshProcessor(test_config_path)
        processor.stats.total_stocks = 10
        processor.stats.successful = 8
        processor.stats.failed = 2
        processor.stats.start_time = datetime.now()
        processor.stats.end_time = datetime.now()

        processor._save_report()

        # Check report was created
        report_dir = Path(temp_dir) / "reports"
        assert report_dir.exists()

        reports = list(report_dir.glob('batch_summary_*.json'))
        assert len(reports) == 1

        # Verify report content
        with open(reports[0]) as f:
            report = json.load(f)

        assert report['total_stocks'] == 10
        assert report['successful'] == 8
        assert report['failed'] == 2

    def test_cleanup_old_reports(self, test_config_path, temp_dir):
        """Test cleanup of old reports"""
        processor = BatchRefreshProcessor(test_config_path)

        # Create report directory
        report_dir = Path(temp_dir) / "reports"
        report_dir.mkdir(exist_ok=True)

        # Create 10 old reports
        for i in range(10):
            report_file = report_dir / f"batch_summary_2024010{i:02d}_000000.json"
            with open(report_file, 'w') as f:
                json.dump({'test': i}, f)

        # Cleanup should keep only last 5
        processor._cleanup_old_reports(report_dir)

        remaining_reports = list(report_dir.glob('batch_summary_*.json'))
        assert len(remaining_reports) == 5

    @patch('batch_refresh.shutil.copy2')
    def test_backup_database(self, mock_copy, test_config_path, temp_dir):
        """Test database backup"""
        # Update config to enable backup
        processor = BatchRefreshProcessor(test_config_path)
        processor.config['database']['backup_before_run'] = True
        processor.config['database']['path'] = os.path.join(temp_dir, 'test.db')

        # Create dummy database file
        Path(processor.config['database']['path']).touch()

        processor._backup_database()

        # Check backup directory was created
        backup_dir = Path(temp_dir) / "backups"
        assert backup_dir.exists()

        # Check copy was called
        assert mock_copy.called

    def test_backup_database_no_file(self, test_config_path, temp_dir):
        """Test database backup when file doesn't exist"""
        processor = BatchRefreshProcessor(test_config_path)
        processor.config['database']['backup_before_run'] = True
        processor.config['database']['path'] = os.path.join(temp_dir, 'nonexistent.db')

        # Should not raise error
        processor._backup_database()

    def test_backup_database_disabled(self, test_config_path):
        """Test that backup is skipped when disabled"""
        processor = BatchRefreshProcessor(test_config_path)
        processor.config['database']['backup_before_run'] = False

        # Should not raise error
        processor._backup_database()


# ============================================================================
# Integration Tests
# ============================================================================

class TestBatchRefreshIntegration:
    """Integration tests for the full batch process"""

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_run_dry_run(self, mock_sleep, mock_fetch, mock_get_symbols, test_config_path, sample_stock_symbols):
        """Test dry run mode"""
        mock_get_symbols.return_value = sample_stock_symbols

        processor = BatchRefreshProcessor(test_config_path)
        processor.run(dry_run=True)

        # Should not have fetched any data
        mock_fetch.assert_not_called()

        # Stats should be empty
        assert processor.stats.total_stocks == 5
        assert processor.stats.successful == 0

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_run_with_limit(self, mock_sleep, mock_fetch, mock_get_symbols, test_config_path, sample_stock_symbols):
        """Test run with stock limit"""
        mock_get_symbols.return_value = sample_stock_symbols
        mock_fetch.return_value = {'symbol': 'AAPL'}

        processor = BatchRefreshProcessor(test_config_path)
        processor.run(limit=3)

        # Should have processed only 3 stocks
        assert processor.stats.total_stocks == 3
        assert processor.stats.successful == 3
        assert mock_fetch.call_count == 3

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_run_full_process(self, mock_sleep, mock_fetch, mock_get_symbols, test_config_path, sample_stock_symbols, temp_dir):
        """Test full batch process"""
        mock_get_symbols.return_value = sample_stock_symbols
        mock_fetch.return_value = {'symbol': 'AAPL'}

        processor = BatchRefreshProcessor(test_config_path)
        processor.run()

        # Should have processed all stocks
        assert processor.stats.total_stocks == 5
        assert processor.stats.successful == 5
        assert processor.stats.failed == 0

        # Should have start and end times
        assert processor.stats.start_time is not None
        assert processor.stats.end_time is not None

        # Should have created a report
        report_dir = Path(temp_dir) / "reports"
        reports = list(report_dir.glob('batch_summary_*.json'))
        assert len(reports) == 1

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_run_with_mixed_results(self, mock_sleep, mock_fetch, mock_get_symbols, test_config_path, sample_stock_symbols):
        """Test run with both successes and failures"""
        mock_get_symbols.return_value = sample_stock_symbols

        # 3 successes, 2 failures
        mock_fetch.side_effect = [
            {'symbol': 'AAPL'},
            {'symbol': 'MSFT'},
            None,
            {'symbol': 'AMZN'},
            ValueError('Error')
        ]

        processor = BatchRefreshProcessor(test_config_path)
        processor.run()

        assert processor.stats.total_stocks == 5
        assert processor.stats.successful == 3
        assert processor.stats.failed == 2

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_run_disabled(self, mock_sleep, mock_fetch, mock_get_symbols, test_config_path):
        """Test that batch process respects enabled flag"""
        processor = BatchRefreshProcessor(test_config_path)
        processor.config['enabled'] = False

        processor.run()

        # Should not have processed anything
        mock_fetch.assert_not_called()

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_run_batch_splitting(self, mock_sleep, mock_fetch, mock_get_symbols, test_config_path):
        """Test that stocks are split into batches correctly"""
        # 25 stocks with batch size of 10
        symbols = [f'STOCK{i}' for i in range(25)]
        mock_get_symbols.return_value = symbols
        mock_fetch.return_value = {'symbol': 'AAPL'}

        processor = BatchRefreshProcessor(test_config_path)
        processor.config['processing']['batch_size'] = 10

        processor.run()

        # Should have processed all 25 stocks in 3 batches
        assert processor.stats.total_stocks == 25
        assert processor.stats.successful == 25

    @patch('batch_refresh.get_nyse_nasdaq_symbols')
    @patch('batch_refresh.fetch_stock_data')
    @patch('batch_refresh.time.sleep')
    def test_run_error_recovery(self, mock_sleep, mock_fetch, mock_get_symbols, test_config_path):
        """Test that errors don't stop the entire process"""
        mock_get_symbols.return_value = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']

        # Simulate errors
        mock_fetch.side_effect = [
            ValueError('Error 1'),
            {'symbol': 'MSFT'},
            ValueError('Error 2'),
            {'symbol': 'AMZN'},
            {'symbol': 'TSLA'}
        ]

        processor = BatchRefreshProcessor(test_config_path)
        processor.run()

        # Should have continued despite errors
        assert processor.stats.total_stocks == 5
        assert processor.stats.successful == 3
        assert processor.stats.failed == 2


# ============================================================================
# Command Line Tests
# ============================================================================

class TestCommandLine:
    """Test command-line argument parsing"""

    @patch('batch_refresh.BatchRefreshProcessor')
    def test_main_default_args(self, mock_processor_class):
        """Test main with default arguments"""
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor

        # Would need to test the main() function
        # This is a placeholder for now
        pass


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
