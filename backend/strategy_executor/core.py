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
from strategy_executor.holding_reevaluation import HoldingReevaluator
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
                self.universe_filter,
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
            holdings = self.db.get_portfolio_holdings(portfolio_id)
            held_symbols = set(holdings.keys())
            new_candidates = [s for s in filtered_candidates if s not in held_symbols]
            held_candidates = [s for s in filtered_candidates if s in held_symbols]

            print(f"  Universe breakdown:")
            print(f"    New positions: {len(new_candidates)}")
            print(f"    Position additions: {len(held_candidates)}")
            if held_candidates:
                print(f"    Held stocks in universe: {held_candidates}")

            self.db.update_strategy_run(run_id, stocks_screened=len(filtered_candidates))
            log_event(self.db, run_id, f"Screened {len(filtered_candidates)} candidates ({len(new_candidates)} new, {len(held_candidates)} additions)")
            print(f"✓ Filtered {len(filtered_candidates)} total candidates\n")

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
            print("=" * 60)
            print("PHASE 3: THESIS GENERATION")
            print("=" * 60)
            if conditions.get('require_thesis', False):
                enriched = self._generate_theses(scored, run_id, job_id=job_id)
                self.db.update_strategy_run(run_id, theses_generated=len(enriched))
                print(f"✓ Generated {len(enriched)} theses\\n")
            else:
                print("Skipping (thesis not required)\\n")
                enriched = scored

            # Phase 4: Deliberate (Lynch and Buffett discuss their theses)
            print("=" * 60)
            print("PHASE 4: DELIBERATION")
            print("=" * 60)
            decisions = self._deliberate(enriched, run_id, conditions, job_id=job_id)
            print(f"✓ {len(decisions)} BUY decisions made\\n")

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
                    log_event(self.db, run_id, f"Re-evaluation: {len(reevaluation_exits)} positions flagged for exit")
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
                'stocks_screened': len(filtered_candidates),
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

