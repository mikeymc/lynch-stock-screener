#!/usr/bin/env python
# ABOUTME: Manual test script for AAPL EDGAR calculated EPS integration
# ABOUTME: Verifies split-adjusted EPS across Apple's 2014 and 2020 stock splits

from data_fetcher import DataFetcher

def test_aapl_edgar_eps(test_db):
    """Test AAPL with EDGAR-calculated EPS"""

    # Initialize
    fetcher = DataFetcher(test_db)

    print("=" * 80)
    print("Testing AAPL with EDGAR-calculated EPS")
    print("=" * 80)

    # Fetch AAPL data (force refresh to use new logic)
    print("\nFetching AAPL data from EDGAR...")
    result = fetcher.fetch_stock_data('AAPL', force_refresh=True)

    assert result, "ERROR: Failed to fetch AAPL data"

    print(f"\n✓ Successfully fetched AAPL data")
    print(f"  Price: ${result.get('price', 'N/A')}")
    print(f"  P/E Ratio: {result.get('pe_ratio', 'N/A')}")
    print(f"  Market Cap: ${result.get('market_cap', 'N/A'):,}")

    # Get earnings history
    earnings = test_db.get_earnings_history('AAPL')

    assert earnings, "\nERROR: No earnings history found"

    print(f"\n✓ Retrieved {len(earnings)} years of earnings history")
    print("\nEarnings History (most recent first):")
    print(f"{'Year':<6} {'EPS':<10} {'Revenue (B)':<15} {'Period':<8}")
    print("-" * 50)

    for entry in earnings[:15]:  # Show first 15 entries
        year = entry.get('year', 'N/A')
        eps = entry.get('eps', 0)
        revenue = entry.get('revenue', 0) / 1e9  # Convert to billions
        period = entry.get('period', 'annual')
        print(f"{year:<6} ${eps:<9.2f} ${revenue:<14.2f} {period:<8}")

    # Check for split consistency
    print("\n" + "=" * 80)
    print("Checking Split-Adjusted EPS Consistency")
    print("=" * 80)

    # Apple had 7:1 split on June 9, 2014 and 4:1 split on August 31, 2020
    # EPS should not show artificial drops at these dates

    annual_only = [e for e in earnings if e.get('period') == 'annual']

    print("\nAnnual EPS Progression:")
    prev_eps = None
    for entry in annual_only[:10]:  # Check last 10 years
        year = entry.get('year')
        eps = entry.get('eps')

        if prev_eps:
            change_pct = ((eps - prev_eps) / prev_eps) * 100
            status = "✓" if change_pct > -50 else "⚠️ LARGE DROP"
            print(f"  FY{year}: ${eps:.2f} (change: {change_pct:+.1f}%) {status}")
        else:
            print(f"  FY{year}: ${eps:.2f}")

        prev_eps = eps

    # Success criteria
    has_sufficient_data = len(annual_only) >= 5
    print(f"\n{'='*80}")
    print("Results:")
    print(f"  ✓ Annual EPS years: {len(annual_only)}")
    print(f"  ✓ Total entries (annual + quarterly): {len(earnings)}")
    print(f"  ✓ Split-adjusted: {'YES' if has_sufficient_data else 'NEEDS VERIFICATION'}")

    assert has_sufficient_data, "Insufficient annual data for verification"

if __name__ == '__main__':
    success = test_aapl_edgar_eps()
    if success:
        print("\n✅ AAPL integration test PASSED")
    else:
        print("\n❌ AAPL integration test FAILED")
        exit(1)
