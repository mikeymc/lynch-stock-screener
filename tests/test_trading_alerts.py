
import sys
import os
import json
import logging
import unittest
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

from worker import BackgroundWorker

class TestTradingAlerts(unittest.TestCase):
    def setUp(self):
        with patch('database.Database'):
            self.worker = BackgroundWorker()

        # Mock database interactions
        self.worker.db = MagicMock()
        self.worker._llm_client = MagicMock()

        # Mock portfolio service (it's imported in worker, so we patch it there)
        self.patcher = patch('worker.portfolio_service')
        self.mock_portfolio_service = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_automated_trade_execution(self):
        """Test that a triggered alert with action_type executes a trade."""
        
        # Setup mock alert data
        alert_id = 999
        symbol = "TEST"
        portfolio_id = 123
        quantity = 10
        
        mock_alert = {
            'id': alert_id,
            'symbol': symbol,
            'condition_type': 'custom',
            'condition_params': {},
            'condition_description': 'Price drops',
            'action_type': 'market_buy',
            'action_payload': {'quantity': quantity},
            'portfolio_id': portfolio_id,
            'action_note': 'Test Buy',
            'status': 'active'
        }
        
        # Mock db responses
        self.worker.db.get_all_active_alerts.return_value = [mock_alert]
        self.worker.db.get_stock_metrics.return_value = {'price': 100.0, 'pe_ratio': 10.0}
        self.worker.db.get_insider_trades.return_value = []
        self.worker.db.get_material_events.return_value = []
        self.worker.db.get_earnings_history.return_value = []
        self.worker.db.get_weekly_prices.return_value = {}

        # Mock LLM to force trigger
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "triggered": True, 
            "reason": "Test condition met"
        })
        self.worker.llm_client.models.generate_content.return_value = mock_response
        
        # Mock trade execution success
        self.mock_portfolio_service.execute_trade.return_value = {
            'success': True,
            'transaction_id': 1,
            'price_per_share': 100.0,
            'total_value': 1000.0
        }
        
        # Run check_alerts
        self.worker._run_check_alerts(job_id=1, params={})
        
        # Verify execute_trade was called correctly
        self.mock_portfolio_service.execute_trade.assert_called_once()
        call_args = self.mock_portfolio_service.execute_trade.call_args[1]
        
        self.assertEqual(call_args['portfolio_id'], portfolio_id)
        self.assertEqual(call_args['symbol'], symbol)
        self.assertEqual(call_args['transaction_type'], 'BUY') # market_buy -> BUY
        self.assertEqual(call_args['quantity'], quantity)
        self.assertIn("Test Buy", call_args['note'])
        
        # Verify alert status update contains trade result
        self.worker.db.update_alert_status.assert_called_once()
        status_args = self.worker.db.update_alert_status.call_args[1] # Or args if positional
        # update_alert_status args: (alert_id, status=..., triggered_at=..., message=...)
        # kwargs usage in worker.py is explicit names usually, let's check positional/keyword
        # The call in worker is: update_alert_status(alert['id'], status='triggered', ..., message=...)
        
        message = status_args.get('message')
        self.assertIn("Auto-Trade: Executed BUY 10 shares", message)
        
    def test_automated_trade_skipped_if_not_triggered(self):
        """Test that trade is NOT executed if alert is active but not triggered."""
        
        mock_alert = {
            'id': 888,
            'symbol': 'TEST',
            'action_type': 'market_buy',
            'portfolio_id': 1,
            'action_payload': {'quantity': 5},
            'condition_type': 'custom',
            'condition_params': {},
            'status': 'active'
        }
        
        self.worker.db.get_all_active_alerts.return_value = [mock_alert]
        self.worker.db.get_stock_metrics.return_value = {'price': 50}
        
        # Mock LLM to NOT trigger
        mock_response = MagicMock()
        mock_response.text = json.dumps({"triggered": False, "reason": "No change"})
        self.worker.llm_client.models.generate_content.return_value = mock_response
        
        self.worker._run_check_alerts(job_id=2, params={})
        
        self.mock_portfolio_service.execute_trade.assert_not_called()

    def test_hold_off_when_market_closed(self):
        """Test that trading alerts are skipped (held off) when market is closed."""
        
        mock_alert = {
            'id': 777,
            'symbol': 'TEST',
            'action_type': 'market_buy',
            'portfolio_id': 1,
            'action_payload': {'quantity': 5},
            'condition_type': 'custom',
            'condition_params': {},
            'status': 'active'
        }
        
        self.worker.db.get_all_active_alerts.return_value = [mock_alert]
        
        # Mock market closed
        self.mock_portfolio_service.is_market_open.return_value = False
        
        # Reset other mocks to ensure they aren't called
        self.worker.db.get_stock_metrics.reset_mock()
        self.worker.llm_client.models.generate_content.reset_mock()
        
        self.worker._run_check_alerts(job_id=3, params={})
        
        # Verify we didn't even fetch metrics or call LLM (because we skipped early)
        self.worker.db.get_stock_metrics.assert_not_called()
        self.worker.llm_client.models.generate_content.assert_not_called()
        self.mock_portfolio_service.execute_trade.assert_not_called()

if __name__ == '__main__':
    unittest.main()
