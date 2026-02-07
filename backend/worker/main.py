# ABOUTME: Entry point for the background worker process
# ABOUTME: Configures SEC rate limiting and starts the worker run loop

import logging
import os

# Import global rate limiter for SEC API (shared across all threads)
from sec_rate_limiter import SEC_RATE_LIMITER

logger = logging.getLogger(__name__)


def main():
    """Entry point for worker process"""
    tier = os.environ.get('WORKER_TIER', 'light')
    logger.info("=" * 60)
    logger.info(f"Lynch Stock Screener - Background Worker ({tier.upper()} TIER)")
    logger.info("=" * 60)

    # Configure global SEC rate limiter done at top level
    logger.info(f"SEC Rate Limiter: {SEC_RATE_LIMITER.get_stats()}")

    from worker import BackgroundWorker
    worker = BackgroundWorker()
    worker.run()


if __name__ == '__main__':
    main()
