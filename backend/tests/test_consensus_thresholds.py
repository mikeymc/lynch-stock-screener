import sys
import os
import unittest
from unittest.mock import MagicMock

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategy_executor.consensus import ConsensusEngine
from strategy_executor.models import ConsensusResult

class TestConsensusIntegration(unittest.TestCase):
    def setUp(self):
        self.engine = ConsensusEngine()

    def test_veto_power_threshold(self):
        """Test that veto_score_threshold is respected."""
        lynch = {'score': 80, 'status': 'BUY'}
        buffett = {'score': 25, 'status': 'AVOID'} # Score 25 < default 30
        
        # Test Default Threshold (30)
        res = self.engine.veto_power(lynch, buffett, {'veto_score_threshold': 30})
        self.assertEqual(res.verdict, 'VETO')
        
        # Test Custom Threshold (20)
        res = self.engine.veto_power(lynch, buffett, {'veto_score_threshold': 20})
        # Score 25 > 20, but status is 'AVOID', so it still vetos
        self.assertEqual(res.verdict, 'VETO')
        
        # Test Custom Threshold (20) and Neutral Status
        buffett_neutral = {'score': 25, 'status': 'WATCH'}
        res = self.engine.veto_power(lynch, buffett_neutral, {'veto_score_threshold': 20})
        self.assertEqual(res.verdict, 'WATCH') # No veto, but score too low for BUY
        
        # Test Custom Threshold (20) and High Score
        buffett_high = {'score': 75, 'status': 'BUY'}
        res = self.engine.veto_power(lynch, buffett_high, {'veto_score_threshold': 20, 'threshold': 70})
        self.assertEqual(res.verdict, 'BUY')

    def test_weighted_consensus_threshold(self):
        """Test that weighted_confidence uses the provided threshold."""
        lynch = {'score': 75, 'status': 'BUY'}
        buffett = {'score': 65, 'status': 'WATCH'}
        
        # Weighted avg: 70
        config = {'lynch_weight': 0.5, 'buffett_weight': 0.5, 'threshold': 75}
        res = self.engine.weighted_confidence(lynch, buffett, config)
        self.assertEqual(res.verdict, 'AVOID') # 70 < 75
        
        config['threshold'] = 65
        res = self.engine.weighted_confidence(lynch, buffett, config)
        self.assertEqual(res.verdict, 'WATCH') # 70 >= 65 (but < 80 for BUY)

if __name__ == '__main__':
    unittest.main()
