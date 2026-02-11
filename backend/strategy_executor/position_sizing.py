# ABOUTME: Calculates position sizes for trades using a Target Portfolio approach
# ABOUTME: Unified ranking of Held + New candidates to determine ideal allocations

import logging
from typing import Dict, Any, List, Optional, Tuple

from strategy_executor.models import PositionSize, ExitSignal
from strategy_executor.models import TargetAllocation

logger = logging.getLogger(__name__)


class PositionSizer:
    """Calculates position sizes and generates buy/sell signals based on target portfolio."""

    def __init__(self, db):
        self.db = db

    def calculate_target_orders(
        self,
        section_id: int,  # can be portfolio_id
        candidates: List[Dict[str, Any]],
        portfolio_value: float,
        holdings: Dict[str, Any],
        method: str,
        rules: Dict[str, Any],
        cash_available: float = 0.0
    ) -> Tuple[List[ExitSignal], List[Dict[str, Any]]]:
        """Core logic: Calculate target portfolio and generate Buy/Sell orders to get there.

        Args:
            candidates: Unified list of {symbol, conviction_score, current_price}
                       Includes both CURRENT holdings and NEW candidates.
            portfolio_value: Total liquidity (Cash + Stock Value)
            holdings: Current holdings {symbol: quantity}
            method: Sizing method (equal_weight, conviction_weighted, etc.)
            rules: Sizing rules (max_positions, etc.)
            cash_available: Current cash (used for validation)

        Returns:
            Tuple(List[ExitSignal], List[final_buy_decision])
        """
        # 1. Calculate Target Allocations
        targets = self._calculate_ideal_allocation(candidates, portfolio_value, method, rules)

        # 2. Generate Signals (Diff vs Current)
        sells, buys = self._generate_signals(targets, holdings, rules)

        return sells, buys

    def _calculate_ideal_allocation(
        self,
        candidates: List[Dict[str, Any]],
        portfolio_value: float,
        method: str,
        rules: Dict[str, Any]
    ) -> List[TargetAllocation]:
        """Rank candidates and assign target $ values."""
        
        # Filter invalid candidates
        valid_candidates = [c for c in candidates if c.get('price') and c['price'] > 0]
        if not valid_candidates:
            return []

        # Sort by conviction (descending)
        valid_candidates.sort(key=lambda x: x.get('conviction', 0), reverse=True)

        # Apply Max Positions Limit
        max_positions = rules.get('max_positions', 100)
        selected_candidates = valid_candidates[:max_positions]

        # Calculate Allocation base
        num_positions = len(selected_candidates)
        if num_positions == 0:
            return []

        allocations = []
        
        # Calculate raw targets based on method
        if method == 'equal_weight':
            # Simple equal weight
            target_per_stock = portfolio_value / num_positions
            for cand in selected_candidates:
                allocations.append(self._create_allocation(cand, target_per_stock))
        
        elif method == 'conviction_weighted':
            total_score = sum(c.get('conviction', 0) for c in selected_candidates)
            if total_score == 0:
                target_per_stock = portfolio_value / num_positions
                for cand in selected_candidates:
                    allocations.append(self._create_allocation(cand, target_per_stock))
            else:
                for cand in selected_candidates:
                    share = cand.get('conviction', 0) / total_score
                    target_val = portfolio_value * share
                    allocations.append(self._create_allocation(cand, target_val))
                    
        elif method == 'fixed_pct':
            # Fixed % of portfolio (e.g. 5%)
            # Note: This might not sum to 100% or might exceed 100%
            pct = rules.get('fixed_position_pct', 5.0) / 100.0
            target_val = portfolio_value * pct
            for cand in selected_candidates:
                 allocations.append(self._create_allocation(cand, target_val))
                 
        elif method == 'kelly':
             # Simplified Kelly
             for cand in selected_candidates:
                target_val = self._size_kelly(portfolio_value, cand.get('conviction', 50), rules)
                allocations.append(self._create_allocation(cand, target_val))
                
        else:
             # Default to equal weight
             target_per_stock = portfolio_value / num_positions
             for cand in selected_candidates:
                allocations.append(self._create_allocation(cand, target_per_stock))

        # Apply Max Position Value Cap (if defined)
        max_pos_pct = rules.get('max_position_pct')
        if max_pos_pct:
            max_val = portfolio_value * (max_pos_pct / 100.0)
            for alloc in allocations:
                if alloc.target_value > max_val:
                    alloc.target_value = max_val
                    # Recalculate drift
                    alloc.drift = alloc.target_value - alloc.current_value

        return allocations

    def _create_allocation(self, candidate: Dict, target_value: float) -> TargetAllocation:
        symbol = candidate['symbol']
        price = candidate['price']
        
        # Calculate current value from holdings
        # candidate dict should optionally contain 'current_quantity' or we assume 0 if not passed, 
        # but better to handle it upstream. 
        # For now, we assume the candidate dict includes current holding info if available.
        # Actually, let's pass holdings separately to _calculate_ideal_allocation? 
        # No, for simplicity, let's assume the caller merged them or we just use 0 here 
        # and handle the diff in `_generate_signals`.
        
        # Wait, TargetAllocation needs current_value to calculate drift? 
        # Actually drift is calculated in _generate_signals usually. 
        # But TargetAllocation definition includes `drift`. 
        # Let's populate what we can.
        
        return TargetAllocation(
            symbol=symbol,
            conviction=candidate.get('conviction', 0),
            target_value=target_value,
            current_value=0.0,
            drift=target_value,  # Initialize to target_value (assuming 0 held)
            price=price,
            source_data=candidate
        )

    def _generate_signals(
        self,
        targets: List[TargetAllocation],
        holdings: Dict[str, Any],
        rules: Dict[str, Any]
    ) -> Tuple[List[ExitSignal], List[Dict[str, Any]]]:
        """Compare targets to holdings and generate buy/sell orders."""

        min_trade_amt = rules.get('min_trade_amount', 100.0)

        sells = []
        buys = []

        # Map targets for easy lookup
        target_map = {t.symbol: t for t in targets}

        # 1. Check all current holdings
        # If a holding is NOT in targets, it means it didn't make the cut -> SELL ALL.
        # If it IS in targets, check for Trim.

        for symbol, qty in holdings.items():
            qty = int(qty)
            if qty <= 0:
                continue

            # Get price (we need it for value)
            price = 0.0
            if symbol in target_map:
                price = target_map[symbol].price
            else:
                price = self._fetch_price(symbol) or 0.0

            if price <= 0:
                logger.warning(f"Could not fetch price for {symbol}, shipping signal generation.")
                continue

            current_val = qty * price

            if symbol not in target_map:
                # Full Exit (Displaced by better candidate)
                reason = "Rebalance: Displaced by higher conviction opportunities"
                sells.append(ExitSignal(
                    symbol=symbol,
                    quantity=qty,
                    reason=reason,
                    current_value=current_val,
                    exit_type='full'
                ))
            else:
                # Update current value in target
                target = target_map[symbol]
                target.current_value = current_val
                target.quantity = qty
                target.drift = target.target_value - current_val

                # Check for TRIM
                # Drift < 0 means we have too much -> Sell
                if target.drift < -min_trade_amt:
                    sell_val = abs(target.drift)
                    sell_shares = int(sell_val / price)
                    if sell_shares > 0:
                        sells.append(ExitSignal(
                            symbol=symbol,
                            quantity=sell_shares,
                            reason=f"Rebalance Trim: Value ${current_val:.0f} exceeds target ${target.target_value:.0f}",
                            current_value=sell_shares * price,
                            exit_type='trim'
                        ))

        # 2. Check for Buys
        # Iterate through targets. If drift > min_trade_amt -> Buy
        # Sort buys by conviction to prioritize execution if cash is constrained (though sizing should handle it)
        targets.sort(key=lambda x: x.conviction, reverse=True)

        for target in targets:
            if target.drift > min_trade_amt:
                buy_val = target.drift
                buy_shares = int(buy_val / target.price)

                if buy_shares > 0:
                    pos = PositionSize(
                        shares=buy_shares,
                        estimated_value=buy_shares * target.price,
                        position_pct=0.0, # todo
                        reasoning=f"Target Rebalance: Target ${target.target_value:.0f} vs Current ${target.current_value:.0f}",
                        target_value=target.target_value,
                        drift=target.drift
                    )

                    buys.append({
                        'symbol': target.symbol,
                        'position': pos,
                        'priority_score': target.conviction,
                        'decision': target.source_data
                    })

        return sells, buys

    def _fetch_price(self, symbol: str) -> Optional[float]:
        """Fetch current price from database."""
        # Simple cache wrapper or direct DB call
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

    def _size_kelly(self, total_value, conviction, rules):
        """Helper for Kelly Criterion sizing."""
        kelly_fraction = rules.get('kelly_fraction', 0.25)
        p = max(0.5, conviction / 100.0)
        q = 1 - p
        b = 1 # 1:1 payoff assumption
        kelly_pct = (b * p - q) / b
        safe_pct = max(0, min(kelly_pct * kelly_fraction, 0.25))
        return total_value * safe_pct
