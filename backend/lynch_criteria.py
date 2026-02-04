# ABOUTME: Evaluates stocks against investment criteria (Lynch, Buffett, etc.)
# ABOUTME: Routes to character-specific scoring based on active character setting

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from database import Database
from earnings_analyzer import EarningsAnalyzer

logger = logging.getLogger(__name__)


# Algorithm metadata for UI display
ALGORITHM_METADATA = {
    'weighted': {
        'name': 'Weighted',
        'short_desc': 'Balanced approach weighting PEG ratio most heavily with earnings quality',
        'description': '''Assigns weighted importance to each metric based on Lynch's priorities:
        • PEG Ratio: 50% (Lynch's primary valuation metric)
        • Earnings Consistency: 25% (quality of growth matters)
        • Debt-to-Equity: 15% (important but contextual)
        • Institutional Ownership: 10% (minor consideration)

        Produces a 0-100 score: Strong Buy (80+), Buy (60-80), Hold (40-60), Caution (20-40), Avoid (0-20).
        Best for: Balanced evaluation that prioritizes what Lynch cared about most.''',
        'recommended': True
    }
}


SCORE_THRESHOLDS = {
    'STRONG_BUY': 80,
    'BUY': 60,
    'HOLD': 40,
    'CAUTION': 20
}


class LynchCriteria:
    # Constants removed in favor of dynamic settings
    # See self.settings in __init__

    def __init__(self, db: Database, analyzer: EarningsAnalyzer):
        self.db = db
        self.analyzer = analyzer

        # Metric calculator for computing derived Buffett metrics
        from metric_calculator import MetricCalculator
        self.metric_calculator = MetricCalculator(db)

        # Initialize default settings if needed
        self.db.init_default_settings()
        self.reload_settings()

    def reload_settings(self):
        """Reload settings from database.
        
        Source of truth: algorithm_configurations table (highest id = current config)
        """
        logger.info("Reloading Lynch criteria settings from database")
        
        # Load from algorithm_configurations table - always use highest ID
        configs = self.db.get_algorithm_configs()
        algo_config = configs[0] if configs else None
        
        # Build settings dict from algorithm_configurations or use defaults
        if algo_config:
            logger.info(f"Using algorithm config: {algo_config.get('name', 'unnamed')} (id={algo_config.get('id')})")
            self.settings = {
                'peg_excellent': {'value': algo_config.get('peg_excellent') if algo_config.get('peg_excellent') is not None else 1.0},
                'peg_good': {'value': algo_config.get('peg_good') if algo_config.get('peg_good') is not None else 1.5},
                'peg_fair': {'value': algo_config.get('peg_fair') if algo_config.get('peg_fair') is not None else 2.0},
                'debt_excellent': {'value': algo_config.get('debt_excellent') if algo_config.get('debt_excellent') is not None else 0.5},
                'debt_good': {'value': algo_config.get('debt_good') if algo_config.get('debt_good') is not None else 1.0},
                'debt_moderate': {'value': algo_config.get('debt_moderate') if algo_config.get('debt_moderate') is not None else 2.0},
                'inst_own_min': {'value': algo_config.get('inst_own_min') if algo_config.get('inst_own_min') is not None else 0.20},
                'inst_own_max': {'value': algo_config.get('inst_own_max') if algo_config.get('inst_own_max') is not None else 0.60},
                'revenue_growth_excellent': {'value': algo_config.get('revenue_growth_excellent') if algo_config.get('revenue_growth_excellent') is not None else 15.0},
                'revenue_growth_good': {'value': algo_config.get('revenue_growth_good') if algo_config.get('revenue_growth_good') is not None else 10.0},
                'revenue_growth_fair': {'value': algo_config.get('revenue_growth_fair') if algo_config.get('revenue_growth_fair') is not None else 5.0},
                'income_growth_excellent': {'value': algo_config.get('income_growth_excellent') if algo_config.get('income_growth_excellent') is not None else 15.0},
                'income_growth_good': {'value': algo_config.get('income_growth_good') if algo_config.get('income_growth_good') is not None else 10.0},
                'income_growth_fair': {'value': algo_config.get('income_growth_fair') if algo_config.get('income_growth_fair') is not None else 5.0},
                'weight_peg': {'value': algo_config.get('weight_peg') if algo_config.get('weight_peg') is not None else 0.50},
                'weight_consistency': {'value': algo_config.get('weight_consistency') if algo_config.get('weight_consistency') is not None else 0.25},
                'weight_debt': {'value': algo_config.get('weight_debt') if algo_config.get('weight_debt') is not None else 0.15},
                'weight_ownership': {'value': algo_config.get('weight_ownership') if algo_config.get('weight_ownership') is not None else 0.10},
            }
        else:
            logger.warning("No algorithm configuration found - using hardcoded defaults")
            self.settings = {
                'peg_excellent': {'value': 1.0},
                'peg_good': {'value': 1.5},
                'peg_fair': {'value': 2.0},
                'debt_excellent': {'value': 0.5},
                'debt_good': {'value': 1.0},
                'debt_moderate': {'value': 2.0},
                'inst_own_min': {'value': 0.20},
                'inst_own_max': {'value': 0.60},
                'revenue_growth_excellent': {'value': 15.0},
                'revenue_growth_good': {'value': 10.0},
                'revenue_growth_fair': {'value': 5.0},
                'income_growth_excellent': {'value': 15.0},
                'income_growth_good': {'value': 10.0},
                'income_growth_fair': {'value': 5.0},
                'weight_peg': {'value': 0.50},
                'weight_consistency': {'value': 0.25},
                'weight_debt': {'value': 0.15},
                'weight_ownership': {'value': 0.10},
            }
        
        # Cache values for easy access
        self.peg_excellent = self.settings['peg_excellent']['value']
        self.peg_good = self.settings['peg_good']['value']
        self.peg_fair = self.settings['peg_fair']['value']
        
        self.debt_excellent = self.settings['debt_excellent']['value']
        self.debt_good = self.settings['debt_good']['value']
        self.debt_moderate = self.settings['debt_moderate']['value']
        
        self.inst_own_min = self.settings['inst_own_min']['value']
        self.inst_own_max = self.settings['inst_own_max']['value']
        
        # Cache growth thresholds
        self.revenue_growth_excellent = self.settings['revenue_growth_excellent']['value']
        self.revenue_growth_good = self.settings['revenue_growth_good']['value']
        self.revenue_growth_fair = self.settings['revenue_growth_fair']['value']
        
        self.income_growth_excellent = self.settings['income_growth_excellent']['value']
        self.income_growth_good = self.settings['income_growth_good']['value']
        self.income_growth_fair = self.settings['income_growth_fair']['value']

    def evaluate_stock(self, symbol: str, algorithm: str = 'weighted', overrides: Dict[str, float] = None, custom_metrics: Dict[str, Any] = None, stock_metrics: Dict[str, Any] = None, character_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Evaluate a stock using the weighted scoring algorithm.

        Args:
            symbol: Stock ticker
            algorithm: Only 'weighted' is supported (kept for API compatibility)
            overrides: Optional scoring weight/threshold overrides
            stock_metrics: Optional pre-fetched stock metrics
            character_id: Optional character ID override (bypasses global setting)

        Returns:
            Dictionary with evaluation results including scoring breakdown
        """
        # Check active character - delegate to StockEvaluator for non-Lynch characters
        # Prioritize passed character_id, else fallback to global setting
        active_character = character_id if character_id else self._get_active_character()

        if active_character != 'lynch':
            # Convert stock_metrics to custom_metrics if provided
            metrics_to_pass = custom_metrics if custom_metrics else stock_metrics
            return self._evaluate_with_character(symbol, active_character, overrides, metrics_to_pass)

        # Lynch evaluation
        # Get base metrics and growth data
        if custom_metrics:
            base_data = custom_metrics
        else:
            base_data = self._get_base_metrics(symbol, stock_metrics=stock_metrics)

        if not base_data:
            return None

        logger.debug(f"Evaluating {symbol}. Base data keys: {list(base_data.keys())}")

        try:
            return self._evaluate_weighted(symbol, base_data, overrides)
        except TypeError as te:
            logger.error(f"TypeError evaluating {symbol}: {te}")
            logger.error(f"DEBUG: peg_ratio={base_data.get('peg_ratio')}, debt_equity={base_data.get('debt_to_equity')}, inst_own={base_data.get('institutional_ownership')}")
            logger.error(f"DEBUG THRESHOLDS: peg_exc={self.peg_excellent}, peg_good={self.peg_good}, debt_exc={self.debt_excellent}, inst_min={self.inst_own_min}")
            raise te

    def _get_active_character(self) -> str:
        """Get the currently active investment character from settings."""
        try:
            setting = self.db.get_setting('active_character')
            return setting['value'] if setting else 'lynch'
        except Exception:
            return 'lynch'

    def _evaluate_with_character(self, symbol: str, character_id: str, overrides: Dict[str, Any] = None, custom_metrics: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Evaluate a stock using a non-Lynch character via StockEvaluator."""
        try:
            from stock_evaluator import StockEvaluator
            from characters import get_character

            character = get_character(character_id)
            if not character:
                logger.warning(f"Character not found: {character_id}, falling back to Lynch")
                return None

            evaluator = StockEvaluator(self.db, self.analyzer, character)
            result = evaluator.evaluate_stock(symbol, overrides, custom_metrics)
            return result
        except Exception as e:
            logger.error(f"Error evaluating with character {character_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None



    def _get_base_metrics(self, symbol: str, stock_metrics: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Get base metrics and growth data for a stock.

        Args:
            symbol: Stock ticker
            stock_metrics: Optional pre-fetched metrics to avoid DB lookup
        """
        # Use provided metrics if available, otherwise fetch from DB
        if stock_metrics:
            metrics = stock_metrics
        else:
            metrics = self.db.get_stock_metrics(symbol)

        if not metrics:
            return None

        growth_data = self.analyzer.calculate_earnings_growth(symbol)

        # Extract growth data or None if unavailable
        earnings_cagr = growth_data['earnings_cagr'] if growth_data else None
        revenue_cagr = growth_data['revenue_cagr'] if growth_data else None
        
        # Get raw consistency scores (std_dev values)
        raw_income_consistency = growth_data.get('income_consistency_score') if growth_data else None
        raw_revenue_consistency = growth_data.get('revenue_consistency_score') if growth_data else None
        
        # Normalize consistency scores to 0-100 scale where 100 is best
        # Lower std dev = Higher consistency
        def normalize_consistency(raw_value):
            if raw_value is None:
                return None
            # Formula: 100 - (std_dev * 2), capped at 0
            return max(0.0, 100.0 - (raw_value * 2.0))
        
        income_consistency_score = normalize_consistency(raw_income_consistency)
        revenue_consistency_score = normalize_consistency(raw_revenue_consistency)
        
        # Keep consistency_score for backward compatibility (uses income consistency)
        consistency_score = income_consistency_score

        pe_ratio = metrics.get('pe_ratio')

        # Calculate PEG ratio only if both P/E and earnings growth are available
        peg_ratio = self.calculate_peg_ratio(pe_ratio, earnings_cagr) if pe_ratio and earnings_cagr else None

        debt_to_equity = metrics.get('debt_to_equity')
        institutional_ownership = metrics.get('institutional_ownership')  # Don't default to 0, keep None as None

        # Calculate individual metric scores
        if peg_ratio is None:
            peg_status = "FAIL"
            peg_score = 0.0
        else:
            peg_status = self.evaluate_peg(peg_ratio)
            peg_score = self.calculate_peg_score(peg_ratio)

        debt_status = self.evaluate_debt(debt_to_equity)
        debt_score = self.calculate_debt_score(debt_to_equity)

        inst_ownership_status = self.evaluate_institutional_ownership(institutional_ownership)
        inst_ownership_score = self.calculate_institutional_ownership_score(institutional_ownership)
        
        # Calculate growth scores
        revenue_growth_score = self.calculate_revenue_growth_score(revenue_cagr)
        income_growth_score = self.calculate_income_growth_score(earnings_cagr)

        # Calculate 52-week P/E range using shared calculator
        pe_range_data = self.metric_calculator.calculate_pe_52_week_range(symbol, metrics)

        # Calculate Buffett metrics for on-the-fly re-scoring
        # These are stored in screening_results so any character can score them
        roe_data = self.metric_calculator.calculate_roe(symbol)
        owner_earnings_data = self.metric_calculator.calculate_owner_earnings(symbol)
        # Pass total_debt from metrics to avoid DB re-fetch (write queue may not have flushed)
        debt_to_earnings_data = self.metric_calculator.calculate_debt_to_earnings(symbol, total_debt=metrics.get('total_debt'))
        gross_margin_data = self.metric_calculator.calculate_gross_margin(symbol)

        # Extract values for storage (use 5yr avg for ROE as Buffett prefers long-term)
        roe = roe_data.get('avg_roe_5yr')
        owner_earnings = owner_earnings_data.get('owner_earnings')
        debt_to_earnings = debt_to_earnings_data.get('debt_to_earnings_years')
        gross_margin = gross_margin_data.get('current')

        # Return base data that all algorithms can use
        return {
            'metrics': metrics,
            'symbol': symbol,
            'company_name': metrics.get('company_name'),
            'country': metrics.get('country'),
            'market_cap': metrics.get('market_cap'),
            'sector': metrics.get('sector'),
            'ipo_year': metrics.get('ipo_year'),
            'price': metrics.get('price'),
            'price_change_pct': metrics.get('price_change_pct'),
            'pe_ratio': pe_ratio,
            'peg_ratio': peg_ratio,
            'debt_to_equity': debt_to_equity,
            'institutional_ownership': institutional_ownership,
            'dividend_yield': metrics.get('dividend_yield'),
            'earnings_cagr': earnings_cagr,
            'revenue_cagr': revenue_cagr,
            'consistency_score': consistency_score,
            'income_consistency_score': income_consistency_score,
            'revenue_consistency_score': revenue_consistency_score,
            'peg_status': peg_status,
            'peg_score': peg_score,
            'debt_status': debt_status,
            'debt_score': debt_score,
            'institutional_ownership_status': inst_ownership_status,
            'institutional_ownership_score': inst_ownership_score,
            'revenue_growth_score': revenue_growth_score,
            'income_growth_score': income_growth_score,
            # 52-week P/E range data
            'pe_52_week_min': pe_range_data['pe_52_week_min'],
            'pe_52_week_max': pe_range_data['pe_52_week_max'],
            'pe_52_week_position': pe_range_data['pe_52_week_position'],
            # Buffett metrics (for on-the-fly character re-scoring)
            'roe': roe,
            'owner_earnings': owner_earnings,
            'debt_to_earnings': debt_to_earnings,
            'gross_margin': gross_margin,
        }

    def _evaluate_weighted(self, symbol: str, base_data: Dict[str, Any], overrides: Dict[str, float] = None) -> Dict[str, Any]:
        """Weighted scoring: PEG 50%, Consistency 25%, Debt 15%, Ownership 10%.
        
        When overrides are provided with threshold values, component scores are
        recalculated from raw metrics to ensure consistency with optimizer.
        """
        # Get weights (from overrides or defaults)
        if overrides:
            peg_weight = overrides.get('weight_peg') if overrides.get('weight_peg') is not None else self.settings['weight_peg']['value']
            consistency_weight = overrides.get('weight_consistency') if overrides.get('weight_consistency') is not None else self.settings['weight_consistency']['value']
            debt_weight = overrides.get('weight_debt') if overrides.get('weight_debt') is not None else self.settings['weight_debt']['value']
            ownership_weight = overrides.get('weight_ownership') if overrides.get('weight_ownership') is not None else self.settings['weight_ownership']['value']
            
            # Log weights if they look suspicious
            if any(w is None for w in [peg_weight, consistency_weight, debt_weight, ownership_weight]):
                logger.error(f"SUSPICIOUS WEIGHTS for {symbol}: peg={peg_weight}, c={consistency_weight}, d={debt_weight}, o={ownership_weight}")
        else:
            peg_weight = self.settings['weight_peg']['value']
            consistency_weight = self.settings['weight_consistency']['value']
            debt_weight = self.settings['weight_debt']['value']
            ownership_weight = self.settings['weight_ownership']['value']

        # Get consistency score (0-100), default to 50 if not available
        consistency_score = base_data.get('consistency_score', 50) if base_data.get('consistency_score') is not None else 50

        # Check if threshold overrides are provided - if so, recalculate component scores
        has_threshold_overrides = overrides and any(
            k in overrides for k in ['peg_excellent', 'peg_good', 'peg_fair', 
                                      'debt_excellent', 'debt_good', 'debt_moderate',
                                      'inst_own_min', 'inst_own_max']
        )

        if has_threshold_overrides:
            # Recalculate component scores from raw metrics using threshold overrides
            # This matches what the optimizer does in _recalculate_score
            
            # PEG score with threshold overrides
            peg_ratio = base_data.get('peg_ratio')
            peg_excellent = overrides.get('peg_excellent') if overrides.get('peg_excellent') is not None else self.peg_excellent
            peg_good = overrides.get('peg_good') if overrides.get('peg_good') is not None else self.peg_good
            peg_fair = overrides.get('peg_fair') if overrides.get('peg_fair') is not None else self.peg_fair
            peg_score = self._calculate_peg_score_with_thresholds(peg_ratio, peg_excellent, peg_good, peg_fair)
            
            # Debt score with threshold overrides
            debt_to_equity = base_data.get('debt_to_equity')
            debt_excellent = overrides.get('debt_excellent') if overrides.get('debt_excellent') is not None else self.debt_excellent
            debt_good = overrides.get('debt_good') if overrides.get('debt_good') is not None else self.debt_good
            debt_moderate = overrides.get('debt_moderate') if overrides.get('debt_moderate') is not None else self.debt_moderate
            debt_score = self._calculate_debt_score_with_thresholds(debt_to_equity, debt_excellent, debt_good, debt_moderate)
            
            # Institutional ownership score with threshold overrides
            inst_own = base_data.get('institutional_ownership')
            inst_own_min = overrides.get('inst_own_min') if overrides.get('inst_own_min') is not None else self.inst_own_min
            inst_own_max = overrides.get('inst_own_max') if overrides.get('inst_own_max') is not None else self.inst_own_max
            ownership_score = self._calculate_ownership_score_with_thresholds(inst_own, inst_own_min, inst_own_max)
        else:
            # Use pre-calculated component scores from base_data
            peg_score = base_data['peg_score']
            debt_score = base_data['debt_score']
            ownership_score = base_data['institutional_ownership_score']

        # Calculate weighted overall score
        overall_score = (
            peg_score * peg_weight +
            consistency_score * consistency_weight +
            debt_score * debt_weight +
            ownership_score * ownership_weight
        )

        # Determine rating based on score
        if overall_score >= SCORE_THRESHOLDS['STRONG_BUY']:
            rating_label = "STRONG BUY"
            overall_status = "STRONG_BUY"
        elif overall_score >= SCORE_THRESHOLDS['BUY']:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= SCORE_THRESHOLDS['HOLD']:
            rating_label = "HOLD"
            overall_status = "HOLD"
        elif overall_score >= SCORE_THRESHOLDS['CAUTION']:
            rating_label = "CAUTION"
            overall_status = "CAUTION"
        else:
            rating_label = "AVOID"
            overall_status = "AVOID"

        result = base_data.copy()
        result['algorithm'] = 'weighted'
        result['overall_score'] = round(overall_score, 1)
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        # Update component scores in result if recalculated
        if has_threshold_overrides:
            result['peg_score'] = peg_score
            result['debt_score'] = debt_score
            result['institutional_ownership_score'] = ownership_score
        result['breakdown'] = {
            'peg_contribution': round(peg_score * peg_weight, 1),
            'consistency_contribution': round(consistency_score * consistency_weight, 1),
            'debt_contribution': round(debt_score * debt_weight, 1),
            'ownership_contribution': round(ownership_score * ownership_weight, 1)
        }
        return result

    def calculate_peg_ratio(self, pe_ratio: float, earnings_growth: float) -> Optional[float]:
        if pe_ratio is None or earnings_growth is None:
            return None
        if isinstance(pe_ratio, str) or isinstance(earnings_growth, str):
            return None
        if earnings_growth <= 0:
            return None  # Can't calculate meaningful PEG for zero or negative growth
        return pe_ratio / earnings_growth

    def evaluate_peg(self, value: float) -> str:
        """Evaluate PEG ratio: lower is better"""
        if value is None:
            return "FAIL"
        
        # Safety: use defaults if loaded from non-Lynch character config
        peg_excellent = self.peg_excellent if self.peg_excellent is not None else 1.0
        peg_good = self.peg_good if self.peg_good is not None else 1.5

        try:
            if value <= peg_excellent:
                return "PASS"
            elif value <= peg_good:
                return "CLOSE"
            else:
                return "FAIL"
        except TypeError as e:
            logger.error(f"TypeError in evaluate_peg: value={value} ({type(value)}), excellent={peg_excellent} ({type(peg_excellent)}), good={peg_good} ({type(peg_good)})")
            raise e

    def calculate_peg_score(self, value: float) -> float:
        """
        Calculate PEG score (0-100).
        Excellent (0-1.0): 100
        Good (1.0-1.5): 75-100
        Fair (1.5-2.0): 25-75
        Poor (2.0+): 0-25
        """
        if value is None:
            return 0.0
            
        # Safety defaults
        peg_excellent = self.peg_excellent if self.peg_excellent is not None else 1.0
        peg_good = self.peg_good if self.peg_good is not None else 1.5
        peg_fair = self.peg_fair if self.peg_fair is not None else 2.0

        if value <= peg_excellent:
            return 100.0
        elif value <= peg_good:
            # 75-100 range
            range_size = peg_good - peg_excellent
            position = (peg_good - value) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value <= peg_fair:
            # 25-75 range
            range_size = peg_fair - peg_good
            position = (peg_fair - value) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 4.0
            max_poor = 4.0
            if value >= max_poor:
                return 0.0
            range_size = max_poor - peg_fair
            position = (max_poor - value) / range_size
            return 25.0 * position

    def evaluate_debt(self, value: float) -> str:
        """Evaluate debt-to-equity: lower is better"""
        if value is None:
            return "PASS"  # Lynch liked no debt
            
        # Safety defaults
        debt_excellent = self.debt_excellent if self.debt_excellent is not None else 0.5
        debt_good = self.debt_good if self.debt_good is not None else 1.0

        try:
            if value <= debt_excellent:
                return "PASS"
            elif value <= debt_good:
                return "CLOSE"
            else:
                return "FAIL"
        except TypeError as e:
            logger.error(f"TypeError in evaluate_debt: value={value} ({type(value)}), excellent={debt_excellent}, good={debt_good}")
            raise e

    def calculate_debt_score(self, value: float) -> float:
        """
        Calculate debt score (0-100).
        Excellent (0-0.5): 100
        Good (0.5-1.0): 75-100
        Moderate (1.0-2.0): 25-75
        High (2.0+): 0-25
        """
        if value is None:
            return 100.0  # No debt is great
            
        # Safety defaults
        debt_excellent = self.debt_excellent if self.debt_excellent is not None else 0.5
        debt_good = self.debt_good if self.debt_good is not None else 1.0
        debt_moderate = self.debt_moderate if self.debt_moderate is not None else 2.0

        if value <= debt_excellent:
            return 100.0
        elif value <= debt_good:
            # 75-100 range
            range_size = debt_good - debt_excellent
            position = (debt_good - value) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value <= debt_moderate:
            # 25-75 range
            range_size = debt_moderate - debt_good
            position = (debt_moderate - value) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 5.0
            max_high = 5.0
            if value >= max_high:
                return 0.0
            range_size = max_high - debt_moderate
            position = (max_high - value) / range_size
            return 25.0 * position

    def evaluate_institutional_ownership(self, value: float) -> str:
        """Evaluate institutional ownership: sweet spot is around 40%"""
        if value is None:
            return "PASS"
            
        # Safety defaults
        inst_own_min = self.inst_own_min if self.inst_own_min is not None else 0.20
        inst_own_max = self.inst_own_max if self.inst_own_max is not None else 0.60

        try:
            if inst_own_min <= value <= inst_own_max:
                return "PASS"
            elif value < inst_own_min:
                return "CLOSE"
            else:
                return "FAIL"
        except TypeError as e:
            logger.error(f"TypeError in evaluate_institutional_ownership: value={value}, min={inst_own_min}, max={inst_own_max}")
            raise e

    def calculate_institutional_ownership_score(self, value: float) -> float:
        """
        Calculate institutional ownership score (0-100).
        Sweet spot (20%-60%): 100
        Under-owned (< 20%): 50-100
        Over-owned (> 60%): 0-50
        """
        if value is None:
            return 75.0  # Neutral
            
        # Safety defaults
        inst_own_min = self.inst_own_min if self.inst_own_min is not None else 0.20
        inst_own_max = self.inst_own_max if self.inst_own_max is not None else 0.60

        if inst_own_min <= value <= inst_own_max:
            return 100.0
        elif value < inst_own_min:
            # Under-owned is okay (50-100)
            return 50.0 + (value / inst_own_min) * 50.0 if inst_own_min > 0 else 100.0
        else:
            # Over-owned is bad (0-50)
            # Dips to 0 at 100% ownership
            range_size = 1.0 - inst_own_max
            if range_size > 0:
                position = (1.0 - value) / range_size
                return max(0.0, 50.0 * position)
            return 0.0

    def calculate_revenue_growth_score(self, value: float) -> float:
        """
        Calculate Revenue Growth score (0-100).
        Excellent (15%+): 100
        Good (10-15%): 75-100
        Fair (5-10%): 25-75
        Poor (<5%): 0-25
        Negative growth: 0
        """
        if value is None:
            return 50.0  # Default neutral score if no data
        
        if value < 0:
            return 0.0  # Negative growth = 0 score
            
        # Safety defaults
        rev_excellent = self.revenue_growth_excellent if self.revenue_growth_excellent is not None else 15.0
        rev_good = self.revenue_growth_good if self.revenue_growth_good is not None else 10.0
        rev_fair = self.revenue_growth_fair if self.revenue_growth_fair is not None else 5.0
        
        if value >= rev_excellent:
            return 100.0
        elif value >= rev_good:
            # 75-100 range
            range_size = rev_excellent - rev_good
            position = (value - rev_good) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value >= rev_fair:
            # 25-75 range
            range_size = rev_good - rev_fair
            position = (value - rev_fair) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range
            if value <= 0:
                return 0.0
            position = value / rev_fair if rev_fair > 0 else 0.0
            return 25.0 * position
    
    def calculate_income_growth_score(self, value: float) -> float:
        """
        Calculate Income/Earnings Growth score (0-100).
        Excellent (15%+): 100
        Good (10-15%): 75-100
        Fair (5-10%): 25-75
        Poor (<5%): 0-25
        Negative growth: 0
        """
        if value is None:
            return 50.0  # Default neutral score if no data
        
        if value < 0:
            return 0.0  # Negative growth = 0 score
            
        # Safety defaults
        inc_excellent = self.income_growth_excellent if self.income_growth_excellent is not None else 15.0
        inc_good = self.income_growth_good if self.income_growth_good is not None else 10.0
        inc_fair = self.income_growth_fair if self.income_growth_fair is not None else 5.0
        
        if value >= inc_excellent:
            return 100.0
        elif value >= inc_good:
            # 75-100 range
            range_size = inc_excellent - inc_good
            position = (value - inc_good) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value >= inc_fair:
            # 25-75 range
            range_size = inc_good - inc_fair
            position = (value - inc_fair) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range
            if value <= 0:
                return 0.0
            position = value / inc_fair if inc_fair > 0 else 0.0
            return 25.0 * position

    # ========== Threshold-aware scoring methods (for optimizer overrides) ==========
    
    def _calculate_peg_score_with_thresholds(self, value: float, excellent: float, good: float, fair: float) -> float:
        """Calculate PEG score using custom thresholds (for optimizer overrides)"""
        if value is None:
            return 0.0
            
        # Safety defaults
        excellent = excellent if excellent is not None else 1.0
        good = good if good is not None else 1.5
        fair = fair if fair is not None else 2.0

        if value <= excellent:
            return 100.0
        elif value <= good:
            range_size = good - excellent
            position = (good - value) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value <= fair:
            range_size = fair - good
            position = (fair - value) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            max_poor = 4.0
            if value >= max_poor:
                return 0.0
            range_size = max_poor - fair
            position = (max_poor - value) / range_size if range_size > 0 else 1.0
            return 25.0 * position

    def _calculate_debt_score_with_thresholds(self, value: float, excellent: float, good: float, moderate: float) -> float:
        """Calculate debt score using custom thresholds (for optimizer overrides)"""
        if value is None:
            return 100.0
            
        # Safety defaults
        excellent = excellent if excellent is not None else 0.5
        good = good if good is not None else 1.0
        moderate = moderate if moderate is not None else 2.0

        if value <= excellent:
            return 100.0
        elif value <= good:
            range_size = good - excellent
            position = (good - value) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value <= moderate:
            range_size = moderate - good
            position = (moderate - value) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            max_high = 5.0
            if value >= max_high:
                return 0.0
            range_size = max_high - moderate
            position = (max_high - value) / range_size if range_size > 0 else 1.0
            return 25.0 * position

    def _calculate_ownership_score_with_thresholds(self, value: float, min_threshold: float, max_threshold: float) -> float:
        """
        Calculate institutional ownership score using custom thresholds.

        Sweet spot (min-max): 100
        Under-owned (< min): 50-100 (interpolated)
        Over-owned (> max): 0-50 (interpolated down to 0 at 100% ownership)
        """
        if value is None:
            return 75.0  # Neutral

        # Safety defaults
        min_threshold = min_threshold if min_threshold is not None else 0.20
        max_threshold = max_threshold if max_threshold is not None else 0.60

        if min_threshold <= value <= max_threshold:
            return 100.0  # Sweet spot
        elif value < min_threshold:
            # Under-owned: 50-100 interpolated
            return 50.0 + (value / min_threshold) * 50.0 if min_threshold > 0 else 100.0
        else:
            # Over-owned: 0-50 interpolated (dips to 0 at 100% ownership)
            range_size = 1.0 - max_threshold
            if range_size > 0:
                position = (1.0 - value) / range_size
                return max(0.0, 50.0 * position)
            return 0.0

    # =========================================================================
    # VECTORIZED BATCH SCORING
    # =========================================================================
    
    def evaluate_batch(self, df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """
        Vectorized scoring for entire stock universe.
        
        This method mirrors _evaluate_weighted() but operates on a DataFrame
        for O(1) batch scoring instead of O(n) per-stock evaluation.
        
        Args:
            df: DataFrame with columns [symbol, peg_ratio, debt_to_equity, 
                institutional_ownership, income_consistency_score, ...]
            config: User's algorithm configuration (weights + thresholds)
        
        Returns:
            DataFrame with [symbol, overall_score, overall_status, ...] sorted by score desc
        """
        # Extract thresholds from config (with defaults)
        peg_excellent = config.get('peg_excellent') if config.get('peg_excellent') is not None else 1.0
        peg_good = config.get('peg_good') if config.get('peg_good') is not None else 1.5
        peg_fair = config.get('peg_fair') if config.get('peg_fair') is not None else 2.0
        
        debt_excellent = config.get('debt_excellent') if config.get('debt_excellent') is not None else 0.5
        debt_good = config.get('debt_good') if config.get('debt_good') is not None else 1.0
        debt_moderate = config.get('debt_moderate') if config.get('debt_moderate') is not None else 2.0
        
        inst_own_min = config.get('inst_own_min') if config.get('inst_own_min') is not None else 0.20
        inst_own_max = config.get('inst_own_max') if config.get('inst_own_max') is not None else 0.60
        
        # Extract weights (default to 0 if not present to support dynamic composition)
        weight_peg = config.get('weight_peg') if config.get('weight_peg') is not None else 0.0
        weight_consistency = config.get('weight_consistency') if config.get('weight_consistency') is not None else 0.0
        weight_debt = config.get('weight_debt') if config.get('weight_debt') is not None else 0.0
        weight_ownership = config.get('weight_ownership') if config.get('weight_ownership') is not None else 0.0
        
        # Buffett Weights
        weight_roe = config.get('weight_roe') if config.get('weight_roe') is not None else 0.0
        weight_debt_earnings = config.get('weight_debt_earnings') if config.get('weight_debt_earnings') is not None else 0.0
        weight_gross_margin = config.get('weight_gross_margin') if config.get('weight_gross_margin') is not None else 0.0
        
        # Initialize overall score
        overall_score = pd.Series(0.0, index=df.index)
        
        # --- Lynch Components ---
        
        peg_score = pd.Series(0.0, index=df.index)
        peg_status = pd.Series('N/A', index=df.index)
        if weight_peg > 0:
            peg_score = self._vectorized_peg_score(
                df['peg_ratio'], peg_excellent, peg_good, peg_fair
            )
            overall_score += peg_score * weight_peg
            
            # Determine PEG status (Legacy PASS/CLOSE/FAIL logic)
            peg_conditions = [
                df['peg_ratio'].isna(),
                df['peg_ratio'] <= peg_excellent,
                df['peg_ratio'] <= peg_good,
            ]
            peg_choices = ['FAIL', 'PASS', 'CLOSE']
            peg_status = np.select(peg_conditions, peg_choices, default='FAIL')
        
        debt_score = pd.Series(0.0, index=df.index)
        debt_status = pd.Series('N/A', index=df.index)
        if weight_debt > 0:
            debt_score = self._vectorized_debt_score(
                df['debt_to_equity'], debt_excellent, debt_good, debt_moderate
            )
            overall_score += debt_score * weight_debt
            
            # Determine debt status
            debt_conditions = [
                df['debt_to_equity'].isna(),
                df['debt_to_equity'] <= debt_excellent,
                df['debt_to_equity'] <= debt_good,
            ]
            debt_choices = ['FAIL', 'PASS', 'CLOSE']
            debt_status = np.select(debt_conditions, debt_choices, default='FAIL')
            
        ownership_score = pd.Series(0.0, index=df.index)
        ownership_status = pd.Series('N/A', index=df.index)
        if weight_ownership > 0:
            ownership_score = self._vectorized_ownership_score(
                df['institutional_ownership'], inst_own_min, inst_own_max
            )
            overall_score += ownership_score * weight_ownership
            
            # Determine institutional ownership status
            inst_pass = (df['institutional_ownership'] >= inst_own_min) & (df['institutional_ownership'] <= inst_own_max)
            dist_min = (df['institutional_ownership'] - inst_own_min).abs()
            dist_max = (df['institutional_ownership'] - inst_own_max).abs()
            inst_close = (~inst_pass) & ((dist_min <= 0.05) | (dist_max <= 0.05))
            
            inst_conditions = [
                df['institutional_ownership'].isna(),
                inst_pass,
                inst_close,
            ]
            inst_choices = ['FAIL', 'PASS', 'CLOSE']
            ownership_status = np.select(inst_conditions, inst_choices, default='FAIL')

        # --- Buffett Components ---
        
        roe_score = pd.Series(0.0, index=df.index)
        if weight_roe > 0:
            # ROE Thresholds (fetching from config or defaults)
            roe_excellent = config.get('roe_excellent') if config.get('roe_excellent') is not None else 20.0
            roe_good = config.get('roe_good') if config.get('roe_good') is not None else 15.0
            roe_fair = config.get('roe_fair') if config.get('roe_fair') is not None else 10.0
            
            roe_score = self._vectorized_roe_score(
                df['roe'], roe_excellent, roe_good, roe_fair
            )
            overall_score += roe_score * weight_roe

        debt_earnings_score = pd.Series(0.0, index=df.index)
        if weight_debt_earnings > 0:
            # Debt/Earnings Thresholds
            de_excellent = config.get('de_excellent') if config.get('de_excellent') is not None else 2.0
            de_good = config.get('de_good') if config.get('de_good') is not None else 4.0
            de_fair = config.get('de_fair') if config.get('de_fair') is not None else 7.0
            
            debt_earnings_score = self._vectorized_debt_earnings_score(
                df['debt_to_earnings'], de_excellent, de_good, de_fair
            )
            overall_score += debt_earnings_score * weight_debt_earnings

        gross_margin_score = pd.Series(0.0, index=df.index)
        if weight_gross_margin > 0 and 'gross_margin' in df.columns:
            # Gross Margin Thresholds
            gm_excellent = config.get('gm_excellent') if config.get('gm_excellent') is not None else 50.0
            gm_good = config.get('gm_good') if config.get('gm_good') is not None else 40.0
            gm_fair = config.get('gm_fair') if config.get('gm_fair') is not None else 30.0
            
            gross_margin_score = self._vectorized_gross_margin_score(
                df['gross_margin'], gm_excellent, gm_good, gm_fair
            )
            overall_score += gross_margin_score * weight_gross_margin

        # --- Shared Components ---

        consistency_score = pd.Series(0.0, index=df.index)
        if weight_consistency > 0:
            # Consistency score is already 0-100 normalized, use directly
            # Default to 50 (neutral) for missing values
            consistency_score = df['income_consistency_score'].fillna(50.0)
            overall_score += consistency_score * weight_consistency
        
        # Assign overall status using np.select
        conditions = [
            overall_score >= 80,
            overall_score >= 60,
            overall_score >= 40,
            overall_score >= 20,
        ]
        choices = ['STRONG_BUY', 'BUY', 'HOLD', 'CAUTION']
        overall_status = np.select(conditions, choices, default='AVOID')
        
        # Build result DataFrame with all display fields
        # Include Buffett columns if available
        cols = ['symbol', 'company_name', 'country', 'sector', 'ipo_year',
                'price', 'price_change_pct', 'market_cap', 'pe_ratio', 'peg_ratio',
                'debt_to_equity', 'institutional_ownership', 'dividend_yield',
                'earnings_cagr', 'revenue_cagr',
                'income_consistency_score', 'revenue_consistency_score',
                'pe_52_week_min', 'pe_52_week_max', 'pe_52_week_position']
        
        # Add Buffett metrics if they exist in df
        for col in ['roe', 'debt_to_earnings', 'owner_earnings', 'gross_margin']:
            if col in df.columns:
                cols.append(col)
                
        result = df[cols].copy()
        
        # Add scoring columns
        result['overall_score'] = overall_score.round(1)
        result['overall_status'] = overall_status
        result['peg_score'] = peg_score.round(1)
        result['peg_status'] = peg_status
        result['debt_score'] = debt_score.round(1)
        result['debt_status'] = debt_status
        result['institutional_ownership_score'] = ownership_score.round(1)
        result['institutional_ownership_status'] = ownership_status
        result['consistency_score'] = consistency_score.round(1)
        
        # Add Buffett Scores
        if weight_roe > 0 or weight_debt_earnings > 0 or weight_gross_margin > 0:
            if weight_roe > 0:
                result['roe_score'] = roe_score.round(1)
            if weight_debt_earnings > 0:
                result['debt_earnings_score'] = debt_earnings_score.round(1)
            if weight_gross_margin > 0:
                result['gross_margin_score'] = gross_margin_score.round(1)
        
        # Sort by overall_score descending
        result = result.sort_values('overall_score', ascending=False)
        
        return result
    
    def _vectorized_peg_score(self, peg: pd.Series, excellent: float, good: float, fair: float) -> pd.Series:
        """
        Vectorized version of calculate_peg_score().
        
        Mirrors the exact interpolation logic from lines 800-829.
        """
        result = pd.Series(0.0, index=peg.index)
        
        # Excellent: 100
        mask_excellent = peg <= excellent
        result[mask_excellent] = 100.0
        
        # Good: 75-100 (interpolate)
        mask_good = (peg > excellent) & (peg <= good)
        if mask_good.any():
            range_size = good - excellent
            position = (good - peg[mask_good]) / range_size
            result[mask_good] = 75.0 + (25.0 * position)
        
        # Fair: 25-75 (interpolate)
        mask_fair = (peg > good) & (peg <= fair)
        if mask_fair.any():
            range_size = fair - good
            position = (fair - peg[mask_fair]) / range_size
            result[mask_fair] = 25.0 + (50.0 * position)
        
        # Poor: 0-25 (interpolate up to max of 4.0)
        max_poor = 4.0
        mask_poor = (peg > fair) & (peg < max_poor)
        if mask_poor.any():
            range_size = max_poor - fair
            position = (max_poor - peg[mask_poor]) / range_size
            result[mask_poor] = 25.0 * position
        
        # Very poor: 0
        result[peg >= max_poor] = 0.0
        
        # Handle None/NaN - score is 0 for missing PEG
        result[peg.isna()] = 0.0
        
        return result
    
    def _vectorized_debt_score(self, debt: pd.Series, excellent: float, good: float, moderate: float) -> pd.Series:
        """
        Vectorized version of calculate_debt_score().

        Excellent (0-excellent): 100
        Good (excellent-good): 75-100
        Moderate (good-moderate): 25-75
        High (moderate+): 0-25
        """
        result = pd.Series(100.0, index=debt.index)  # Default for None (no debt is great)
        
        # Excellent: 100
        mask_excellent = debt <= excellent
        result[mask_excellent] = 100.0
        
        # Good: 75-100 (interpolate)
        mask_good = (debt > excellent) & (debt <= good)
        if mask_good.any():
            range_size = good - excellent
            position = (good - debt[mask_good]) / range_size
            result[mask_good] = 75.0 + (25.0 * position)
        
        # Moderate: 25-75 (interpolate)
        mask_moderate = (debt > good) & (debt <= moderate)
        if mask_moderate.any():
            range_size = moderate - good
            position = (moderate - debt[mask_moderate]) / range_size
            result[mask_moderate] = 25.0 + (50.0 * position)
        
        # High: 0-25 (interpolate up to max of 5.0)
        max_high = 5.0
        mask_high = (debt > moderate) & (debt < max_high)
        if mask_high.any():
            range_size = max_high - moderate
            position = (max_high - debt[mask_high]) / range_size
            result[mask_high] = 25.0 * position
        
        # Very high: 0
        result[debt >= max_high] = 0.0

        # None/NaN means no debt reported, which is great
        result[debt.isna()] = 100.0

        return result
    
    def _vectorized_ownership_score(self, ownership: pd.Series, min_thresh: float, max_thresh: float) -> pd.Series:
        """
        Vectorized version of calculate_institutional_ownership_score().

        Sweet spot (min-max): 100
        Under-owned (< min): 50-100 (interpolated)
        Over-owned (> max): 0-50 (interpolated down to 0 at 100% ownership)
        """
        # Default to neutral (75) for missing values
        result = pd.Series(75.0, index=ownership.index)

        # Sweet spot: full score
        mask_ideal = (ownership >= min_thresh) & (ownership <= max_thresh)
        result[mask_ideal] = 100.0

        # Under-owned (< min): 50-100 interpolated
        # Lower ownership is okay but not ideal
        mask_low = (ownership < min_thresh) & (ownership >= 0) & ownership.notna()
        if mask_low.any():
            # Score = 50 + (value / min_thresh) * 50
            # At 0% ownership: 50, at min_thresh: 100
            result[mask_low] = 50.0 + (ownership[mask_low] / min_thresh) * 50.0

        # Over-owned (> max): 0-50 interpolated
        # Too much institutional ownership is bad (overcrowded)
        mask_high = (ownership > max_thresh) & (ownership < 1.0) & ownership.notna()
        if mask_high.any():
            # Score = 50 * (1.0 - value) / (1.0 - max_thresh)
            # At max_thresh: 50, at 100% ownership: 0
            range_size = 1.0 - max_thresh
            result[mask_high] = 50.0 * (1.0 - ownership[mask_high]) / range_size

        # At 100% ownership: 0
        result[ownership >= 1.0] = 0.0

        return result
    
    def _vectorized_roe_score(self, roe: pd.Series, excellent: float, good: float, fair: float) -> pd.Series:
        """
        Vectorized ROE score (Higher is Better).
        excellent (20) -> 100
        good (15) -> 75
        fair (10) -> 50
        poor (0) -> 25
        """
        result = pd.Series(50.0, index=roe.index) # Default neutral
        
        # Excellent: 100
        mask_exc = roe >= excellent
        result[mask_exc] = 100.0
        
        # Good: 75-100
        mask_good = (roe >= good) & (roe < excellent)
        if mask_good.any():
            rng = excellent - good
            pos = (roe[mask_good] - good) / rng
            result[mask_good] = 75.0 + (25.0 * pos)
            
        # Fair: 50-75
        mask_fair = (roe >= fair) & (roe < good)
        if mask_fair.any():
            rng = good - fair
            pos = (roe[mask_fair] - fair) / rng
            result[mask_fair] = 50.0 + (25.0 * pos)
            
        # Poor: 25-50
        mask_poor = (roe >= 0) & (roe < fair)
        if mask_poor.any():
            rng = fair
            pos = roe[mask_poor] / rng
            result[mask_poor] = 25.0 + (25.0 * pos)
            
        # Negative: 0-25
        mask_neg = roe < 0
        result[mask_neg] = 0.0
        
        return result

    def _vectorized_debt_earnings_score(self, de: pd.Series, excellent: float, good: float, fair: float) -> pd.Series:
        """
        Vectorized Debt/Earnings score (Lower is Better).
        excellent (2.0) -> 100
        good (4.0) -> 75
        fair (7.0) -> 50
        poor -> 25
        """
        result = pd.Series(50.0, index=de.index) 
        
        # Excellent
        mask_exc = de <= excellent
        result[mask_exc] = 100.0
        
        # Good: 75-100
        mask_good = (de > excellent) & (de <= good)
        if mask_good.any():
            rng = good - excellent
            pos = (good - de[mask_good]) / rng
            result[mask_good] = 75.0 + (25.0 * pos)
            
        # Fair: 50-75
        mask_fair = (de > good) & (de <= fair)
        if mask_fair.any():
            rng = fair - good
            pos = (fair - de[mask_fair]) / rng
            result[mask_fair] = 50.0 + (25.0 * pos)
            
        # Poor: 0-50
        # Let's say max reasonable is 10.0
        max_poor = 10.0
        mask_poor = (de > fair) & (de < max_poor)
        if mask_poor.any():
            rng = max_poor - fair
            pos = (max_poor - de[mask_poor]) / rng
            result[mask_poor] = 25.0 * pos
            
        result[de >= max_poor] = 0.0
        
        return result
    def _vectorized_gross_margin_score(self, gm: pd.Series, excellent: float, good: float, fair: float) -> pd.Series:
        """
        Vectorized Gross Margin score (Higher is Better).
        Similar to ROE scoring - higher margins indicate pricing power and competitive advantage.
        
        excellent (50%) -> 100
        good (40%) -> 75
        fair (30%) -> 50
        poor (0%) -> 25
        """
        result = pd.Series(50.0, index=gm.index)  # Default neutral
        
        # Excellent: 100
        mask_exc = gm >= excellent
        result[mask_exc] = 100.0
        
        # Good: 75-100
        mask_good = (gm >= good) & (gm < excellent)
        if mask_good.any():
            rng = excellent - good
            pos = (gm[mask_good] - good) / rng
            result[mask_good] = 75.0 + (25.0 * pos)
        
        # Fair: 50-75
        mask_fair = (gm >= fair) & (gm < good)
        if mask_fair.any():
            rng = good - fair
            pos = (gm[mask_fair] - fair) / rng
            result[mask_fair] = 50.0 + (25.0 * pos)
        
        # Poor: 25-50
        mask_poor = (gm >= 0) & (gm < fair)
        if mask_poor.any():
            pos = gm[mask_poor] / fair
            result[mask_poor] = 25.0 + (25.0 * pos)
        
        # Negative margins: 0
        result[gm < 0] = 0.0
        
        # None/NaN gets 50 (neutral default)
        result[gm.isna()] = 50.0
        
        return result
