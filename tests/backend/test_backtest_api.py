import pytest
import requests
import unittest
import json


class TestBacktestAPI(unittest.TestCase):
    BASE_URL = "http://localhost:8081/api"

    @pytest.mark.skip(reason="Requires running server - convert to use Flask test client or move to e2e tests")
    def test_backtest_endpoint(self):
        """Test backtest API endpoint for GOOGL."""
        url = f"{self.BASE_URL}/backtest"
        payload = {
            "symbol": "GOOGL",
            "years_back": 1
        }

        response = requests.post(url, json=payload, timeout=5)
        self.assertEqual(response.status_code, 200, f"Expected 200, got {response.status_code}: {response.text}")

        data = response.json()
        self.assertIn('symbol', data)
        self.assertEqual(data['symbol'], 'GOOGL')
        self.assertIn('total_return', data)
        self.assertIn('historical_score', data)
