import numpy as np
from typing import List, Dict, Any, Tuple
import logging
from scipy import stats

from database import Database

logger = logging.getLogger(__name__)

class CorrelationAnalyzer:
    def __init__(self, db: Database):
        self.db = db
    
    def analyze_results(self, years_back: int) -> Dict[str, Any]:
        """
        Analyze backtest results to determine how well the algorithm predicts returns
        
        Returns comprehensive correlation analysis and insights
        """
        results = self.db.get_backtest_results(years_back=years_back)
        
        if len(results) < 10:
            return {'error': f'Insufficient data: only {len(results)} results found'}
        
        logger.info(f"Analyzing {len(results)} backtest results for {years_back} year(s)")
        
        # Extract data arrays
        scores = [r['historical_score'] for r in results if r['historical_score'] is not None]
        returns = [r['total_return'] for r in results if r['total_return'] is not None and r['historical_score'] is not None]
        
        # Calculate overall correlation
        overall_corr = self._calculate_correlation(scores, returns)
        
        # Component correlations
        component_corrs = self._analyze_components(results)
        
        # Score bucket analysis
        bucket_analysis = self._analyze_score_buckets(results)
        
        # Rating category analysis
        rating_analysis = self._analyze_by_rating(results)
        
        # Top/bottom performers
        performers = self._analyze_performers(results)
        
        analysis = {
            'years_back': years_back,
            'total_stocks': len(results),
            'overall_correlation': overall_corr,
            'component_correlations': component_corrs,
            'score_buckets': bucket_analysis,
            'rating_analysis': rating_analysis,
            'performers': performers,
            'insights': self._generate_insights(overall_corr, component_corrs, rating_analysis)
        }
        
        logger.info(f"Analysis complete. Overall correlation: {overall_corr['coefficient']:.3f}")
        
        return analysis
    
    def _calculate_correlation(self, x: List[float], y: List[float]) -> Dict[str, Any]:
        """Calculate Pearson correlation coefficient"""
        if len(x) < 2 or len(y) < 2:
            return {'coefficient': 0.0, 'p_value': 1.0, 'significant': False}
        
        # Remove None values
        paired = [(xi, yi) for xi, yi in zip(x, y) if xi is not None and yi is not None]
        if len(paired) < 2:
            return {'coefficient': 0.0, 'p_value': 1.0, 'significant': False}
        
        x_clean, y_clean = zip(*paired)
        
        coefficient, p_value = stats.pearsonr(x_clean, y_clean)
        
        return {
            'coefficient': float(coefficient),
            'p_value': float(p_value),
            'significant': p_value < 0.05,
            'sample_size': len(x_clean),
            'interpretation': self._interpret_correlation(coefficient)
        }
    
    def _interpret_correlation(self, r: float) -> str:
        """Interpret correlation strength"""
        abs_r = abs(r)
        if abs_r > 0.7:
            strength = "strong"
        elif abs_r > 0.4:
            strength = "moderate"
        elif abs_r > 0.2:
            strength = "weak"
        else:
            strength = "negligible"
        
        direction = "positive" if r > 0 else "negative"
        return f"{strength} {direction}"
    
    def _analyze_components(self, results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Analyze correlation of individual components with returns"""
        returns = [r['total_return'] for r in results]
        
        components = {
            'peg_score': [r.get('peg_score') for r in results],
            'debt_score': [r.get('debt_score') for r in results],
            'ownership_score': [r.get('ownership_score') for r in results],
            'consistency_score': [r.get('consistency_score') for r in results]
        }
        
        correlations = {}
        for component, values in components.items():
            correlations[component] = self._calculate_correlation(values, returns)
        
        return correlations
    
    def _analyze_score_buckets(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group stocks by score ranges and calculate average returns"""
        buckets = [
            {"range": "0-20", "min": 0, "max": 20},
            {"range": "20-40", "min": 20, "max": 40},
            {"range": "40-60", "min": 40, "max": 60},
            {"range": "60-80", "min": 60, "max": 80},
            {"range": "80-100", "min": 80, "max": 100}
        ]
        
        for bucket in buckets:
            filtered = [r for r in results 
                       if r['historical_score'] is not None 
                       and bucket['min'] <= r['historical_score'] < bucket['max']]
            
            if filtered:
                returns = [r['total_return'] for r in filtered if r['total_return'] is not None]
                bucket['count'] = len(filtered)
                bucket['avg_return'] = np.mean(returns) if returns else 0.0
                bucket['median_return'] = np.median(returns) if returns else 0.0
                bucket['std_return'] = np.std(returns) if returns else 0.0
            else:
                bucket['count'] = 0
                bucket['avg_return'] = 0.0
                bucket['median_return'] = 0.0
                bucket['std_return'] = 0.0
        
        return buckets
    
    def _analyze_by_rating(self, results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Analyze returns by rating category"""
        ratings = {}
        
        for result in results:
            rating = result.get('historical_rating')
            if not rating:
                continue
            
            if rating not in ratings:
                ratings[rating] = {'returns': [], 'count': 0}
            
            if result.get('total_return') is not None:
                ratings[rating]['returns'].append(result['total_return'])
            ratings[rating]['count'] += 1
        
        # Calculate statistics for each rating
        for rating, data in ratings.items():
            if data['returns']:
                data['avg_return'] = np.mean(data['returns'])
                data['median_return'] = np.median(data['returns'])
                data['std_return'] = np.std(data['returns'])
                data['min_return'] = min(data['returns'])
                data['max_return'] = max(data['returns'])
            else:
                data['avg_return'] = 0.0
                data['median_return'] = 0.0
                data['std_return'] = 0.0
            
            # Remove raw returns list for cleaner output
            del data['returns']
        
        return ratings
    
    def _analyze_performers(self, results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Identify top and bottom performers"""
        sorted_results = sorted(results, key=lambda x: x.get('total_return', 0), reverse=True)
        
        top_5 = [
            {
                'symbol': r['symbol'],
                'return': r['total_return'],
                'score': r['historical_score'],
                'rating': r['historical_rating']
            }
            for r in sorted_results[:5] if r.get('total_return') is not None
        ]
        
        bottom_5 = [
            {
                'symbol': r['symbol'],
                'return': r['total_return'],
                'score': r['historical_score'],
                'rating': r['historical_rating']
            }
            for r in sorted_results[-5:] if r.get('total_return') is not None
        ]
        
        return {'top_5': top_5, 'bottom_5': bottom_5}
    
    def _generate_insights(self, overall_corr: Dict[str, Any], 
                          component_corrs: Dict[str, Dict[str, Any]],
                          rating_analysis: Dict[str, Dict[str, Any]]) -> List[str]:
        """Generate actionable insights from the analysis"""
        insights = []
        
        # Overall correlation insight
        if overall_corr['significant']:
            insights.append(
                f"✅ The algorithm shows a {overall_corr['interpretation']} "
                f"correlation ({overall_corr['coefficient']:.3f}) with actual returns. "
                f"This is statistically significant (p={overall_corr['p_value']:.4f})."
            )
        else:
            insights.append(
                f"⚠️ The algorithm shows weak predictive power "
                f"(correlation: {overall_corr['coefficient']:.3f}, p={overall_corr['p_value']:.4f}). "
                f"Consider adjusting weights or adding new factors."
            )
        
        # Component insights - find best predictor
        best_component = max(component_corrs.items(), 
                            key=lambda x: abs(x[1]['coefficient']))
        
        insights.append(
            f"🎯 Best predictor: {best_component[0].replace('_', ' ').title()} "
            f"(correlation: {best_component[1]['coefficient']:.3f}). "
            f"Consider increasing its weight in the algorithm."
        )
        
        # Rating insights
        if rating_analysis:
            ratings_by_return = sorted(rating_analysis.items(), 
                                      key=lambda x: x[1].get('avg_return', 0), 
                                      reverse=True)
            
            if ratings_by_return:
                best_rating = ratings_by_return[0]
                insights.append(
                    f"📊 Best performing rating: {best_rating[0]} "
                    f"(avg return: {best_rating[1].get('avg_return', 0):.2f}%)"
                )
        
        return insights
