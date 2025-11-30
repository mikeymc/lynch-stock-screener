import requests
import unittest
import json
import time

class TestBacktestAPI(unittest.TestCase):
    BASE_URL = "http://localhost:8080/api"

    def test_backtest_endpoint(self):
        url = f"{self.BASE_URL}/backtest"
        payload = {
            "symbol": "GOOGL",
            "years_back": 1
        }
        
        print(f"Testing API endpoint: {url}")
        try:
            response = requests.post(url, json=payload)
            
            if response.status_code != 200:
                print(f"API Error: {response.status_code} - {response.text}")
                
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            self.assertIn('symbol', data)
            self.assertEqual(data['symbol'], 'GOOGL')
            self.assertIn('total_return', data)
            self.assertIn('historical_score', data)
            
            print("API Test Passed!")
            print(json.dumps(data, indent=2))
            
        except requests.exceptions.ConnectionError:
            self.fail("Could not connect to API. Is the server running?")

if __name__ == "__main__":
    unittest.main()
