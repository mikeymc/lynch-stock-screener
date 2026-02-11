# ABOUTME: Package that composes ToolExecutor from mixins and re-exports declarations
# ABOUTME: Replaces the monolithic agent_tools.py with a modular package

from agent_tools.declarations import AGENT_TOOLS, TOOL_DECLARATIONS
from agent_tools.core import ToolExecutorCore
from agent_tools.stock_tools import StockToolsMixin
from agent_tools.portfolio_tools import PortfolioToolsMixin
from agent_tools.research_tools import ResearchToolsMixin
from agent_tools.analysis_tools import AnalysisToolsMixin
from agent_tools.screening_tools import ScreeningToolsMixin
from agent_tools.utility_tools import UtilityToolsMixin
from agent_tools.strategy_tools import StrategyToolsMixin


class ToolExecutor(ToolExecutorCore, StockToolsMixin, PortfolioToolsMixin,
                   ResearchToolsMixin, AnalysisToolsMixin,
                   ScreeningToolsMixin, UtilityToolsMixin, StrategyToolsMixin):
    pass
