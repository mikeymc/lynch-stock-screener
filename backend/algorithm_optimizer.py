import numpy as np
from typing import Dict, Any, List, Tuple, Optional, Callable
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
        
    def optimize(self, years_back: int, character_id: str = 'lynch', user_id: Optional[int] = None, 
                 method: str = 'gradient_descent', max_iterations: int = 100, learning_rate: float = 0.01,
                 progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """
        Optimize algorithm weights to maximize correlation with returns
        
        Args:
            years_back: Which backtest timeframe to optimize for
            character_id: Character to optimize ('lynch', 'buffett', etc.)
            user_id: User performing the optimization (for config lookup)
            method: 'gradient_descent', 'grid_search', or 'bayesian'
        """
        # Get backtest results
        results = self.db.get_backtest_results(years_back=years_back)
        
        if len(results) < 10:
            return {'error': f'Insufficient data: only {len(results)} results found'}
        
        logger.info(f"Starting optimization for {character_id} (User {user_id}) with {len(results)} results")
        
        # Get current configuration
        current_config = self._get_current_config(user_id, character_id)
        
        # Determine tunable parameters based on character
        weight_keys = self._get_weight_keys(character_id)
        threshold_keys = self._get_threshold_keys(character_id)
        
        initial_correlation = self._calculate_correlation_with_config(results, current_config, character_id)
        logger.info(f"Initial correlation: {initial_correlation:.4f}")
        
        if method == 'gradient_descent':
            best_config, history = self._gradient_descent_optimize(
                results, current_config, character_id, weight_keys, max_iterations, learning_rate, progress_callback
            )
        elif method == 'grid_search':
            best_config, history = self._grid_search_optimize(results, character_id)
        elif method == 'bayesian':
            best_config, history = self._bayesian_optimize(results, character_id, current_config, weight_keys, threshold_keys, max_iterations, progress_callback)
        else:
            return {'error': f'Unknown optimization method: {method}'}
        
        # Calculate final correlation
        final_correlation = self._calculate_correlation_with_config(results, best_config, character_id)
        improvement = final_correlation - initial_correlation
        
        logger.info(f"Optimization complete. Final correlation: {final_correlation:.4f}, Improvement: {improvement:.4f}")
        
        return {
            'character_id': character_id,
            'initial_config': current_config,
            'best_config': best_config,
            'initial_correlation': initial_correlation,
            'final_correlation': final_correlation,
            'improvement': improvement,
            'iterations': len(history),
            'history': history[-10:],
        }
    
    def _get_current_config(self, user_id: Optional[int], character_id: str) -> Dict[str, float]:
        """Get current algorithm weights and thresholds from database."""
        # Use simple method first, we can expand later
        # We need a robust 'defaults' map if nothing is found
        algo_config = self.db.get_user_algorithm_config(user_id, character_id)
        
        if algo_config:
             # Filter out non-numeric fields
             return {k: float(v) for k, v in algo_config.items() if isinstance(v, (int, float)) and k != 'id'}
             
        # Fallback Defaults
        if character_id == 'buffett':
            return {
                'weight_roe': 0.35,
                'weight_consistency': 0.25,
                'weight_debt_to_earnings': 0.20,
                'weight_gross_margin': 0.20,
                'roe_excellent': 20.0,
                'roe_good': 15.0,
                'roe_fair': 10.0,
                'debt_to_earnings_excellent': 2.0,
                'debt_to_earnings_good': 4.0,
                'debt_to_earnings_fair': 7.0,
                'gross_margin_excellent': 50.0,
                'gross_margin_good': 40.0,
                'gross_margin_fair': 30.0
            }
        else: # Lynch default
            return {
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
                'inst_own_max': 0.60
            }

    def _get_weight_keys(self, character_id: str) -> List[str]:
        if character_id == 'buffett':
            return ['weight_roe', 'weight_consistency', 'weight_debt_to_earnings', 'weight_gross_margin']
        return ['weight_peg', 'weight_consistency', 'weight_debt', 'weight_ownership']

    def _get_threshold_keys(self, character_id: str) -> List[str]:
         if character_id == 'buffett':
             return [
                 'roe_excellent', 'roe_good', 'roe_fair', 
                 'debt_to_earnings_excellent', 'debt_to_earnings_good', 'debt_to_earnings_fair',
                 'gross_margin_excellent', 'gross_margin_good', 'gross_margin_fair',
                 'revenue_growth_excellent', 'revenue_growth_good', 'revenue_growth_fair',
                 'income_growth_excellent', 'income_growth_good', 'income_growth_fair'
             ]
         return [
             'peg_excellent', 'peg_good', 'peg_fair', 
             'debt_excellent', 'debt_good', 'debt_moderate', 
             'inst_own_min', 'inst_own_max',
             'revenue_growth_excellent', 'revenue_growth_good', 'revenue_growth_fair',
             'income_growth_excellent', 'income_growth_good', 'income_growth_fair'
         ]

    def _calculate_correlation_with_config(self, results: List[Dict[str, Any]], 
                                         config: Dict[str, float], character_id: str) -> float:
        """Calculate correlation between scores generated with config and actual returns"""
        scores = []
        returns = []
        
        for result in results:
            hist_data = result.get('historical_data', {})
            # Merge flat historical data with the result for easy access
            combined_data = {**result, **hist_data}
            
            score = self._recalculate_score(combined_data, config, character_id)
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
    
    def _recalculate_score(self, result: Dict[str, Any], config: Dict[str, float], character_id: str) -> Optional[float]:
        if character_id == 'buffett':
            return self._recalculate_score_buffett(result, config)
        return self._recalculate_score_lynch(result, config)

    def _recalculate_score_lynch(self, result: Dict[str, Any], config: Dict[str, float]) -> Optional[float]:
        # Extract raw metrics
        peg_ratio = result.get('peg_ratio')
        debt_to_equity = result.get('debt_to_equity')
        institutional_ownership = result.get('institutional_ownership')
        # Recalculate Consistency (Growth) Score from raw CAGRs
        revenue_score = self._calculate_growth_score_with_thresholds(
            result.get('revenue_cagr'),
            config.get('revenue_growth_excellent', 15.0),
            config.get('revenue_growth_good', 10.0),
            config.get('revenue_growth_fair', 5.0)
        )
        income_score = self._calculate_growth_score_with_thresholds(
            result.get('earnings_cagr'),
            config.get('income_growth_excellent', 15.0),
            config.get('income_growth_good', 10.0),
            config.get('income_growth_fair', 5.0)
        )
        consistency_score = (revenue_score + income_score) / 2
        
        # Calculate other component scores
        peg_score = self._calculate_peg_score_with_thresholds(
            peg_ratio, 
            config.get('peg_excellent') if config.get('peg_excellent') is not None else 1.0, 
            config.get('peg_good') if config.get('peg_good') is not None else 1.5, 
            config.get('peg_fair') if config.get('peg_fair') is not None else 2.0
        )
        debt_score = self._calculate_debt_score_with_thresholds(
            debt_to_equity, 
            config.get('debt_excellent') if config.get('debt_excellent') is not None else 0.5, 
            config.get('debt_good') if config.get('debt_good') is not None else 1.0, 
            config.get('debt_moderate') if config.get('debt_moderate') is not None else 2.0
        )
        ownership_score = self._calculate_ownership_score_with_thresholds(
            institutional_ownership, 
            config.get('inst_own_min') if config.get('inst_own_min') is not None else 0.20, 
            config.get('inst_own_max') if config.get('inst_own_max') is not None else 0.60
        )
        
        overall_score = (
            (config.get('weight_peg') if config.get('weight_peg') is not None else 0.5) * peg_score +
            (config.get('weight_consistency') if config.get('weight_consistency') is not None else 0.25) * consistency_score +
            (config.get('weight_debt') if config.get('weight_debt') is not None else 0.15) * debt_score +
            (config.get('weight_ownership') if config.get('weight_ownership') is not None else 0.1) * ownership_score
        )
        return round(overall_score, 1)

    def _recalculate_score_buffett(self, result: Dict[str, Any], config: Dict[str, float]) -> Optional[float]:
        # Buffett Metrics: ROE, Debt/Earnings, Consistency
        roe = result.get('roe')
        debt_to_earnings = result.get('debt_to_earnings')
        consistency_score = result.get('consistency_score', 50) if result.get('consistency_score') is not None else 50
        
        # Defensive check: ensure metrics are numeric (not datetimes or strings)
        def to_float(val):
            if val is None: return None
            try: return float(val)
            except (TypeError, ValueError): return None

        roe = to_float(roe)
        debt_to_earnings = to_float(debt_to_earnings)
        
        # Recalculate Consistency (Growth) Score from raw CAGRs
        revenue_score = self._calculate_growth_score_with_thresholds(
            result.get('revenue_cagr'),
            config.get('revenue_growth_excellent', 15.0),
            config.get('revenue_growth_good', 10.0),
            config.get('revenue_growth_fair', 5.0)
        )
        income_score = self._calculate_growth_score_with_thresholds(
            result.get('earnings_cagr'),
            config.get('income_growth_excellent', 15.0),
            config.get('income_growth_good', 10.0),
            config.get('income_growth_fair', 5.0)
        )
        consistency_score = (revenue_score + income_score) / 2
        
        roe_score = 0
        if roe is not None:
            if roe >= (config.get('roe_excellent') if config.get('roe_excellent') is not None else 20.0): roe_score = 100
            elif roe >= (config.get('roe_good') if config.get('roe_good') is not None else 15.0): roe_score = 75
            elif roe >= (config.get('roe_fair') if config.get('roe_fair') is not None else 10.0): roe_score = 50
            else: roe_score = 25
            
        # Debt/Earnings Score (Lower is better)
        de_score = 0
        if debt_to_earnings is not None:
            if debt_to_earnings <= (config.get('debt_to_earnings_excellent') if config.get('debt_to_earnings_excellent') is not None else 2.0): de_score = 100
            elif debt_to_earnings <= (config.get('debt_to_earnings_good') if config.get('debt_to_earnings_good') is not None else 4.0): de_score = 75
            elif debt_to_earnings <= (config.get('debt_to_earnings_fair') if config.get('debt_to_earnings_fair') is not None else 7.0): de_score = 50
            else: de_score = 25
        else:
             # Penalize missing debt/earnings data 
             de_score = 0
        
        # Gross Margin Score (Higher is better)
        gm_score = 0
        gm = to_float(result.get('gross_margin'))
        if gm is not None:
            if gm >= (config.get('gross_margin_excellent') if config.get('gross_margin_excellent') is not None else 50.0): gm_score = 100
            elif gm >= (config.get('gross_margin_good') if config.get('gross_margin_good') is not None else 40.0): gm_score = 75
            elif gm >= (config.get('gross_margin_fair') if config.get('gross_margin_fair') is not None else 30.0): gm_score = 50
            else: gm_score = 25

        overall_score = (
            (config.get('weight_roe') if config.get('weight_roe') is not None else 0.35) * roe_score +
            (config.get('weight_consistency') if config.get('weight_consistency') is not None else 0.25) * consistency_score +
            (config.get('weight_debt_to_earnings') if config.get('weight_debt_to_earnings') is not None else 0.20) * de_score +
            (config.get('weight_gross_margin') if config.get('weight_gross_margin') is not None else 0.20) * gm_score
        )
        return round(overall_score, 1)

    def _normalize_weights(self, config: Dict[str, float], keys: List[str] = None) -> Dict[str, float]:
        """Ensure specific weights sum to 1.0"""
        new_config = config.copy()
        
        if not keys:
             # Detect keys if not provided (fallback)
             if 'weight_roe' in config:
                 keys = ['weight_roe', 'weight_consistency', 'weight_debt_to_earnings', 'weight_gross_margin']
             else:
                 keys = ['weight_peg', 'weight_consistency', 'weight_debt', 'weight_ownership']

        total_weight = sum(new_config.get(k, 0) for k in keys)
        
        if total_weight > 0:
            for k in keys:
                new_config[k] = new_config.get(k, 0) / total_weight
        
        return new_config

    def _gradient_descent_optimize(self, results: List[Dict[str, Any]], 
                                   initial_config: Dict[str, float], character_id: str,
                                   weight_keys: List[str], max_iterations: int, learning_rate: float,
                                   progress_callback=None) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        config = initial_config.copy()
        history = []
        
        best_config = config.copy()
        best_correlation = self._calculate_correlation_with_config(results, config, character_id)
        
        # Report initial baseline
        if progress_callback:
            progress_callback({
                'iteration': 0,
                'correlation': best_correlation,
                'config': best_config.copy(),
                'best_correlation': best_correlation,
                'best_config': best_config.copy()
            })
        
        for iteration in range(max_iterations):
            gradients = {}
            epsilon = 0.01
            
            for key in weight_keys:
                test_config = config.copy()
                test_config[key] += epsilon
                test_config = self._normalize_weights(test_config, weight_keys)
                
                correlation_plus = self._calculate_correlation_with_config(results, test_config, character_id)
                gradients[key] = (correlation_plus - best_correlation) / epsilon
            
            # Apply gradients
            changed = False
            for key, grad in gradients.items():
                if abs(grad) > 0.0001:
                    config[key] += grad * learning_rate
                    changed = True
            
            config = self._normalize_weights(config, weight_keys)
            
            new_correlation = self._calculate_correlation_with_config(results, config, character_id)
            
            if new_correlation > best_correlation:
                best_correlation = new_correlation
                best_config = config.copy()
            
            history.append({
                'iteration': iteration,
                'correlation': new_correlation,
                'config': config.copy()
            })
            
            if progress_callback:
                progress_callback({
                    'iteration': iteration + 1,
                    'correlation': new_correlation,
                    'config': config.copy(),
                    'best_correlation': best_correlation,
                    'best_config': best_config.copy()
                })
            
            if not changed:
                break
                
        return best_config, history

    def _bayesian_optimize(self, results: List[Dict[str, Any]], character_id: str,
                          initial_config: Dict[str, float], weight_keys: List[str], threshold_keys: List[str],
                          max_iterations: int, progress_callback=None) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        """
        Bayesian optimization using Gaussian Processes
        Optimizes both WEIGHTS and THRESHOLDS
        """
        
        # Define search space
        dimensions = []
        param_names = []
        
        # Weights (0.0 to 1.0)
        for key in weight_keys:
            dimensions.append(Real(0.01, 0.99, name=key))
            param_names.append(key)
            
        # Thresholds (Variable ranges)
        for key in threshold_keys:
            # Dynamic ranges based on parameter type
            if 'peg' in key:
                dimensions.append(Real(0.5, 3.0, name=key))
            elif 'debt' in key and 'earnings' not in key: # Debt/Equity
                dimensions.append(Real(0.1, 3.0, name=key))
            elif 'debt_to_earnings' in key:
                dimensions.append(Real(0.5, 10.0, name=key))
            elif 'roe' in key:
                dimensions.append(Real(5.0, 30.0, name=key))
            elif 'own' in key: # Ownership
                dimensions.append(Real(0.05, 0.9, name=key))
            elif 'growth' in key:
                dimensions.append(Real(2.0, 30.0, name=key))
            else:
                 dimensions.append(Real(0.0, 100.0, name=key))
            param_names.append(key)

        history = []
        n_seeds = 50  # Fixed seed count
        
        # Track best so far manually for reporting
        best_so_far_corr = self._calculate_correlation_with_config(results, initial_config, character_id)
        best_so_far_config = initial_config.copy()
        
        @use_named_args(dimensions=dimensions)
        def objective(**params):
            nonlocal best_so_far_corr, best_so_far_config
            
            config = initial_config.copy()
            config.update(params)
            config = self._normalize_weights(config, weight_keys)
            
            correlation = self._calculate_correlation_with_config(results, config, character_id)
            
            if correlation > best_so_far_corr:
                best_so_far_corr = correlation
                best_so_far_config = config.copy()

            history.append({
                'iteration': len(history) + 1,
                'correlation': correlation,
                'config': config.copy()
            })
            
            # Only report progress after seed phase
            # Iteration count: 0-based during seeds, then 1-max_iterations for guided
            current_iter = len(history)
            if current_iter > n_seeds and progress_callback:
                progress_callback({
                    'iteration': current_iter - n_seeds,  # Start from 1 after seeds
                    'correlation': correlation,
                    'config': config.copy(),
                    'best_correlation': best_so_far_corr,
                    'best_config': best_so_far_config.copy()
                })
                
            return -correlation # Minimize negative correlation
        
        # Seed the optimizer with current configuration (x0)
        # Clamp values to dimension bounds to avoid "not within bounds" error
        x0 = []
        for i, key in enumerate(param_names):
            val = initial_config.get(key, 0.0)
            # Clamp to dimension bounds
            dim = dimensions[i]
            val = max(dim.low, min(dim.high, val))
            x0.append(val)
        
        # Run optimization
        # Use fixed 50 initial random samples (matching Lynch behavior)
        # Then run max_iterations guided trials
        
        res = gp_minimize(
            objective, 
            dimensions, 
            n_calls=max_iterations + n_seeds,  # Total = 50 seeds + max_iterations
            n_initial_points=n_seeds,
            x0=x0,
            y0=-best_so_far_corr,
            random_state=42
        )
        
        return best_so_far_config, history

    # --- Helper Calculation Methods (unchanged/adapted) ---

    def _calculate_peg_score_with_thresholds(self, peg_ratio, excellent, good, fair):
        if peg_ratio is None or peg_ratio <= 0: return 0
        
        # Safety defaults for thresholds
        excellent = excellent if excellent is not None else 1.0
        good = good if good is not None else 1.5
        fair = fair if fair is not None else 2.0
        
        if peg_ratio <= excellent: return 100
        if peg_ratio <= good: return 75
        if peg_ratio <= fair: return 50
        return 25

    def _calculate_debt_score_with_thresholds(self, debt_ratio, excellent, good, moderate):
        if debt_ratio is None: return 50 # Neutral if unknown
        
        # Safety defaults
        excellent = excellent if excellent is not None else 0.5
        good = good if good is not None else 1.0
        moderate = moderate if moderate is not None else 2.0
        
        if debt_ratio <= excellent: return 100
        if debt_ratio <= good: return 75
        if debt_ratio <= moderate: return 50
        return 25

    def _calculate_ownership_score_with_thresholds(self, ownership, minimum, maximum):
        if ownership is None: return 50
        
        # Safety defaults
        minimum = minimum if minimum is not None else 0.20
        maximum = maximum if maximum is not None else 0.60
        
        if ownership < minimum: return 25 # Too low (unnoticed)
        if ownership > maximum: return 25 # Too high (overcrowded)
        return 100 # Sweet spot

    def _calculate_growth_score_with_thresholds(self, cagr, excellent, good, fair):
        if cagr is None: return 0
        
        # Safety defaults
        excellent = excellent if excellent is not None else 15.0
        good = good if good is not None else 10.0
        fair = fair if fair is not None else 5.0
        
        if cagr >= excellent: return 100
        if cagr >= good: return 75
        if cagr >= fair: return 50
        return 25
    
    def save_config(self, config: Dict[str, Any], name: str = "Optimized Config", 
                   user_id: Optional[int] = None, character_id: str = 'lynch'):
        """Save configuration to database"""
        # Clean config to only valid columns
        valid_keys = [
            'weight_peg', 'weight_consistency', 'weight_debt', 'weight_ownership',
            'peg_excellent', 'peg_good', 'peg_fair',
            'debt_excellent', 'debt_good', 'debt_moderate',
            'inst_own_min', 'inst_own_max',
            'weight_roe', 'weight_debt_to_earnings',
            'roe_excellent', 'roe_good', 'roe_fair',
            'debt_to_earnings_excellent', 'debt_to_earnings_good', 'debt_to_earnings_fair'
        ]
        
        filtered_config = {k: v for k, v in config.items() if k in valid_keys}
        
        # Add metadata
        filtered_config['name'] = name
        filtered_config['character'] = character_id
        filtered_config['description'] = f"Optimized via {config.get('method', 'algorithm')} for {character_id}"
        
        self.db.save_algorithm_config(filtered_config, user_id=user_id)
        logger.info(f"Saved optimized configuration '{name}' for user {user_id}")

