# ABOUTME: Calculates position sizes for trades based on various sizing methods
# ABOUTME: Supports equal weight, conviction weighted, fixed percentage, and Kelly criterion

import logging
from typing import Dict, Any, List, Optional
from strategy_executor.models import PositionSize

logger = logging.getLogger(__name__)


class PositionSizer:
    """Calculates position sizes for trades."""

    def __init__(self, db):
        self.db = db

    def calculate_position(
        self,
        portfolio_id: int,
        symbol: str,
        conviction_score: float,
        method: str,
        rules: Dict[str, Any],
        other_buys: List[Dict[str, Any]] = None,
        current_price: float = None
    ) -> PositionSize:
        """Calculate shares to buy based on sizing method.

        Methods:
        - equal_weight: Divide equally among all positions
        - conviction_weighted: Higher conviction = larger position
        - fixed_pct: Fixed percentage of portfolio per position
        - kelly: Kelly criterion based on expected value

        Args:
            portfolio_id: Portfolio to trade in
            symbol: Stock symbol
            conviction_score: 0-100 score
            method: Sizing method
            rules: Position sizing rules from strategy
            other_buys: Other stocks being bought this run
            current_price: Current stock price (fetched if not provided)

        Returns:
            PositionSize with shares, value, and reasoning
        """
        if other_buys is None:
            other_buys = []

        # Get portfolio state
        summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
        if not summary:
            return PositionSize(0, 0.0, 0.0, "Portfolio not found")

        total_value = summary.get('total_value', 0)
        available_cash = summary.get('cash', 0)
        holdings = summary.get('holdings', {})

        # Get current price if not provided
        if current_price is None:
            current_price = self._fetch_price(symbol)
            if not current_price:
                return PositionSize(0, 0.0, 0.0, f"Price unavailable for {symbol}")

        # Calculate maximum allowed position value
        max_position_pct = rules.get('max_position_pct', 5.0)
        max_position_value = total_value * (max_position_pct / 100)

        # Check current position
        current_shares = holdings.get(symbol, 0)
        current_value = current_shares * current_price

        # Room to add
        room_to_add = max_position_value - current_value
        if room_to_add <= 0:
            return PositionSize(
                0, 0.0, 0.0,
                f"Already at max position ({current_shares} shares = ${current_value:.2f})"
            )

        # Calculate target size based on method
        if method == 'equal_weight':
            target_value = self._size_equal_weight(available_cash, other_buys)
        elif method == 'conviction_weighted':
            target_value = self._size_conviction_weighted(
                available_cash, conviction_score, other_buys
            )
        elif method == 'fixed_pct':
            target_value = self._size_fixed_pct(total_value, rules)
        elif method == 'kelly':
            target_value = self._size_kelly(total_value, conviction_score, rules)
        else:
            target_value = self._size_equal_weight(available_cash, other_buys)

        # Apply constraints
        final_value = min(target_value, room_to_add, available_cash)
        final_value = max(final_value, 0)

        # Apply minimum position size
        min_position = rules.get('min_position_value', 500)
        if 0 < final_value < min_position:
            if available_cash >= min_position:
                final_value = min_position
            else:
                final_value = 0

        shares = int(final_value / current_price)

        return PositionSize(
            shares=shares,
            estimated_value=shares * current_price,
            position_pct=(shares * current_price) / total_value * 100 if total_value > 0 else 0,
            reasoning=f"{method}: ${final_value:.2f} -> {shares} shares @ ${current_price:.2f}"
        )

    def _fetch_price(self, symbol: str) -> Optional[float]:
        """Fetch current price from database."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT price FROM stock_metrics WHERE symbol = %s",
                (symbol,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            self.db.return_connection(conn)

    def _size_equal_weight(
        self,
        available_cash: float,
        other_buys: List[Dict[str, Any]]
    ) -> float:
        """Divide cash equally among all buys."""
        num_buys = len(other_buys) + 1
        return available_cash / num_buys

    def _size_conviction_weighted(
        self,
        available_cash: float,
        conviction_score: float,
        other_buys: List[Dict[str, Any]]
    ) -> float:
        """Weight by conviction score."""
        total_conviction = conviction_score + sum(
            b.get('conviction', 50) for b in other_buys
        )
        if total_conviction == 0:
            return self._size_equal_weight(available_cash, other_buys)

        weight = conviction_score / total_conviction
        return available_cash * weight

    def _size_fixed_pct(
        self,
        total_value: float,
        rules: Dict[str, Any]
    ) -> float:
        """Fixed percentage of portfolio."""
        target_pct = rules.get('fixed_position_pct', 5.0)
        return total_value * (target_pct / 100)

    def _size_kelly(
        self,
        total_value: float,
        conviction_score: float,
        rules: Dict[str, Any]
    ) -> float:
        """Simplified Kelly criterion.

        Full Kelly: f* = (bp - q) / b
        We approximate: p = conviction/100, assuming 1:1 payoff
        Then apply kelly_fraction for safety (typically 0.25 = quarter-Kelly)
        """
        kelly_fraction = rules.get('kelly_fraction', 0.25)

        # Convert conviction (0-100) to probability (0.5-1.0)
        p = max(0.5, conviction_score / 100)
        q = 1 - p

        # Assume 1:1 payoff (b=1)
        b = 1
        kelly_pct = (b * p - q) / b

        # Apply fractional Kelly and cap
        safe_pct = kelly_pct * kelly_fraction
        safe_pct = max(0, min(safe_pct, 0.25))  # Cap at 25%

        return total_value * safe_pct
