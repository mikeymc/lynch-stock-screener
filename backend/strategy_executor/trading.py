# ABOUTME: Trading mixin for position sizing and trade execution
# ABOUTME: Handles Phase 6 of strategy execution with three-phase trade execution

import logging
from typing import Dict, Any, List, Tuple

from portfolio_service import fetch_current_prices_batch
from strategy_executor.models import ExitSignal
from strategy_executor.utils import log_event

logger = logging.getLogger(__name__)


class TradingMixin:
    """Phase 6: Position sizing and trade execution."""

    def _process_exits(
        self,
        exits: List[ExitSignal],
        portfolio_id: int,
        is_market_open: bool,
        user_id: int,
        existing_alerts: List[Dict],
        run_id: int
    ) -> Tuple[int, float]:
        """Execute or queue all exit signals.

        Market open: executes sells immediately via execute_trade.
        Market closed: queues market_sell alerts with idempotency check.

        Returns:
            (count, anticipated_proceeds) — proceeds are always summed
            regardless of market status, so callers can use them for
            off-hours cash anticipation.
        """
        import portfolio_service

        count = 0
        anticipated_proceeds = 0.0

        print("\n  Executing SELL orders...")

        for exit_signal in exits:
            try:
                value = exit_signal.current_value
                if value is None:
                    price = self.position_sizer._fetch_price(exit_signal.symbol)
                    value = (exit_signal.quantity * price) if price else 0.0
                anticipated_proceeds += value

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
                        count += 1
                        log_event(self.db, run_id, f"SELL {exit_signal.symbol}: {exit_signal.reason}")
                        print(f"    ✓ SOLD {exit_signal.symbol}: {exit_signal.quantity} shares "
                              f"(freed ${value:,.2f})")
                elif user_id:
                    # Idempotency check: don't queue duplicate sell alert
                    is_duplicate = any(
                        a['symbol'] == exit_signal.symbol and
                        a['action_type'] == 'market_sell' and
                        a.get('portfolio_id') == portfolio_id
                        for a in existing_alerts
                    )

                    if is_duplicate:
                        count += 1
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
                    count += 1

            except Exception as e:
                logger.error(f"Failed to execute/queue sell for {exit_signal.symbol}: {e}")
                print(f"    ✗ Failed to sell {exit_signal.symbol}: {e}")

        return count, anticipated_proceeds

    def _execute_buys(
        self,
        prioritized_positions: List[Dict[str, Any]],
        portfolio_id: int,
        is_market_open: bool,
        user_id: int,
        existing_alerts: List[Dict],
        run_id: int
    ) -> int:
        """Execute or queue all buy orders in priority order.

        Market open: executes buys immediately and updates decision records.
        Market closed: queues market_buy alerts with idempotency check.

        Returns:
            Count of buys executed or queued.
        """
        import portfolio_service

        if not prioritized_positions:
            print("\n  No buy positions to execute")
            return 0

        count = 0
        running_cash = None  # tracked for logging only; actual cash already computed

        print(f"\n  Phase 2: Executing {len(prioritized_positions)} BUY orders in priority order...")
        log_event(self.db, run_id, f"Phase 2: Executing {len(prioritized_positions)} buys")

        for pos_data in prioritized_positions:
            symbol = pos_data['symbol']
            position = pos_data['position']
            decision = pos_data['decision']

            print(f"\n  Executing {symbol}:")
            print(f"    Shares: {position.shares}")
            print(f"    Value: ${position.estimated_value:,.2f}")

            if position.shares <= 0:
                reason = position.reasoning
                print(f"    ⚠ Skipping trade: {reason}")
                logger.info(f"Skipping {symbol} buy: {reason}")
                log_event(self.db, run_id, f"Skipped {symbol}: {reason}")

                if decision.get('id'):
                    current_reason = decision.get('decision_reasoning', '')
                    self.db.update_strategy_decision(
                        decision_id=decision['id'],
                        shares_traded=0,
                        decision_reasoning=f"{current_reason} [Skipped Execution: {reason}]"
                    )
                continue

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
                    count += 1
                    log_event(
                        self.db,
                        run_id,
                        f"BUY {symbol}: {position.shares} shares, ${position.estimated_value:,.2f} spent"
                    )
                    print(f"    ✓ Trade executed successfully")

                    if decision.get('id'):
                        self.db.update_strategy_decision(
                            decision_id=decision['id'],
                            shares_traded=position.shares,
                            trade_price=position.estimated_value / position.shares,
                            position_value=position.estimated_value,
                            transaction_id=result.get('transaction_id')
                        )
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"    ✗ Trade failed: {error}")
                    logger.warning(f"Trade execution failed for {symbol}: {error}")
                    log_event(self.db, run_id, f"BUY {symbol} FAILED: {error}")

            elif user_id:
                # Idempotency check: don't queue duplicate buy alert
                is_duplicate = any(
                    a['symbol'] == symbol and
                    a['action_type'] == 'market_buy' and
                    a.get('portfolio_id') == portfolio_id
                    for a in existing_alerts
                )

                if is_duplicate:
                    count += 1
                    print(f"    ⚠ Skipped {symbol}: Buy alert already queued.")
                    log_event(self.db, run_id, f"DUPLICATE BUY SKIP: {symbol} already queued.")
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
                count += 1

                if decision.get('id'):
                    self.db.update_strategy_decision(
                        decision_id=decision['id'],
                        shares_traded=position.shares,
                        trade_price=position.estimated_value / position.shares,
                        position_value=position.estimated_value,
                        decision_reasoning=f"{decision.get('decision_reasoning', '')} [QUEUED via Alert {alert_id}]"
                    )
                print(f"    ✓ Trade queued for market open (Alert {alert_id})")

        return count

    def _execute_trades(
        self,
        buy_decisions: List[Dict[str, Any]],
        exits: List[ExitSignal],
        strategy: Dict[str, Any],
        run_id: int,
        held_verdicts: List[Dict] = None
    ) -> int:
        """Coordinate the trade execution: Use Target Portfolio approach."""
        import portfolio_service

        portfolio_id = strategy['portfolio_id']
        position_rules = strategy.get('position_sizing', {})
        method = position_rules.get('method', 'equal_weight')

        # Check market status and resolve user context once
        is_market_open = portfolio_service.is_market_open()

        user_id = None
        existing_alerts = []

        if not is_market_open:
            print(f"   Market is closed. Queuing trades for next open via Alerts.")
            log_event(self.db, run_id, "Market closed. Queuing transactions for next market open.")

            try:
                portfolio = self.db.get_portfolio(portfolio_id)
                if portfolio:
                    user_id = portfolio.get('user_id')
            except Exception as e:
                logger.error(f"Failed to fetch portfolio {portfolio_id} for user lookup: {e}")

            if not user_id:
                logger.error(f"Could not determine user_id for portfolio {portfolio_id}, cannot queue off-hours trades.")

            if user_id:
                try:
                    existing_alerts = self.db.get_alerts(user_id, status='active')
                    logger.info(f"Fetched {len(existing_alerts)} existing active alerts for idempotency check.")
                except Exception as e:
                    logger.error(f"Failed to fetch existing alerts for user {user_id}: {e}")

        # Query current portfolio state
        portfolio_summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
        portfolio_cash = portfolio_summary.get('cash', 0) if portfolio_summary else 0
        portfolio_value = portfolio_summary.get('total_value', 0) if portfolio_summary else 0

        # Phase A: Process mandatory exits (Universe, Price, Time, Deliberation AVOID)
        sells_executed, anticipated_proceeds = self._process_exits(
            exits=exits,
            portfolio_id=portfolio_id,
            is_market_open=is_market_open,
            user_id=user_id,
            existing_alerts=existing_alerts,
            run_id=run_id
        )

        # Cash available before rebalancing
        cash_available_to_trade = portfolio_cash + (anticipated_proceeds if not is_market_open else 0)

        print(f"\n  Processed mandatory exits. Cash state: ${cash_available_to_trade:,.2f} "
              f"(db=${portfolio_cash:,.2f}, anticipated=${anticipated_proceeds:,.2f})")
        log_event(self.db, run_id, f"Available cash: ${cash_available_to_trade:,.2f}")

        # Get current holdings and remove exited symbols to get post-exit state
        post_exit_holdings = {}
        try:
            current_portfolio_holdings = self.db.get_portfolio_holdings(portfolio_id) or {}
            exit_symbols = {s.symbol for s in exits}
            # Convert to symbol -> quantity map for PositionSizer
            for sym, qty in current_portfolio_holdings.items():
                if sym not in exit_symbols:
                    post_exit_holdings[sym] = qty
        except Exception as e:
            logger.warning(f"Could not fetch holdings for portfolio {portfolio_id}: {e}")

        # Phase B: Calculate Target Portfolio
        print("\n  Phase B: Calculating Target Portfolio...")
        log_event(self.db, run_id, "Phase B: Calculating Target Portfolio")

        # 1. Build unified candidates list (New Buys + Held Verdicts)
        candidates = []
        seen_candidates = set()

        def add_candidate(source_item):
            sym = source_item['symbol']
            if sym in seen_candidates:
                return
            seen_candidates.add(sym)

            # Determine score/conviction
            score = source_item.get('consensus_score')
            if score is None:
                l = source_item.get('lynch_score') or 0
                b = source_item.get('buffett_score') or 0
                score = (l + b) / 2

            candidates.append({
                'symbol': sym,
                'conviction': score,
                'price': 0,
                'source_data': source_item
            })

        for d in buy_decisions:
            add_candidate(d)
        for h in (held_verdicts or []):
            add_candidate(h)

        if candidates:
            symbols = [c['symbol'] for c in candidates]
            prices = fetch_current_prices_batch(symbols, db=self.db)
            for c in candidates:
                c['price'] = prices.get(c['symbol'], 0)
            missing = [c['symbol'] for c in candidates if c['price'] == 0]
            if missing:
                logger.warning(f"No price data for candidates: {missing}")

        log_event(self.db, run_id, f"Moving to #2: calculating target orders")
        log_event(self.db, run_id, f"Candidates: {len(candidates)} and {len(post_exit_holdings)} post-exit")
        log_event(self.db, run_id, f"Candidates: portfolio value: {portfolio_value} and cash available: {cash_available_to_trade}")
        log_event(self.db, run_id, f"Method: {method}")
        log_event(self.db, run_id, f"Rules: {position_rules}")

        # 2. Calculate Targets and Generate Signals
        target_sells, target_buys = self.position_sizer.calculate_target_orders(
            section_id=portfolio_id,
            candidates=candidates,
            portfolio_value=portfolio_value, # Uses total liquidity as base
            holdings=post_exit_holdings,
            method=method,
            rules=position_rules,
            cash_available=cash_available_to_trade
        )

        print(f"  Generated {len(target_sells)} rebalancing sells and {len(target_buys)} buys")
        log_event(self.db, run_id, f"Target Portfolio: {len(target_sells)} trims/exits, {len(target_buys)} buys")

        # Phase C: Execute Target Sells (Trims/Displacements)
        if target_sells:
            print(f"\n  Phase C: Executing Rebalancing Sells...")
            s_count, s_proceeds = self._process_exits(
                exits=target_sells,
                portfolio_id=portfolio_id,
                is_market_open=is_market_open,
                user_id=user_id,
                existing_alerts=existing_alerts,
                run_id=run_id
            )
            sells_executed += s_count
            cash_available_to_trade += (s_proceeds if not is_market_open else 0)
            print(f"  Proceeds from rebalancing: ${s_proceeds:,.2f}. Updated Allocatable Cash: ${cash_available_to_trade:,.2f}")

        # Phase D: Execute Target Buys
        # Note: prioritize_positions logic in _execute_buys is specific to the old way.
        # target_buys is ALREADY prioritized (sorted by conviction in generate_signals)
        # We need to adapt _execute_buys or just call the inner logic.
        # _execute_buys expects `prioritized_positions` format which matches `target_buys` format:
        # {symbol, position, decision, priority_score}

        if target_buys:
            print(f"\n  Phase D: Executing Target Buys...")
            buys_executed = self._execute_buys(
                prioritized_positions=target_buys,
                portfolio_id=portfolio_id,
                is_market_open=is_market_open,
                user_id=user_id,
                existing_alerts=existing_alerts,
                run_id=run_id
            )
        else:
            buys_executed = 0

        return sells_executed + buys_executed
