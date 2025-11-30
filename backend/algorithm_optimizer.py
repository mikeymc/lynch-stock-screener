import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging
from scipy import stats

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
            method: 'gradient_descent' or 'grid_search'
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
        current_config = self._get_current_weights()
        initial_correlation = self._calculate_correlation_with_config(results, current_config)
        
        logger.info(f"Initial correlation: {initial_correlation:.4f}")
        
        if method == 'gradient_descent':
            best_config, history = self._gradient_descent_optimize(
                results, current_config, max_iterations, learning_rate
            )
        elif method == 'grid_search':
            best_config, history = self._grid_search_optimize(results)
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
    
    def _get_current_weights(self) -> Dict[str, float]:
        """Get current algorithm weights from settings"""
        return {
            'weight_peg': self.db.get_setting('weight_peg', 0.50),
            'weight_consistency': self.db.get_setting('weight_consistency', 0.25),
            'weight_debt': self.db.get_setting('weight_debt', 0.15),
            'weight_ownership': self.db.get_setting('weight_ownership', 0.10)
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
        Recalculate overall score using new weights
        
        Uses stored component scores (peg_score, debt_score, etc.) from backtest results
        """
        peg_score = result.get('peg_score', 0) or 0
        consistency_score = result.get('consistency_score', 50) or 50
        debt_score = result.get('debt_score', 0) or 0
        ownership_score = result.get('ownership_score', 0) or 0
        
        # Weighted score calculation
        overall_score = (
            config['weight_peg'] * peg_score +
            config['weight_consistency'] * consistency_score +
            config['weight_debt'] * debt_score +
            config['weight_ownership'] * ownership_score
        )
        
        return overall_score
    
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
