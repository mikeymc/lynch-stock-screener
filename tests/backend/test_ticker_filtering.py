#!/usr/bin/env python3
"""
Test script to verify ticker filtering logic
"""

import sys
sys.path.insert(0, '/Users/mikey/workspace/lynch-stock-screener/backend')

from tradingview_fetcher import TradingViewFetcher

def test_ticker_filtering():
    print("=" * 80)
    print("Testing Ticker Filtering Logic")
    print("=" * 80)
    
    fetcher = TradingViewFetcher()
    
    # Test each region to verify filtering
    print("\n" + "=" * 80)
    print("Testing US Region (should have NO filtering)")
    print("=" * 80)
    us_stocks = fetcher.fetch_all_stocks(limit=100, regions=['us'])
    
    # Check for Apple variants
    apple_tickers = [s for s in us_stocks.keys() if 'AAPL' in s.upper()]
    print(f"\nApple-related tickers found: {apple_tickers}")
    print(f"Expected: ['AAPL'] (and possibly ZAAP)")
    
    # Test European region
    print("\n" + "=" * 80)
    print("Testing European Region (should filter ADRs)")
    print("=" * 80)
    eu_stocks = fetcher.fetch_all_stocks(limit=200, regions=['europe'])
    
    # Check for problematic tickers
    problematic_tickers = ['1AAPL', '4AAPL', '0QZ6', '865985']
    found_problematic = [t for t in problematic_tickers if t in eu_stocks]
    
    print(f"\nProblematic tickers that should be filtered:")
    print(f"  Looking for: {problematic_tickers}")
    print(f"  Found: {found_problematic}")
    
    if found_problematic:
        print(f"  ❌ FAIL: These tickers should have been filtered!")
        for ticker in found_problematic:
            data = eu_stocks[ticker]
            print(f"     {ticker}: {data.get('company_name')} ({data.get('exchange')})")
    else:
        print(f"  ✅ PASS: All problematic tickers were filtered!")
    
    # Check for legitimate European companies
    print(f"\nTotal European stocks after filtering: {len(eu_stocks)}")
    print("Sample legitimate European companies:")
    sample_count = 0
    for ticker, data in list(eu_stocks.items())[:10]:
        exchange = data.get('exchange', 'N/A')
        if exchange not in fetcher.EUROPEAN_ADR_EXCHANGES:
            print(f"  {ticker:10} | {data.get('company_name', '')[:40]:40} | {exchange}")
            sample_count += 1
            if sample_count >= 5:
                break
    
    # Test Asian region
    print("\n" + "=" * 80)
    print("Testing Asian Region (should ALLOW numeric tickers)")
    print("=" * 80)
    asia_stocks = fetcher.fetch_all_stocks(limit=200, regions=['asia'])
    
    # Count numeric tickers
    numeric_tickers = [s for s in asia_stocks.keys() if s and s[0].isdigit()]
    print(f"\nNumeric tickers found: {len(numeric_tickers)}")
    print(f"Expected: Many (Korean/Taiwanese stocks use numeric tickers)")
    
    if len(numeric_tickers) > 0:
        print(f"✅ PASS: Numeric Asian tickers are preserved!")
        print("\nSample numeric Asian tickers:")
        for ticker in sorted(numeric_tickers)[:5]:
            data = asia_stocks[ticker]
            print(f"  {ticker:10} | {data.get('company_name', '')[:40]:40} | {data.get('exchange', '')}")
    else:
        print(f"❌ FAIL: No numeric tickers found - filtering may be too aggressive!")
    
    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"US stocks: {len(us_stocks)}")
    print(f"European stocks (after filtering): {len(eu_stocks)}")
    print(f"Asian stocks: {len(asia_stocks)}")
    print(f"Asian numeric tickers: {len(numeric_tickers)}")
    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)

if __name__ == '__main__':
    test_ticker_filtering()
