#!/usr/bin/env python3
"""
Nightly Batch Process for Stock Data Refresh

This script refreshes stock data for all NYSE and NASDAQ stocks in the database.
It's designed to run as a scheduled job (cron or systemd timer) during off-hours.

Usage:
    python batch_refresh.py [--config CONFIG_FILE] [--dry-run] [--limit N]

Options:
    --config: Path to configuration file (default: batch_config.json)
    --dry-run: Show what would be processed without actually fetching data
    --limit: Limit to first N stocks (for testing)
    --verbose: Enable verbose console output
"""

import argparse
import json
import logging
import os
import sys
import time
import shutil
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Tuple

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import get_nyse_nasdaq_symbols, fetch_stock_data
from database import Database


class BatchRefreshStats:
    """Track statistics for the batch refresh process"""

    def __init__(self):
        self.total_stocks = 0
        self.successful = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = None
        self.end_time = None
        self.failed_symbols = []
        self.error_counts = {}

    def record_success(self, symbol: str):
        self.successful += 1

    def record_failure(self, symbol: str, error: str):
        self.failed += 1
        self.failed_symbols.append(symbol)
        error_type = type(error).__name__ if isinstance(error, Exception) else str(error)
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

    def record_skip(self, symbol: str):
        self.skipped += 1

    def get_duration(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    def get_summary(self) -> Dict:
        return {
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.get_duration(),
            'total_stocks': self.total_stocks,
            'successful': self.successful,
            'failed': self.failed,
            'skipped': self.skipped,
            'success_rate': f"{(self.successful / self.total_stocks * 100) if self.total_stocks > 0 else 0:.2f}%",
            'failed_symbols': self.failed_symbols[:50],  # Limit to first 50
            'error_types': self.error_counts
        }


class BatchRefreshProcessor:
    """Main batch refresh processor"""

    def __init__(self, config_path: str = 'batch_config.json'):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        self.db = Database(self.config['database']['path'])
        self.stats = BatchRefreshStats()

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, 'r') as f:
            return json.load(f)

    def _setup_logging(self) -> logging.Logger:
        """Set up logging with rotation"""
        log_config = self.config['logging']

        # Create logs directory if it doesn't exist
        log_dir = Path(log_config['log_directory'])
        log_dir.mkdir(exist_ok=True)

        # Create logger
        logger = logging.getLogger('batch_refresh')
        logger.setLevel(getattr(logging, log_config['log_level']))

        # File handler with rotation
        log_file = log_dir / log_config['log_file']
        max_bytes = log_config['max_log_size_mb'] * 1024 * 1024
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=log_config['backup_count']
        )
        file_handler.setLevel(logging.DEBUG)

        # Console handler (optional)
        if log_config.get('console_output', False):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger

    def _backup_database(self):
        """Create a backup of the database before processing"""
        if not self.config['database'].get('backup_before_run', False):
            return

        backup_dir = Path(self.config['database']['backup_directory'])
        backup_dir.mkdir(exist_ok=True)

        db_path = Path(self.config['database']['path'])
        if not db_path.exists():
            self.logger.info("Database doesn't exist yet, skipping backup")
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f"stocks_backup_{timestamp}.db"

        try:
            shutil.copy2(db_path, backup_path)
            self.logger.info(f"Database backed up to: {backup_path}")
        except Exception as e:
            self.logger.error(f"Failed to backup database: {e}")

    def _get_stock_symbols(self, limit: int = None) -> List[str]:
        """Get list of stock symbols to process"""
        try:
            symbols = get_nyse_nasdaq_symbols()
            self.logger.info(f"Fetched {len(symbols)} stock symbols from NYSE/NASDAQ")

            if limit:
                symbols = symbols[:limit]
                self.logger.info(f"Limited to first {limit} symbols for testing")

            return symbols
        except Exception as e:
            self.logger.error(f"Failed to fetch stock symbols: {e}")
            raise

    def _process_stock(self, symbol: str, force_refresh: bool = True) -> Tuple[bool, str]:
        """
        Process a single stock

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        try:
            # Fetch stock data (using existing function)
            data = fetch_stock_data(symbol, self.db, force_refresh=force_refresh)

            if data:
                return True, ""
            else:
                return False, "No data returned"

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            return False, error_msg

    def _process_batch(self, symbols: List[str], batch_num: int, total_batches: int):
        """Process a batch of stocks"""
        force_refresh = self.config['processing'].get('force_refresh', True)

        self.logger.info(f"Processing batch {batch_num}/{total_batches} ({len(symbols)} stocks)")

        for i, symbol in enumerate(symbols, 1):
            try:
                success, error = self._process_stock(symbol, force_refresh)

                if success:
                    self.stats.record_success(symbol)
                    self.logger.debug(f"[{i}/{len(symbols)}] ✓ {symbol}")
                else:
                    self.stats.record_failure(symbol, error)
                    self.logger.warning(f"[{i}/{len(symbols)}] ✗ {symbol}: {error}")

                # Add small delay to respect rate limits
                time.sleep(self.config['rate_limiting'].get('yfinance_delay_seconds', 0.5))

            except Exception as e:
                self.stats.record_failure(symbol, str(e))
                self.logger.error(f"[{i}/{len(symbols)}] ✗ {symbol}: {e}", exc_info=True)

                # Check if we've hit max consecutive failures
                if self._check_max_failures():
                    raise RuntimeError("Max consecutive failures exceeded, aborting batch process")

    def _check_max_failures(self) -> bool:
        """Check if we've exceeded max consecutive failures"""
        max_failures = self.config['error_handling'].get('max_consecutive_failures', 50)

        # Check last N results for consecutive failures
        if self.stats.failed >= max_failures:
            recent_success_rate = self.stats.successful / (self.stats.successful + self.stats.failed)
            if recent_success_rate < 0.1:  # Less than 10% success rate
                return True

        return False

    def _save_report(self):
        """Save summary report to file"""
        if not self.config['reporting'].get('generate_summary', True):
            return

        report_dir = Path(self.config['reporting']['summary_directory'])
        report_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = report_dir / f"batch_summary_{timestamp}.json"

        try:
            with open(report_path, 'w') as f:
                json.dump(self.stats.get_summary(), f, indent=2)

            self.logger.info(f"Summary report saved to: {report_path}")

            # Clean up old reports
            self._cleanup_old_reports(report_dir)

        except Exception as e:
            self.logger.error(f"Failed to save report: {e}")

    def _cleanup_old_reports(self, report_dir: Path):
        """Keep only the last N reports"""
        keep_count = self.config['reporting'].get('keep_last_n_reports', 30)

        reports = sorted(report_dir.glob('batch_summary_*.json'))

        if len(reports) > keep_count:
            for old_report in reports[:-keep_count]:
                try:
                    old_report.unlink()
                    self.logger.debug(f"Deleted old report: {old_report}")
                except Exception as e:
                    self.logger.error(f"Failed to delete old report {old_report}: {e}")

    def run(self, dry_run: bool = False, limit: int = None):
        """Run the batch refresh process"""

        if not self.config.get('enabled', True):
            self.logger.info("Batch process is disabled in configuration")
            return

        self.logger.info("=" * 80)
        self.logger.info("Starting nightly batch stock data refresh")
        self.logger.info("=" * 80)

        self.stats.start_time = datetime.now()

        try:
            # Backup database
            self._backup_database()

            # Get stock symbols
            symbols = self._get_stock_symbols(limit)
            self.stats.total_stocks = len(symbols)

            if dry_run:
                self.logger.info(f"DRY RUN: Would process {len(symbols)} stocks")
                for i, symbol in enumerate(symbols[:10], 1):
                    self.logger.info(f"  {i}. {symbol}")
                if len(symbols) > 10:
                    self.logger.info(f"  ... and {len(symbols) - 10} more")
                return

            # Process in batches
            batch_size = self.config['processing'].get('batch_size', 100)
            total_batches = (len(symbols) + batch_size - 1) // batch_size

            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(symbols))
                batch_symbols = symbols[start_idx:end_idx]

                self._process_batch(batch_symbols, batch_num + 1, total_batches)

                # Delay between batches
                if batch_num < total_batches - 1:
                    delay = self.config['processing'].get('delay_between_batches_seconds', 5)
                    self.logger.info(f"Waiting {delay} seconds before next batch...")
                    time.sleep(delay)

            self.stats.end_time = datetime.now()

            # Log summary
            summary = self.stats.get_summary()
            self.logger.info("=" * 80)
            self.logger.info("Batch refresh completed")
            self.logger.info(f"Duration: {summary['duration_seconds']:.2f} seconds")
            self.logger.info(f"Total stocks: {summary['total_stocks']}")
            self.logger.info(f"Successful: {summary['successful']}")
            self.logger.info(f"Failed: {summary['failed']}")
            self.logger.info(f"Success rate: {summary['success_rate']}")
            self.logger.info("=" * 80)

            # Save report
            self._save_report()

        except Exception as e:
            self.stats.end_time = datetime.now()
            self.logger.error(f"Batch process failed: {e}", exc_info=True)
            self._save_report()
            raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Nightly batch process for stock data refresh'
    )
    parser.add_argument(
        '--config',
        default='batch_config.json',
        help='Path to configuration file (default: batch_config.json)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be processed without actually fetching data'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit to first N stocks (for testing)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose console output'
    )

    args = parser.parse_args()

    try:
        # Create processor
        processor = BatchRefreshProcessor(args.config)

        # Enable console output if verbose
        if args.verbose:
            processor.config['logging']['console_output'] = True
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            processor.logger.addHandler(console_handler)

        # Run batch process
        processor.run(dry_run=args.dry_run, limit=args.limit)

        sys.exit(0)

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
