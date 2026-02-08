# ABOUTME: Portfolio snapshot job mixin for the background worker
# ABOUTME: Handles portfolio value snapshots and benchmark recording

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PortfolioJobsMixin:
    """Mixin for portfolio-related jobs: snapshots and benchmarks"""

    def _snapshot_portfolio_values(self) -> int:
        """
        Snapshot current value of all portfolios.

        Called after price updates to record portfolio values for historical charts.
        Uses cached prices from stock_metrics (just updated) to value holdings.

        Returns:
            Number of portfolios snapshotted
        """
        portfolios = self.db.get_all_portfolios()
        if not portfolios:
            return 0

        snapshot_count = 0
        for portfolio in portfolios:
            try:
                portfolio_id = portfolio['id']
                # Use cached prices (use_live_prices=False) since we just updated them
                summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
                if summary:
                    self.db.save_portfolio_snapshot(
                        portfolio_id=portfolio_id,
                        total_value=summary['total_value'],
                        cash_value=summary['cash'],
                        holdings_value=summary['holdings_value']
                    )
                    snapshot_count += 1
            except Exception as e:
                logger.warning(f"Failed to snapshot portfolio {portfolio.get('id')}: {e}")
                continue

        self.db.flush()
        logger.info(f"Created {snapshot_count} portfolio value snapshots")
        return snapshot_count

    def _run_benchmark_snapshot(self, job_id: int, params: Dict[str, Any]):
        """Record daily benchmark (SPY) price."""
        logger.info(f"Running benchmark_snapshot job {job_id}")

        from strategy_executor import BenchmarkTracker
        tracker = BenchmarkTracker(self.db)

        try:
            result = tracker.record_daily_benchmark()
            self.db.complete_job(job_id, result=result)
            logger.info(f"Benchmark snapshot completed: {result}")
        except Exception as e:
            logger.error(f"Benchmark snapshot failed: {e}")
            self.db.fail_job(job_id, str(e))
    def _run_portfolio_sweep(self, job_id: int, params: Dict[str, Any]):
        """
        Daily portfolio maintenance job (Market Close/After Hours).
        
        Tasks:
        1. Record daily SPY benchmark price
        2. Process dividends for all portfolios
        3. Snapshot portfolio values
        """
        logger.info(f"Running portfolio_sweep job {job_id}")
        
        results = {
            'benchmark': None,
            'dividends': None,
            'snapshots': 0,
            'errors': []
        }

        # 1. Benchmark Recording
        try:
            from strategy_executor import BenchmarkTracker
            self.db.update_job_progress(job_id, progress_pct=10, progress_message='Recording benchmark...')
            tracker = BenchmarkTracker(self.db)
            results['benchmark'] = tracker.record_daily_benchmark()
            logger.info(f"Benchmark recorded: {results['benchmark']}")
        except Exception as e:
            msg = f"Benchmark recording failed: {e}"
            logger.error(msg)
            results['errors'].append(msg)

        # 2. Dividend Processing
        try:
            self.db.update_job_progress(job_id, progress_pct=40, progress_message='Processing dividends...')
            # Using the process_all_portfolios wrapper (or direct manager call)
            # We use the manager directly here since it's a dedicated sweep
            self.dividend_manager.process_all_portfolios()
            results['dividends'] = 'completed'
            logger.info("Dividend processing completed")
        except Exception as e:
            msg = f"Dividend processing failed: {e}"
            logger.error(msg)
            results['errors'].append(msg)

        # 3. Portfolio Snapshots
        try:
            self.db.update_job_progress(job_id, progress_pct=80, progress_message='Snapshotting portfolios...')
            results['snapshots'] = self._snapshot_portfolio_values()
            logger.info(f"Snapshotted {results['snapshots']} portfolios")
        except Exception as e:
            msg = f"Portfolio snapshot failed: {e}"
            logger.error(msg)
            results['errors'].append(msg)

        # Complete
        if results['errors']:
            self.db.complete_job(job_id, result=results) # Complete with partial errors
        else:
            self.db.complete_job(job_id, result=results)
