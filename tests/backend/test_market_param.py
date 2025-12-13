#!/usr/bin/env python3
"""
Test script to verify if we can query specific markets
"""

import sys
sys.path.insert(0, '/Users/mikey/workspace/lynch-stock-screener/backend')

# We need to check if Query accepts arguments. 
# Since I can't see the library code easily, I'll try to guess the API or inspect it.
from tradingview_screener import Query, Column

def test_markets():
    print("Testing specific markets...")
    
    markets = ['uk', 'germany', 'hongkong', 'china', 'india']
    
    for market in markets:
        print(f"\nTesting market: {market}")
        try:
            # Try passing market to Query constructor - this is a common pattern in this lib
            # Note: The library might use 'market' or 'screener' kwarg.
            # Let's try to inspect Query first if possible, or just try.
            # Based on common knowledge of this lib, it might be Query().set_markets() or similar?
            # Actually, usually it's not passed to Query, but the library might have a way.
            # Let's try standard Query() but look for a way to set market.
            
            # Attempt 1: Constructor
            # q = Query(market=market) 
            
            # Wait, let's look at how the library is typically used.
            # If I can't change market, I can't get LSE stocks.
            
            # Let's try to just run it and see if it errors or works.
            # I'll try to find a way to set the market.
            pass
        except Exception as e:
            print(f"Error: {e}")

    # Let's try to inspect the Query class
    print("\nInspecting Query class...")
    print(dir(Query))
    
    try:
        # Try to use a different screener if possible
        # Some versions use Query(screener='uk')
        q = Query()
        print(f"Default screener: {q.screener if hasattr(q, 'screener') else 'Unknown'}")
        print(f"Default exchange: {q.exchange if hasattr(q, 'exchange') else 'Unknown'}")
        
    except Exception as e:
        print(f"Error inspecting: {e}")

if __name__ == '__main__':
    test_markets()
