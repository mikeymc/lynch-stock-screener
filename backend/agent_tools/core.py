# ABOUTME: Core ToolExecutor class with __init__ and execute() dispatch method
# ABOUTME: Routes tool calls to the appropriate mixin method by name

from typing import Dict, Any


class ToolExecutorCore:
    """Executes tool calls against the database and other data sources."""

    def __init__(self, db, stock_context=None):
        """
        Initialize the tool executor.

        Args:
            db: Database instance
            stock_context: Optional StockContext instance for filing sections and news
        """
        self.db = db
        self.stock_context = stock_context

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by name with the given arguments.

        Args:
            tool_name: Name of the tool to execute
            args: Dictionary of arguments for the tool

        Returns:
            Result of the tool execution
        """
        executor_map = {
            "get_stock_metrics": self._get_stock_metrics,
            "get_financials": self._get_financials,
            "get_roe_metrics": self._get_roe_metrics,
            "get_owner_earnings": self._get_owner_earnings,
            "get_debt_to_earnings_ratio": self._get_debt_to_earnings_ratio,
            "get_gross_margin": self._get_gross_margin,
            "get_earnings_consistency": self._get_earnings_consistency,
            "get_price_to_book_ratio": self._get_price_to_book_ratio,
            "get_share_buyback_activity": self._get_share_buyback_activity,
            "get_cash_position": self._get_cash_position,
            "get_peers": self._get_peers,
            "get_insider_activity": self._get_insider_activity,
            "search_news": self._search_news,
            "get_filing_section": self._get_filing_section,
            "get_earnings_transcript": self._get_earnings_transcript,
            "get_material_events": self._get_material_events,
            "get_price_history": self._get_price_history,
            "get_historical_pe": self._get_historical_pe,
            "get_growth_rates": self._get_growth_rates,
            "get_cash_flow_analysis": self._get_cash_flow_analysis,
            "get_dividend_analysis": self._get_dividend_analysis,
            "get_analyst_estimates": self._get_analyst_estimates,
            "compare_stocks": self._compare_stocks,
            "find_similar_stocks": self._find_similar_stocks,
            "search_company": self._search_company,
            "screen_stocks": self._screen_stocks,
            "get_sector_comparison": self._get_sector_comparison,
            "get_sector_comparison": self._get_sector_comparison,
            "get_earnings_history": self._get_earnings_history,
            "manage_alerts": self._manage_alerts,
            # FRED macroeconomic tools
            "get_fred_series": self._get_fred_series,
            "get_economic_indicators": self._get_economic_indicators,
            "get_analyst_sentiment": self._get_analyst_sentiment,
            "get_average_pe_ratio": self._get_average_pe_ratio,
            # Portfolio management tools
            "create_portfolio": self._create_portfolio,
            "get_my_portfolios": self._get_my_portfolios,
            "get_portfolio_status": self._get_portfolio_status,
            "buy_stock": self._buy_stock,
            "sell_stock": self._sell_stock,
            # Strategy management tools
            "get_strategy_templates": self._get_strategy_templates,
            "create_strategy": self._create_strategy,
        }

        executor = executor_map.get(tool_name)
        if not executor:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return executor(**args)
        except Exception as e:
            return {"error": str(e)}
