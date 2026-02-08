import unittest
from unittest.mock import MagicMock
from strategy_executor.position_sizing import PositionSizer
from strategy_executor.models import PositionSize

class TestPositionSizer(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.sizer = PositionSizer(self.mock_db)

    def test_nvr_max_position_limit(self):
        """
        Test the NVR scenario where adding another share would exceed the 10% max position limit.
        """
        # Scenario Configuration
        portfolio_id = 9
        symbol = 'NVR'
        current_price = 8009.84
        
        # Portfolio State: $100k total, holding 1 share of NVR
        self.mock_db.get_portfolio_summary.return_value = {
            'total_value': 100000.0,
            'cash': 91965.36,
            'holdings': {
                'NVR': 1
            }
        }
        
        # Sizing Rules: Max 10%
        rules = {
            'method': 'conviction_weighted',
            'max_position_pct': 10,
            'min_position_value': 500
        }
        
        # Execute Sizing
        result = self.sizer.calculate_position(
            portfolio_id=portfolio_id,
            symbol=symbol,
            conviction_score=50,
            method='conviction_weighted',
            rules=rules,
            other_buys=[],
            current_price=current_price
        )
        
        # Assertions
        # 1 share ($8009) + 1 share ($8009) = $16,018 > $10,000 limit
        # So should execute 0 shares
        self.assertEqual(result.shares, 0)
        self.assertEqual(result.estimated_value, 0.0)
        self.assertTrue("Already at max position" in str(result.reasoning) or result.shares == 0)

    def test_basic_buy(self):
        """Test a standard buy scenario with sufficient cash and room."""
        portfolio_id = 1
        symbol = 'AAPL'
        current_price = 150.0
        
        self.mock_db.get_portfolio_summary.return_value = {
            'total_value': 10000.0,
            'cash': 5000.0,
            'holdings': {}
        }
        
        rules = {
            'method': 'fixed_pct',
            'fixed_position_pct': 10,  # Target $1000
            'max_position_pct': 20,
            'min_position_value': 100
        }
        
        result = self.sizer.calculate_position(
            portfolio_id=portfolio_id,
            symbol=symbol,
            conviction_score=50,
            method='fixed_pct',
            rules=rules,
            current_price=current_price
        )
        
        # Target $1000 / $150 = 6 shares
        self.assertEqual(result.shares, 6)
        self.assertAlmostEqual(result.estimated_value, 900.0)

if __name__ == '__main__':
    unittest.main()
