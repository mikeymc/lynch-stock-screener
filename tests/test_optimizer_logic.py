
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

import unittest
from algorithm_optimizer import AlgorithmOptimizer

class MockDB:
    pass

class TestOptimizerLogic(unittest.TestCase):
    def setUp(self):
        self.optimizer = AlgorithmOptimizer(MockDB())

    def test_enforce_threshold_constraints_margin(self):
        # Case 1: Too close (Raw: Exc=50, Good=49, Fair=48)
        # Should force 10% separation -> Exc=50, Good=40, Fair=30
        config = {
            'gross_margin_excellent': 50.0,
            'gross_margin_good': 49.0,
            'gross_margin_fair': 48.0
        }
        fixed = self.optimizer._enforce_threshold_constraints(config, 'buffett')
        
        print(f"\n[Test Case 1] Input: {config}\nOutput: {fixed}")
        
        self.assertLessEqual(fixed['gross_margin_good'], fixed['gross_margin_excellent'] - 10.0)
        self.assertLessEqual(fixed['gross_margin_fair'], fixed['gross_margin_good'] - 10.0)
        self.assertEqual(fixed['gross_margin_excellent'], 50.0) # Should stay anchored if room exists

    def test_enforce_threshold_constraints_sliding_window(self):
        # Case 2: Pushed Out of Bounds (Raw: Exc=20, Good=19, Fair=18)
        # 1. Enforce Sep: Exc=20, Good=10, Fair=0
        # 2. Check Min Bound (10.0): Fair is 0 (-10 violation)
        # 3. Slide Up by 10: Exc=30, Good=20, Fair=10
        config = {
            'gross_margin_excellent': 20.0,
            'gross_margin_good': 19.0,
            'gross_margin_fair': 18.0
        }
        fixed = self.optimizer._enforce_threshold_constraints(config, 'buffett')
        
        print(f"\n[Test Case 2 (Sliding)] Input: {config}\nOutput: {fixed}")
        
        self.assertGreaterEqual(fixed['gross_margin_fair'], 10.0) # Min bound
        self.assertLessEqual(fixed['gross_margin_good'], fixed['gross_margin_excellent'] - 10.0)
        self.assertLessEqual(fixed['gross_margin_fair'], fixed['gross_margin_good'] - 10.0)

    def test_enforce_ascending_peg(self):
        # Case 3: PEG (Lower is Better)
        # Raw: Exc=1.0, Good=1.1, Fair=1.2
        # Sep=0.4 -> Good >= 1.4, Fair >= 1.8
        config = {
            'peg_excellent': 1.0,
            'peg_good': 1.1,
            'peg_fair': 1.2,
            'inst_own_min': 0.1,  # Aux required keys
            'inst_own_max': 0.5
        }
        fixed = self.optimizer._enforce_threshold_constraints(config, 'lynch')
        
        print(f"\n[Test Case 3 (PEG)] Input: {config}\nOutput: {fixed}")
        
        self.assertGreaterEqual(fixed['peg_good'], fixed['peg_excellent'] + 0.4)
        self.assertGreaterEqual(fixed['peg_fair'], fixed['peg_good'] + 0.4)

    def test_low_peg_bounds(self):
        # Case 4: Low PEG below min_bound (min_bound=0.5)
        # Raw: Exc=0.05, Good=0.1, Fair=0.2
        # Sep=0.4 -> Good=0.45, Fair=0.85
        # Sliding window: excess_low = 0.5 - 0.05 = 0.45, slide up
        # Final: Exc=0.5, Good=0.9, Fair=1.3
        config = {
            'peg_excellent': 0.05,
            'peg_good': 0.1,
            'peg_fair': 0.2,
            'inst_own_min': 0.1,
            'inst_own_max': 0.5
        }
        fixed = self.optimizer._enforce_threshold_constraints(config, 'lynch')

        print(f"\n[Test Case 4 (Low PEG)] Input: {config}\nOutput: {fixed}")

        self.assertEqual(fixed['peg_excellent'], 0.5)
        self.assertGreaterEqual(fixed['peg_good'], 0.9)
        self.assertGreaterEqual(fixed['peg_fair'], 1.3)

if __name__ == '__main__':
    unittest.main()
