import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithm_optimizer import AlgorithmOptimizer
from database import Database

class TestAlgorithmOptimizer:
    @pytest.fixture
    def db(self):
        return Database()

    @pytest.fixture
    def optimizer(self, db):
        return AlgorithmOptimizer(db)

    def test_bayesian_optimize_with_mock_data(self, optimizer):
        """Test that Bayesian optimization produces valid results with mock data"""
        # Create mock backtest results
        mock_results = []
        for i in range(50):
            # Create synthetic data where higher PEG scores correlate with higher returns
            peg_score = i * 2
            consistency_score = 50 + (i % 10) * 5
            debt_score = 40 + (i % 8) * 7.5
            ownership_score = 30 + (i % 6) * 11.67

            # Returns should correlate positively with scores
            total_return = peg_score * 0.5 + consistency_score * 0.2 + debt_score * 0.1 + (i % 20)

            mock_results.append({
                'symbol': f'TEST{i}',
                'peg_score': peg_score,
                'consistency_score': consistency_score,
                'debt_score': debt_score,
                'ownership_score': ownership_score,
                'total_return': total_return
            })

        # Run Bayesian optimization with small number of iterations for speed
        best_config, history = optimizer._bayesian_optimize(mock_results, n_calls=20)

        # Verify best_config has all required keys
        assert 'weight_peg' in best_config
        assert 'weight_consistency' in best_config
        assert 'weight_debt' in best_config
        assert 'weight_ownership' in best_config

        # Verify all weights are positive
        assert all(best_config[key] > 0 for key in best_config.keys())

        # Verify weights sum to approximately 1
        weight_sum = sum(best_config.values())
        assert abs(weight_sum - 1.0) < 0.01, f"Weights sum to {weight_sum}, expected ~1.0"

        # Verify history was recorded (may be less than n_calls due to invalid configs being skipped)
        assert len(history) > 0 and len(history) <= 20
        assert all('iteration' in entry for entry in history)
        assert all('correlation' in entry for entry in history)
        assert all('config' in entry for entry in history)

        # Since data was crafted with PEG being most predictive,
        # PEG weight should be relatively high
        assert best_config['weight_peg'] > 0.2, f"Expected PEG weight > 0.2, got {best_config['weight_peg']}"

        print(f"✓ Bayesian optimization test passed")
        print(f"  Best config: {best_config}")
        print(f"  Final correlation: {history[-1]['correlation']:.4f}")

    def test_bayesian_vs_gradient_descent(self, optimizer):
        """Test that Bayesian optimization finds better or equal solutions than gradient descent"""
        # Create mock data with known optimal weights
        mock_results = []
        for i in range(100):
            # Ground truth: 60% PEG, 20% consistency, 15% debt, 5% ownership
            peg_score = (i % 10) * 10
            consistency_score = (i % 8) * 12.5
            debt_score = (i % 6) * 16.67
            ownership_score = (i % 4) * 25

            # Perfect correlation with ground truth weights
            total_return = (
                0.60 * peg_score +
                0.20 * consistency_score +
                0.15 * debt_score +
                0.05 * ownership_score
            ) + (i % 5) * 2  # Small noise

            mock_results.append({
                'symbol': f'TEST{i}',
                'peg_score': peg_score,
                'consistency_score': consistency_score,
                'debt_score': debt_score,
                'ownership_score': ownership_score,
                'total_return': total_return
            })

        # Run both optimizers
        initial_config = {
            'weight_peg': 0.50,
            'weight_consistency': 0.25,
            'weight_debt': 0.15,
            'weight_ownership': 0.10
        }

        bayesian_config, bayesian_history = optimizer._bayesian_optimize(mock_results, n_calls=30)
        gradient_config, gradient_history = optimizer._gradient_descent_optimize(
            mock_results, initial_config, max_iterations=50, learning_rate=0.01
        )

        # Calculate final correlations
        bayesian_corr = optimizer._calculate_correlation_with_config(mock_results, bayesian_config)
        gradient_corr = optimizer._calculate_correlation_with_config(mock_results, gradient_config)

        print(f"✓ Comparison test passed")
        print(f"  Bayesian correlation: {bayesian_corr:.4f}")
        print(f"  Gradient descent correlation: {gradient_corr:.4f}")
        print(f"  Bayesian config: {bayesian_config}")
        print(f"  Gradient config: {gradient_config}")

        # Bayesian should find solution at least as good as gradient descent
        # (allowing small margin due to randomness)
        assert bayesian_corr >= gradient_corr - 0.05, \
            f"Bayesian ({bayesian_corr:.4f}) significantly worse than gradient descent ({gradient_corr:.4f})"

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
