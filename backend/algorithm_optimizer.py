import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging
from scipy import stats
from skopt import gp_minimize
from skopt.space import Real
from skopt.utils import use_named_args

from database import Database
from correlation_analyzer import CorrelationAnalyzer

logger = logging.getLogger(__name__)

class AlgorithmOptimizer:
    def __init__(self, db: Database):
        self.db = db
        self.analyzer = CorrelationAnalyzer(db)
        
    def optimize(self, years_back: int, method: str = 'gradient_descent',
                 max_iterations: int = 100, learning_rate: float = 0.01) -> Dict[str, Any]:
        """
        Optimize algorithm weights to maximize correlation with returns

        Args:
            years_back: Which backtest timeframe to optimize for
            method: 'gradient_descent', 'grid_search', or 'bayesian'
            max_iterations: Maximum optimization iterations
            learning_rate: Step size for gradient descent

        Returns:
            Dict with best configuration and optimization history
        """
        # Get backtest results
        results = self.db.get_backtest_results(years_back=years_back)
        
        if len(results) < 10:
            return {'error': f'Insufficient data: only {len(results)} results found'}
        
        logger.info(f"Starting optimization with {len(results)} backtest results")
        
        # Get current configuration
        current_config = self._get_current_config()
        initial_correlation = self._calculate_correlation_with_config(results, current_config)
        
        logger.info(f"Initial correlation: {initial_correlation:.4f}")
        
        if method == 'gradient_descent':
            best_config, history = self._gradient_descent_optimize(
                results, current_config, max_iterations, learning_rate
            )
        elif method == 'grid_search':
            best_config, history = self._grid_search_optimize(results)
        elif method == 'bayesian':
            best_config, history = self._bayesian_optimize(results, max_iterations)
        else:
            return {'error': f'Unknown optimization method: {method}'}
        
        # Calculate final correlation
        final_correlation = self._calculate_correlation_with_config(results, best_config)
        improvement = final_correlation - initial_correlation
        
        logger.info(f"Optimization complete. Final correlation: {final_correlation:.4f}, Improvement: {improvement:.4f}")
        
        # Save configuration to database
        config_data = {
            'name': f'Optimized ({years_back}yr)',
            'weight_peg': best_config['weight_peg'],
            'weight_consistency': best_config['weight_consistency'],
            'weight_debt': best_config['weight_debt'],
            'weight_ownership': best_config['weight_ownership'],
            f'correlation_{years_back}yr': final_correlation
        }
        config_id = self.db.save_algorithm_config(config_data)
        
        # Save optimization run
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO optimization_runs
            (years_back, iterations, initial_correlation, final_correlation, improvement, best_config_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (years_back, len(history), initial_correlation, final_correlation, improvement, config_id))
        conn.commit()
        self.db.return_connection(conn)
        
        return {
            'initial_config': current_config,
            'best_config': best_config,
            'initial_correlation': initial_correlation,
            'final_correlation': final_correlation,
            'improvement': improvement,
            'iterations': len(history),
            'history': history[-10:],  # Last 10 iterations for display
            'config_id': config_id
        }
    
    def _get_current_config(self) -> Dict[str, float]:
        """Get current algorithm weights and thresholds from settings"""
        return {
            # Weights
            'weight_peg': self.db.get_setting('weight_peg', 0.50),
            'weight_consistency': self.db.get_setting('weight_consistency', 0.25),
            'weight_debt': self.db.get_setting('weight_debt', 0.15),
            'weight_ownership': self.db.get_setting('weight_ownership', 0.10),
            
            # PEG thresholds
            'peg_excellent': self.db.get_setting('peg_excellent', 1.0),
            'peg_good': self.db.get_setting('peg_good', 1.5),
            'peg_fair': self.db.get_setting('peg_fair', 2.0),
            
            # Debt thresholds
            'debt_excellent': self.db.get_setting('debt_excellent', 0.5),
            'debt_good': self.db.get_setting('debt_good', 1.0),
            'debt_moderate': self.db.get_setting('debt_moderate', 2.0),
            
            # Institutional ownership thresholds
            'inst_own_min': self.db.get_setting('inst_own_min', 0.20),
            'inst_own_max': self.db.get_setting('inst_own_max', 0.60),
            
            # Revenue growth thresholds
            'revenue_growth_excellent': self.db.get_setting('revenue_growth_excellent', 15.0),
            'revenue_growth_good': self.db.get_setting('revenue_growth_good', 10.0),
            'revenue_growth_fair': self.db.get_setting('revenue_growth_fair', 5.0),
            
            # Income growth thresholds
            'income_growth_excellent': self.db.get_setting('income_growth_excellent', 15.0),
            'income_growth_good': self.db.get_setting('income_growth_good', 10.0),
            'income_growth_fair': self.db.get_setting('income_growth_fair', 5.0),
        }
    
    def _calculate_correlation_with_config(self, results: List[Dict[str, Any]], 
                                          config: Dict[str, float]) -> float:
        """
        Calculate correlation between returns and scores recalculated with given weights
        """
        scores = []
        returns = []
        
        for result in results:
            if result.get('total_return') is None:
                continue
            
            # Recalculate score with new weights
            score = self._recalculate_score(result, config)
            if score is not None:
                scores.append(score)
                returns.append(result['total_return'])
        
        if len(scores) < 2:
            return 0.0
        
        try:
            correlation, _ = stats.pearsonr(scores, returns)
            return float(correlation) if not np.isnan(correlation) else 0.0
        except:
            return 0.0
    
    def _recalculate_score(self, result: Dict[str, Any], 
                          config: Dict[str, float]) -> Optional[float]:
        """
        Recalculate overall score using new weights AND thresholds
        
        Recalculates component scores from raw metrics using threshold overrides
        """
        # Extract raw metrics from backtest result
        peg_ratio = result.get('peg_ratio')
        debt_to_equity = result.get('debt_to_equity')
        institutional_ownership = result.get('institutional_ownership')
        revenue_cagr = result.get('revenue_cagr')
        earnings_cagr = result.get('earnings_cagr')
        consistency_score = result.get('consistency_score', 50) or 50  # This doesn't depend on thresholds
        
        # Recalculate PEG score with new thresholds
        peg_score = self._calculate_peg_score_with_thresholds(
            peg_ratio,
            config.get('peg_excellent', 1.0),
            config.get('peg_good', 1.5),
            config.get('peg_fair', 2.0)
        )
        
        # Recalculate debt score with new thresholds
        debt_score = self._calculate_debt_score_with_thresholds(
            debt_to_equity,
            config.get('debt_excellent', 0.5),
            config.get('debt_good', 1.0),
            config.get('debt_moderate', 2.0)
        )
        
        # Recalculate institutional ownership score with new thresholds
        ownership_score = self._calculate_ownership_score_with_thresholds(
            institutional_ownership,
            config.get('inst_own_min', 0.20),
            config.get('inst_own_max', 0.60)
        )
        
        # Recalculate revenue growth score with new thresholds
        revenue_growth_score = self._calculate_growth_score_with_thresholds(
            revenue_cagr,
            config.get('revenue_growth_excellent', 15.0),
            config.get('revenue_growth_good', 10.0),
            config.get('revenue_growth_fair', 5.0)
        )
        
        # Recalculate income growth score with new thresholds
        income_growth_score = self._calculate_growth_score_with_thresholds(
            earnings_cagr,
            config.get('income_growth_excellent', 15.0),
            config.get('income_growth_good', 10.0),
            config.get('income_growth_fair', 5.0)
        )
        
        # Weighted score calculation (currently only uses the original 4 components)
        # Note: growth scores are calculated but not yet weighted in the overall score
        # This can be added later if desired
        overall_score = (
            config['weight_peg'] * peg_score +
            config['weight_consistency'] * consistency_score +
            config['weight_debt'] * debt_score +
            config['weight_ownership'] * ownership_score
        )
        
        return round(overall_score, 1)
    
    def _gradient_descent_optimize(self, results: List[Dict[str, Any]], 
                                   initial_config: Dict[str, float],
                                   max_iterations: int, learning_rate: float) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        """
        Gradient descent optimization
        
        Iteratively adjusts weights in direction that improves correlation
        """
        config = initial_config.copy()
        history = []
        
        best_config = config.copy()
        best_correlation = self._calculate_correlation_with_config(results, config)
        
        for iteration in range(max_iterations):
            # Calculate gradients by finite differences
            gradients = {}
            epsilon = 0.01
            
            for key in ['weight_peg', 'weight_consistency', 'weight_debt', 'weight_ownership']:
                # Try increasing this weight
                test_config = config.copy()
                test_config[key] += epsilon
                test_config = self._normalize_weights(test_config)
                
                correlation_plus = self._calculate_correlation_with_config(results, test_config)
                
                # Try decreasing this weight
                test_config = config.copy()
                test_config[key] -= epsilon
                test_config = self._normalize_weights(test_config)
                
                correlation_minus = self._calculate_correlation_with_config(results, test_config)
                
                # Gradient is (f(x+ε) - f(x-ε)) / (2ε)
                gradients[key] = (correlation_plus - correlation_minus) / (2 * epsilon)
            
            # Update weights in direction of gradient
            for key in config.keys():
                config[key] += learning_rate * gradients[key]
            
            # Normalize to ensure weights sum to 1
            config = self._normalize_weights(config)
            
            # Calculate new correlation
            current_correlation = self._calculate_correlation_with_config(results, config)
            
            # Track history
            history.append({
                'iteration': iteration,
                'correlation': current_correlation,
                'config': config.copy()
            })
            
            # Update best if improved
            if current_correlation > best_correlation:
                best_correlation = current_correlation
                best_config = config.copy()
                logger.info(f"Iteration {iteration}: New best correlation {current_correlation:.4f}")
            
            # Early stopping if no improvement
            if iteration > 10 and current_correlation < best_correlation - 0.01:
                logger.info(f"Early stopping at iteration {iteration}")
                break
        
        return best_config, history
    
    def _grid_search_optimize(self, results: List[Dict[str, Any]]) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        """
        Grid search optimization
        
        Tests many weight combinations to find the best
        """
        best_config = None
        best_correlation = -1
        history = []
        
        # Search grid (coarse)
        peg_weights = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        consistency_weights = [0.1, 0.2, 0.3, 0.4]
        
        iteration = 0
        for peg_w in peg_weights:
            for cons_w in consistency_weights:
                # Remaining weight split between debt and ownership
                remaining = 1.0 - peg_w - cons_w
                if remaining < 0:
                    continue
                
                debt_w = remaining * 0.6  # 60% of remaining to debt
                own_w = remaining * 0.4   # 40% to ownership
                
                config = {
                    'weight_peg': peg_w,
                    'weight_consistency': cons_w,
                    'weight_debt': debt_w,
                    'weight_ownership': own_w
                }
                
                correlation = self._calculate_correlation_with_config(results, config)
                
                history.append({
                    'iteration': iteration,
                    'correlation': correlation,
                    'config': config.copy()
                })
                
                if correlation > best_correlation:
                    best_correlation = correlation
                    best_config = config.copy()
                    logger.info(f"Grid iteration {iteration}: New best {correlation:.4f}")
                
                iteration += 1
        
        return best_config, history

    def _bayesian_optimize(self, results: List[Dict[str, Any]],
                          n_calls: int = 200) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        """
        Bayesian optimization using Gaussian processes

        Intelligently explores weight and threshold space to find optimal configuration
        More efficient than grid search, better at avoiding local optima than gradient descent
        """
        history = []

        # Define search space for weights and thresholds
        # Weights: 3 weights (4th is determined by constraint that sum = 1)
        # Thresholds: All tunable threshold parameters
        space = [
            # Weights
            Real(0.1, 0.8, name='weight_peg'),
            Real(0.05, 0.5, name='weight_consistency'),
            Real(0.05, 0.4, name='weight_debt'),
            
            # PEG thresholds
            Real(0.5, 1.5, name='peg_excellent'),
            Real(1.0, 2.5, name='peg_good'),
            Real(1.5, 3.0, name='peg_fair'),
            
            # Debt thresholds
            Real(0.2, 1.0, name='debt_excellent'),
            Real(0.5, 1.5, name='debt_good'),
            Real(1.0, 3.0, name='debt_moderate'),
            
            # Institutional ownership thresholds
            Real(0.0, 0.60, name='inst_own_min'),
            Real(0.50, 1.10, name='inst_own_max'),
            
            # Revenue growth thresholds
            Real(10.0, 25.0, name='revenue_growth_excellent'),
            Real(5.0, 20.0, name='revenue_growth_good'),
            Real(0.0, 15.0, name='revenue_growth_fair'),
            
            # Income growth thresholds
            Real(10.0, 25.0, name='income_growth_excellent'),
            Real(5.0, 20.0, name='income_growth_good'),
            Real(0.0, 15.0, name='income_growth_fair'),
        ]

        # Objective function to minimize (we negate correlation since we want to maximize it)
        @use_named_args(space)
        def objective(weight_peg, weight_consistency, weight_debt,
                     peg_excellent, peg_good, peg_fair,
                     debt_excellent, debt_good, debt_moderate,
                     inst_own_min, inst_own_max,
                     revenue_growth_excellent, revenue_growth_good, revenue_growth_fair,
                     income_growth_excellent, income_growth_good, income_growth_fair):
            
            # Calculate ownership weight to ensure sum = 1
            weight_ownership = 1.0 - (weight_peg + weight_consistency + weight_debt)

            # Validate weight constraints
            if weight_ownership < 0.01 or weight_ownership > 0.5:
                return 1.0  # Return high value (bad) for invalid configs
            
            # Validate threshold ordering constraints
            if peg_excellent >= peg_good or peg_good >= peg_fair:
                return 1.0  # PEG thresholds must be in ascending order
            
            if debt_excellent >= debt_good or debt_good >= debt_moderate:
                return 1.0  # Debt thresholds must be in ascending order
            
            if inst_own_min >= inst_own_max:
                return 1.0  # Inst own min must be less than max
            
            if revenue_growth_excellent <= revenue_growth_good or revenue_growth_good <= revenue_growth_fair:
                return 1.0  # Revenue growth thresholds must be in descending order
            
            if income_growth_excellent <= income_growth_good or income_growth_good <= income_growth_fair:
                return 1.0  # Income growth thresholds must be in descending order

            config = {
                # Weights
                'weight_peg': weight_peg,
                'weight_consistency': weight_consistency,
                'weight_debt': weight_debt,
                'weight_ownership': weight_ownership,
                
                # PEG thresholds
                'peg_excellent': peg_excellent,
                'peg_good': peg_good,
                'peg_fair': peg_fair,
                
                # Debt thresholds
                'debt_excellent': debt_excellent,
                'debt_good': debt_good,
                'debt_moderate': debt_moderate,
                
                # Institutional ownership thresholds
                'inst_own_min': inst_own_min,
                'inst_own_max': inst_own_max,
                
                # Revenue growth thresholds
                'revenue_growth_excellent': revenue_growth_excellent,
                'revenue_growth_good': revenue_growth_good,
                'revenue_growth_fair': revenue_growth_fair,
                
                # Income growth thresholds
                'income_growth_excellent': income_growth_excellent,
                'income_growth_good': income_growth_good,
                'income_growth_fair': income_growth_fair,
            }

            correlation = self._calculate_correlation_with_config(results, config)

            # Track history
            history.append({
                'iteration': len(history),
                'correlation': correlation,
                'config': config.copy()
            })

            # Log progress
            if correlation > 0:
                logger.info(f"Bayesian iteration {len(history)}: correlation {correlation:.4f}")

            # Return negative correlation (we're minimizing, but want to maximize correlation)
            return -correlation

        # Run Bayesian optimization
        logger.info(f"Starting Bayesian optimization with {n_calls} evaluations")
        result = gp_minimize(
            objective,
            space,
            n_calls=n_calls,
            random_state=42,
            n_initial_points=20,  # Increased from 10 for larger search space
            acq_func='EI',  # Expected Improvement acquisition function
            verbose=False
        )

        # Extract best configuration from all parameters
        (best_weight_peg, best_weight_consistency, best_weight_debt,
         best_peg_excellent, best_peg_good, best_peg_fair,
         best_debt_excellent, best_debt_good, best_debt_moderate,
         best_inst_own_min, best_inst_own_max,
         best_revenue_growth_excellent, best_revenue_growth_good, best_revenue_growth_fair,
         best_income_growth_excellent, best_income_growth_good, best_income_growth_fair) = result.x
        
        best_weight_ownership = 1.0 - (best_weight_peg + best_weight_consistency + best_weight_debt)

        best_config = {
            # Weights
            'weight_peg': best_weight_peg,
            'weight_consistency': best_weight_consistency,
            'weight_debt': best_weight_debt,
            'weight_ownership': best_weight_ownership,
            
            # PEG thresholds
            'peg_excellent': best_peg_excellent,
            'peg_good': best_peg_good,
            'peg_fair': best_peg_fair,
            
            # Debt thresholds
            'debt_excellent': best_debt_excellent,
            'debt_good': best_debt_good,
            'debt_moderate': best_debt_moderate,
            
            # Institutional ownership thresholds
            'inst_own_min': best_inst_own_min,
            'inst_own_max': best_inst_own_max,
            
            # Revenue growth thresholds
            'revenue_growth_excellent': best_revenue_growth_excellent,
            'revenue_growth_good': best_revenue_growth_good,
            'revenue_growth_fair': best_revenue_growth_fair,
            
            # Income growth thresholds
            'income_growth_excellent': best_income_growth_excellent,
            'income_growth_good': best_income_growth_good,
            'income_growth_fair': best_income_growth_fair,
        }

        best_correlation = -result.fun  # Negate since we minimized negative correlation
        logger.info(f"Bayesian optimization complete. Best correlation: {best_correlation:.4f}")

        return best_config, history


    def _normalize_weights(self, config: Dict[str, float]) -> Dict[str, float]:
        """Ensure all weights are positive and sum to 1"""
        # Make all weights positive
        for key in config.keys():
            config[key] = max(0.01, config[key])  # Minimum 1%
        
        # Normalize to sum to 1
        total = sum(config.values())
        for key in config.keys():
            config[key] /= total
        
        return config

    def _calculate_peg_score_with_thresholds(self, value: float, excellent: float, good: float, fair: float) -> float:
        """Calculate PEG score using custom thresholds"""
        if value is None:
            return 0.0
        if value <= excellent:
            return 100.0
        elif value <= good:
            range_size = good - excellent
            position = (good - value) / range_size
            return 75.0 + (25.0 * position)
        elif value <= fair:
            range_size = fair - good
            position = (fair - value) / range_size
            return 25.0 + (50.0 * position)
        else:
            max_poor = 4.0
            if value >= max_poor:
                return 0.0
            range_size = max_poor - fair
            position = (max_poor - value) / range_size
            return 25.0 * position
    
    def _calculate_debt_score_with_thresholds(self, value: float, excellent: float, good: float, moderate: float) -> float:
        """Calculate debt score using custom thresholds"""
        if value is None:
            return 0.0
        if value <= excellent:
            return 100.0
        elif value <= good:
            range_size = good - excellent
            position = (good - value) / range_size
            return 75.0 + (25.0 * position)
        elif value <= moderate:
            range_size = moderate - good
            position = (moderate - value) / range_size
            return 25.0 + (50.0 * position)
        else:
            max_high = 5.0
            if value >= max_high:
                return 0.0
            range_size = max_high - moderate
            position = (max_high - value) / range_size
            return 25.0 * position
    
    def _calculate_ownership_score_with_thresholds(self, value: float, min_threshold: float, max_threshold: float) -> float:
        """Calculate institutional ownership score using custom thresholds"""
        if value is None:
            return 0.0
        
        ideal_center = (min_threshold + max_threshold) / 2
        
        if min_threshold <= value <= max_threshold:
            distance_from_center = abs(value - ideal_center)
            max_distance = ideal_center - min_threshold
            position = 1.0 - (distance_from_center / max_distance)
            return 75.0 + (25.0 * position)
        elif value < min_threshold:
            if value <= 0:
                return 0.0
            position = value / min_threshold
            return 75.0 * position
        else:
            if value >= 1.0:
                return 0.0
            range_size = 1.0 - max_threshold
            position = (1.0 - value) / range_size
            return 75.0 * position
    
    def _calculate_growth_score_with_thresholds(self, value: float, excellent: float, good: float, fair: float) -> float:
        """Calculate growth score using custom thresholds"""
        if value is None:
            return 50.0
        
        if value < 0:
            return 0.0
        
        if value >= excellent:
            return 100.0
        elif value >= good:
            range_size = excellent - good
            position = (value - good) / range_size
            return 75.0 + (25.0 * position)
        elif value >= fair:
            range_size = good - fair
            position = (value - fair) / range_size
            return 25.0 + (50.0 * position)
        else:
            if value <= 0:
                return 0.0
            position = value / fair
            return 25.0 * position
