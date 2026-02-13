import sys
import os
import unittest
from unittest.mock import MagicMock

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategy_executor.position_sizing import PositionSizer
from strategy_executor.models import TargetAllocation

class TestPositionSizingReconciliation(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.sizer = PositionSizer(self.mock_db)

    def test_min_position_value_respected(self):
        """Verify that min_position_value in rules is used to skip small trades."""
        
        # Scenario: Target is $500, current holding is $0.
        # If min_position_value is $1000, it should skip.
        # If min_position_value is $100, it should buy.
        
        target = TargetAllocation(
            symbol='AAPL',
            conviction=50,
            target_value=500.0,
            current_value=0.0,
            drift=500.0,
            price=150.0,
            source_data={'symbol': 'AAPL', 'price': 150.0}
        )
        
        holdings = {} # No current holdings
        
        # Case 1: High threshold ($1000) -> Skip
        rules = {'min_position_value': 1000.0}
        sells, buys = self.sizer._generate_signals([target], holdings, rules)
        
        self.assertEqual(len(buys), 0, "Should skip buy if below min_position_value")
        
        # Case 2: Low threshold ($100) -> Buy
        rules = {'min_position_value': 100.0}
        sells, buys = self.sizer._generate_signals([target], holdings, rules)
        
        self.assertEqual(len(buys), 1, "Should buy if above min_position_value")
        self.assertEqual(buys[0]['symbol'], 'AAPL')
        self.assertEqual(buys[0]['position'].shares, 3) # $500 / $150 = 3.33 -> 3 shares

    def test_min_trade_amount_fallback(self):
        """Verify that min_trade_amount is used if min_position_value is missing."""
        target = TargetAllocation(
            symbol='AAPL',
            conviction=50,
            target_value=500.0,
            current_value=0.0,
            drift=500.0,
            price=150.0,
            source_data={'symbol': 'AAPL', 'price': 150.0}
        )
        holdings = {}
        
        # Case: No min_position_value, but min_trade_amount is $1000 -> Skip
        rules = {'min_trade_amount': 1000.0}
        sells, buys = self.sizer._generate_signals([target], holdings, rules)
        self.assertEqual(len(buys), 0)
        
        # Case: No min_position_value, but min_trade_amount is $100 -> Buy
        rules = {'min_trade_amount': 100.0}
        sells, buys = self.sizer._generate_signals([target], holdings, rules)
        self.assertEqual(len(buys), 1)

if __name__ == '__main__':
    unittest.main()
