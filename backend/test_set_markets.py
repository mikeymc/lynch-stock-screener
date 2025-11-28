#!/usr/bin/env python3
"""
Test script to verify set_markets usage
"""

import sys
sys.path.insert(0, '/Users/mikey/workspace/lynch-stock-screener/backend')

from tradingview_screener import Query, Column

def test_set_markets():
    print("Testing set_markets...")
    
    # List of markets to test
    markets = ['america', 'uk', 'germany', 'france', 'hongkong', 'china', 'india']
    
    for market in markets:
        try:
            print(f"\nTesting market: {market}")
            q = (Query()
                 .set_markets(market)
                 .select('name', 'description', 'exchange', 'close', 'currency')
                 .where(Column('market_cap_basic') > 1_000_000)
                 .limit(3))
            
            count, df = q.get_scanner_data()
            
            if len(df) > 0:
                print(f"✓ {market}: Found {len(df)} stocks")
                for _, row in df.iterrows():
                    print(f"  - {row['name']}: {row.get('description', 'N/A')} ({row.get('exchange', 'N/A')}) {row.get('close')} {row.get('currency')}")
            else:
                print(f"✗ {market} - No results")
                
        except Exception as e:
            print(f"✗ {market} - Error: {e}")

if __name__ == '__main__':
    test_set_markets()
