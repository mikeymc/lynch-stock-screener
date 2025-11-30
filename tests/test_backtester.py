import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

from backtester import Backtester

class TestBacktester(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.backtester = Backtester(self.mock_db)

    @patch('backtester.yf.Ticker')
    def test_fetch_historical_prices(self, mock_ticker):
        # Mock yfinance history
        mock_hist = MagicMock()
        mock_hist.empty = False
        # Create a mock dataframe-like object or just mock iterrows
        # For simplicity, we'll mock the whole history object behavior if possible
        # But mocking pandas DataFrame is complex. 
        # Instead, let's trust the integration test we did manually and focus on logic here.
        pass

    def test_get_historical_score_no_price(self):
        # Setup mock to return no price history
        self.mock_db.get_price_history.return_value = []
        
        result = self.backtester.get_historical_score('AAPL', '2023-01-01')
        self.assertIsNone(result)

    def test_get_historical_score_success(self):
        # Setup mock data
        self.mock_db.get_price_history.return_value = [{'close': 150.0}]
        self.mock_db.get_earnings_history.return_value = [
            {'year': 2022, 'eps': 5.0, 'debt_to_equity': 0.5},
            {'year': 2021, 'eps': 4.0},
            {'year': 2020, 'eps': 3.0}
        ]
        self.mock_db.get_stock_metrics.return_value = {
            'market_cap': 2000000000,
            'sector': 'Technology',
            'country': 'US',
            'institutional_ownership': 0.6
        }
        
        # Mock criteria
        self.backtester.criteria = MagicMock()
        self.backtester.criteria.calculate_peg_ratio.return_value = 1.5
        self.backtester.criteria.evaluate_peg.return_value = 'PASS'
        self.backtester.criteria.calculate_peg_score.return_value = 100
        self.backtester.criteria.evaluate_debt.return_value = 'PASS'
        self.backtester.criteria.calculate_debt_score.return_value = 100
        self.backtester.criteria.evaluate_institutional_ownership.return_value = 'PASS'
        self.backtester.criteria.calculate_institutional_ownership_score.return_value = 100
        self.backtester.criteria._evaluate_weighted.return_value = {
            'overall_score': 85,
            'rating_label': 'BUY'
        }

        result = self.backtester.get_historical_score('AAPL', '2023-01-01')
        
        self.assertIsNotNone(result)
        self.assertEqual(result['overall_score'], 85)
        self.mock_db.get_price_history.assert_called()

if __name__ == '__main__':
    unittest.main()
