# ABOUTME: Backfills missing debt-to-equity data from yfinance balance sheets
# ABOUTME: Targets only stocks with NULL debt_to_equity values in earnings_history

from database import Database
from data_fetcher import DataFetcher
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

def backfill_all_debt_to_equity():
    """Backfill missing debt-to-equity data for all stocks"""
    db = Database('stocks.db')
    fetcher = DataFetcher(db)

    # Get all symbols with NULL debt_to_equity in annual earnings
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT symbol, GROUP_CONCAT(year) as years
        FROM earnings_history
        WHERE debt_to_equity IS NULL AND period = 'annual'
        GROUP BY symbol
        ORDER BY symbol
    """)
    results = cursor.fetchall()
    conn.close()

    total_stocks = len(results)
    logger.info(f"Found {total_stocks} stocks needing D/E data")

    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, (symbol, years_str) in enumerate(results, 1):
        years = [int(y) for y in years_str.split(',')]
        logger.info(f"[{i}/{total_stocks}] Processing {symbol} ({len(years)} years needing D/E)...")

        try:
            # Get the count before backfill
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM earnings_history
                WHERE symbol = ? AND period = 'annual' AND debt_to_equity IS NOT NULL
            """, (symbol,))
            before_count = cursor.fetchone()[0]
            conn.close()

            # Attempt backfill
            fetcher._backfill_debt_to_equity(symbol, years)

            # Get the count after backfill
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM earnings_history
                WHERE symbol = ? AND period = 'annual' AND debt_to_equity IS NOT NULL
            """, (symbol,))
            after_count = cursor.fetchone()[0]
            conn.close()

            filled = after_count - before_count
            if filled > 0:
                logger.info(f"  ✓ Filled {filled} year(s) for {symbol}")
                success_count += 1
            else:
                logger.warning(f"  ✗ No data available from yfinance for {symbol}")
                skip_count += 1

        except Exception as e:
            logger.error(f"  ✗ Error processing {symbol}: {type(e).__name__}: {e}")
            fail_count += 1

        # Rate limiting to be nice to yfinance
        if i % 50 == 0:
            logger.info(f"Progress: {i}/{total_stocks} processed. Pausing for 5 seconds...")
            time.sleep(5)
        else:
            time.sleep(0.1)

    logger.info("="*60)
    logger.info(f"Backfill complete!")
    logger.info(f"  Success: {success_count} stocks")
    logger.info(f"  No data: {skip_count} stocks")
    logger.info(f"  Errors: {fail_count} stocks")
    logger.info(f"  Total: {total_stocks} stocks")

    # Final stats
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(DISTINCT symbol) as total_stocks,
            SUM(CASE WHEN debt_to_equity IS NULL THEN 1 ELSE 0 END) as null_records,
            SUM(CASE WHEN debt_to_equity IS NOT NULL THEN 1 ELSE 0 END) as filled_records
        FROM earnings_history
        WHERE period = 'annual'
    """)
    total_stocks, null_records, filled_records = cursor.fetchone()
    conn.close()

    logger.info("="*60)
    logger.info("Database Stats:")
    logger.info(f"  Total annual records: {null_records + filled_records}")
    logger.info(f"  Records with D/E: {filled_records} ({filled_records*100/(null_records+filled_records):.1f}%)")
    logger.info(f"  Records without D/E: {null_records} ({null_records*100/(null_records+filled_records):.1f}%)")

if __name__ == '__main__':
    backfill_all_debt_to_equity()
