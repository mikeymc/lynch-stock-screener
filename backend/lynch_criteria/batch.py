# ABOUTME: Vectorized batch scoring for evaluating entire stock universes at once.
# ABOUTME: Provides DataFrame-based scoring instead of per-stock evaluation loops.

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BatchScoringMixin:

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
