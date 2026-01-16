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

    def test_bayesian_vs_gradient_descent(self, optimizer):
        """Test that Bayesian optimization finds better or equal solutions than gradient descent"""
        # Create mock data with known optimal weights and raw metrics
        mock_results = []
        for i in range(100):
            # Ground truth: 60% PEG, 20% consistency, 15% debt, 5% ownership
            peg_ratio = 0.5 + (i % 10) * 0.2
            revenue_cagr = 5.0 + (i % 8) * 2
            earnings_cagr = 6.0 + (i % 8) * 2
            debt_to_equity = 0.3 + (i % 6) * 0.3
            institutional_ownership = 0.2 + (i % 4) * 0.15

            # Simple linear relationship for testing
            total_return = (
                -10 * peg_ratio +  # Lower PEG is better
                2 * revenue_cagr +
                2 * earnings_cagr +
                -5 * debt_to_equity +  # Lower debt is better
                20 * institutional_ownership
            ) + (i % 5) * 2  # Small noise

            mock_results.append({
                'symbol': f'TEST{i}',
                'peg_ratio': peg_ratio,
                'revenue_cagr': revenue_cagr,
                'earnings_cagr': earnings_cagr,
                'debt_to_equity': debt_to_equity,
                'institutional_ownership': institutional_ownership,
                'total_return': total_return,
                'historical_data': {}
            })

        # Run both optimizers
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

        bayesian_config, bayesian_history = optimizer._bayesian_optimize(
            mock_results,
            'lynch',
            initial_config,
            weight_keys,
            threshold_keys,
            max_iterations=50
        )
        gradient_config, gradient_history = optimizer._gradient_descent_optimize(
            mock_results,
            initial_config,
            'lynch',
            weight_keys,
            max_iterations=50,
            learning_rate=0.01
        )

        # Calculate final correlations
        bayesian_corr = optimizer._calculate_correlation_with_config(mock_results, bayesian_config, 'lynch')
        gradient_corr = optimizer._calculate_correlation_with_config(mock_results, gradient_config, 'lynch')

        print(f"✓ Comparison test passed")
        print(f"  Bayesian correlation: {bayesian_corr:.4f}")
        print(f"  Gradient descent correlation: {gradient_corr:.4f}")
        print(f"  Bayesian config: {bayesian_config}")
        print(f"  Gradient config: {gradient_config}")

        # Bayesian should find solution at least as good as gradient descent
        # (allowing small margin due to randomness)
        assert bayesian_corr >= gradient_corr - 0.05, \
            f"Bayesian ({bayesian_corr:.4f}) significantly worse than gradient descent ({gradient_corr:.4f})"

class TestThresholdConstraints:
    """Tests for threshold ordering constraints in trial generation"""

    @pytest.fixture
    def optimizer(self):
        import unittest.mock as mock
        db_mock = mock.MagicMock()
        return AlgorithmOptimizer(db_mock)

    def test_lynch_peg_thresholds_lower_is_better(self, optimizer):
        """PEG thresholds must be: excellent < good < fair"""
        config = {
            'peg_excellent': 2.5,  # Wrong: should be lowest
            'peg_good': 1.0,       # Wrong: should be middle
            'peg_fair': 1.5,       # Wrong: should be highest
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['peg_excellent'] < result['peg_good'] < result['peg_fair']
        assert result['peg_excellent'] == 1.0
        assert result['peg_good'] == 1.5
        assert result['peg_fair'] == 2.5

    def test_lynch_debt_equity_thresholds_lower_is_better(self, optimizer):
        """Debt/Equity thresholds must be: excellent < good < moderate"""
        config = {
            'debt_excellent': 3.0,
            'debt_good': 0.5,
            'debt_moderate': 1.5,
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['debt_excellent'] < result['debt_good'] < result['debt_moderate']
        assert result['debt_excellent'] == 0.5
        assert result['debt_good'] == 1.5
        assert result['debt_moderate'] == 3.0

    def test_lynch_institutional_ownership_min_less_than_max(self, optimizer):
        """Institutional ownership min must be less than max"""
        config = {
            'inst_own_min': 0.75,  # Wrong: should be lower
            'inst_own_max': 0.25,  # Wrong: should be higher
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['inst_own_min'] < result['inst_own_max']
        assert result['inst_own_min'] == 0.25
        assert result['inst_own_max'] == 0.75

    def test_lynch_revenue_growth_higher_is_better(self, optimizer):
        """Revenue growth thresholds must be: excellent > good > fair"""
        config = {
            'revenue_growth_excellent': 5.0,   # Wrong: should be highest
            'revenue_growth_good': 20.0,       # Wrong: should be middle
            'revenue_growth_fair': 10.0,       # Wrong: should be lowest
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['revenue_growth_excellent'] > result['revenue_growth_good'] > result['revenue_growth_fair']
        assert result['revenue_growth_excellent'] == 20.0
        assert result['revenue_growth_good'] == 10.0
        assert result['revenue_growth_fair'] == 5.0

    def test_lynch_income_growth_higher_is_better(self, optimizer):
        """Income growth thresholds must be: excellent > good > fair"""
        config = {
            'income_growth_excellent': 8.0,
            'income_growth_good': 25.0,
            'income_growth_fair': 12.0,
        }
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        assert result['income_growth_excellent'] > result['income_growth_good'] > result['income_growth_fair']
        assert result['income_growth_excellent'] == 25.0
        assert result['income_growth_good'] == 12.0
        assert result['income_growth_fair'] == 8.0

    def test_buffett_debt_to_earnings_lower_is_better(self, optimizer):
        """Debt/Earnings thresholds must be: excellent < good < fair"""
        config = {
            'debt_to_earnings_excellent': 7.0,
            'debt_to_earnings_good': 2.0,
            'debt_to_earnings_fair': 4.0,
        }
        result = optimizer._enforce_threshold_constraints(config, 'buffett')

        assert result['debt_to_earnings_excellent'] < result['debt_to_earnings_good'] < result['debt_to_earnings_fair']
        assert result['debt_to_earnings_excellent'] == 2.0
        assert result['debt_to_earnings_good'] == 4.0
        assert result['debt_to_earnings_fair'] == 7.0

    def test_buffett_roe_higher_is_better(self, optimizer):
        """ROE thresholds must be: excellent > good > fair"""
        config = {
            'roe_excellent': 10.0,  # Wrong: should be highest
            'roe_good': 20.0,       # Wrong: should be middle
            'roe_fair': 15.0,       # Wrong: should be lowest
        }
        result = optimizer._enforce_threshold_constraints(config, 'buffett')

        assert result['roe_excellent'] > result['roe_good'] > result['roe_fair']
        assert result['roe_excellent'] == 20.0
        assert result['roe_good'] == 15.0
        assert result['roe_fair'] == 10.0

    def test_buffett_gross_margin_higher_is_better(self, optimizer):
        """Gross margin thresholds must be: excellent > good > fair"""
        config = {
            'gross_margin_excellent': 30.0,
            'gross_margin_good': 50.0,
            'gross_margin_fair': 40.0,
        }
        result = optimizer._enforce_threshold_constraints(config, 'buffett')

        assert result['gross_margin_excellent'] > result['gross_margin_good'] > result['gross_margin_fair']
        assert result['gross_margin_excellent'] == 50.0
        assert result['gross_margin_good'] == 40.0
        assert result['gross_margin_fair'] == 30.0

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
        """Missing threshold keys should not cause errors"""
        config = {'peg_excellent': 1.0}  # Only one threshold
        result = optimizer._enforce_threshold_constraints(config, 'lynch')

        # Should not raise, should leave partial config unchanged
        assert result['peg_excellent'] == 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
