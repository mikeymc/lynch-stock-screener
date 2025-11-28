#!/usr/bin/env python3
"""
Test script to verify international stock support
Fetches a small sample of stocks from US, Europe, and Asia
"""

import sys
sys.path.insert(0, '/Users/mikey/workspace/lynch-stock-screener/backend')

from tradingview_fetcher import TradingViewFetcher
import json

def test_international_stocks():
    print("=" * 80)
    print("Testing International Stock Support")
    print("=" * 80)
    
    fetcher = TradingViewFetcher()
    
    # Test with a small limit to keep it fast
    print("\n1. Testing US stocks (limit: 5)...")
    us_stocks = fetcher.fetch_all_stocks(limit=5, regions=['us'])
    print(f"   Fetched {len(us_stocks)} US stocks")
    if us_stocks:
        sample = list(us_stocks.items())[0]
        print(f"   Sample: {sample[0]} - {sample[1].get('company_name')} ({sample[1].get('exchange')})")
    
    print("\n2. Testing European stocks (limit: 5)...")
    eu_stocks = fetcher.fetch_all_stocks(limit=5, regions=['europe'])
    print(f"   Fetched {len(eu_stocks)} European stocks")
    if eu_stocks:
        for symbol, data in list(eu_stocks.items())[:3]:
            print(f"   - {symbol}: {data.get('company_name')} ({data.get('exchange')}, Country: {data.get('country')})")
    
    print("\n3. Testing Asian stocks (limit: 5)...")
    asia_stocks = fetcher.fetch_all_stocks(limit=5, regions=['asia'])
    print(f"   Fetched {len(asia_stocks)} Asian stocks")
    if asia_stocks:
        for symbol, data in list(asia_stocks.items())[:3]:
            print(f"   - {symbol}: {data.get('company_name')} ({data.get('exchange')}, Country: {data.get('country')})")
    
    print("\n4. Testing all regions combined (limit: 3 each)...")
    all_stocks = fetcher.fetch_all_stocks(limit=3, regions=['us', 'europe', 'asia'])
    print(f"   Total unique stocks: {len(all_stocks)}")
    
    # Group by exchange to see distribution
    by_exchange = {}
    for symbol, data in all_stocks.items():
        exchange = data.get('exchange', 'UNKNOWN')
        if exchange not in by_exchange:
            by_exchange[exchange] = []
        by_exchange[exchange].append(symbol)
    
    print("\n   Distribution by exchange:")
    for exchange, symbols in sorted(by_exchange.items()):
        print(f"   - {exchange}: {len(symbols)} stocks")
    
    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)

if __name__ == '__main__':
    test_international_stocks()
