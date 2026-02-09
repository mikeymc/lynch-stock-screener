# ABOUTME: Track strategy performance vs S&P 500 (SPY) benchmark
# ABOUTME: Provides performance comparison, alpha calculation, and historical series

import logging
from datetime import date, timedelta
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class BenchmarkTracker:
    """Tracks strategy performance vs S&P 500."""

    def __init__(self, db):
        self.db = db

    def record_daily_benchmark(self) -> Dict[str, Any]:
        """Record daily SPY price. Call once per day after market close."""
        try:
            import yfinance as yf
            spy = yf.Ticker("SPY")
            price = spy.fast_info.get('lastPrice')

            if not price:
                raise ValueError("Could not fetch SPY price")

            today = date.today()
            self.db.save_benchmark_snapshot(today, price)

            return {'date': today, 'spy_price': price}
        except Exception as e:
            logger.error(f"Failed to record benchmark: {e}")
            raise

    def record_strategy_performance(
        self,
        strategy_id: int,
        portfolio_value: float
    ) -> Dict[str, Any]:
        """Record strategy performance and calculate alpha."""
        today = date.today()

        # Get inception data
        inception = self.db.get_strategy_inception_data(strategy_id)

        if inception:
            inception_value = inception['portfolio_value']
            inception_spy = inception['spy_price']
        else:
            # First run - current values as inception
            inception_value = portfolio_value
            benchmark = self.db.get_benchmark_snapshot(today)
            inception_spy = benchmark['spy_price'] if benchmark else None

        # Get current SPY
        benchmark = self.db.get_benchmark_snapshot(today)
        current_spy = benchmark['spy_price'] if benchmark else None

        # Calculate returns
        if inception_value and inception_value > 0:
            portfolio_return_pct = ((portfolio_value - inception_value) / inception_value) * 100
        else:
            portfolio_return_pct = 0

        if inception_spy and inception_spy > 0 and current_spy:
            spy_return_pct = ((current_spy - inception_spy) / inception_spy) * 100
        else:
            spy_return_pct = 0

        alpha = portfolio_return_pct - spy_return_pct

        # Save performance
        self.db.save_strategy_performance(
            strategy_id, today, portfolio_value,
            portfolio_return_pct, spy_return_pct, alpha
        )

        return {
            'date': today,
            'portfolio_value': portfolio_value,
            'portfolio_return_pct': portfolio_return_pct,
            'spy_return_pct': spy_return_pct,
            'alpha': alpha
        }

    def get_performance_series(
        self,
        strategy_id: int,
        days: int = 365
    ) -> List[Dict[str, Any]]:
        """Get time series of performance for charting."""
        start_date = date.today() - timedelta(days=days)
        return self.db.get_strategy_performance(strategy_id, start_date)
