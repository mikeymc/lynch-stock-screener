#!/usr/bin/env python3
"""
Test script to try country-based filtering instead of exchange
"""

import sys
sys.path.insert(0, '/Users/mikey/workspace/lynch-stock-screener/backend')

from tradingview_screener import Query, Column

def test_country_filtering():
    print("Testing country-based filtering...")
    
    # Try filtering by country instead of exchange
    test_countries = ['United Kingdom', 'Germany', 'France', 'China', 'Japan', 'India']
    
    for country in test_countries:
        try:
            q = (Query()
                 .select('name', 'description', 'exchange', 'country')
                 .where(
                     Column('country') == country,
                     Column('market_cap_basic') > 1_000_000
                 )
                 .limit(3))
            
            count, df = q.get_scanner_data()
            
            if len(df) > 0:
                print(f"\n✓ {country}:")
                for _, row in df.iterrows():
                    print(f"  - {row['name']}: {row.get('description', 'N/A')} ({row.get('exchange', 'N/A')})")
            else:
                print(f"✗ {country} - No results")
        except Exception as e:
            print(f"✗ {country} - Error: {str(e)[:80]}")

if __name__ == '__main__':
    test_country_filtering()
