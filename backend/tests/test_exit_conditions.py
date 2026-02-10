# ABOUTME: Tests for ExitConditionChecker — price/time exits and score degradation
# ABOUTME: Covers default score degradation and explicit config override

import sys
import os
import unittest
from unittest.mock import MagicMock
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategy_executor.exit_conditions import ExitConditionChecker, DEFAULT_SCORE_DEGRADATION
from strategy_executor.models import ExitSignal

class TestExitConditions(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.checker = ExitConditionChecker(self.mock_db)

    def test_check_exits_max_hold_days_hit(self):
        """Test that max hold days triggers an exit."""
        # Setup mock data
        portfolio_id = 1
        symbol = "AAPL"
        quantity = 10
        current_value = 1500
        
        # Mock holdings
        self.mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': symbol,
            'quantity': quantity,
            'current_value': current_value,
            'total_cost': 1000
        }]

        # Mock entry dates (bought 400 days ago)
        entry_date = date.today() - timedelta(days=400)
        self.mock_db.get_position_entry_dates.return_value = {
            symbol: {'first_buy_date': entry_date}
        }

        # Exit conditions
        conditions = {
            "max_hold_days": 365
        }

        # Run check
        exits = self.checker.check_exits(portfolio_id, conditions)

        # Assertions
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].symbol, symbol)
        self.assertIn("Max hold duration reached", exits[0].reason)
        # Verify 400 days > 365 days
        self.assertIn("400 days", exits[0].reason)

    def test_check_exits_max_hold_days_not_hit(self):
        """Test that max hold days does not trigger exit if not reached."""
        # Setup mock data
        portfolio_id = 1
        symbol = "AAPL"
        
        # Mock holdings
        self.mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': symbol,
            'quantity': 10,
            'current_value': 1500,
            'total_cost': 1000
        }]

        # Mock entry dates (bought 100 days ago)
        entry_date = date.today() - timedelta(days=100)
        self.mock_db.get_position_entry_dates.return_value = {
            symbol: {'first_buy_date': entry_date}
        }

        # Exit conditions
        conditions = {
            "max_hold_days": 365
        }

        # Run check
        exits = self.checker.check_exits(portfolio_id, conditions)

        # Assertions
        self.assertEqual(len(exits), 0)

    def test_check_exits_no_entry_date(self):
        """Test that missing entry date doesn't crash."""
        # Setup mock data
        portfolio_id = 1
        symbol = "AAPL"
        
        # Mock holdings
        self.mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': symbol,
            'quantity': 10,
            'current_value': 1500,
            'total_cost': 1000
        }]

        # Mock entry dates (none for this symbol)
        self.mock_db.get_position_entry_dates.return_value = {}

        # Exit conditions
        conditions = {
            "max_hold_days": 365
        }

        # Run check
        exits = self.checker.check_exits(portfolio_id, conditions)

        # Assertions
        self.assertEqual(len(exits), 0)

    def test_default_score_degradation_constant_exists(self):
        """DEFAULT_SCORE_DEGRADATION is exported and has expected keys."""
        self.assertIn('lynch_below', DEFAULT_SCORE_DEGRADATION)
        self.assertIn('buffett_below', DEFAULT_SCORE_DEGRADATION)
        self.assertEqual(DEFAULT_SCORE_DEGRADATION['lynch_below'], 50)
        self.assertEqual(DEFAULT_SCORE_DEGRADATION['buffett_below'], 50)

    def test_default_score_degradation_applied_when_not_configured(self):
        """check_exits uses default degradation thresholds when none configured."""
        self.mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': 'AAPL',
            'quantity': 10,
            'current_value': 1200.0,
            'total_cost': 1000.0
        }]
        self.mock_db.get_position_entry_dates.return_value = {}

        # Both scores at 15 — below default threshold of 50 (AND: both must fail)
        def scoring_func(symbol):
            return {'lynch_score': 15, 'buffett_score': 15}

        exits = self.checker.check_exits(1, {}, scoring_func=scoring_func)

        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].symbol, 'AAPL')
        self.assertIn('degraded', exits[0].reason.lower())

    def test_explicit_score_degradation_overrides_default(self):
        """Explicit score_degradation in exit_conditions overrides the default."""
        self.mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': 'AAPL',
            'quantity': 10,
            'current_value': 1200.0,
            'total_cost': 1000.0
        }]
        self.mock_db.get_position_entry_dates.return_value = {}

        # Both scores at 35 — above default (50 AND) but below explicit (40 AND)
        def scoring_func(symbol):
            return {'lynch_score': 35, 'buffett_score': 35}

        exits = self.checker.check_exits(
            1,
            {'score_degradation': {'lynch_below': 40, 'buffett_below': 40}},
            scoring_func=scoring_func
        )

        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].symbol, 'AAPL')
