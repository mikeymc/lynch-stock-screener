#!/usr/bin/env python3
# ABOUTME: Standalone script to re-score stocks from latest screening session with current algorithm settings
# ABOUTME: Run this manually after updating algorithm settings to refresh all scores

import sys
import logging
from database import Database
from earnings_analyzer import EarningsAnalyzer
from lynch_criteria import LynchCriteria
from stock_rescorer import StockRescorer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    algorithm = sys.argv[1] if len(sys.argv) > 1 else 'weighted'

    logger.info(f"Re-scoring stocks from latest screening session using algorithm: {algorithm}")

    try:
        # Initialize components
        db = Database()
        analyzer = EarningsAnalyzer(db)
        criteria = LynchCriteria(db, analyzer)
        rescorer = StockRescorer(db, criteria)

        # Perform re-scoring
        summary = rescorer.rescore_saved_stocks(algorithm=algorithm)

        # Print summary
        print("\n" + "="*60)
        print("RE-SCORING SUMMARY")
        print("="*60)
        print(f"Total stocks: {summary['total']}")
        print(f"Successfully re-scored: {summary['success']}")
        print(f"Failed: {summary['failed']}")

        if summary['errors']:
            print("\nErrors:")
            for error in summary['errors'][:10]:  # Show first 10 errors
                print(f"  - {error}")

        print("="*60)

        # Exit with appropriate code
        sys.exit(0 if summary['failed'] == 0 else 1)

    except Exception as e:
        logger.error(f"Re-scoring failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
