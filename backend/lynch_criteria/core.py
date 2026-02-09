# ABOUTME: Core evaluation logic for Lynch investment criteria scoring.
# ABOUTME: Contains initialization, settings management, metric gathering, and weighted scoring.

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from database import Database
from earnings_analyzer import EarningsAnalyzer

logger = logging.getLogger(__name__)


# Algorithm metadata for UI display


SCORE_THRESHOLDS = {
    'STRONG_BUY': 80,
    'BUY': 60,
    'HOLD': 40,
    'CAUTION': 20
}


class LynchCriteriaCore:
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


def normalize_consistency(raw_value):
    if raw_value is None:
        return None
    # Formula: 100 - (std_dev * 2), capped at 0
    return max(0.0, 100.0 - (raw_value * 2.0))
