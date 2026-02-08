# ABOUTME: Main orchestrator for autonomous strategy execution
# ABOUTME: Coordinates screening, scoring, thesis generation, consensus, and trade execution

import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai

from strategy_executor.models import ExitSignal
from strategy_executor.conditions import ConditionEvaluator
from strategy_executor.consensus import ConsensusEngine
from strategy_executor.position_sizing import PositionSizer
from strategy_executor.exit_conditions import ExitConditionChecker
from strategy_executor.holding_reevaluation import HoldingReevaluator

logger = logging.getLogger(__name__)


class BenchmarkTracker:
    """Tracks strategy performance vs S&P 500."""

    def __init__(self, db):
        self.db = db

    def record_daily_benchmark(self) -> Dict[str, Any]:
        """Record daily SPY price. Call once per day after market close."""
        try:
            import yfinance as yf
            spy = yf.Ticker("SPY")
            price = spy.fast_info.get('lastPrice')

            if not price:
                raise ValueError("Could not fetch SPY price")

            today = date.today()
            self.db.save_benchmark_snapshot(today, price)

            return {'date': today, 'spy_price': price}
        except Exception as e:
            logger.error(f"Failed to record benchmark: {e}")
            raise

    def record_strategy_performance(
        self,
        strategy_id: int,
        portfolio_value: float
    ) -> Dict[str, Any]:
        """Record strategy performance and calculate alpha."""
        today = date.today()

        # Get inception data
        inception = self.db.get_strategy_inception_data(strategy_id)

        if inception:
            inception_value = inception['portfolio_value']
            inception_spy = inception['spy_price']
        else:
            # First run - current values as inception
            inception_value = portfolio_value
            benchmark = self.db.get_benchmark_snapshot(today)
            inception_spy = benchmark['spy_price'] if benchmark else None

        # Get current SPY
        benchmark = self.db.get_benchmark_snapshot(today)
        current_spy = benchmark['spy_price'] if benchmark else None

        # Calculate returns
        if inception_value and inception_value > 0:
            portfolio_return_pct = ((portfolio_value - inception_value) / inception_value) * 100
        else:
            portfolio_return_pct = 0

        if inception_spy and inception_spy > 0 and current_spy:
            spy_return_pct = ((current_spy - inception_spy) / inception_spy) * 100
        else:
            spy_return_pct = 0

        alpha = portfolio_return_pct - spy_return_pct

        # Save performance
        self.db.save_strategy_performance(
            strategy_id, today, portfolio_value,
            portfolio_return_pct, spy_return_pct, alpha
        )

        return {
            'date': today,
            'portfolio_value': portfolio_value,
            'portfolio_return_pct': portfolio_return_pct,
            'spy_return_pct': spy_return_pct,
            'alpha': alpha
        }

    def get_performance_series(
        self,
        strategy_id: int,
        days: int = 365
    ) -> List[Dict[str, Any]]:
        """Get time series of performance for charting."""
        from datetime import timedelta
        start_date = date.today() - timedelta(days=days)
        return self.db.get_strategy_performance(strategy_id, start_date)


class StrategyExecutor:
    """Main orchestrator for autonomous strategy execution."""

    def __init__(self, db, analyst=None, lynch_criteria=None):
        self.db = db
        self.condition_evaluator = ConditionEvaluator(db)
        self.consensus_engine = ConsensusEngine()
        self.position_sizer = PositionSizer(db)
        self.exit_checker = ExitConditionChecker(db)
        self.benchmark_tracker = BenchmarkTracker(db)

        # Lazily initialize analyst and lynch_criteria if not provided
        self._analyst = analyst
        self._lynch_criteria = lynch_criteria
        self._holding_reevaluator = None

    @property
    def analyst(self):
        """Lazy initialization of StockAnalyst."""
        if self._analyst is None:
            from stock_analyst import StockAnalyst
            self._analyst = StockAnalyst(self.db)
        return self._analyst

    @property
    def lynch_criteria(self):
        """Lazy initialization of LynchCriteria."""
        if self._lynch_criteria is None:
            from lynch_criteria import LynchCriteria
            from earnings_analyzer import EarningsAnalyzer
            analyzer = EarningsAnalyzer(self.db)
            self._lynch_criteria = LynchCriteria(self.db, analyzer)
        return self._lynch_criteria

    @property
    def holding_reevaluator(self):
        """Lazy initialization of HoldingReevaluator."""
        if self._holding_reevaluator is None:
            self._holding_reevaluator = HoldingReevaluator(
                self.db,
                self.condition_evaluator,
                self.lynch_criteria
            )
        return self._holding_reevaluator

    def execute_strategy(self, strategy_id: int, limit: Optional[int] = None, job_id: Optional[int] = None) -> Dict[str, Any]:
        """Execute a strategy run.

        Args:
            strategy_id: ID of strategy to run
            limit: Optional limit on number of stocks to score
            job_id: Optional job ID for progress reporting

        Returns:
            Summary of the run with statistics
        """
        # Load strategy
        print(f"Loading strategy {strategy_id}...")
        strategy = self.db.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        if not strategy.get('enabled', True):
            return {'status': 'skipped', 'reason': 'Strategy is disabled'}

        print(f"✓ Strategy loaded: {strategy.get('name', 'Unnamed')}")

        # Create run record
        run_id = self.db.create_strategy_run(strategy_id)
        print(f"✓ Created run record: {run_id}\n")

        try:
            # Benchmark recorded by portfolio_sweep job
            print("Skipping benchmark recording (handled by portfolio_sweep)\n")

            # Get portfolio state
            portfolio_id = strategy['portfolio_id']
            summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
            portfolio_value = summary['total_value'] if summary else 0

            self.db.update_strategy_run(
                run_id,
                portfolio_value=portfolio_value,
                spy_price=self._get_spy_price()
            )

            # Phase 1: Screen candidates
            print("=" * 60)
            print("PHASE 1: SCREENING")
            print("=" * 60)
            self._log_event(run_id, "Starting screening phase")
            conditions = strategy.get('conditions', {})
            all_candidates = self.condition_evaluator.evaluate_universe(conditions)

            # Apply limit if requested
            if limit and limit > 0:
                print(f"  Limiting candidates to {limit} per request (found {len(all_candidates)})")
                all_candidates = all_candidates[:limit]

            # Separate held vs new positions
            holdings = self.db.get_portfolio_holdings(portfolio_id)
            held_symbols = set(holdings.keys())
            new_candidates = [s for s in all_candidates if s not in held_symbols]
            held_candidates = [s for s in all_candidates if s in held_symbols]

            print(f"  Universe breakdown:")
            print(f"    New positions: {len(new_candidates)}")
            print(f"    Position additions: {len(held_candidates)}")
            if held_candidates:
                print(f"    Held stocks in universe: {held_candidates}")

            self.db.update_strategy_run(run_id, stocks_screened=len(all_candidates))
            self._log_event(run_id, f"Screened {len(all_candidates)} candidates ({len(new_candidates)} new, {len(held_candidates)} additions)")
            print(f"✓ Screened {len(all_candidates)} total candidates\n")

            # Phase 2: Score candidates (with differentiated thresholds)
            print("=" * 60)
            print("PHASE 2: SCORING")
            print("=" * 60)

            # Score new positions with standard thresholds
            scored_new = []
            if new_candidates:
                print(f"  Scoring {len(new_candidates)} new position candidates...")
                scored_new = self._score_candidates(new_candidates, conditions, run_id, is_addition=False)
                print(f"  ✓ {len(scored_new)} new positions passed requirements\n")

            # Score additions with higher thresholds
            scored_additions = []
            if held_candidates:
                print(f"  Scoring {len(held_candidates)} position addition candidates (higher thresholds)...")
                scored_additions = self._score_candidates(held_candidates, conditions, run_id, is_addition=True)
                print(f"  ✓ {len(scored_additions)} additions passed requirements\n")

            # Combine scored candidates
            scored = scored_new + scored_additions
            self.db.update_strategy_run(run_id, stocks_scored=len(scored))
            print(f"✓ Scored {len(scored)} stocks that passed requirements\n")

            # Phase 3: Thesis Generation (with parallel processing)
            # Phase 3: Thesis Generation (with parallel processing)
            print("=" * 60)
            print("PHASE 3: THESIS GENERATION")
            print("=" * 60)
            if conditions.get('require_thesis', False):
                user_id = strategy.get('user_id')
                enriched = self._generate_theses(scored, run_id, user_id, job_id=job_id)
                self.db.update_strategy_run(run_id, theses_generated=len(enriched))
                print(f"✓ Generated {len(enriched)} theses\\n")
            else:
                print("Skipping (thesis not required)\\n")
                enriched = scored

            # Phase 4: Deliberate (Lynch and Buffett discuss their theses)
            print("=" * 60)
            print("PHASE 4: DELIBERATION")
            print("=" * 60)
            user_id = strategy.get('user_id')
            decisions = self._deliberate(enriched, run_id, conditions, user_id, job_id=job_id)
            print(f"✓ {len(decisions)} BUY decisions made\\n")

            # Phase 4.5: Process dividends - REMOVED (Handled by portfolio_sweep)
            # print("=" * 60)
            # print("PHASE 4.5: DIVIDEND PROCESSING")
            # print("=" * 60)
             # try:
            #     from dividend_manager import DividendManager
            #     dividend_mgr = DividendManager(self.db)
            #     dividend_mgr.process_portfolio(portfolio_id)
            #     print("✓ Dividend processing complete\n")
            #     self._log_event(run_id, "Processed dividends for all portfolios")
            # except Exception as e:
            #     logger.warning(f"Dividend processing failed (non-critical): {e}")
            #     print(f"⚠ Dividend processing failed: {e}\n")

            # Phase 5: Check exits
            print("=" * 60)
            print("PHASE 5: EXIT CHECKS")
            print("=" * 60)
            exit_conditions = strategy.get('exit_conditions', {})
            exits = self.exit_checker.check_exits(
                portfolio_id,
                exit_conditions,
                scoring_func=self._get_current_scores
            )
            print(f"✓ Found {len(exits)} positions to exit\n")

            # Phase 5.5: Holding Re-evaluation (check if held positions still meet criteria)
            print("=" * 60)
            print("PHASE 5.5: HOLDING RE-EVALUATION")
            print("=" * 60)
            reevaluation_config = conditions.get('holding_reevaluation', {})
            if reevaluation_config.get('enabled', False):
                reevaluation_exits = self.holding_reevaluator.check_holdings(
                    portfolio_id,
                    conditions,
                    reevaluation_config
                )
                if reevaluation_exits:
                    print(f"✓ Re-evaluation flagged {len(reevaluation_exits)} positions for exit:")
                    for exit_signal in reevaluation_exits:
                        print(f"    {exit_signal.symbol}: {exit_signal.reason}")
                    exits.extend(reevaluation_exits)
                    self._log_event(run_id, f"Re-evaluation: {len(reevaluation_exits)} positions flagged for exit")
                else:
                    print("✓ All held positions still meet criteria")
            else:
                print("Skipping (re-evaluation not enabled)\n")

            # Phase 6: Execute trades
            print("=" * 60)
            print("PHASE 6: TRADE EXECUTION")
            print("=" * 60)
            trades_executed = self._execute_trades(
                decisions, exits, strategy, run_id
            )
            print(f"✓ Executed {trades_executed} trades\n")

            # Phase 7: Record performance
            new_summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
            new_value = new_summary['total_value'] if new_summary else portfolio_value

            perf = self.benchmark_tracker.record_strategy_performance(strategy_id, new_value)

            # Complete run
            self.db.update_strategy_run(
                run_id,
                status='completed',
                completed_at=datetime.now(),
                trades_executed=trades_executed
            )

            return {
                'status': 'completed',
                'run_id': run_id,
                'stocks_screened': len(all_candidates),
                'stocks_scored': len(scored),
                'theses_generated': len(enriched) if conditions.get('require_thesis') else 0,
                'trades_executed': trades_executed,
                'alpha': perf.get('alpha', 0)
            }

        except Exception as e:
            logger.error(f"Strategy execution failed: {e}")
            self.db.update_strategy_run(
                run_id,
                status='failed',
                completed_at=datetime.now(),
                error_message=str(e)
            )
            raise

    def _get_spy_price(self) -> Optional[float]:
        """Get current SPY price from benchmark snapshots."""
        benchmark = self.db.get_benchmark_snapshot(date.today())
        return benchmark['spy_price'] if benchmark else None

    def _get_current_scores(self, symbol: str) -> Dict[str, Any]:
        """Get current Lynch and Buffett scores for a symbol.

        Used by ExitConditionChecker for score degradation checks.
        """
        scores = {}
        try:
            lynch_result = self.lynch_criteria.evaluate_stock(symbol, character_id='lynch')
            if lynch_result:
                scores['lynch_score'] = lynch_result.get('overall_score', 0)
                scores['lynch_status'] = lynch_result.get('overall_status', 'N/A')

            buffett_result = self.lynch_criteria.evaluate_stock(symbol, character_id='buffett')
            if buffett_result:
                scores['buffett_score'] = buffett_result.get('overall_score', 0)
                scores['buffett_status'] = buffett_result.get('overall_status', 'N/A')
        except Exception as e:
            logger.warning(f"Failed to get scores for {symbol}: {e}")

        return scores

    def _log_event(self, run_id: int, message: str):
        """Log an event to the run log."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'message': message
        }
        self.db.append_to_run_log(run_id, event)
        logger.info(f"[Run {run_id}] {message}")

    def _score_candidates(
        self,
        candidates: List[str],
        conditions: Dict[str, Any],
        run_id: int,
        is_addition: bool = False
    ) -> List[Dict[str, Any]]:
        """Score candidates with Lynch and Buffett scoring.

        Args:
            candidates: List of symbols to score
            conditions: Strategy conditions with scoring requirements
            run_id: Current run ID for logging
            is_addition: If True, use higher thresholds for position additions

        Returns:
            List of stocks that passed scoring requirements
        """
        from lynch_criteria import SCORE_THRESHOLDS
        scored = []
        scoring_reqs = conditions.get('scoring_requirements', [])

        # Parse scoring requirements (Default to 'BUY' threshold - 60)
        # We use OR logic: A stock must meet AT LEAST ONE criteria to pass.
        default_min = SCORE_THRESHOLDS.get('BUY', 60)
        lynch_req = default_min
        buffett_req = default_min

        # For additions, use higher thresholds if configured
        if is_addition:
            addition_reqs = conditions.get('addition_scoring_requirements', [])
            if addition_reqs:
                # Use explicit addition requirements
                for req in addition_reqs:
                    if req.get('character') == 'lynch':
                        lynch_req = req.get('min_score', default_min)
                    elif req.get('character') == 'buffett':
                        buffett_req = req.get('min_score', default_min)
            else:
                # Default: +10 higher than base requirements
                for req in scoring_reqs:
                    if req.get('character') == 'lynch':
                        lynch_req = req.get('min_score', default_min) + 10
                    elif req.get('character') == 'buffett':
                        buffett_req = req.get('min_score', default_min) + 10
                # If no base requirements, use default + 10
                if not scoring_reqs:
                    lynch_req = default_min + 10
                    buffett_req = default_min + 10
        else:
            # New positions: use standard requirements
            for req in scoring_reqs:
                if req.get('character') == 'lynch':
                    lynch_req = req.get('min_score', default_min)
                elif req.get('character') == 'buffett':
                    buffett_req = req.get('min_score', default_min)

        position_type = "addition" if is_addition else "new position"
        self._log_event(run_id, f"Scoring {len(candidates)} {position_type} candidates (Lynch: {lynch_req}, Buffett: {buffett_req})")

        # Use vectorized scoring for batch operations
        if not candidates:
            return []

        try:
            import pandas as pd
            from stock_vectors import StockVectors, DEFAULT_ALGORITHM_CONFIG
            from characters.buffett import BUFFETT

            print(f"  Loading stock data for {len(candidates)} candidates...")

            # Load all stock data with vectorized approach
            vectors = StockVectors(self.db)
            df_all = vectors.load_vectors(country_filter='US')

            if df_all is None or df_all.empty:
                self._log_event(run_id, "No stock data available for scoring")
                return []

            # Filter to just our candidates
            df = df_all[df_all['symbol'].isin(candidates)].copy()

            if df.empty:
                self._log_event(run_id, f"No data found for candidates: {candidates[:5]}...")
                return []

            print(f"  Found data for {len(df)} stocks")

            # Score with Lynch using vectorized batch scoring
            print(f"  Scoring with Lynch criteria...")
            df_lynch = self.lynch_criteria.evaluate_batch(df, DEFAULT_ALGORITHM_CONFIG)

            # Score with Buffett using vectorized batch scoring
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

            # Merge Lynch and Buffett scores
            df_merged = df_lynch[['symbol', 'overall_score', 'overall_status']].rename(
                columns={'overall_score': 'lynch_score', 'overall_status': 'lynch_status'}
            )
            df_buffett_scores = df_buffett[['symbol', 'overall_score', 'overall_status']].rename(
                columns={'overall_score': 'buffett_score', 'overall_status': 'buffett_status'}
            )
            df_merged = df_merged.merge(df_buffett_scores, on='symbol', how='inner')

            # Add position_type
            df_merged['position_type'] = 'addition' if is_addition else 'new'

            # Convert to list of dicts and process each
            for _, row in df_merged.iterrows():
                symbol = row['symbol']
                stock_data = {
                    'symbol': symbol,
                    'lynch_score': row['lynch_score'],
                    'lynch_status': row['lynch_status'],
                    'buffett_score': row['buffett_score'],
                    'buffett_status': row['buffett_status'],
                    'position_type': row['position_type']
                }

                type_label = "ADDITION" if is_addition else "NEW"
                print(f"  {symbol} ({type_label}): Lynch {stock_data['lynch_score']:.0f}, Buffett {stock_data['buffett_score']:.0f}")

                # Check if passes scoring requirements (OR Logic)
                # Pass if ANY requirement is met
                lynch_pass = stock_data['lynch_score'] >= lynch_req
                buffett_pass = stock_data['buffett_score'] >= buffett_req

                passes = lynch_pass or buffett_pass

                if passes:
                    scored.append(stock_data)
                    # Create reasoning string for log
                    reason_parts = []
                    if lynch_pass:
                        reason_parts.append(f"Lynch {stock_data['lynch_score']:.0f} >= {lynch_req}")
                    if buffett_pass:
                        reason_parts.append(f"Buffett {stock_data['buffett_score']:.0f} >= {buffett_req}")

                    reason_str = ", ".join(reason_parts)

                    threshold_note = " (higher bar for additions)" if is_addition else ""
                    print(f"    ✓ PASSED requirements ({reason_str}){threshold_note}")
                    logger.debug(
                        f"{symbol}: PASSED as {type_label} ({reason_str})"
                    )
                else:
                    fail_reasons = []
                    if not lynch_pass:
                        fail_reasons.append(f"Lynch {stock_data['lynch_score']:.0f} < {lynch_req}")
                    if not buffett_pass:
                        fail_reasons.append(f"Buffett {stock_data['buffett_score']:.0f} < {buffett_req}")

                    fail_str = ", ".join(fail_reasons)
                    threshold_note = " (higher bar for additions)" if is_addition else ""
                    print(f"    ✗ FAILED requirements ({fail_str}){threshold_note}")

        except Exception as e:
            logger.error(f"Vectorized scoring failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_event(run_id, f"ERROR: Vectorized scoring failed: {e}")
            return []

        self._log_event(run_id, f"Scoring complete: {len(scored)}/{len(candidates)} {position_type}s passed requirements")
        return scored

    def _generate_theses(
        self,
        scored: List[Dict[str, Any]],
        run_id: int,
        user_id: int,
        job_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Generate investment theses for scored stocks (Parallelized).

        Generates theses from BOTH Lynch and Buffett characters, each with
        their own verdict (BUY/WATCH/AVOID).

        Args:
            scored: List of scored stock data
            run_id: Current run ID for logging
            user_id: User ID (ignored, uses System User 0 for shared cache)
            job_id: Optional job ID for progress reporting

        Returns:
            List of stocks enriched with thesis data from both characters
        """
        total = len(scored)
        self._log_event(run_id, f"Generating theses for {total} stocks")
        enriched = []

        if not scored:
            return []
            
        # Helper function for parallel execution
        def process_stock(stock):
            symbol = stock['symbol']
            try:
                # Get stock data for thesis generation
                stock_metrics = self.db.get_stock_metrics(symbol)
                if not stock_metrics:
                    logger.warning(f"No metrics for {symbol}, skipping thesis")
                    stock['lynch_thesis_verdict'] = None
                    stock['buffett_thesis_verdict'] = None
                    return stock

                # Get earnings history
                history = self.db.get_earnings_history(symbol)

                # Generate Lynch thesis (Force System User 0)
                lynch_thesis_text = ""
                for chunk in self.analyst.get_or_generate_analysis(
                    user_id=0, # Force System User for shared cache
                    symbol=symbol,
                    stock_data=stock_metrics,
                    history=history or [],
                    use_cache=True,
                    character_id='lynch'
                ):
                    lynch_thesis_text += chunk

                lynch_verdict = self._extract_thesis_verdict(lynch_thesis_text)
                stock['lynch_thesis'] = lynch_thesis_text
                stock['lynch_thesis_verdict'] = lynch_verdict

                # Fetch timestamp for cache invalidation (Force System User 0)
                lynch_meta = self.db.get_lynch_analysis(0, symbol, character_id='lynch')
                stock['lynch_thesis_timestamp'] = lynch_meta.get('generated_at') if lynch_meta else None

                # Generate Buffett thesis (Force System User 0)
                buffett_thesis_text = ""
                for chunk in self.analyst.get_or_generate_analysis(
                    user_id=0, # Force System User for shared cache
                    symbol=symbol,
                    stock_data=stock_metrics,
                    history=history or [],
                    use_cache=True,
                    character_id='buffett'
                ):
                    buffett_thesis_text += chunk

                buffett_verdict = self._extract_thesis_verdict(buffett_thesis_text)
                stock['buffett_thesis'] = buffett_thesis_text
                stock['buffett_thesis_verdict'] = buffett_verdict

                # Fetch timestamp for cache invalidation (Force System User 0)
                buffett_meta = self.db.get_lynch_analysis(0, symbol, character_id='buffett')
                stock['buffett_thesis_timestamp'] = buffett_meta.get('generated_at') if buffett_meta else None

                logger.debug(f"{symbol}: Lynch={lynch_verdict}, Buffett={buffett_verdict}")
                return stock

            except Exception as e:
                logger.warning(f"Failed to generate thesis for {symbol}: {e}")
                stock['lynch_thesis_verdict'] = None
                stock['buffett_thesis_verdict'] = None
                return stock

        # Execute in parallel
        completed = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_stock, stock): stock for stock in scored}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    enriched.append(result)
                except Exception as e:
                    logger.error(f"Thesis generation worker failed: {e}")
                
                completed += 1
                
                # Report progress every 10 items
                if job_id and (completed % 10 == 0 or completed == total):
                    pct = 20 + int((completed / total) * 40) # Phase 3 is 20-60% of total job
                    self.db.update_job_progress(
                        job_id,
                        progress_pct=pct,
                        progress_message=f'Generated theses for {completed}/{total} stocks',
                        processed_count=completed,
                        total_count=total
                    )
                    # Log every 10 completions
                    print(f"  Generated theses for {completed}/{total} stocks")

        self._log_event(run_id, f"Thesis generation complete for {len(enriched)} stocks")
        return enriched

    def _conduct_deliberation(
        self,
        user_id: int,
        symbol: str,
        lynch_thesis: str,
        lynch_verdict: str,
        buffett_thesis: str,
        buffett_verdict: str,
        lynch_timestamp: Optional[datetime] = None,
        buffett_timestamp: Optional[datetime] = None
    ) -> tuple[str, str]:
        """Conduct deliberation between Lynch and Buffett to reach consensus.

        Args:
            user_id: User ID (ignored, uses System User 0 for shared cache)
            symbol: Stock symbol
            lynch_thesis: Lynch's full thesis text
            lynch_verdict: Lynch's verdict (BUY/WATCH/AVOID)
            buffett_thesis: Buffett's full thesis text
            buffett_verdict: Buffett's verdict (BUY/WATCH/AVOID)
            lynch_timestamp: Timestamp when Lynch thesis was generated
            buffett_timestamp: Timestamp when Buffett thesis was generated

        Returns:
            Tuple of (deliberation_text, final_verdict)
        """
        import os
        import time
        from google.genai.types import GenerateContentConfig

        # Check cache first (Force System User 0)
        cached = self.db.get_deliberation(0, symbol)
        if cached:
            # Check for invalidation based on timestamps
            is_stale = False
            cached_time = cached['generated_at']

            # Ensure timezone awareness for comparison if needed
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=None) # Assume naive if inputs are naive

            invalidation_reason = ""

            if lynch_timestamp:
                if lynch_timestamp.tzinfo is None:
                    lynch_timestamp = lynch_timestamp.replace(tzinfo=None)
                if cached_time < lynch_timestamp:
                    is_stale = True
                    invalidation_reason = f"Lynch thesis newer ({lynch_timestamp} > {cached_time})"

            if not is_stale and buffett_timestamp:
                if buffett_timestamp.tzinfo is None:
                    buffett_timestamp = buffett_timestamp.replace(tzinfo=None)
                if cached_time < buffett_timestamp:
                    is_stale = True
                    invalidation_reason = f"Buffett thesis newer ({buffett_timestamp} > {cached_time})"

            if not is_stale:
                logger.info(f"[Deliberation] Using cached deliberation for {symbol}")
                print(f"    Using cached deliberation from {cached['generated_at']}")
                return cached['deliberation_text'], cached['final_verdict']
            else:
                logger.info(f"[Deliberation] Cache invalid for {symbol}: {invalidation_reason}")
                print(f"    Cache invalid: {invalidation_reason}")
                print(f"    Regenerating deliberation...")

        print(f"    No cached deliberation found, generating new one...")

        # Create deliberation prompt
        prompt = f"""You are facilitating a discussion between Peter Lynch and Warren Buffett about {symbol}.

LYNCH'S THESIS (Verdict: {lynch_verdict}):
{lynch_thesis}

BUFFETT'S THESIS (Verdict: {buffett_verdict}):
{buffett_thesis}

Now have them discuss these theses together. They should:
1. Acknowledge each other's key points
2. Discuss where they agree or disagree
3. Consider whether either should revise their verdict based on the other's insights
4. Reach a final consensus verdict

Format the output as a discussion between them, ending with:

## Final Consensus
**[BUY/WATCH/AVOID]**

Reasoning: [Brief explanation of their final decision]
"""

        # Retry configuration
        models = ['gemini-3-flash-preview', 'gemini-2.5-flash']
        max_retries = 3
        base_delay = 2  # Initialize base delay for exponential backoff
        client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

        for model in models:
            retry_count = 0
            while retry_count < max_retries:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=GenerateContentConfig(temperature=0.7)
                    )
                    
                    text = response.text
                    
                    # Extract verdict
                    import re
                    match = re.search(r'\*\*\[?(BUY|WATCH|AVOID)\]?\*\*', text, re.IGNORECASE)
                    verdict = match.group(1).upper() if match else "WATCH" # Default to WATCH if unclear

                    # Save to cache (Force System User 0)
                    self.db.save_deliberation(0, symbol, text, verdict, model)
                    
                    return text, verdict

                except Exception as e:
                    error_msg = str(e)  # Capture error message for logging
                    logger.warning(f"[Deliberation] {model} failed (attempt {retry_count+1}/{max_retries + 1}): {error_msg}. Retrying in {2 * (retry_count + 1)}s...")
                    retry_count += 1

                    if retry_count <= max_retries:
                        delay = base_delay * (2 ** (retry_count - 1))
                        logger.warning(f"[Deliberation] {model} failed (attempt {retry_count}/{max_retries + 1}): {error_msg}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.warning(f"[Deliberation] {model} failed after {max_retries + 1} attempts: {error_msg}")
                        break

        # All models failed
        raise Exception(f"Deliberation failed for {symbol} after trying all models with retries")

    def _extract_thesis_verdict(self, thesis_text: str) -> Optional[str]:
        """Extract BUY/WATCH/AVOID verdict from thesis text.

        The thesis typically starts with '## Bottom Line' followed by
        **BUY**, **WATCH**, or **AVOID**.
        """
        if not thesis_text:
            print("      WARNING: No thesis text to extract verdict from")
            return None

        # Look for verdict markers
        text_upper = thesis_text.upper()

        # Check for explicit verdict patterns
        if '**BUY**' in thesis_text or 'VERDICT: BUY' in text_upper:
            print("      Found BUY verdict (explicit)")
            return 'BUY'
        elif '**WATCH**' in thesis_text or 'VERDICT: WATCH' in text_upper:
            print("      Found WATCH verdict (explicit)")
            return 'WATCH'
        elif '**AVOID**' in thesis_text or 'VERDICT: AVOID' in text_upper:
            print("      Found AVOID verdict (explicit)")
            return 'AVOID'

        # Fallback: look in first 500 chars for verdict keywords
        first_section = text_upper[:500]
        if 'BUY' in first_section and 'AVOID' not in first_section:
            print("      Found BUY verdict (fallback in first 500 chars)")
            return 'BUY'
        elif 'AVOID' in first_section:
            print("      Found AVOID verdict (fallback in first 500 chars)")
            return 'AVOID'
        elif 'WATCH' in first_section or 'HOLD' in first_section:
            print("      Found WATCH verdict (fallback in first 500 chars)")
            return 'WATCH'

        print(f"      WARNING: Could not extract verdict. First 200 chars: {thesis_text[:200]}")
        return None

    def _deliberate(
        self,
        enriched: List[Dict[str, Any]],
        run_id: int,
        conditions: Dict[str, Any] = None,
        user_id: int = None,
        job_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Apply consensus logic to determine final decisions (Parallelized).

        For stocks with theses, conducts deliberation between Lynch and Buffett.
        Otherwise, uses score-based consensus evaluation.

        Args:
            enriched: Stocks with scores and optional thesis data
            run_id: Current run ID for logging
            conditions: Strategy conditions (for thesis_verdict_required filtering)
            user_id: User ID who owns the strategy
            job_id: Optional job ID for progress reporting

        Returns:
            List of stocks with BUY decisions
        """
        decisions = []
        conditions = conditions or {}
        thesis_verdicts_required = conditions.get('thesis_verdict_required', [])
        
        total = len(enriched)
        
        # Helper for parallel execution
        def process_deliberation(stock):
            symbol = stock['symbol']

            # If we have both theses, conduct deliberation
            lynch_thesis = stock.get('lynch_thesis')
            buffett_thesis = stock.get('buffett_thesis')

            if lynch_thesis and buffett_thesis:
                # print(f"  Conducting deliberation for {symbol}...") # Reduced logging noise

                try:
                    deliberation_text, final_verdict = self._conduct_deliberation(
                        user_id=user_id,
                        symbol=symbol,
                        lynch_thesis=lynch_thesis,
                        lynch_verdict=stock.get('lynch_thesis_verdict', 'UNKNOWN'),
                        buffett_thesis=buffett_thesis,
                        buffett_verdict=stock.get('buffett_thesis_verdict', 'UNKNOWN'),
                        lynch_timestamp=stock.get('lynch_thesis_timestamp'),
                        buffett_timestamp=stock.get('buffett_thesis_timestamp')
                    )

                    stock['deliberation'] = deliberation_text
                    stock['final_verdict'] = final_verdict
                    # print(f"    Final verdict after deliberation: {final_verdict}")

                except Exception as e:
                    logger.error(f"Deliberation failed for {symbol}: {e}")
                    stock['final_verdict'] = None
                    stock['deliberation'] = None
                    # print(f"    Deliberation FAILED: {e}")

                # Check if final verdict meets requirements
                if thesis_verdicts_required:
                    final_verdict = stock.get('final_verdict')
                    if final_verdict not in thesis_verdicts_required:
                        # Record as SKIP
                        self.db.create_strategy_decision(
                            run_id=run_id,
                            symbol=symbol,
                            lynch_score=stock.get('lynch_score'),
                            lynch_status=stock.get('lynch_status'),
                            buffett_score=stock.get('buffett_score'),
                            buffett_status=stock.get('buffett_status'),
                            consensus_score=None,
                            consensus_verdict=None,  # Was 'SKIP' - violated constraint
                            thesis_verdict=final_verdict,
                            thesis_summary=stock.get('deliberation', '')[:500] if stock.get('deliberation') else None,
                            thesis_full=stock.get('deliberation'),
                            final_decision='SKIP',
                            decision_reasoning=f"Deliberation verdict '{final_verdict}' not in required: {thesis_verdicts_required}"
                        )
                        return None # Not a BUY decision

                # If verdict is BUY, return it
                final_decision = 'SKIP'
                if stock.get('final_verdict') == 'BUY':
                    final_decision = 'BUY'

                # Record decision
                decision_id = self.db.create_strategy_decision(
                    run_id=run_id,
                    symbol=symbol,
                    lynch_score=stock.get('lynch_score'),
                    lynch_status=stock.get('lynch_status'),
                    buffett_score=stock.get('buffett_score'),
                    buffett_status=stock.get('buffett_status'),
                    consensus_score=None,
                    consensus_verdict=stock.get('final_verdict'),
                    thesis_verdict=stock.get('final_verdict'),
                    thesis_summary=stock.get('deliberation', '')[:500] if stock.get('deliberation') else None,
                    thesis_full=stock.get('deliberation'),
                    final_decision=final_decision,
                    decision_reasoning=f"Deliberation result: {stock.get('final_verdict')}"
                )
                
                if final_decision == 'BUY':
                    stock['id'] = decision_id
                    stock['decision_id'] = decision_id
                    return stock
                return None

            else:
                # No theses available - SKIP
                # We now strictly require AI deliberation to trade.
                # print(f"    ⚠ Skipping {symbol}: No theses generated for deliberation")
                self.db.create_strategy_decision(
                    run_id=run_id,
                    symbol=symbol,
                    lynch_score=stock.get('lynch_score'),
                    lynch_status=stock.get('lynch_status'),
                    buffett_score=stock.get('buffett_score'),
                    buffett_status=stock.get('buffett_status'),
                    consensus_score=None,
                    consensus_verdict=None,  # Was 'SKIP' - violated constraint
                    thesis_verdict=None,
                    thesis_summary=None,
                    thesis_full=None,
                    final_decision='SKIP',
                    decision_reasoning="Skipped: No theses generated for AI deliberation"
                )
                return None

        # Execute in parallel
        completed = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_deliberation, stock): stock for stock in enriched}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        decisions.append(result)
                except Exception as e:
                    logger.error(f"Deliberation worker failed: {e}")
                
                completed += 1
                
                # Report progress every 10 items
                if job_id and (completed % 10 == 0 or completed == total):
                    pct = 60 + int((completed / total) * 30) # Phase 4 is 60-90% of total job
                    self.db.update_job_progress(
                        job_id,
                        progress_pct=pct,
                        progress_message=f'Deliberated on {completed}/{total} stocks ({len(decisions)} BUYs)',
                        processed_count=completed,
                        total_count=total
                    )
                    # Log every 10 completions
                    print(f"  Deliberated on {completed}/{total} stocks")

        return decisions

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
        self._log_event(run_id, f"Phase 1: Calculating positions for {len(buy_decisions)} buy decisions")

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
        self._log_event(run_id, f"Total requested: ${total_requested:,.2f}, Available: ${available_cash:,.2f}")

        # If we exceed available cash, need to rebalance
        if total_requested > available_cash:
            print(f"  ⚠ Insufficient cash! Selecting highest priority positions...")
            self._log_event(run_id, f"Insufficient cash. Prioritizing highest conviction positions.")

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
                    self._log_event(run_id, f"Skipped {pos_data['symbol']} - insufficient cash")

            positions_data = selected
            print(f"  Selected {len(positions_data)}/{len(buy_decisions)} positions, "
                  f"using ${available_cash - remaining_cash:,.2f} of ${available_cash:,.2f}")
            self._log_event(run_id, f"Selected {len(positions_data)} positions totaling ${available_cash - remaining_cash:,.2f}")
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

        if not is_market_open:
            print(f"   Market is closed. Queuing trades for next open via Alerts.")
            self._log_event(run_id, "Market closed. Queuing transactions for next market open.")

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
                        self._log_event(run_id, f"SELL {exit_signal.symbol}: {exit_signal.reason}")
                        print(f"    ✓ SOLD {exit_signal.symbol}: {exit_signal.quantity} shares "
                              f"(freed ${exit_signal.current_value:,.2f})")
                elif user_id:
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
                    self._log_event(run_id, f"QUEUED SELL {exit_signal.symbol}: {exit_signal.quantity} shares (Alert {alert_id})")
                    trades_executed += 1

            except Exception as e:
                logger.error(f"Failed to execute/queue sell for {exit_signal.symbol}: {e}")
                print(f"    ✗ Failed to sell {exit_signal.symbol}: {e}")

        # Get current cash after sells
        summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
        available_cash = summary.get('cash', 0) if summary else 0
        print(f"\n  Available cash after sells: ${available_cash:,.2f} "
              f"(freed ${cash_freed:,.2f} from {len(exits)} sells)")
        self._log_event(run_id, f"Available cash: ${available_cash:,.2f}")

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
            self._log_event(run_id, f"Phase 2: Executing {len(prioritized_positions)} buys")

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
                            self._log_event(
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
                            self._log_event(run_id, f"BUY {symbol} FAILED: {error}")
                    elif user_id:
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
                        self._log_event(run_id, f"QUEUED BUY {symbol}: {position.shares} shares (Alert {alert_id})")
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
                    self._log_event(run_id, f"Skipped {symbol}: {reason}")
                    
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
