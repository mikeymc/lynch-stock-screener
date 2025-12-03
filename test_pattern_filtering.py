#!/usr/bin/env python3
"""
Test script to verify pattern-based ticker filtering
"""

import sys
sys.path.insert(0, '/Users/mikey/workspace/lynch-stock-screener/backend')

from tradingview_fetcher import TradingViewFetcher

def test_pattern_filtering():
    print("=" * 80)
    print("Testing Pattern-Based Ticker Filtering")
    print("=" * 80)
    
    fetcher = TradingViewFetcher()
    
    # Test cases for different ticker patterns
    test_cases = [
        # (ticker, exchange, should_be_filtered, reason)
        ('AAPL', 'NASDAQ', False, 'Common stock'),
        ('AAPL-P', 'NASDAQ', True, 'Preferred stock (-P)'),
        ('AAPL-PR', 'NASDAQ', True, 'Preferred stock (-PR)'),
        ('AAPL.PR', 'NASDAQ', True, 'Preferred stock (.PR)'),
        ('AAPL-W', 'NASDAQ', True, 'Warrant (-W)'),
        ('AAPL-WT', 'NASDAQ', True, 'Warrant (-WT)'),
        ('AAPL.W', 'NASDAQ', True, 'Warrant (.W)'),
        ('AAPL-WS', 'NASDAQ', True, 'Warrant (-WS)'),
        ('AAPL-U', 'NASDAQ', True, 'Unit (-U)'),
        ('AAPL.U', 'NASDAQ', True, 'Unit (.U)'),
        ('AAPL-WI', 'NASDAQ', True, 'When-issued (-WI)'),
        ('AAPL.WI', 'NASDAQ', True, 'When-issued (.WI)'),
        ('Z1', 'NASDAQ', True, 'Test ticker (Z + number)'),
        ('ZZ', 'NASDAQ', True, 'Test ticker (short Z ticker)'),
        ('ZOOM', 'NASDAQ', False, 'Legitimate ticker starting with Z'),
        ('000660', 'KRX', False, 'Korean stock (numeric)'),
        ('2330', 'TWSE', False, 'Taiwanese stock (numeric)'),
        ('1AAPL', 'MIL', True, 'European ADR'),
        ('AAPL', 'LSE', True, 'European ADR exchange'),
    ]
    
    print("\nTesting individual ticker patterns:\n")
    
    passed = 0
    failed = 0
    
    for ticker, exchange, should_filter, reason in test_cases:
        result = fetcher._should_skip_ticker(ticker, exchange)
        expected = should_filter
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        action = "FILTERED" if result else "ALLOWED"
        expected_action = "FILTERED" if expected else "ALLOWED"
        
        print(f"{status} | {ticker:15} ({exchange:10}) | {action:8} | Expected: {expected_action:8} | {reason}")
    
    print("\n" + "=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)
    
    # Now test with real data
    print("\n" + "=" * 80)
    print("Testing with real TradingView data (US market, limit 500)")
    print("=" * 80)
    
    us_stocks = fetcher.fetch_all_stocks(limit=500, regions=['us'])
    
    # Count filtered patterns
    all_tickers = list(us_stocks.keys())
    
    # Check for any that slipped through
    problematic = []
    for ticker in all_tickers:
        ticker_upper = ticker.upper()
        if any(ticker_upper.endswith(suffix) for suffix in ['-P', '-PR', '.PR', '-W', '-WT', '.W', '-U', '.U', '-WI', '.WI']):
            problematic.append(ticker)
    
    print(f"\nTotal tickers fetched: {len(all_tickers)}")
    print(f"Problematic patterns found: {len(problematic)}")
    
    if problematic:
        print("\n❌ FAIL: Found tickers that should have been filtered:")
        for ticker in problematic[:10]:
            print(f"  - {ticker}")
    else:
        print("\n✅ PASS: No problematic ticker patterns found!")
    
    # Show some sample tickers
    print("\nSample tickers (should all be common stock):")
    for ticker in sorted(all_tickers)[:20]:
        print(f"  {ticker}")
    
    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)

if __name__ == '__main__':
    test_pattern_filtering()
