# ABOUTME: Core orchestration for autonomous strategy execution
# ABOUTME: Main execute_strategy method coordinates all 7 phases of execution

import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai

from strategy_executor.models import ExitSignal
from strategy_executor.universe_filter import UniverseFilter
from strategy_executor.consensus import ConsensusEngine
from strategy_executor.position_sizing import PositionSizer
from strategy_executor.exit_conditions import ExitConditionChecker
from benchmark_tracker import BenchmarkTracker
from strategy_executor.utils import log_event, get_spy_price

logger = logging.getLogger(__name__)


class StrategyExecutorCore:
    """Main orchestrator for autonomous strategy execution."""

    def __init__(self, db, analyst=None, lynch_criteria=None):
        self.db = db
        self.universe_filter = UniverseFilter(db)
        self.consensus_engine = ConsensusEngine()
        self.position_sizer = PositionSizer(db)
        self.exit_checker = ExitConditionChecker(db)
        self.benchmark_tracker = BenchmarkTracker(db)

        # Lazily initialize analyst and lynch_criteria if not provided
        self._analyst = analyst
        self._lynch_criteria = lynch_criteria

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
            # Get portfolio state
            portfolio_id = strategy['portfolio_id']
            summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
            portfolio_value = summary['total_value'] if summary else 0

            self.db.update_strategy_run(
                run_id,
                portfolio_value=portfolio_value,
                spy_price=get_spy_price(self.db)
            )

            # Phase 1: Screen candidates
            print("=" * 60)
            print("PHASE 1: UNIVERSE FILTERING")
            print("=" * 60)
            log_event(self.db, run_id, "Starting universe filtering phase")
            conditions = strategy.get('conditions', {})
            filtered_candidates = self.universe_filter.filter_universe(conditions)

            # Apply limit if requested
            if limit and limit > 0:
                print(f"  Limiting candidates to {limit} per request (found {len(filtered_candidates)})")
                filtered_candidates = filtered_candidates[:limit]

            # Separate held vs new positions
            current_portfolio_holdings = self.db.get_portfolio_holdings(portfolio_id)
            current_portfolio_holdings_symbols = set(current_portfolio_holdings.keys())
            new_candidates = [s for s in filtered_candidates if s not in current_portfolio_holdings_symbols]
            held_candidates = [s for s in filtered_candidates if s in current_portfolio_holdings_symbols]

            print(f"  Universe breakdown:")
            print(f"    New candidates: {len(new_candidates)}")
            if held_candidates:
                print(f"    Currently held candidates: {len(held_candidates)}")

            self.db.update_strategy_run(run_id, stocks_screened=len(filtered_candidates))
            log_event(self.db, run_id, f"Screened {len(filtered_candidates)} candidates ({len(new_candidates)} new, {len(held_candidates)} additions)")
            print(f"✓ Filtered {len(filtered_candidates)} total candidates\n")

            # Phase 2: Score candidates (with differentiated thresholds)
            print("=" * 60)
            print("PHASE 2: SCORING")
            print("=" * 60)

            # Score new positions with standard thresholds
            new_stocks_with_passing_scores = []
            if new_candidates:
                print(f"  Scoring {len(new_candidates)} new position candidates...")
                new_stocks_with_passing_scores, _ = self._score_candidates(new_candidates, conditions, run_id, is_addition=False)
                print(f"  ✓ {len(new_stocks_with_passing_scores)} new positions passed requirements\n")

            # Score additions with higher thresholds; capture held stocks that declined
            held_stocks_with_passing_scores = []
            held_stocks_with_failing_scores = []
            if held_candidates:
                print(f"  Scoring {len(held_candidates)} position addition candidates (higher thresholds)...")
                held_stocks_with_passing_scores, held_stocks_with_failing_scores = self._score_candidates(held_candidates, conditions, run_id, is_addition=True)
                print(f"  ✓ {len(held_stocks_with_passing_scores)} additions passed requirements\n")
                if held_stocks_with_failing_scores:
                    print(f"  {len(held_stocks_with_failing_scores)} held stocks with failing scores routing to deliberation for evaluation")

            # Combine scored candidates
            new_and_held_stocks_with_passing_scores = new_stocks_with_passing_scores + held_stocks_with_passing_scores
            self.db.update_strategy_run(run_id, stocks_scored=len(new_and_held_stocks_with_passing_scores))
            print(f"✓ Scored {len(new_and_held_stocks_with_passing_scores)} stocks that passed requirements\n")

            # Phase 3: Thesis Generation (with parallel processing)
            # held_stocks_with_failing_scores are included so Lynch and Buffett can deliberate on whether to exit
            print("=" * 60)
            print("PHASE 3: THESIS GENERATION")
            print("=" * 60)
            all_for_deliberation = new_and_held_stocks_with_passing_scores + held_stocks_with_failing_scores
            if conditions.get('require_thesis', False):
                enriched = self._generate_theses(all_for_deliberation, run_id, job_id=job_id)
                self.db.update_strategy_run(run_id, theses_generated=len(enriched))
                print(f"✓ Generated {len(enriched)} theses\\n")
            else:
                print("Skipping (thesis not required)\\n")
                enriched = all_for_deliberation

            # Phase 4: Deliberate (Lynch and Buffett discuss their theses)
            print("=" * 60)
            print("PHASE 4: DELIBERATION")
            print("=" * 60)
            symbols_of_held_stocks_with_failing_scores = {s['symbol'] for s in held_stocks_with_failing_scores}
            buy_decisions, deliberation_exit_decisions, held_verdicts = self._deliberate(
                enriched, run_id, conditions, job_id=job_id,
                held_symbols=current_portfolio_holdings_symbols, holdings=current_portfolio_holdings,
                symbols_of_held_stocks_with_failing_scores=symbols_of_held_stocks_with_failing_scores
            )
            print(f"✓ {len(buy_decisions)} BUY decisions made in deliberation")
            print(f"  {len(deliberation_exit_decisions)} EXIT decisions made in deliberation")
            if held_verdicts:
                print(f"  {len(held_verdicts)} held positions captured for rebalancing")

            # Phase 5: Exit Detection
            print("=" * 60)
            print("PHASE 5: EXIT DETECTION")
            print("=" * 60)
            exit_conditions = strategy.get('exit_conditions', {})
            exit_decisions = []

            # Source 1: Universe compliance — held stocks no longer passing entry filters
            universe_exits = self.exit_checker.check_universe_compliance(
                current_portfolio_holdings_symbols, filtered_candidates, current_portfolio_holdings
            )
            if universe_exits:
                print(f"  Universe compliance: {len(universe_exits)} positions no longer pass filters")
                for s in universe_exits:
                    print(f"    {s.symbol}: {s.reason}")
                log_event(self.db, run_id, f"Universe compliance exits: {len(universe_exits)} positions")
            exit_decisions.extend(universe_exits)

            # Source 2: Price, time, and explicit score-degradation exits
            price_time_exits = self.exit_checker.check_exits(
                portfolio_id,
                exit_conditions,
                scoring_func=self._get_current_scores
            )
            exit_decisions.extend(price_time_exits)

            # Source 3: Deliberation AVOID on held positions (computed in Phase 4)
            if deliberation_exit_decisions:
                print(f"  Deliberation: {len(deliberation_exit_decisions)} held positions flagged AVOID:")
                for exit_signal in deliberation_exit_decisions:
                    print(f"    {exit_signal.symbol}: {exit_signal.reason[:80]}")
                log_event(self.db, run_id, f"Deliberation exits: {len(deliberation_exit_decisions)} positions")
            exit_decisions.extend(deliberation_exit_decisions)

            print(f"✓ Found {len(exit_decisions)} positions to exit\n")

            # Phase 6: Execute trades
            print("=" * 60)
            print("PHASE 6: TRADE EXECUTION")
            print("=" * 60)
            trades_executed = self._execute_trades(
                buy_decisions, exit_decisions, strategy, run_id,
                held_verdicts=held_verdicts
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
                'stocks_screened': len(filtered_candidates),
                'stocks_scored': len(new_and_held_stocks_with_passing_scores),
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

