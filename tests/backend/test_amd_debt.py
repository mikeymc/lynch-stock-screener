# ABOUTME: Test script to verify debt-to-equity fetching for AMD
# ABOUTME: Ensures yfinance fallback properly fetches and stores D/E data

from data_fetcher import DataFetcher
from database import Database
import logging

logging.basicConfig(level=logging.INFO)

def test_amd(test_db):
    fetcher = DataFetcher(test_db)

    print("Fetching AMD data...")
    result = fetcher.fetch_stock_data("AMD", force_refresh=True)

    if result:
        print(f"✓ Successfully fetched AMD data")
        print(f"  Price: ${result.get('price', 'N/A')}")
        print(f"  P/E Ratio: {result.get('pe_ratio', 'N/A')}")
        print(f"  Debt-to-Equity: {result.get('debt_to_equity', 'N/A')}")
    else:
        print("✗ Failed to fetch AMD data")
        assert False, "Failed to fetch AMD data"

    # Check earnings history for debt-to-equity data
    print("\nChecking earnings history...")
    earnings_history = test_db.get_earnings_history("AMD")

    assert earnings_history, "✗ No earnings history found"

    print(f"Found {len(earnings_history)} periods")

    # Check annual periods
    annual_periods = [e for e in earnings_history if e.get('period') == 'annual']
    annual_with_de = [e for e in annual_periods if e.get('debt_to_equity') is not None]

    print(f"  Annual periods: {len(annual_periods)}")
    print(f"  Annual with D/E: {len(annual_with_de)}")

    # Check quarterly periods
    quarterly_periods = [e for e in earnings_history if e.get('period', '').startswith('Q')]
    quarterly_with_de = [e for e in quarterly_periods if e.get('debt_to_equity') is not None]

    print(f"  Quarterly periods: {len(quarterly_periods)}")
    print(f"  Quarterly with D/E: {len(quarterly_with_de)}")

    # Show sample data
    if annual_with_de:
        print(f"\nSample annual data with D/E:")
        for e in annual_with_de[:3]:
            print(f"  {e['year']}: D/E = {e['debt_to_equity']:.2f}")

    if quarterly_with_de:
        print(f"\nSample quarterly data with D/E:")
        for e in quarterly_with_de[:3]:
            print(f"  {e['period']}'{str(e['year'])[2:]}: D/E = {e['debt_to_equity']:.2f}")

    assert annual_with_de or quarterly_with_de, "\n✗ FAILURE: No debt-to-equity data found"
    print("\n✓ SUCCESS: Debt-to-equity data is present!")

if __name__ == "__main__":
    success = test_amd()
    exit(0 if success else 1)
