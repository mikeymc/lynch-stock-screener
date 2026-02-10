# ABOUTME: Strategy execution package for autonomous investment management
# ABOUTME: Composes StrategyExecutor from domain-specific mixins and re-exports public API

from strategy_executor.models import ConsensusResult, PositionSize, ExitSignal
from strategy_executor.universe_filter import UniverseFilter
from strategy_executor.consensus import ConsensusEngine
from strategy_executor.position_sizing import PositionSizer
from strategy_executor.exit_conditions import ExitConditionChecker
from strategy_executor.holding_reevaluation import HoldingReevaluator
from benchmark_tracker import BenchmarkTracker
from strategy_executor.core import StrategyExecutorCore
from strategy_executor.scoring import ScoringMixin
from strategy_executor.thesis import ThesisMixin
from strategy_executor.deliberation import DeliberationMixin
from strategy_executor.trading import TradingMixin


class StrategyExecutor(StrategyExecutorCore, ScoringMixin, ThesisMixin,
                       DeliberationMixin, TradingMixin):
    """Main orchestrator for autonomous strategy execution.

    Composed from domain-specific mixins:
    - ScoringMixin: Candidate scoring with Lynch/Buffett criteria
    - ThesisMixin: AI thesis generation and verdict extraction
    - DeliberationMixin: Consensus building via Gemini deliberation
    - TradingMixin: Position sizing and trade execution
    """
    pass
