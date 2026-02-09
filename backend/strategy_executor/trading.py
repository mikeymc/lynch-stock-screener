# ABOUTME: Trading mixin for position sizing and trade execution
# ABOUTME: Handles Phase 6 of strategy execution with two-phase trade execution

import logging
from typing import Dict, Any, List

from strategy_executor.models import ExitSignal
from strategy_executor.utils import log_event

logger = logging.getLogger(__name__)


class TradingMixin:
    """Phase 6: Position sizing and trade execution."""

    def _calculate_all_positions(
        self,
        buy_decisions: List[Dict[str, Any]],
        portfolio_id: int,
        available_cash: float,
        method: str,
        rules: Dict[str, Any],
        run_id: int
    ) -> List[Dict[str, Any]]:
        """Phase 1: Calculate all positions with priority ordering.

        Calculates position sizes for all buy decisions, prioritizes by conviction,
        and ensures total doesn't exceed available cash.

        Args:
            buy_decisions: List of stocks with BUY decisions
            portfolio_id: Portfolio to trade in
            available_cash: Current available cash
            method: Position sizing method
            rules: Position sizing rules
            run_id: Current run ID for logging

        Returns:
            List of dicts with: {symbol, decision, position, priority_score}
            Sorted by priority (highest conviction first)
        """
        if not buy_decisions:
            return []

        print("\n  Phase 1: Calculating all positions with priority ordering...")
        log_event(self.db, run_id, f"Phase 1: Calculating positions for {len(buy_decisions)} buy decisions")

        # Calculate positions for all decisions
        positions_data = []
        for decision in buy_decisions:
            symbol = decision['symbol']
            conviction = decision.get('consensus_score', 50)

            try:
                position = self.position_sizer.calculate_position(
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    conviction_score=conviction,
                    method=method,
                    rules=rules,
                    other_buys=[d for d in buy_decisions if d != decision]
                )

                # Calculate priority score
                # Primary: conviction score (higher = more priority)
                # Secondary: position size (smaller = more priority for diversification)
                priority_score = conviction - (position.position_pct * 0.1)

                positions_data.append({
                    'symbol': symbol,
                    'decision': decision,
                    'position': position,
                    'conviction': conviction,
                    'priority_score': priority_score
                })

                print(f"    {symbol}: {position.shares} shares (${position.estimated_value:,.2f}), "
                      f"conviction={conviction:.0f}, priority={priority_score:.1f}")

            except Exception as e:
                logger.error(f"Failed to calculate position for {symbol}: {e}")
                continue

        # Sort by priority (highest first)
        positions_data.sort(key=lambda x: x['priority_score'], reverse=True)

        # Calculate total cash needed
        total_requested = sum(p['position'].estimated_value for p in positions_data)
        print(f"\n  Total requested: ${total_requested:,.2f}, Available: ${available_cash:,.2f}")
        log_event(self.db, run_id, f"Total requested: ${total_requested:,.2f}, Available: ${available_cash:,.2f}")

        # If we exceed available cash, need to rebalance
        if total_requested > available_cash:
            print(f"  ⚠ Insufficient cash! Selecting highest priority positions...")
            log_event(self.db, run_id, f"Insufficient cash. Prioritizing highest conviction positions.")

            # Select positions that fit in budget (greedy by priority)
            selected = []
            remaining_cash = available_cash

            for pos_data in positions_data:
                if pos_data['position'].estimated_value <= remaining_cash:
                    selected.append(pos_data)
                    remaining_cash -= pos_data['position'].estimated_value
                    print(f"    ✓ Selected {pos_data['symbol']} (${pos_data['position'].estimated_value:,.2f})")
                else:
                    print(f"    ✗ Skipped {pos_data['symbol']} (${pos_data['position'].estimated_value:,.2f}) - insufficient cash")
                    log_event(self.db, run_id, f"Skipped {pos_data['symbol']} - insufficient cash")

            positions_data = selected
            print(f"  Selected {len(positions_data)}/{len(buy_decisions)} positions, "
                  f"using ${available_cash - remaining_cash:,.2f} of ${available_cash:,.2f}")
            log_event(self.db, run_id, f"Selected {len(positions_data)} positions totaling ${available_cash - remaining_cash:,.2f}")
        else:
            print(f"  ✓ All positions fit within available cash")

        return positions_data


    def _execute_trades(
        self,
        buy_decisions: List[Dict[str, Any]],
        exits: List[ExitSignal],
        strategy: Dict[str, Any],
        run_id: int
    ) -> int:
        """Execute buy and sell trades with two-phase cash tracking."""
        import portfolio_service

        portfolio_id = strategy['portfolio_id']
        position_rules = strategy.get('position_sizing', {})
        method = position_rules.get('method', 'equal_weight')

        trades_executed = 0

        # Check market status
        is_market_open = portfolio_service.is_market_open()

        # If market is closed, we need user_id to create alerts
        user_id = None
        if not is_market_open:
            # We need to fetch the portfolio to get the user_id
            try:
                portfolio = self.db.get_portfolio(portfolio_id)
                if portfolio:
                    user_id = portfolio.get('user_id')
            except Exception as e:
                logger.error(f"Failed to fetch portfolio {portfolio_id} for user lookup: {e}")

            if not user_id:
                logger.error(f"Could not determine user_id for portfolio {portfolio_id}, cannot queue off-hours trades.")
                # We can either return or attempt to process (which will fail for trades).
                # Let's proceed but warn.

        existing_alerts = []
        if not is_market_open:
            print(f"   Market is closed. Queuing trades for next open via Alerts.")
            log_event(self.db, run_id, "Market closed. Queuing transactions for next market open.")
            
            if user_id:
                try:
                    existing_alerts = self.db.get_alerts(user_id, status='active')
                    logger.info(f"Fetched {len(existing_alerts)} existing active alerts for idempotency check.")
                except Exception as e:
                    logger.error(f"Failed to fetch existing alerts for user {user_id}: {e}")

        # Execute sells first (to free up cash)
        print("\n  Executing SELL orders...")
        cash_freed = 0.0
        for exit_signal in exits:
            try:
                if is_market_open:
                    result = portfolio_service.execute_trade(
                        portfolio_id=portfolio_id,
                        symbol=exit_signal.symbol,
                        transaction_type='SELL',
                        quantity=exit_signal.quantity,
                        note=exit_signal.reason,
                        position_type='exit',
                        db=self.db
                    )
                    if result.get('success'):
                        trades_executed += 1
                        cash_freed += exit_signal.current_value
                        log_event(self.db, run_id, f"SELL {exit_signal.symbol}: {exit_signal.reason}")
                        print(f"    ✓ SOLD {exit_signal.symbol}: {exit_signal.quantity} shares "
                              f"(freed ${exit_signal.current_value:,.2f})")
                elif user_id:
                    # Idempotency check: Don't queue duplicate sell alert
                    is_duplicate = any(
                        a['symbol'] == exit_signal.symbol and 
                        a['action_type'] == 'market_sell' and
                        a.get('portfolio_id') == portfolio_id
                        for a in existing_alerts
                    )
                    
                    if is_duplicate:
                        print(f"    ⚠ Skipped {exit_signal.symbol}: Sell alert already queued.")
                        log_event(self.db, run_id, f"DUPLICATE SELL SKIP: {exit_signal.symbol} already queued.")
                        continue

                    alert_id = self.db.create_alert(
                        user_id=user_id,
                        symbol=exit_signal.symbol,
                        condition_type='price_above',
                        condition_params={'threshold': 0},
                        condition_description=f"Strategy Queue: Sell {exit_signal.quantity} {exit_signal.symbol} at Open",
                        action_type='market_sell',
                        action_payload={'quantity': exit_signal.quantity},
                        portfolio_id=portfolio_id,
                        action_note=f"Queued Strategy Sell (Run {run_id}): {exit_signal.reason}"
                    )
                    logger.info(f"Queued sell alert {alert_id} for {exit_signal.symbol}")
                    log_event(self.db, run_id, f"QUEUED SELL {exit_signal.symbol}: {exit_signal.quantity} shares (Alert {alert_id})")
                    trades_executed += 1

            except Exception as e:
                logger.error(f"Failed to execute/queue sell for {exit_signal.symbol}: {e}")
                print(f"    ✗ Failed to sell {exit_signal.symbol}: {e}")

        # Get current cash after sells
        summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
        available_cash = summary.get('cash', 0) if summary else 0
        print(f"\n  Available cash after sells: ${available_cash:,.2f} "
              f"(freed ${cash_freed:,.2f} from {len(exits)} sells)")
        log_event(self.db, run_id, f"Available cash: ${available_cash:,.2f}")

        # Phase 1: Calculate all positions with priority ordering
        prioritized_positions = self._calculate_all_positions(
            buy_decisions=buy_decisions,
            portfolio_id=portfolio_id,
            available_cash=available_cash,
            method=method,
            rules=position_rules,
            run_id=run_id
        )

        # Phase 2: Execute buys in priority order with real-time cash tracking
        if prioritized_positions:
            print(f"\n  Phase 2: Executing {len(prioritized_positions)} BUY orders in priority order...")
            log_event(self.db, run_id, f"Phase 2: Executing {len(prioritized_positions)} buys")

            running_cash = available_cash

            for pos_data in prioritized_positions:
                symbol = pos_data['symbol']
                position = pos_data['position']
                decision = pos_data['decision']

                print(f"\n  Executing {symbol}:")
                print(f"    Shares: {position.shares}")
                print(f"    Value: ${position.estimated_value:,.2f}")
                print(f"    Cash before: ${running_cash:,.2f}")

                if position.shares > 0:
                    # Get position type from decision
                    pos_type = decision.get('position_type', 'new')

                    if is_market_open:
                        result = portfolio_service.execute_trade(
                            portfolio_id=portfolio_id,
                            symbol=symbol,
                            transaction_type='BUY',
                            quantity=position.shares,
                            note=f"Strategy buy ({pos_type}): {decision.get('consensus_reasoning', '')}",
                            position_type=pos_type,
                            db=self.db
                        )
                        if result.get('success'):
                            trades_executed += 1
                            running_cash -= position.estimated_value
                            log_event(
                                self.db,
                                run_id,
                                f"BUY {symbol}: {position.shares} shares, ${position.estimated_value:,.2f} spent, ${running_cash:,.2f} remaining"
                            )
                            print(f"    ✓ Trade executed successfully")
                            print(f"    Cash after: ${running_cash:,.2f}")

                            # Update decision with trade details
                            if decision.get('id'):
                                self.db.update_strategy_decision(
                                    decision_id=decision['id'],
                                    shares_traded=position.shares,
                                    trade_price=position.estimated_value / position.shares if position.shares > 0 else 0,
                                    position_value=position.estimated_value,
                                    transaction_id=result.get('transaction_id')
                                )
                        else:
                            error = result.get('error', 'Unknown error')
                            print(f"    ✗ Trade failed: {error}")
                            logger.warning(f"Trade execution failed for {symbol}: {error}")
                            log_event(self.db, run_id, f"BUY {symbol} FAILED: {error}")
                    elif user_id:
                        # Idempotency check: Don't queue duplicate buy alert
                        is_duplicate = any(
                            a['symbol'] == symbol and 
                            a['action_type'] == 'market_buy' and
                            a.get('portfolio_id') == portfolio_id
                            for a in existing_alerts
                        )
                        
                        if is_duplicate:
                            print(f"    ⚠ Skipped {symbol}: Buy alert already queued.")
                            log_event(self.db, run_id, f"DUPLICATE BUY SKIP: {symbol} already queued.")
                            # Still count as "executed" (or at least processed) for the summary
                            trades_executed += 1
                            continue

                        alert_id = self.db.create_alert(
                            user_id=user_id,
                            symbol=symbol,
                            condition_type='price_above',
                            condition_params={'threshold': 0},
                            condition_description=f"Strategy Queue: Buy {position.shares} {symbol} at Open",
                            action_type='market_buy',
                            action_payload={'quantity': position.shares, 'decision_id': decision.get('id')},
                            portfolio_id=portfolio_id,
                            action_note=f"Queued Strategy Buy (Run {run_id}): {decision.get('consensus_reasoning', '')}"
                        )
                        logger.info(f"Queued buy alert {alert_id} for {symbol}")
                        log_event(self.db, run_id, f"QUEUED BUY {symbol}: {position.shares} shares (Alert {alert_id})")
                        trades_executed += 1

                        # Update decision to reflect queued status (optional but good)
                        # Update decision to reflect queued status (optional but good)
                        if decision.get('id'):
                             self.db.update_strategy_decision(
                                decision_id=decision['id'],
                                shares_traded=position.shares,
                                trade_price=position.estimated_value / position.shares if position.shares > 0 else 0,
                                position_value=position.estimated_value,
                                decision_reasoning=f"{decision.get('decision_reasoning', '')} [QUEUED via Alert {alert_id}]"
                            )
                        print(f"    ✓ Trade queued for market open (Alert {alert_id})")
                        running_cash -= position.estimated_value
                else:
                    reason = position.reasoning
                    print(f"    ⚠ Skipping trade: {reason}")
                    logger.info(f"Skipping {symbol} buy: {reason}")
                    log_event(self.db, run_id, f"Skipped {symbol}: {reason}")
                    
                    # Update decision to reflect skip
                    if decision.get('id'):
                        current_reason = decision.get('decision_reasoning', '')
                        self.db.update_strategy_decision(
                            decision_id=decision['id'],
                            shares_traded=0,
                            decision_reasoning=f"{current_reason} [Skipped Execution: {reason}]"
                        )
        else:
            print("\n  No buy positions to execute")

        return trades_executed
