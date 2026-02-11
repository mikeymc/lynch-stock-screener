# ABOUTME: Scoring mixin for candidate evaluation with Lynch/Buffett criteria
# ABOUTME: Handles Phase 2 of strategy execution with vectorized batch scoring

import logging
from typing import Dict, Any, List

from strategy_executor.utils import log_event

logger = logging.getLogger(__name__)


class ScoringMixin:
    """Phase 2: Candidate scoring with Lynch/Buffett criteria."""

    def _score_candidates(
        self,
        candidates: List[str],
        conditions: Dict[str, Any],
        run_id: int,
        is_addition: bool = False
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Score candidates with Lynch and Buffett scoring.

        Args:
            candidates: List of symbols to score
            conditions: Strategy conditions with scoring requirements
            run_id: Current run ID for logging
            is_addition: If True, use higher thresholds for position additions

        Returns:
            Tuple of (passing, declined). For is_addition=True, declined contains
            held stocks that have score data but failed addition thresholds — they
            are routed through deliberation for exit evaluation. For is_addition=False,
            declined is always empty.
        """
        if not candidates:
            return [], []

        # 1. Determine thresholds
        lynch_req, buffett_req = self._get_scoring_thresholds(conditions, is_addition)

        position_type = "addition" if is_addition else "new position"
        log_event(self.db, run_id, f"Scoring {len(candidates)} {position_type} candidates (Lynch: {lynch_req}, Buffett: {buffett_req})")

        try:
            # 2. Load Data
            df = self._load_candidate_data(candidates, run_id)
            if df is None or df.empty:
                return [], []

            # 3. Calculate Scores
            df_scores = self._calculate_batch_scores(df)

            # 4. Evaluate Candidates
            scored, declined = self._evaluate_candidates(df_scores, lynch_req, buffett_req, is_addition, run_id)

            log_event(self.db, run_id, f"Scoring complete: {len(scored)}/{len(candidates)} {position_type}s passed requirements")
            return scored, declined

        except Exception as e:
            logger.error(f"Vectorized scoring failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            log_event(self.db, run_id, f"ERROR: Vectorized scoring failed: {e}")
            return [], []

    def _get_scoring_thresholds(self, conditions: Dict[str, Any], is_addition: bool) -> tuple[int, int]:
        """Determine Lynch and Buffett score thresholds based on conditions."""
        from lynch_criteria import SCORE_THRESHOLDS

        scoring_reqs = conditions.get('scoring_requirements', [])
        default_min = SCORE_THRESHOLDS.get('BUY', 60)
        lynch_req = default_min
        buffett_req = default_min

        if is_addition:
            addition_reqs = conditions.get('addition_scoring_requirements', [])
            if addition_reqs:
                for req in addition_reqs:
                    if req.get('character') == 'lynch':
                        lynch_req = int(req.get('min_score', default_min))
                    elif req.get('character') == 'buffett':
                        buffett_req = int(req.get('min_score', default_min))
            else:
                # Default: +10 higher than base requirements
                for req in scoring_reqs:
                    if req.get('character') == 'lynch':
                        lynch_req = int(req.get('min_score', default_min)) + 10
                    elif req.get('character') == 'buffett':
                        buffett_req = int(req.get('min_score', default_min)) + 10

                if not scoring_reqs:
                    lynch_req = default_min + 10
                    buffett_req = default_min + 10
        else:
            for req in scoring_reqs:
                if req.get('character') == 'lynch':
                    lynch_req = int(req.get('min_score', default_min))
                elif req.get('character') == 'buffett':
                    buffett_req = int(req.get('min_score', default_min))

        return int(lynch_req), int(buffett_req)

    def _load_candidate_data(self, candidates: List[str], run_id: int):
        """Load vectorized stock data for candidates."""
        import pandas as pd
        from stock_vectors import StockVectors

        print(f"  Loading stock data for {len(candidates)} candidates...")

        vectors = StockVectors(self.db)
        df_all = vectors.load_vectors(country_filter='US')

        if df_all is None or df_all.empty:
            log_event(self.db, run_id, "No stock data available for scoring")
            return None

        # Filter to just our candidates
        df = df_all[df_all['symbol'].isin(candidates)].copy()

        if df.empty:
            log_event(self.db, run_id, f"No data found for candidates: {candidates[:5]}...")
            return None

        print(f"  Found data for {len(df)} stocks")
        return df

    def _calculate_batch_scores(self, df):
        """Calculate Lynch and Buffett scores for the dataframe."""
        from stock_vectors import DEFAULT_ALGORITHM_CONFIG
        from characters.buffett import BUFFETT

        # Score with Lynch
        print(f"  Scoring with Lynch criteria...")
        df_lynch = self.lynch_criteria.evaluate_batch(df, DEFAULT_ALGORITHM_CONFIG)

        # Score with Buffett
        print(f"  Scoring with Buffett criteria...")
        buffett_config = {}
        for sw in BUFFETT.scoring_weights:
            if sw.metric == 'roe':
                buffett_config['weight_roe'] = sw.weight
                buffett_config['roe_excellent'] = sw.threshold.excellent
                buffett_config['roe_good'] = sw.threshold.good
                buffett_config['roe_fair'] = sw.threshold.fair
            elif sw.metric == 'debt_to_earnings':
                buffett_config['weight_debt_earnings'] = sw.weight
                buffett_config['de_excellent'] = sw.threshold.excellent
                buffett_config['de_good'] = sw.threshold.good
                buffett_config['de_fair'] = sw.threshold.fair
            elif sw.metric == 'gross_margin':
                buffett_config['weight_gross_margin'] = sw.weight
                buffett_config['gm_excellent'] = sw.threshold.excellent
                buffett_config['gm_good'] = sw.threshold.good
                buffett_config['gm_fair'] = sw.threshold.fair

        df_buffett = self.lynch_criteria.evaluate_batch(df, buffett_config)

        # Merge scores
        df_merged = df_lynch[['symbol', 'overall_score', 'overall_status']].rename(
            columns={'overall_score': 'lynch_score', 'overall_status': 'lynch_status'}
        )
        df_buffett_scores = df_buffett[['symbol', 'overall_score', 'overall_status']].rename(
            columns={'overall_score': 'buffett_score', 'overall_status': 'buffett_status'}
        )

        return df_merged.merge(df_buffett_scores, on='symbol', how='inner')

    def _evaluate_candidates(self, df_scores, lynch_req, buffett_req, is_addition, run_id):
        """Evaluate scored candidates against requirements.

        Returns:
            Tuple of (passing, declined). declined is populated only when is_addition=True
            and contains held stocks that have score data but failed addition thresholds.
        """
        scored = []
        declined = []
        df_scores['position_type'] = 'addition' if is_addition else 'new'
        type_label = "ADDITION" if is_addition else "NEW"

        for _, row in df_scores.iterrows():
            symbol = row['symbol']
            stock_data = {
                'symbol': symbol,
                'lynch_score': row['lynch_score'],
                'lynch_status': row['lynch_status'],
                'buffett_score': row['buffett_score'],
                'buffett_status': row['buffett_status'],
                'position_type': row['position_type']
            }

            print(f"  {symbol} ({type_label}): Lynch {stock_data['lynch_score']:.0f}, Buffett {stock_data['buffett_score']:.0f}")

            # Check if passes scoring requirements (OR Logic)
            lynch_pass = stock_data['lynch_score'] >= lynch_req
            buffett_pass = stock_data['buffett_score'] >= buffett_req
            passes = lynch_pass or buffett_pass

            if passes:
                scored.append(stock_data)
                reason_parts = []
                if lynch_pass:
                    reason_parts.append(f"Lynch {stock_data['lynch_score']:.0f} >= {lynch_req}")
                if buffett_pass:
                    reason_parts.append(f"Buffett {stock_data['buffett_score']:.0f} >= {buffett_req}")

                reason_str = ", ".join(reason_parts)
                threshold_note = " (higher bar for additions)" if is_addition else ""

                print(f"    ✓ PASSED requirements ({reason_str}){threshold_note}")
                logger.debug(f"{symbol}: PASSED as {type_label} ({reason_str})")
            else:
                fail_reasons = []
                if not lynch_pass:
                    fail_reasons.append(f"Lynch {stock_data['lynch_score']:.0f} < {lynch_req}")
                if not buffett_pass:
                    fail_reasons.append(f"Buffett {stock_data['buffett_score']:.0f} < {buffett_req}")

                fail_str = ", ".join(fail_reasons)
                threshold_note = " (higher bar for additions)" if is_addition else ""
                print(f"    ✗ FAILED requirements ({fail_str}){threshold_note}")

                if is_addition:
                    stock_data['position_type'] = 'held_exit_evaluation'
                    declined.append(stock_data)

        return scored, declined
