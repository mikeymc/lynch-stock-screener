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
    },
    'two_tier': {
        'name': 'Two-Tier System',
        'short_desc': 'Must-have deal-breakers plus nice-to-have scoring for quality checks',
        'description': '''First checks critical deal-breakers, then scores on quality metrics:

        Must-Have Criteria (automatic AVOID if failed):
        • PEG Ratio < 2.0 (Lynch's outer limit)
        • Debt-to-Equity < 1.0 (manageable debt)

        Nice-to-Have Scoring (if passed must-haves):
        • PEG < 1.0 (ideal territory)
        • Strong earnings consistency
        • Moderate institutional ownership

        Best for: Conservative investors who want clear deal-breaker rules.''',
        'recommended': False
    },
    'category_based': {
        'name': 'Category-Based',
        'short_desc': 'Different criteria for different stock types (fast growers, stalwarts, etc.)',
        'description': '''Classifies stocks by Lynch's categories, then applies appropriate criteria:

        • Fast Growers: Emphasis on PEG < 1.0, earnings growth, low debt
        • Stalwarts: Allow higher PEG (up to 1.5), focus on consistency
        • Cyclicals: Consider P/E vs historical average, allow more debt
        • Turnarounds: Different criteria focused on improvement trajectory
        • Asset Plays: Focus on book value and asset coverage

        Each category uses different thresholds and weights tailored to that investment type.
        Best for: Sophisticated investors who understand different stock categories.''',
        'recommended': False
    },
    'critical_factors': {
        'name': 'Critical Factors',
        'short_desc': 'Simplified qualitative assessment of only the most important factors',
        'description': '''Simplified approach focusing on Lynch's core principles:

        • PEG acceptability (contextual, not rigid threshold)
        • Positive earnings trend (growth trajectory matters)
        • Manageable debt (industry-relative assessment)
        • The "story" makes sense (qualitative evaluation)

        More qualitative and flexible than pure numbers. Uses broader ranges and contextual judgment.
        Best for: Quick screening and investors who prefer simpler, story-based evaluation.''',
        'recommended': False
    },
    'classic': {
        'name': 'Classic (Original)',
        'short_desc': 'Original rigid pass/fail system requiring all metrics to pass',
        'description': '''The original strict evaluation system:

        • PASS: All three metrics (PEG, Debt, Institutional Ownership) must PASS
        • FAIL: If ANY single metric FAILS, the entire stock FAILS
        • CLOSE: Some metrics PASS, some CLOSE (no FAILs)

        Thresholds: PEG < 1.0, Debt/Equity < 0.5, Institutional < 50%

        Best for: Very conservative screening with strict requirements.
        Note: May be too rigid for Lynch's actual philosophy.''',
        'recommended': False
    }
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
                'peg_excellent': {'value': algo_config.get('peg_excellent', 1.0)},
                'peg_good': {'value': algo_config.get('peg_good', 1.5)},
                'peg_fair': {'value': algo_config.get('peg_fair', 2.0)},
                'debt_excellent': {'value': algo_config.get('debt_excellent', 0.5)},
                'debt_good': {'value': algo_config.get('debt_good', 1.0)},
                'debt_moderate': {'value': algo_config.get('debt_moderate', 2.0)},
                'inst_own_min': {'value': algo_config.get('inst_own_min', 0.20)},
                'inst_own_max': {'value': algo_config.get('inst_own_max', 0.60)},
                'revenue_growth_excellent': {'value': algo_config.get('revenue_growth_excellent', 15.0)},
                'revenue_growth_good': {'value': algo_config.get('revenue_growth_good', 10.0)},
                'revenue_growth_fair': {'value': algo_config.get('revenue_growth_fair', 5.0)},
                'income_growth_excellent': {'value': algo_config.get('income_growth_excellent', 15.0)},
                'income_growth_good': {'value': algo_config.get('income_growth_good', 10.0)},
                'income_growth_fair': {'value': algo_config.get('income_growth_fair', 5.0)},
                'weight_peg': {'value': algo_config.get('weight_peg', 0.50)},
                'weight_consistency': {'value': algo_config.get('weight_consistency', 0.25)},
                'weight_debt': {'value': algo_config.get('weight_debt', 0.15)},
                'weight_ownership': {'value': algo_config.get('weight_ownership', 0.10)},
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

    def evaluate_stock(self, symbol: str, algorithm: str = 'weighted', overrides: Dict[str, float] = None, custom_metrics: Dict[str, Any] = None, stock_metrics: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Evaluate a stock using the specified algorithm.

        Checks the active character setting and routes to character-specific
        evaluation when appropriate.

        Args:
            symbol: Stock ticker symbol
            algorithm: One of 'weighted', 'two_tier', 'category_based', 'critical_factors', 'classic'
            stock_metrics: Optional pre-fetched stock metrics to avoid re-querying DB

        Returns:
            Dictionary with evaluation results including algorithm-specific scoring
        """
        # Check active character - delegate to StockEvaluator for non-Lynch characters
        active_character = self._get_active_character()
        if active_character != 'lynch':
            return self._evaluate_with_character(symbol, active_character)

        # Lynch evaluation (original logic)
        # Get base metrics and growth data
        if custom_metrics:
            base_data = custom_metrics
        else:
            base_data = self._get_base_metrics(symbol, stock_metrics=stock_metrics)

        if not base_data:
            return None

        # Route to appropriate algorithm
        if algorithm == 'weighted':
            return self._evaluate_weighted(symbol, base_data, overrides)
        elif algorithm == 'two_tier':
            return self._evaluate_two_tier(symbol, base_data)
        elif algorithm == 'category_based':
            return self._evaluate_category_based(symbol, base_data)
        elif algorithm == 'critical_factors':
            return self._evaluate_critical_factors(symbol, base_data)
        elif algorithm == 'classic':
            return self._evaluate_classic(symbol, base_data)
        else:
            # Default to weighted if unknown algorithm
            return self._evaluate_weighted(symbol, base_data, overrides)

    def _get_active_character(self) -> str:
        """Get the currently active investment character from settings."""
        try:
            setting = self.db.get_setting('active_character')
            return setting['value'] if setting else 'lynch'
        except Exception:
            return 'lynch'

    def _evaluate_with_character(self, symbol: str, character_id: str) -> Optional[Dict[str, Any]]:
        """Evaluate a stock using a non-Lynch character via StockEvaluator."""
        try:
            from stock_evaluator import StockEvaluator
            from characters import get_character

            character = get_character(character_id)
            if not character:
                logger.warning(f"Character not found: {character_id}, falling back to Lynch")
                return None

            evaluator = StockEvaluator(self.db, self.analyzer, character)
            return evaluator.evaluate_stock(symbol)
        except Exception as e:
            logger.error(f"Error evaluating with character {character_id}: {e}")
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

    def _evaluate_classic(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Original strict pass/fail algorithm - all metrics must pass."""
        statuses = [base_data['peg_status'], base_data['debt_status'], base_data['institutional_ownership_status']]

        if all(s == "PASS" for s in statuses):
            overall_status = "PASS"
        elif any(s == "FAIL" for s in statuses):
            overall_status = "FAIL"
        else:
            overall_status = "CLOSE"

        result = base_data.copy()
        result['algorithm'] = 'classic'
        result['overall_status'] = overall_status
        result['overall_score'] = self._status_to_score(overall_status)
        result['rating_label'] = overall_status
        return result

    def _evaluate_weighted(self, symbol: str, base_data: Dict[str, Any], overrides: Dict[str, float] = None) -> Dict[str, Any]:
        """Weighted scoring: PEG 50%, Consistency 25%, Debt 15%, Ownership 10%.
        
        When overrides are provided with threshold values, component scores are
        recalculated from raw metrics to ensure consistency with optimizer.
        """
        # Get weights (from overrides or defaults)
        if overrides:
            peg_weight = overrides.get('weight_peg', self.settings['weight_peg']['value'])
            consistency_weight = overrides.get('weight_consistency', self.settings['weight_consistency']['value'])
            debt_weight = overrides.get('weight_debt', self.settings['weight_debt']['value'])
            ownership_weight = overrides.get('weight_ownership', self.settings['weight_ownership']['value'])
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
            peg_excellent = overrides.get('peg_excellent', self.peg_excellent)
            peg_good = overrides.get('peg_good', self.peg_good)
            peg_fair = overrides.get('peg_fair', self.peg_fair)
            peg_score = self._calculate_peg_score_with_thresholds(peg_ratio, peg_excellent, peg_good, peg_fair)
            
            # Debt score with threshold overrides
            debt_to_equity = base_data.get('debt_to_equity')
            debt_excellent = overrides.get('debt_excellent', self.debt_excellent)
            debt_good = overrides.get('debt_good', self.debt_good)
            debt_moderate = overrides.get('debt_moderate', self.debt_moderate)
            debt_score = self._calculate_debt_score_with_thresholds(debt_to_equity, debt_excellent, debt_good, debt_moderate)
            
            # Institutional ownership score with threshold overrides
            inst_own = base_data.get('institutional_ownership')
            inst_own_min = overrides.get('inst_own_min', self.inst_own_min)
            inst_own_max = overrides.get('inst_own_max', self.inst_own_max)
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
        if overall_score >= 80:
            rating_label = "STRONG BUY"
            overall_status = "STRONG_BUY"
        elif overall_score >= 60:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= 40:
            rating_label = "HOLD"
            overall_status = "HOLD"
        elif overall_score >= 20:
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

    def _evaluate_two_tier(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Two-tier: Must-have criteria first, then nice-to-have scoring."""
        # Must-have criteria (deal breakers)
        peg_ratio = base_data.get('peg_ratio')
        debt_to_equity = base_data.get('debt_to_equity', 0)

        # Check deal breakers
        deal_breakers = []
        if peg_ratio is None or peg_ratio > 2.0:
            deal_breakers.append('PEG > 2.0')
        if debt_to_equity > 1.0:
            deal_breakers.append('Debt/Equity > 1.0')

        if deal_breakers:
            # Failed must-haves = automatic AVOID
            result = base_data.copy()
            result['algorithm'] = 'two_tier'
            result['overall_score'] = 0
            result['overall_status'] = 'AVOID'
            result['rating_label'] = 'AVOID'
            result['breakdown'] = {
                'passed_must_haves': False,
                'deal_breakers': deal_breakers
            }
            return result

        # Passed must-haves, now score on nice-to-haves
        # PEG < 1.0: 40 points, Consistency: 30 points, Ownership: 30 points
        peg_nice_score = 40 if peg_ratio <= 1.0 else max(0, 40 * (2.0 - peg_ratio) / 1.0)
        consistency_score = base_data.get('consistency_score', 50) if base_data.get('consistency_score') is not None else 50
        consistency_nice_score = (consistency_score / 100) * 30
        ownership_nice_score = (base_data['institutional_ownership_score'] / 100) * 30

        overall_score = peg_nice_score + consistency_nice_score + ownership_nice_score

        # Determine rating
        if overall_score >= 80:
            rating_label = "STRONG BUY"
            overall_status = "STRONG_BUY"
        elif overall_score >= 60:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= 40:
            rating_label = "HOLD"
            overall_status = "HOLD"
        else:
            rating_label = "CAUTION"
            overall_status = "CAUTION"

        result = base_data.copy()
        result['algorithm'] = 'two_tier'
        result['overall_score'] = round(overall_score, 1)
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        result['breakdown'] = {
            'passed_must_haves': True,
            'peg_nice_score': round(peg_nice_score, 1),
            'consistency_nice_score': round(consistency_nice_score, 1),
            'ownership_nice_score': round(ownership_nice_score, 1)
        }
        return result

    def _evaluate_category_based(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Category-based: Classify stock type, then apply appropriate criteria."""
        # Classify stock category based on Lynch's categories
        earnings_cagr = base_data.get('earnings_cagr')
        revenue_cagr = base_data.get('revenue_cagr')
        peg_ratio = base_data.get('peg_ratio')
        debt_to_equity = base_data.get('debt_to_equity', 0)
        dividend_yield = base_data.get('dividend_yield', 0)

        # Simple category classification logic
        category = self._classify_stock_category(earnings_cagr, revenue_cagr, dividend_yield, base_data.get('market_cap'))

        # Apply category-specific scoring
        if category == 'fast_grower':
            # Fast Growers: Emphasize PEG < 1.0, high growth, low debt
            peg_threshold = 1.0
            debt_threshold = 0.4
            peg_weight = 0.60
            growth_weight = 0.30
            debt_weight = 0.10
        elif category == 'stalwart':
            # Stalwarts: Allow higher PEG, focus on consistency
            peg_threshold = 1.5
            debt_threshold = 0.6
            peg_weight = 0.40
            growth_weight = 0.40
            debt_weight = 0.20
        elif category == 'cyclical':
            # Cyclicals: Allow more debt, focus on current valuation
            peg_threshold = 1.2
            debt_threshold = 0.8
            peg_weight = 0.50
            growth_weight = 0.20
            debt_weight = 0.30
        else:  # slow_grower or other
            # Conservative approach
            peg_threshold = 1.0
            debt_threshold = 0.5
            peg_weight = 0.50
            growth_weight = 0.25
            debt_weight = 0.25

        # Calculate category-specific scores
        peg_category_score = 100 if peg_ratio and peg_ratio <= peg_threshold else (base_data['peg_score'] * 0.8)
        debt_category_score = 100 if debt_to_equity and debt_to_equity <= debt_threshold else (base_data['debt_score'] * 0.8)
        consistency_score = base_data.get('consistency_score', 50) if base_data.get('consistency_score') is not None else 50

        overall_score = (
            peg_category_score * peg_weight +
            consistency_score * growth_weight +
            debt_category_score * debt_weight
        )

        # Determine rating
        if overall_score >= 80:
            rating_label = "STRONG BUY"
            overall_status = "STRONG_BUY"
        elif overall_score >= 60:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= 40:
            rating_label = "HOLD"
            overall_status = "HOLD"
        elif overall_score >= 20:
            rating_label = "CAUTION"
            overall_status = "CAUTION"
        else:
            rating_label = "AVOID"
            overall_status = "AVOID"

        result = base_data.copy()
        result['algorithm'] = 'category_based'
        result['overall_score'] = round(overall_score, 1)
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        result['stock_category'] = category
        result['breakdown'] = {
            'category': category,
            'peg_threshold': peg_threshold,
            'debt_threshold': debt_threshold,
            'peg_contribution': round(peg_category_score * peg_weight, 1),
            'growth_contribution': round(consistency_score * growth_weight, 1),
            'debt_contribution': round(debt_category_score * debt_weight, 1)
        }
        return result

    def _evaluate_critical_factors(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Critical factors: Simplified qualitative assessment."""
        peg_ratio = base_data.get('peg_ratio')
        earnings_cagr = base_data.get('earnings_cagr')
        debt_to_equity = base_data.get('debt_to_equity', 0)

        # Simple scoring based on critical factors
        score_components = []
        reasons = []

        # Factor 1: PEG acceptability (0-40 points)
        if peg_ratio is None:
            peg_points = 0
            reasons.append("No PEG ratio available")
        elif peg_ratio <= 1.0:
            peg_points = 40
            reasons.append(f"Excellent PEG ratio ({peg_ratio:.2f})")
        elif peg_ratio <= 1.5:
            peg_points = 30
            reasons.append(f"Good PEG ratio ({peg_ratio:.2f})")
        elif peg_ratio <= 2.0:
            peg_points = 20
            reasons.append(f"Acceptable PEG ratio ({peg_ratio:.2f})")
        else:
            peg_points = 0
            reasons.append(f"High PEG ratio ({peg_ratio:.2f})")

        # Factor 2: Earnings trend (0-35 points)
        if earnings_cagr is None:
            earnings_points = 15
            reasons.append("No earnings growth data")
        elif earnings_cagr >= 20:
            earnings_points = 35
            reasons.append(f"Strong earnings growth ({earnings_cagr:.1f}%)")
        elif earnings_cagr >= 10:
            earnings_points = 25
            reasons.append(f"Good earnings growth ({earnings_cagr:.1f}%)")
        elif earnings_cagr > 0:
            earnings_points = 15
            reasons.append(f"Positive earnings growth ({earnings_cagr:.1f}%)")
        else:
            earnings_points = 0
            reasons.append(f"Negative earnings growth ({earnings_cagr:.1f}%)")

        # Factor 3: Manageable debt (0-25 points)
        if debt_to_equity <= 0.3:
            debt_points = 25
            reasons.append(f"Minimal debt ({debt_to_equity:.2f})")
        elif debt_to_equity <= 0.6:
            debt_points = 20
            reasons.append(f"Moderate debt ({debt_to_equity:.2f})")
        elif debt_to_equity <= 1.0:
            debt_points = 10
            reasons.append(f"Elevated debt ({debt_to_equity:.2f})")
        else:
            debt_points = 0
            reasons.append(f"High debt ({debt_to_equity:.2f})")

        overall_score = peg_points + earnings_points + debt_points

        # Simple rating
        if overall_score >= 75:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= 50:
            rating_label = "HOLD"
            overall_status = "HOLD"
        else:
            rating_label = "AVOID"
            overall_status = "AVOID"

        result = base_data.copy()
        result['algorithm'] = 'critical_factors'
        result['overall_score'] = overall_score
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        result['breakdown'] = {
            'peg_points': peg_points,
            'earnings_points': earnings_points,
            'debt_points': debt_points,
            'reasons': reasons
        }
        return result

    def _classify_stock_category(self, earnings_cagr, revenue_cagr, dividend_yield, market_cap):
        """Classify stock into Lynch's categories."""
        if earnings_cagr is None:
            return 'unknown'

        # Fast Grower: High growth (20%+), usually smaller companies
        if earnings_cagr >= 20:
            return 'fast_grower'
        # Stalwart: Moderate growth (10-20%), usually large established companies
        elif earnings_cagr >= 10:
            return 'stalwart'
        # Slow Grower: Low growth (<10%), often pays dividends
        elif earnings_cagr >= 0:
            return 'slow_grower'
        # Potential turnaround: Negative growth
        else:
            return 'turnaround'

    def _status_to_score(self, status: str) -> float:
        """Convert old PASS/CLOSE/FAIL status to numeric score for compatibility."""
        if status == "PASS":
            return 80.0
        elif status == "CLOSE":
            return 60.0
        else:
            return 20.0

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
        if value <= self.peg_excellent:
            return "PASS"
        elif value <= self.peg_good:
            return "CLOSE"
        else:
            return "FAIL"

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
        if value <= self.peg_excellent:
            return 100.0
        elif value <= self.peg_good:
            # 75-100 range
            range_size = self.peg_good - self.peg_excellent
            position = (self.peg_good - value) / range_size
            return 75.0 + (25.0 * position)
        elif value <= self.peg_fair:
            # 25-75 range
            range_size = self.peg_fair - self.peg_good
            position = (self.peg_fair - value) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 4.0
            max_poor = 4.0
            if value >= max_poor:
                return 0.0
            range_size = max_poor - self.peg_fair
            position = (max_poor - value) / range_size
            return 25.0 * position

    def evaluate_debt(self, value: float) -> str:
        """Evaluate Debt to Equity: lower is better"""
        if value is None:
            return "FAIL"
        if value <= self.debt_excellent:
            return "PASS"
        elif value <= self.debt_good:
            return "CLOSE"
        else:
            return "FAIL"

    def calculate_debt_score(self, value: float) -> float:
        """
        Calculate Debt score (0-100).
        Excellent (0-0.5): 100
        Good (0.5-1.0): 75-100
        Moderate (1.0-2.0): 25-75
        High (2.0+): 0-25
        """
        if value is None:
            return 0.0
        if value <= self.debt_excellent:
            return 100.0
        elif value <= self.debt_good:
            # 75-100 range
            range_size = self.debt_good - self.debt_excellent
            position = (self.debt_good - value) / range_size
            return 75.0 + (25.0 * position)
        elif value <= self.debt_moderate:
            # 25-75 range
            range_size = self.debt_moderate - self.debt_good
            position = (self.debt_moderate - value) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 5.0
            max_high = 5.0
            if value >= max_high:
                return 0.0
            range_size = max_high - self.debt_moderate
            position = (max_high - value) / range_size
            return 25.0 * position

    def evaluate_institutional_ownership(self, value: float) -> str:
        """Evaluate Institutional Ownership: sweet spot in middle (20%-60%)"""
        if value is None:
            return "FAIL"
        if self.inst_own_min <= value <= self.inst_own_max:
            return "PASS"
        else:
            # Check if it's close to either boundary (within 5 percentage points)
            close_to_min = abs(value - self.inst_own_min) <= 0.05
            close_to_max = abs(value - self.inst_own_max) <= 0.05
            if close_to_min or close_to_max:
                return "CLOSE"
            return "FAIL"

    def calculate_institutional_ownership_score(self, value: float) -> float:
        """
        Calculate Institutional Ownership score (0-100).
        Sweet spot (20%-60%): 100 at center (40%), tapering to 75 at edges
        Too low (0-20%): 0-75
        Too high (60%-100%): 75-0
        """
        if value is None:
            return 0.0

        # Ideal range: peak at center of min/max
        ideal_center = (self.inst_own_min + self.inst_own_max) / 2

        if self.inst_own_min <= value <= self.inst_own_max:
            # In ideal range: score 75-100
            # Calculate distance from center
            distance_from_center = abs(value - ideal_center)
            max_distance = ideal_center - self.inst_own_min
            position = 1.0 - (distance_from_center / max_distance)
            return 75.0 + (25.0 * position)
        elif value < self.inst_own_min:
            # Too low: 0-75
            if value <= 0:
                return 0.0
            position = value / self.inst_own_min
            return 75.0 * position
        else:
            # Too high: 75-0
            if value >= 1.0:
                return 0.0
            range_size = 1.0 - self.inst_own_max
            position = (1.0 - value) / range_size
            return 75.0 * position

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
        
        if value >= self.revenue_growth_excellent:
            return 100.0
        elif value >= self.revenue_growth_good:
            # 75-100 range
            range_size = self.revenue_growth_excellent - self.revenue_growth_good
            position = (value - self.revenue_growth_good) / range_size
            return 75.0 + (25.0 * position)
        elif value >= self.revenue_growth_fair:
            # 25-75 range
            range_size = self.revenue_growth_good - self.revenue_growth_fair
            position = (value - self.revenue_growth_fair) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range
            if value <= 0:
                return 0.0
            position = value / self.revenue_growth_fair
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
        
        if value >= self.income_growth_excellent:
            return 100.0
        elif value >= self.income_growth_good:
            # 75-100 range
            range_size = self.income_growth_excellent - self.income_growth_good
            position = (value - self.income_growth_good) / range_size
            return 75.0 + (25.0 * position)
        elif value >= self.income_growth_fair:
            # 25-75 range
            range_size = self.income_growth_good - self.income_growth_fair
            position = (value - self.income_growth_fair) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range
            if value <= 0:
                return 0.0
            position = value / self.income_growth_fair
            return 25.0 * position

    # ========== Threshold-aware scoring methods (for optimizer overrides) ==========
    
    def _calculate_peg_score_with_thresholds(self, value: float, excellent: float, good: float, fair: float) -> float:
        """Calculate PEG score using custom thresholds (for optimizer overrides)"""
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
        """Calculate debt score using custom thresholds (for optimizer overrides)"""
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
        """Calculate institutional ownership score using custom thresholds (for optimizer overrides)"""
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
        peg_excellent = config.get('peg_excellent', 1.0)
        peg_good = config.get('peg_good', 1.5)
        peg_fair = config.get('peg_fair', 2.0)
        
        debt_excellent = config.get('debt_excellent', 0.5)
        debt_good = config.get('debt_good', 1.0)
        debt_moderate = config.get('debt_moderate', 2.0)
        
        inst_own_min = config.get('inst_own_min', 0.20)
        inst_own_max = config.get('inst_own_max', 0.60)
        
        # Extract weights
        weight_peg = config.get('weight_peg', 0.50)
        weight_consistency = config.get('weight_consistency', 0.25)
        weight_debt = config.get('weight_debt', 0.15)
        weight_ownership = config.get('weight_ownership', 0.10)
        
        # Calculate component scores using vectorized methods
        peg_score = self._vectorized_peg_score(
            df['peg_ratio'], peg_excellent, peg_good, peg_fair
        )
        
        debt_score = self._vectorized_debt_score(
            df['debt_to_equity'], debt_excellent, debt_good, debt_moderate
        )
        
        ownership_score = self._vectorized_ownership_score(
            df['institutional_ownership'], inst_own_min, inst_own_max
        )
        
        # Consistency score is already 0-100 normalized, use directly
        # Default to 50 (neutral) for missing values
        consistency_score = df['income_consistency_score'].fillna(50.0)
        
        # Calculate overall score (weighted sum)
        overall_score = (
            peg_score * weight_peg +
            consistency_score * weight_consistency +
            debt_score * weight_debt +
            ownership_score * weight_ownership
        )
        
        # Assign overall status using np.select (matches _evaluate_weighted)
        conditions = [
            overall_score >= 80,
            overall_score >= 60,
            overall_score >= 40,
            overall_score >= 20,
        ]
        choices = ['STRONG_BUY', 'BUY', 'HOLD', 'CAUTION']
        overall_status = np.select(conditions, choices, default='AVOID')
        
        # Determine PEG status (Legacy PASS/CLOSE/FAIL logic)
        peg_conditions = [
            df['peg_ratio'].isna(),
            df['peg_ratio'] <= peg_excellent,
            df['peg_ratio'] <= peg_good,
        ]
        peg_choices = ['FAIL', 'PASS', 'CLOSE']
        peg_status = np.select(peg_conditions, peg_choices, default='FAIL')
        
        # Determine debt status (Legacy PASS/CLOSE/FAIL logic)
        debt_conditions = [
            df['debt_to_equity'].isna(),
            df['debt_to_equity'] <= debt_excellent,
            df['debt_to_equity'] <= debt_good,
        ]
        debt_choices = ['FAIL', 'PASS', 'CLOSE']
        debt_status = np.select(debt_conditions, debt_choices, default='FAIL')
        
        # Determine institutional ownership status (Legacy PASS/CLOSE/FAIL logic)
        # PASS: Inside the sweet spot (min-max)
        inst_pass = (df['institutional_ownership'] >= inst_own_min) & (df['institutional_ownership'] <= inst_own_max)
        
        # CLOSE: Within 5% of boundaries (only if not passing)
        dist_min = (df['institutional_ownership'] - inst_own_min).abs()
        dist_max = (df['institutional_ownership'] - inst_own_max).abs()
        inst_close = (~inst_pass) & ((dist_min <= 0.05) | (dist_max <= 0.05))
        
        inst_conditions = [
            df['institutional_ownership'].isna(),
            inst_pass,
            inst_close,
        ]
        inst_choices = ['FAIL', 'PASS', 'CLOSE']
        inst_status = np.select(inst_conditions, inst_choices, default='FAIL')
        
        # Build result DataFrame with all display fields
        result = df[['symbol', 'company_name', 'country', 'sector', 'ipo_year',
                     'price', 'market_cap', 'pe_ratio', 'peg_ratio', 
                     'debt_to_equity', 'institutional_ownership', 'dividend_yield',
                     'earnings_cagr', 'revenue_cagr', 
                     'income_consistency_score', 'revenue_consistency_score',
                     'pe_52_week_min', 'pe_52_week_max', 'pe_52_week_position']].copy()
        
        # Add scoring columns
        result['overall_score'] = overall_score.round(1)
        result['overall_status'] = overall_status
        result['peg_score'] = peg_score.round(1)
        result['peg_status'] = peg_status
        result['debt_score'] = debt_score.round(1)
        result['debt_status'] = debt_status
        result['institutional_ownership_score'] = ownership_score.round(1)
        result['institutional_ownership_status'] = inst_status
        result['consistency_score'] = consistency_score.round(1)
        
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
        
        Mirrors the exact interpolation logic from lines 842-871.
        """
        result = pd.Series(50.0, index=debt.index)  # Default for None
        
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
        
        # None/NaN gets neutral score
        result[debt.isna()] = 50.0
        
        return result
    
    def _vectorized_ownership_score(self, ownership: pd.Series, min_thresh: float, max_thresh: float) -> pd.Series:
        """
        Vectorized version of calculate_institutional_ownership_score().
        
        Mirrors the exact interpolation logic from lines 887-919.
        Sweet spot is between min_thresh and max_thresh.
        """
        result = pd.Series(0.0, index=ownership.index)
        
        ideal_center = (min_thresh + max_thresh) / 2
        
        # Ideal range: 75-100 (interpolate based on distance from center)
        mask_ideal = (ownership >= min_thresh) & (ownership <= max_thresh)
        if mask_ideal.any():
            distance_from_center = (ownership[mask_ideal] - ideal_center).abs()
            max_distance = ideal_center - min_thresh
            position = 1.0 - (distance_from_center / max_distance)
            result[mask_ideal] = 75.0 + (25.0 * position)
        
        # Below minimum: 0-75 (interpolate)
        mask_low = (ownership < min_thresh) & (ownership > 0)
        if mask_low.any():
            position = ownership[mask_low] / min_thresh
            result[mask_low] = 75.0 * position
        
        # Above maximum: 0-75 (interpolate up to 1.0)
        mask_high = (ownership > max_thresh) & (ownership < 1.0)
        if mask_high.any():
            range_size = 1.0 - max_thresh
            position = (1.0 - ownership[mask_high]) / range_size
            result[mask_high] = 75.0 * position
        
        # At extremes: 0
        result[ownership <= 0] = 0.0
        result[ownership >= 1.0] = 0.0
        
        # None/NaN gets 0
        result[ownership.isna()] = 0.0
        
        return result
