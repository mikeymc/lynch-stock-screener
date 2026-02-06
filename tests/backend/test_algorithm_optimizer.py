import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithm_optimizer import AlgorithmOptimizer
from database import Database

class TestAlgorithmOptimizer:
    @pytest.fixture
    def db(self):
        import unittest.mock as mock
        db_mock = mock.MagicMock()
        db_mock.get_algorithm_configs.return_value = []
        return db_mock

    @pytest.fixture
    def optimizer(self, db):
        return AlgorithmOptimizer(db)

    def test_bayesian_optimize_with_mock_data(self, optimizer):
        """Test that Bayesian optimization produces valid results with stubbed gp_minimize"""
        import unittest.mock as mock

        # Create mock backtest results with raw metrics
        mock_results = []
        for i in range(50):
            total_return = 10 + (i % 20)
            mock_results.append({
                'symbol': f'TEST{i}',
                'peg_ratio': 1.0 + (i % 10) * 0.1,
                'debt_to_equity': 0.5 + (i % 8) * 0.2,
                'institutional_ownership': 0.3 + (i % 6) * 0.05,
                'revenue_cagr': 10.0 + (i % 5) * 2,
                'earnings_cagr': 12.0 + (i % 5) * 2,
                'total_return': total_return,
                'historical_data': {}
            })

        initial_config = {
            'weight_peg': 0.50,
            'weight_consistency': 0.25,
            'weight_debt': 0.15,
            'weight_ownership': 0.10,
            'peg_excellent': 1.0,
            'peg_good': 1.5,
            'peg_fair': 2.0,
            'debt_excellent': 0.5,
            'debt_good': 1.0,
            'debt_moderate': 2.0,
            'inst_own_min': 0.20,
            'inst_own_max': 0.60,
            'revenue_growth_excellent': 15.0,
            'revenue_growth_good': 10.0,
            'revenue_growth_fair': 5.0,
            'income_growth_excellent': 15.0,
            'income_growth_good': 10.0,
            'income_growth_fair': 5.0
        }

        weight_keys = ['weight_peg', 'weight_consistency', 'weight_debt', 'weight_ownership']
        threshold_keys = [
            'peg_excellent', 'peg_good', 'peg_fair',
            'debt_excellent', 'debt_good', 'debt_moderate',
            'inst_own_min', 'inst_own_max',
            'revenue_growth_excellent', 'revenue_growth_good', 'revenue_growth_fair',
            'income_growth_excellent', 'income_growth_good', 'income_growth_fair'
        ]

        # Stub gp_minimize to return controlled, valid weights
        mock_result = mock.MagicMock()
        mock_result.x = [
            0.50, 0.25, 0.15,  # weights (sum=0.9, ownership=0.1)
            1.0, 1.5, 2.0,    # peg thresholds
            0.5, 1.0, 2.0,    # debt thresholds
            0.20, 0.60,       # inst ownership thresholds
            15.0, 10.0, 5.0,  # revenue growth thresholds
            15.0, 10.0, 5.0   # income growth thresholds
        ]
        mock_result.fun = -0.85  # Correlation of 0.85 (negated because we minimize)

        with mock.patch('algorithm_optimizer.gp_minimize', return_value=mock_result) as mock_gp:
            best_config, history = optimizer._bayesian_optimize(
                mock_results,
                'lynch',
                initial_config,
                weight_keys,
                threshold_keys,
                max_iterations=50
            )

            # Verify gp_minimize was called
            assert mock_gp.called

        # Verify best_config has all required keys
        assert 'weight_peg' in best_config
        assert 'weight_consistency' in best_config
        assert 'weight_debt' in best_config
        assert 'weight_ownership' in best_config

        # Verify all weights are positive
        weight_keys_check = [k for k in best_config.keys() if k.startswith('weight_')]
        assert all(best_config[key] > 0 for key in weight_keys_check), f"Not all weights positive: {best_config}"

        # Verify weights sum to approximately 1
        weight_sum = sum(best_config[key] for key in weight_keys_check)
        assert abs(weight_sum - 1.0) < 0.01, f"Weights sum to {weight_sum}, expected ~1.0"

        print(f"✓ Bayesian optimization test passed with stubbed gp_minimize")
        print(f"  Best config: {best_config}")

class TestThresholdConstraints:
    """Tests for threshold ordering constraints in trial generation.

    _enforce_threshold_constraints uses a rigid-body sliding window:
    1. Enforce minimum separation from the 'excellent' anchor outward
    2. Slide the whole chain to fit within (min_bound, max_bound)

    It does NOT sort values - it pushes good/fair away from excellent,
    then slides the entire chain within bounds.
    """

    @pytest.fixture
    def optimizer(self):
        import unittest.mock as mock
        db_mock = mock.MagicMock()
        return AlgorithmOptimizer(db_mock)

    def test_lynch_peg_thresholds_lower_is_better(self, optimizer):
        """PEG: ascending order enforced (excellent < good < fair).
        Input: exc=2.5, good=1.0, fair=1.5
        PEG bounds: min=0.5, max=3.0, sep=0.4
        Step 1: good=max(1.0, 2.5+0.4)=2.9, fair=max(1.5, 2.9+0.4)=3.3
        Step 2: excess_high=3.3-3.0=0.3 -> slide down: exc=2.2, good=2.6, fair=3.0
        """
        config = {
            'peg_excellent': 2.5,
            'peg_good': 1.0,
            'peg_fair': 1.5,
            'inst_own_min': 0.20,
            'inst_own_max': 0.60,
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['peg_excellent'] < result['peg_good'] < result['peg_fair']
        assert abs(result['peg_excellent'] - 2.2) < 0.01
        assert abs(result['peg_good'] - 2.6) < 0.01
        assert abs(result['peg_fair'] - 3.0) < 0.01

    def test_lynch_debt_equity_thresholds_lower_is_better(self, optimizer):
        """Debt: ascending order enforced (excellent < good < moderate).
        Input: exc=3.0, good=0.5, moderate=1.5
        Debt bounds: min=0.0, max=2.5, sep=0.4
        Step 1: good=max(0.5, 3.0+0.4)=3.4, moderate=max(1.5, 3.4+0.4)=3.8
        Step 2: excess_high=3.8-2.5=1.3 -> slide down: exc=1.7, good=2.1, moderate=2.5
        """
        config = {
            'debt_excellent': 3.0,
            'debt_good': 0.5,
            'debt_moderate': 1.5,
            'inst_own_min': 0.20,
            'inst_own_max': 0.60,
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['debt_excellent'] < result['debt_good'] < result['debt_moderate']
        assert abs(result['debt_excellent'] - 1.7) < 0.01
        assert abs(result['debt_good'] - 2.1) < 0.01
        assert abs(result['debt_moderate'] - 2.5) < 0.01

    def test_lynch_institutional_ownership_min_less_than_max(self, optimizer):
        """Inst ownership: min < max enforced with sliding.
        Input: min=0.75, max=0.25
        Bounds: min_b=0.05, max_b=0.90, sep=0.3
        Step 1: max=max(0.25, 0.75+0.3)=1.05
        Step 2: 1.05>0.90 -> diff=0.15 -> max=0.90, min=0.60
        """
        config = {
            'inst_own_min': 0.75,
            'inst_own_max': 0.25,
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['inst_own_min'] < result['inst_own_max']
        assert abs(result['inst_own_min'] - 0.60) < 0.01
        assert abs(result['inst_own_max'] - 0.90) < 0.01

    def test_lynch_revenue_growth_higher_is_better(self, optimizer):
        """Revenue growth: descending order enforced (excellent > good > fair).
        Input: exc=5.0, good=20.0, fair=10.0
        Growth bounds: min=2.0, max=35.0, sep=5.0
        Step 1: good=min(20.0, 5.0-5.0)=0.0, fair=min(10.0, 0.0-5.0)=-5.0
        Step 2: excess_low=2.0-(-5.0)=7.0 -> slide up: exc=12.0, good=7.0, fair=2.0
        """
        config = {
            'revenue_growth_excellent': 5.0,
            'revenue_growth_good': 20.0,
            'revenue_growth_fair': 10.0,
            'inst_own_min': 0.20,
            'inst_own_max': 0.60,
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['revenue_growth_excellent'] > result['revenue_growth_good'] > result['revenue_growth_fair']
        assert abs(result['revenue_growth_excellent'] - 12.0) < 0.01
        assert abs(result['revenue_growth_good'] - 7.0) < 0.01
        assert abs(result['revenue_growth_fair'] - 2.0) < 0.01

    def test_lynch_income_growth_higher_is_better(self, optimizer):
        """Income growth: descending order enforced (excellent > good > fair).
        Input: exc=8.0, good=25.0, fair=12.0
        Growth bounds: min=2.0, max=35.0, sep=5.0
        Step 1: good=min(25.0, 8.0-5.0)=3.0, fair=min(12.0, 3.0-5.0)=-2.0
        Step 2: excess_low=2.0-(-2.0)=4.0 -> slide up: exc=12.0, good=7.0, fair=2.0
        """
        config = {
            'income_growth_excellent': 8.0,
            'income_growth_good': 25.0,
            'income_growth_fair': 12.0,
            'inst_own_min': 0.20,
            'inst_own_max': 0.60,
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['income_growth_excellent'] > result['income_growth_good'] > result['income_growth_fair']
        assert abs(result['income_growth_excellent'] - 12.0) < 0.01
        assert abs(result['income_growth_good'] - 7.0) < 0.01
        assert abs(result['income_growth_fair'] - 2.0) < 0.01

    def test_buffett_debt_to_earnings_lower_is_better(self, optimizer):
        """Debt/Earnings: ascending order enforced (excellent < good < fair).
        Input: exc=7.0, good=2.0, fair=4.0
        debt_to_earnings bounds: min=0.0, max=10.0, sep=2.0
        Step 1: good=max(2.0, 7.0+2.0)=9.0, fair=max(4.0, 9.0+2.0)=11.0
        Step 2: excess_high=11.0-10.0=1.0 -> slide down: exc=6.0, good=8.0, fair=10.0
        """
        config = {
            'debt_to_earnings_excellent': 7.0,
            'debt_to_earnings_good': 2.0,
            'debt_to_earnings_fair': 4.0,
        }
        result = optimizer._enforce_threshold_constraints(config, 'buffett')

        assert result['debt_to_earnings_excellent'] < result['debt_to_earnings_good'] < result['debt_to_earnings_fair']
        assert abs(result['debt_to_earnings_excellent'] - 6.0) < 0.01
        assert abs(result['debt_to_earnings_good'] - 8.0) < 0.01
        assert abs(result['debt_to_earnings_fair'] - 10.0) < 0.01

    def test_buffett_roe_higher_is_better(self, optimizer):
        """ROE: descending order enforced (excellent > good > fair).
        Input: exc=10.0, good=20.0, fair=15.0
        ROE bounds: min=5.0, max=40.0, sep=5.0
        Step 1: good=min(20.0, 10.0-5.0)=5.0, fair=min(15.0, 5.0-5.0)=0.0
        Step 2: excess_low=5.0-0.0=5.0 -> slide up: exc=15.0, good=10.0, fair=5.0
        """
        config = {
            'roe_excellent': 10.0,
            'roe_good': 20.0,
            'roe_fair': 15.0,
        }
        result = optimizer._enforce_threshold_constraints(config, 'buffett')

        assert result['roe_excellent'] > result['roe_good'] > result['roe_fair']
        assert abs(result['roe_excellent'] - 15.0) < 0.01
        assert abs(result['roe_good'] - 10.0) < 0.01
        assert abs(result['roe_fair'] - 5.0) < 0.01

    def test_buffett_gross_margin_higher_is_better(self, optimizer):
        """Gross margin: descending order enforced (excellent > good > fair).
        Input: exc=30.0, good=50.0, fair=40.0
        gross_margin bounds: min=10.0, max=80.0, sep=10.0
        Step 1: good=min(50.0, 30.0-10.0)=20.0, fair=min(40.0, 20.0-10.0)=10.0
        Step 2: excess_low=10.0-10.0=0.0 -> no slide
        """
        config = {
            'gross_margin_excellent': 30.0,
            'gross_margin_good': 50.0,
            'gross_margin_fair': 40.0,
        }
        result = optimizer._enforce_threshold_constraints(config, 'buffett')

        assert result['gross_margin_excellent'] > result['gross_margin_good'] > result['gross_margin_fair']
        assert abs(result['gross_margin_excellent'] - 30.0) < 0.01
        assert abs(result['gross_margin_good'] - 20.0) < 0.01
        assert abs(result['gross_margin_fair'] - 10.0) < 0.01

    def test_correctly_ordered_config_unchanged(self, optimizer):
        """If thresholds are already correctly ordered, don't change them"""
        lynch_config = {
            'peg_excellent': 1.0,
            'peg_good': 1.5,
            'peg_fair': 2.0,
            'debt_excellent': 0.5,
            'debt_good': 1.0,
            'debt_moderate': 2.0,
            'inst_own_min': 0.20,
            'inst_own_max': 0.60,
            'revenue_growth_excellent': 15.0,
            'revenue_growth_good': 10.0,
            'revenue_growth_fair': 5.0,
        }
        result = optimizer._enforce_threshold_constraints(lynch_config, 'lynch')

        for key in lynch_config:
            assert result[key] == lynch_config[key], f"{key} changed unexpectedly"

    def test_missing_thresholds_handled_gracefully(self, optimizer):
        """Missing threshold keys should not cause errors (inst_own required for lynch)"""
        config = {
            'peg_excellent': 1.0,
            'inst_own_min': 0.20,
            'inst_own_max': 0.60,
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        # Should not raise, should leave partial config unchanged
        assert result['peg_excellent'] == 1.0
        assert result['inst_own_min'] == 0.20
        assert result['inst_own_max'] == 0.60


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
