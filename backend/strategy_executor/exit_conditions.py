# ABOUTME: Checks existing positions against exit conditions like profit targets and stop losses
# ABOUTME: Supports price-based exits and score degradation detection

import logging
from typing import Dict, Any, List, Optional
from strategy_executor.models import ExitSignal

logger = logging.getLogger(__name__)


class ExitConditionChecker:
    """Checks existing positions against exit conditions."""

    def __init__(self, db):
        self.db = db

    def check_exits(
        self,
        portfolio_id: int,
        exit_conditions: Dict[str, Any],
        scoring_func=None
    ) -> List[ExitSignal]:
        """Check all holdings against exit conditions.

        Exit conditions format:
        {
            "profit_target_pct": 50,      # Sell if up 50%
            "stop_loss_pct": -20,         # Sell if down 20%
            "max_hold_days": 365,         # Sell after 1 year
            "score_degradation": {
                "lynch_below": 40,
                "buffett_below": 40
            }
        }

        Args:
            portfolio_id: Portfolio to check
            exit_conditions: Exit rules
            scoring_func: Optional function to re-score stocks (for degradation check)

        Returns:
            List of ExitSignal for positions that should be sold
        """
        if not exit_conditions:
            return []

        exits = []
        holdings = self.db.get_portfolio_holdings_detailed(portfolio_id, use_live_prices=False)

        for holding in holdings:
            signal = self._check_holding(holding, exit_conditions, scoring_func)
            if signal:
                exits.append(signal)

        return exits

    def _check_holding(
        self,
        holding: Dict[str, Any],
        conditions: Dict[str, Any],
        scoring_func
    ) -> Optional[ExitSignal]:
        """Check a single holding against exit conditions."""
        symbol = holding['symbol']
        quantity = holding['quantity']
        current_value = holding.get('current_value', 0)
        cost_basis = holding.get('total_cost', 0)

        if cost_basis > 0:
            gain_pct = ((current_value - cost_basis) / cost_basis) * 100
        else:
            gain_pct = 0

        # Check profit target
        profit_target = conditions.get('profit_target_pct')
        if profit_target and gain_pct >= profit_target:
            return ExitSignal(
                symbol=symbol,
                quantity=quantity,
                reason=f"Profit target hit: {gain_pct:.1f}% >= {profit_target}%",
                current_value=current_value,
                gain_pct=gain_pct
            )

        # Check stop loss
        stop_loss = conditions.get('stop_loss_pct')
        if stop_loss and gain_pct <= stop_loss:
            return ExitSignal(
                symbol=symbol,
                quantity=quantity,
                reason=f"Stop loss hit: {gain_pct:.1f}% <= {stop_loss}%",
                current_value=current_value,
                gain_pct=gain_pct
            )

        # Check hold duration (would need transaction dates)
        # TODO: Implement max_hold_days check

        # Check score degradation
        degradation = conditions.get('score_degradation')
        if degradation and scoring_func:
            signal = self._check_score_degradation(
                symbol, quantity, current_value, gain_pct, degradation, scoring_func
            )
            if signal:
                return signal

        return None

    def _check_score_degradation(
        self,
        symbol: str,
        quantity: int,
        current_value: float,
        gain_pct: float,
        degradation: Dict[str, Any],
        scoring_func
    ) -> Optional[ExitSignal]:
        """Check if stock scores have degraded below thresholds."""
        try:
            scores = scoring_func(symbol)
            lynch_threshold = degradation.get('lynch_below')
            buffett_threshold = degradation.get('buffett_below')

            if lynch_threshold and scores.get('lynch_score', 100) < lynch_threshold:
                return ExitSignal(
                    symbol=symbol,
                    quantity=quantity,
                    reason=f"Lynch score degraded: {scores['lynch_score']:.0f} < {lynch_threshold}",
                    current_value=current_value,
                    gain_pct=gain_pct
                )

            if buffett_threshold and scores.get('buffett_score', 100) < buffett_threshold:
                return ExitSignal(
                    symbol=symbol,
                    quantity=quantity,
                    reason=f"Buffett score degraded: {scores['buffett_score']:.0f} < {buffett_threshold}",
                    current_value=current_value,
                    gain_pct=gain_pct
                )
        except Exception as e:
            logger.warning(f"Failed to check score degradation for {symbol}: {e}")

        return None
