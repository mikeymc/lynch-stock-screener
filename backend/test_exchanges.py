#!/usr/bin/env python3
"""
Test script to discover what exchanges TradingView supports
"""

import sys
sys.path.insert(0, '/Users/mikey/workspace/lynch-stock-screener/backend')

from tradingview_screener import Query, Column

def test_exchange_discovery():
    print("Testing different exchange codes...")
    
    # Try some common exchange variations
    test_exchanges = [
        # European
        ['LSE'], ['LONDON'], ['LON'],
        ['XETRA'], ['FRA'], ['FRANKFURT'],
        ['EURONEXT'], ['EPA'], ['PAR'], ['PARIS'],
        ['SIX'], ['SWX'],
        ['BME'], ['MCE'], ['MADRID'],
        ['BIT'], ['MIL'], ['MILAN'],
        
        # Asian
        ['HKEX'], ['HKG'], ['HKSE'],
        ['TSE'], ['TYO'], ['TOKYO'],
        ['SSE'], ['SHA'], ['SHANGHAI'],
        ['SZSE'], ['SHE'], ['SHENZHEN'],
        ['KRX'], ['KSC'], ['KOREA'],
        ['NSE'], ['NSI'], ['INDIA'],
        ['BSE'], ['BOM'], ['BOMBAY'],
        ['SGX'], ['SES'], ['SINGAPORE'],
    ]
    
    for exchanges in test_exchanges:
        try:
            q = (Query()
                 .select('name', 'description', 'exchange')
                 .where(Column('exchange').isin(exchanges))
                 .limit(1))
            
            count, df = q.get_scanner_data()
            
            if len(df) > 0:
                print(f"✓ {exchanges[0]:15} - WORKS! Sample: {df.iloc[0]['name']} ({df.iloc[0].get('exchange', 'N/A')})")
            else:
                print(f"✗ {exchanges[0]:15} - No results")
        except Exception as e:
            print(f"✗ {exchanges[0]:15} - Error: {str(e)[:50]}")

if __name__ == '__main__':
    test_exchange_discovery()
