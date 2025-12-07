#!/usr/bin/env python3
"""
Test script to check if numeric-prefixed tickers come from international markets
"""

import sys
sys.path.insert(0, '/Users/mikey/workspace/lynch-stock-screener/backend')

from tradingview_fetcher import TradingViewFetcher
import json

def test_international_ticker_patterns():
    print("=" * 80)
    print("Testing International Ticker Patterns")
    print("=" * 80)
    
    fetcher = TradingViewFetcher()
    
    # Test each region separately
    for region in ['us', 'europe', 'asia']:
        print(f"\n{'=' * 80}")
        print(f"Region: {region.upper()}")
        print('=' * 80)
        
        stocks = fetcher.fetch_all_stocks(limit=200, regions=[region])
        
        # Look for Apple, Fox, Nike variants
        target_companies = ['Apple', 'Fox', 'Nike']
        
        for company in target_companies:
            matches = []
            for symbol, data in stocks.items():
                company_name = data.get('company_name', '')
                if company_name and company.lower() in company_name.lower():
                    matches.append({
                        'symbol': symbol,
                        'company': company_name,
                        'exchange': data.get('exchange'),
                        'country': data.get('country')
                    })
            
            if matches:
                print(f"\n{company} matches:")
                for m in sorted(matches, key=lambda x: x['symbol']):
                    print(f"  {m['symbol']:15} | {m['company'][:40]:40} | {m['exchange']:10} | {m.get('country', 'N/A')}")
        
        # Count tickers with numeric prefixes
        numeric_tickers = [s for s in stocks.keys() if s and s[0].isdigit()]
        print(f"\nTickers with numeric prefixes: {len(numeric_tickers)}")
        if numeric_tickers:
            print("Sample:")
            for ticker in sorted(numeric_tickers)[:10]:
                data = stocks[ticker]
                print(f"  {ticker:15} | {data.get('company_name', '')[:40]:40} | {data.get('exchange', '')}")

if __name__ == '__main__':
    test_international_ticker_patterns()
