import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()
sys.modules["price_history_fetcher"] = MagicMock()
sys.modules["sec_data_fetcher"] = MagicMock()
sys.modules["news_fetcher"] = MagicMock()
sys.modules["material_events_fetcher"] = MagicMock()
sys.modules["sec_rate_limiter"] = MagicMock()
sys.modules["yfinance.cache"] = MagicMock()
sys.modules["portfolio_service"] = MagicMock()

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

class TestCalculatePositionWithProvidedState(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.sizer = PositionSizer(self.mock_db)

    def test_calculate_position_uses_provided_state_not_db(self):
        """When available_cash, total_value, and holdings are all provided, DB is not queried."""
        result = self.sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=70,
            method='fixed_pct',
            rules={'fixed_position_pct': 5, 'max_position_pct': 20, 'min_position_value': 100},
            current_price=150.0,
            available_cash=8000.0,
            total_value=50000.0,
            holdings={}
        )

        self.mock_db.get_portfolio_summary.assert_not_called()
        self.assertGreater(result.shares, 0)


class TestPrioritizePositions(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.sizer = PositionSizer(self.mock_db)

        # Make calculate_position return a real-ish PositionSize without DB calls
        def fake_calculate(portfolio_id, symbol, conviction_score, method, rules,
                           other_buys=None, current_price=None,
                           available_cash=None, total_value=None, holdings=None):
            shares = int(1000 / current_price) if current_price else 10
            value = shares * (current_price or 100.0)
            pct = value / total_value * 100 if total_value else 1.0
            return PositionSize(shares=shares, estimated_value=value, position_pct=pct, reasoning='test')

        self.sizer.calculate_position = fake_calculate

    def _make_decision(self, symbol, conviction, price=100.0):
        return {'symbol': symbol, 'consensus_score': conviction, '_price': price}

    def test_prioritize_positions_sorts_by_conviction(self):
        """High-conviction symbol appears first in output."""
        decisions = [
            {'symbol': 'LOW_CONV', 'consensus_score': 40},
            {'symbol': 'HIGH_CONV', 'consensus_score': 80},
        ]

        result = self.sizer.prioritize_positions(
            buy_decisions=decisions,
            available_cash=10000.0,
            portfolio_value=50000.0,
            portfolio_id=1,
            method='fixed_pct',
            rules={'fixed_position_pct': 2, 'max_position_pct': 20, 'min_position_value': 100},
        )

        self.assertEqual(result[0]['symbol'], 'HIGH_CONV')
        self.assertEqual(result[1]['symbol'], 'LOW_CONV')

    def test_prioritize_positions_greedy_excludes_over_budget(self):
        """When total exceeds available_cash, lowest-priority decision is excluded."""
        # Each position costs ~$1000. With $2500 cash, we can only fit 2 of 3.
        decisions = [
            {'symbol': 'A', 'consensus_score': 90},  # highest priority
            {'symbol': 'B', 'consensus_score': 70},  # middle
            {'symbol': 'C', 'consensus_score': 50},  # lowest priority — should be excluded
        ]

        result = self.sizer.prioritize_positions(
            buy_decisions=decisions,
            available_cash=2500.0,
            portfolio_value=50000.0,
            portfolio_id=1,
            method='fixed_pct',
            rules={'fixed_position_pct': 2, 'max_position_pct': 20, 'min_position_value': 100},
        )

        symbols = [r['symbol'] for r in result]
        self.assertIn('A', symbols)
        self.assertIn('B', symbols)
        self.assertNotIn('C', symbols)

    def test_prioritize_positions_excludes_exited_holdings(self):
        """Passing holdings={} (AAPL removed) means room_to_add is full max, not 0."""
        # Restore real calculate_position to verify holdings flow
        self.mock_db.get_portfolio_summary.return_value = {
            'total_value': 50000.0,
            'cash': 10000.0,
            'holdings': {'AAPL': 100}  # DB still shows AAPL (not yet sold)
        }
        real_sizer = PositionSizer(self.mock_db)

        decisions = [{'symbol': 'AAPL', 'consensus_score': 70}]

        # Pass holdings={} to simulate AAPL already exited (not in post-exit holdings)
        result = real_sizer.prioritize_positions(
            buy_decisions=decisions,
            available_cash=10000.0,
            portfolio_value=50000.0,
            portfolio_id=1,
            method='fixed_pct',
            rules={'fixed_position_pct': 2, 'max_position_pct': 10, 'min_position_value': 100},
            holdings={},
            current_prices={'AAPL': 150.0}
        )

        # AAPL should not be blocked by its former holding
        self.assertEqual(len(result), 1)
        self.assertGreater(result[0]['position'].shares, 0)


if __name__ == '__main__':
    unittest.main()
