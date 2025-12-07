import requests
import json

def test_algorithm(symbol, algorithm):
    url = f"http://localhost:5001/api/stock/{symbol}?algorithm={algorithm}"
    print(f"Testing {algorithm} for {symbol}...")
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            evaluation = data.get('evaluation', {})
            
            required_fields = [
                'symbol', 'company_name', 'country', 'market_cap', 'sector', 'ipo_year',
                'price', 'peg_ratio', 'pe_ratio', 'debt_to_equity', 'institutional_ownership',
                'dividend_yield', 'earnings_cagr', 'revenue_cagr',
                'peg_status', 'peg_score', 'debt_status', 'debt_score',
                'institutional_ownership_status', 'institutional_ownership_score',
                'overall_status'
            ]
            
            missing_fields = [field for field in required_fields if field not in evaluation]
            if missing_fields:
                print(f"MISSING FIELDS: {missing_fields}")
            else:
                print("All required fields present.")
                
            print("Overall Status:", evaluation.get('overall_status'))
        else:
            print("Error:", response.text)
    except Exception as e:
        print(f"Exception: {e}")

test_algorithm('AAPL', 'category_based')
test_algorithm('AAPL', 'classic')
test_algorithm('AAPL', 'weighted')
