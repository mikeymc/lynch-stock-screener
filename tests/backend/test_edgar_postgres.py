#!/usr/bin/env python3
"""Test EdgarFetcher with PostgreSQL backend"""

from database import Database
from data_fetcher import DataFetcher
import logging

logging.basicConfig(level=logging.INFO)

def test_edgar_with_postgres():
    print("Testing EdgarFetcher with PostgreSQL...")

    # Initialize database
    db = Database()
    print("✓ Database initialized")

    # Initialize DataFetcher (which creates EdgarFetcher with db connection)
    fetcher = DataFetcher(db)
    print("✓ DataFetcher initialized")

    # Test fetching Apple data
    print("\nFetching Apple (AAPL) fundamentals...")
    fundamentals = fetcher.edgar_fetcher.fetch_stock_fundamentals("AAPL")

    if fundamentals:
        print(f"✓ Successfully fetched AAPL data")
        print(f"  Company: {fundamentals.get('company_name')}")
        print(f"  CIK: {fundamentals.get('cik')}")
        print(f"  EPS history entries: {len(fundamentals.get('eps_history', []))}")
        print(f"  Revenue history entries: {len(fundamentals.get('revenue_history', []))}")
        print(f"  Cash flow history entries: {len(fundamentals.get('cash_flow_history', []))}")

        # Show most recent EPS
        if fundamentals.get('calculated_eps_history'):
            latest = fundamentals['calculated_eps_history'][0]
            print(f"  Latest EPS: ${latest['eps']:.2f} (FY{latest['year']})")
    else:
        print("✗ Failed to fetch AAPL data")
        assert False, "Failed to fetch AAPL data"

    print("\n" + "="*60)
    print("SUCCESS! EdgarFetcher is working with PostgreSQL")
    print("="*60)

if __name__ == '__main__':
    try:
        test_edgar_with_postgres()
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
