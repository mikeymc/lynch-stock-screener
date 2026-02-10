# ABOUTME: Checks if held positions still meet entry criteria for the strategy
# ABOUTME: Evaluates universe compliance and scoring requirements with grace periods

import logging
from typing import Dict, Any, List, Optional
from strategy_executor.models import ExitSignal

logger = logging.getLogger(__name__)


class HoldingReevaluator:
    """Checks if held positions still meet entry criteria."""

    def __init__(self, db, condition_evaluator, lynch_criteria):
        self.db = db
        self.condition_evaluator = condition_evaluator
        self.lynch_criteria = lynch_criteria

    def check_holdings(
        self,
        portfolio_id: int,
        strategy_conditions: Dict[str, Any],
        reevaluation_config: Dict[str, Any]
    ) -> List[ExitSignal]:
        """Check all holdings against re-evaluation criteria.

        Args:
            portfolio_id: Portfolio to check
            strategy_conditions: Strategy conditions (universe filters, scoring requirements)
            reevaluation_config: Re-evaluation configuration with:
                - enabled: bool
                - check_universe_filters: bool
                - check_scoring_requirements: bool
                - grace_period_days: int

        Returns:
            List of ExitSignal for positions that fail re-evaluation
        """
        if not reevaluation_config.get('enabled', False):
            return []

        holdings = self.db.get_portfolio_holdings(portfolio_id)
        if not holdings:
            return []

        entry_dates = self.db.get_position_entry_dates(portfolio_id)
        grace_period = reevaluation_config.get('grace_period_days', 30)

        exits = []
        for symbol, quantity in holdings.items():
            # Apply grace period
            entry_info = entry_dates.get(symbol, {})
            days_held = entry_info.get('days_held', 0)
            if days_held < grace_period:
                logger.debug(f"Skipping {symbol} re-evaluation: within grace period ({days_held}/{grace_period} days)")
                continue

            # Check universe filters
            if reevaluation_config.get('check_universe_filters', True):
                exit_signal = self._check_universe_compliance(
                    symbol, quantity, strategy_conditions
                )
                if exit_signal:
                    exits.append(exit_signal)
                    continue

            # Check scoring requirements
            if reevaluation_config.get('check_scoring_requirements', True):
                exit_signal = self._check_scoring_compliance(
                    symbol, quantity, strategy_conditions
                )
                if exit_signal:
                    exits.append(exit_signal)
                    continue

            # Update last evaluated date
            self.db.update_position_evaluation_date(portfolio_id, symbol)

        return exits

    def _check_universe_compliance(
        self,
        symbol: str,
        quantity: int,
        conditions: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """Check if position still passes universe filters."""
        try:
            # Evaluate universe with just this symbol
            passing_symbols = self.condition_evaluator.filter_inverse(conditions)

            if symbol not in passing_symbols:
                # Get current price for exit signal
                price = self._get_current_price(symbol)
                current_value = quantity * price if price else 0

                return ExitSignal(
                    symbol=symbol,
                    quantity=quantity,
                    reason=f"Re-evaluation: No longer passes universe filters",
                    current_value=current_value,
                    gain_pct=0.0  # Will be calculated by caller if needed
                )
        except Exception as e:
            logger.warning(f"Failed universe compliance check for {symbol}: {e}")

        return None

    def _check_scoring_compliance(
        self,
        symbol: str,
        quantity: int,
        conditions: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """Check if position still meets scoring requirements."""
        try:
            from lynch_criteria import SCORE_THRESHOLDS

            scoring_reqs = conditions.get('scoring_requirements', [])
            if not scoring_reqs:
                return None

            # Default thresholds
            lynch_req = SCORE_THRESHOLDS.get('BUY', 60)
            buffett_req = SCORE_THRESHOLDS.get('BUY', 60)

            for req in scoring_reqs:
                if req.get('character') == 'lynch':
                    lynch_req = req.get('min_score', lynch_req)
                elif req.get('character') == 'buffett':
                    buffett_req = req.get('min_score', buffett_req)

            # Score the stock
            lynch_result = self.lynch_criteria.evaluate_stock(symbol, character_id='lynch')
            buffett_result = self.lynch_criteria.evaluate_stock(symbol, character_id='buffett')

            lynch_score = lynch_result.get('overall_score', 0) if lynch_result else 0
            buffett_score = buffett_result.get('overall_score', 0) if buffett_result else 0

            # Check if still meets requirements (OR logic: at least one must pass)
            lynch_pass = lynch_score >= lynch_req
            buffett_pass = buffett_score >= buffett_req

            if not (lynch_pass or buffett_pass):
                price = self._get_current_price(symbol)
                current_value = quantity * price if price else 0

                return ExitSignal(
                    symbol=symbol,
                    quantity=quantity,
                    reason=f"Re-evaluation: Scores degraded (Lynch {lynch_score:.0f} < {lynch_req}, Buffett {buffett_score:.0f} < {buffett_req})",
                    current_value=current_value,
                    gain_pct=0.0
                )

        except Exception as e:
            logger.warning(f"Failed scoring compliance check for {symbol}: {e}")

        return None

    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from database."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT price FROM stock_metrics WHERE symbol = %s", (symbol,))
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            self.db.return_connection(conn)
