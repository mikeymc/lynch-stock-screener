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

    def test_min_position_value_alias(self):
        """Test that min_position_value in rules is respected (it's the UI name)."""
        portfolio_id = 1
        symbol = 'AAPL'
        current_price = 150.0
        
        self.mock_db.get_portfolio_summary.return_value = {
            'total_value': 10000.0,
            'cash': 5000.0,
            'holdings': {}
        }
        
        # Test 1: Amount below threshold ($500 < $1000)
        rules = {
            'method': 'fixed_pct',
            'fixed_position_pct': 5,  # Target $500
            'max_position_pct': 20,
            'min_position_value': 1000 # High threshold
        }
        
        result = self.sizer.calculate_position(
            portfolio_id=portfolio_id,
            symbol=symbol,
            conviction_score=50,
            method='fixed_pct',
            rules=rules,
            current_price=current_price
        )
        
        self.assertEqual(result.shares, 0, "Should skip trade as $500 < $1000 min_position_value")
        self.assertIn("below minimum trade amount", result.reasoning.lower())

        # Test 2: Amount above threshold ($1500 > $1000)
        rules['fixed_position_pct'] = 15 # Target $1500
        result = self.sizer.calculate_position(
            portfolio_id=portfolio_id,
            symbol=symbol,
            conviction_score=50,
            method='fixed_pct',
            rules=rules,
            current_price=current_price
        )
        self.assertEqual(result.shares, 10, "Should execute 10 shares ($1500)")
        self.assertEqual(result.estimated_value, 1500.0)

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


class TestRebalancingTrims(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.sizer = PositionSizer(self.mock_db)

    def _held_verdict(self, symbol, lynch_score, buffett_score, verdict='WATCH'):
        return {'symbol': symbol, 'lynch_score': lynch_score, 'buffett_score': buffett_score, 'final_verdict': verdict}

    def _buy_decision(self, symbol, consensus_score=70):
        return {'symbol': symbol, 'consensus_score': consensus_score}

    def test_rebalancing_trims_over_weight_equal_weight(self):
        """Over-weight holding generates a trim signal to bring it to equal-weight target."""
        # Universe: AAPL (held) + MSFT (buy) → N=2, target=$1000 each in $2000 portfolio
        # AAPL: 20 shares @ $100 = $2000, which is 2× the $1000 target
        self.sizer._fetch_price = lambda s: 100.0
        trims = self.sizer.compute_rebalancing_trims(
            holdings={'AAPL': 20},
            held_verdicts=[self._held_verdict('AAPL', 70, 70)],
            buy_decisions=[self._buy_decision('MSFT')],
            portfolio_value=2000.0,
            method='equal_weight',
            rules={'max_position_pct': 100, 'min_position_value': 100},
        )

        self.assertEqual(len(trims), 1)
        self.assertEqual(trims[0].symbol, 'AAPL')
        self.assertEqual(trims[0].quantity, 10)
        self.assertEqual(trims[0].exit_type, 'trim')

    def test_rebalancing_trims_at_weight_no_trim(self):
        """Holding exactly at target weight produces no trim."""
        # Universe: AAPL + MSFT → target=$1000. AAPL is at $1000 (10 shares @ $100).
        self.sizer._fetch_price = lambda s: 100.0
        trims = self.sizer.compute_rebalancing_trims(
            holdings={'AAPL': 10},
            held_verdicts=[self._held_verdict('AAPL', 70, 70)],
            buy_decisions=[self._buy_decision('MSFT')],
            portfolio_value=2000.0,
            method='equal_weight',
            rules={'max_position_pct': 100, 'min_position_value': 100},
        )

        self.assertEqual(len(trims), 0)

    def test_rebalancing_trims_empty_held_verdicts_returns_empty(self):
        """No held_verdicts and no buy_decisions → no universe → no trims."""
        trims = self.sizer.compute_rebalancing_trims(
            holdings={'AAPL': 10},
            held_verdicts=[],
            buy_decisions=[],
            portfolio_value=10000.0,
            method='equal_weight',
            rules={'max_position_pct': 100, 'min_position_value': 100},
        )

        self.assertEqual(trims, [])

    def test_rebalancing_trims_conviction_weighted(self):
        """Over-weight holding trimmed to its conviction-proportional target."""
        # AAPL conviction=80, TSLA conviction=20 → targets 80%/20% of $10k
        # AAPL target=$8000: 45 shares @ $200 = $9000 → trim 5 shares
        # TSLA target=$2000: 10 shares @ $100 = $1000 → no trim
        price_map = {'AAPL': 200.0, 'TSLA': 100.0}
        self.sizer._fetch_price = lambda s: price_map.get(s)

        held_verdicts = [
            self._held_verdict('AAPL', lynch_score=90, buffett_score=70),  # conviction=80
            self._held_verdict('TSLA', lynch_score=30, buffett_score=10),  # conviction=20
        ]
        trims = self.sizer.compute_rebalancing_trims(
            holdings={'AAPL': 45, 'TSLA': 10},
            held_verdicts=held_verdicts,
            buy_decisions=[],
            portfolio_value=10000.0,
            method='conviction_weighted',
            rules={'max_position_pct': 100, 'min_position_value': 100},
        )

        trim_symbols = [t.symbol for t in trims]
        self.assertIn('AAPL', trim_symbols)
        self.assertNotIn('TSLA', trim_symbols)
        aapl_trim = next(t for t in trims if t.symbol == 'AAPL')
        self.assertEqual(aapl_trim.quantity, 5)

    def test_rebalancing_trims_does_not_full_exit(self):
        """Trim quantity is always less than total shares held (partial sell only)."""
        # AAPL: 30 shares @ $100 = $3000. Target=$1000 in 4-stock portfolio.
        # Should sell 20 shares, keep 10.
        self.sizer._fetch_price = lambda s: 100.0
        buy_decisions = [
            self._buy_decision('MSFT'),
            self._buy_decision('GOOG'),
            self._buy_decision('TSLA'),
        ]
        trims = self.sizer.compute_rebalancing_trims(
            holdings={'AAPL': 30},
            held_verdicts=[self._held_verdict('AAPL', 70, 70)],
            buy_decisions=buy_decisions,
            portfolio_value=4000.0,
            method='equal_weight',
            rules={'max_position_pct': 100, 'min_position_value': 100},
        )

        self.assertEqual(len(trims), 1)
        trim = trims[0]
        self.assertEqual(trim.quantity, 20)
        self.assertLess(trim.quantity, 30, "Trim must not sell entire position")
        self.assertEqual(trim.exit_type, 'trim')


if __name__ == '__main__':
    unittest.main()
