# ABOUTME: Defines atomic tools for the Smart Chat Agent using Gemini Native format
# ABOUTME: Each tool wraps an existing data fetcher for use in ReAct loops

from typing import Dict, Any, List, Optional, Callable
from google.genai.types import FunctionDeclaration, Schema, Type, Tool


# =============================================================================
# Tool Definitions (Gemini Native FunctionDeclaration format)
# =============================================================================

get_stock_metrics_decl = FunctionDeclaration(
    name="get_stock_metrics",
    description="Get comprehensive stock metrics including price, valuation ratios (P/E, forward P/E, PEG), analyst estimates (rating, price targets), market data (market cap, beta), financial ratios (debt-to-equity), short interest, and institutional ownership.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol (e.g., 'NVDA', 'AAPL')"),
        },
        required=["ticker"],
    ),
)

get_financials_decl = FunctionDeclaration(
    name="get_financials",
    description="Get historical financial metrics for a stock. Returns annual data including revenue, EPS, net income, cash flows, capital expenditures, dividends, and debt ratios.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "metric": Schema(
                type=Type.STRING, 
                description="The specific financial metric to retrieve",
                enum=["revenue", "eps", "net_income", "free_cash_flow", "operating_cash_flow", "capital_expenditures", "dividend_amount", "debt_to_equity"]
            ),
            "years": Schema(
                type=Type.ARRAY, 
                items=Schema(type=Type.INTEGER),
                description="List of years to retrieve data for (e.g., [2022, 2023, 2024])"
            ),
        },
        required=["ticker", "metric", "years"],
    ),
)

get_peers_decl = FunctionDeclaration(
    name="get_peers",
    description="Get information about competitors and the competitive landscape. This retrieves the 'Business' section from the company's 10-K filing which typically discusses competitors, market position, and industry dynamics. The LLM should extract and identify specific competitor names from this context.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol to find competitor information for"),
        },
        required=["ticker"],
    ),
)

get_insider_activity_decl = FunctionDeclaration(
    name="get_insider_activity",
    description="Get recent insider trading activity (open market buys and sells by executives and directors). Useful for understanding insider sentiment.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "limit": Schema(type=Type.INTEGER, description="Maximum number of trades to return (default: 20)"),
        },
        required=["ticker"],
    ),
)

search_news_decl = FunctionDeclaration(
    name="search_news",
    description="Search for recent news articles about a stock. Returns headlines, summaries, sources, and publication dates.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "limit": Schema(type=Type.INTEGER, description="Maximum number of articles to return (default: 10)"),
        },
        required=["ticker"],
    ),
)

get_filing_section_decl = FunctionDeclaration(
    name="get_filing_section",
    description="Read a specific section from the company's SEC 10-K or 10-Q filing. Useful for understanding business model, risk factors, or management discussion.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "section": Schema(
                type=Type.STRING, 
                description="Section name to retrieve",
                enum=["business", "risk_factors", "mda", "market_risk"]
            ),
        },
        required=["ticker", "section"],
    ),
)


# =============================================================================
# Tool Registry: Maps tool names to their declarations
# =============================================================================

TOOL_DECLARATIONS = [
    get_stock_metrics_decl,
    get_financials_decl,
    get_peers_decl,
    get_insider_activity_decl,
    search_news_decl,
    get_filing_section_decl,
]

# Create the Tool object for Gemini API
AGENT_TOOLS = Tool(function_declarations=TOOL_DECLARATIONS)


# =============================================================================
# Tool Executors: Actual Python functions that execute the tools
# =============================================================================

class ToolExecutor:
    """Executes tool calls against the database and other data sources."""
    
    def __init__(self, db, rag_context=None):
        """
        Initialize the tool executor.
        
        Args:
            db: Database instance
            rag_context: Optional RAGContext instance for filing sections and news
        """
        self.db = db
        self.rag_context = rag_context
    
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
            "get_peers": self._get_peers,
            "get_insider_activity": self._get_insider_activity,
            "search_news": self._search_news,
            "get_filing_section": self._get_filing_section,
        }
        
        executor = executor_map.get(tool_name)
        if not executor:
            return {"error": f"Unknown tool: {tool_name}"}
        
        try:
            return executor(**args)
        except Exception as e:
            return {"error": str(e)}
    
    def _get_stock_metrics(self, ticker: str) -> Dict[str, Any]:
        """Get all available stock metrics."""
        ticker = ticker.upper()
        result = self.db.get_stock_metrics(ticker)
        if not result:
            return {"error": f"No data found for {ticker}"}
        
        # Return all available metrics organized by category
        return {
            "ticker": ticker,
            "company_name": result.get("company_name"),
            "sector": result.get("sector"),
            "country": result.get("country"),
            "exchange": result.get("exchange"),
            "ipo_year": result.get("ipo_year"),
            # Current price and market data
            "price": result.get("price"),
            "market_cap": result.get("market_cap"),
            "beta": result.get("beta"),
            # Valuation ratios
            "pe_ratio": result.get("pe_ratio"),
            "forward_pe": result.get("forward_pe"),
            "forward_peg_ratio": result.get("forward_peg_ratio"),
            "forward_eps": result.get("forward_eps"),
            # Financial ratios
            "debt_to_equity": result.get("debt_to_equity"),
            "total_debt": result.get("total_debt"),
            "interest_expense": result.get("interest_expense"),
            "effective_tax_rate": result.get("effective_tax_rate"),
            "revenue": result.get("revenue"),
            # Dividends and ownership
            "dividend_yield": result.get("dividend_yield"),
            "institutional_ownership": result.get("institutional_ownership"),
            "insider_net_buying_6m": result.get("insider_net_buying_6m"),
            # Short interest
            "short_ratio": result.get("short_ratio"),
            "short_percent_float": result.get("short_percent_float"),
            # Analyst data
            "analyst_rating": result.get("analyst_rating"),
            "analyst_rating_score": result.get("analyst_rating_score"),
            "analyst_count": result.get("analyst_count"),
            "price_target_high": result.get("price_target_high"),
            "price_target_low": result.get("price_target_low"),
            "price_target_mean": result.get("price_target_mean"),
            # Dates
            "next_earnings_date": result.get("next_earnings_date"),
            "last_updated": result.get("last_updated"),
        }
    
    def _get_financials(self, ticker: str, metric: str, years: List[int]) -> Dict[str, Any]:
        """Get historical financial metrics."""
        ticker = ticker.upper()
        history = self.db.get_earnings_history(ticker, period_type='annual')
        
        if not history:
            return {"error": f"No financial history found for {ticker}"}
        
        # Map metric names to database field names
        metric_field_map = {
            "revenue": "revenue",
            "eps": "eps",
            "net_income": "net_income",
            "free_cash_flow": "free_cash_flow",
            "operating_cash_flow": "operating_cash_flow",
            "capital_expenditures": "capital_expenditures",
            "dividend_amount": "dividend_amount",
            "debt_to_equity": "debt_to_equity",
        }
        
        field = metric_field_map.get(metric)
        if not field:
            return {"error": f"Unknown metric: {metric}"}
        
        # Filter to requested years and extract metric
        result = {"ticker": ticker, "metric": metric, "data": {}}
        for entry in history:
            year = entry.get("year")
            if year in years:
                value = entry.get(field)
                result["data"][year] = value
        
        return result
    
    def _get_peers(self, ticker: str) -> Dict[str, Any]:
        """Get competitor information from 10-K business section."""
        ticker = ticker.upper()
        
        if not self.rag_context:
            return {"error": "Competitor info not available: RAGContext not configured"}
        
        # Get the business section which typically discusses competitors
        sections, _ = self.rag_context._get_filing_sections(ticker, user_query=None, max_sections=4)
        
        if 'business' not in sections:
            return {
                "error": f"No business section found for {ticker}",
                "suggestion": "Try searching news or checking the company's sector for general context."
            }
        
        business_data = sections['business']
        content = business_data.get('content', '')
        
        # Truncate if very long
        if len(content) > 8000:
            content = content[:8000] + "\n... [TRUNCATED - see full 10-K for complete details]"
        
        return {
            "ticker": ticker,
            "section": "business",
            "filing_type": business_data.get("filing_type"),
            "filing_date": business_data.get("filing_date"),
            "content": content,
            "instruction": "Extract competitor names and market position information from this business description."
        }
    
    def _get_insider_activity(self, ticker: str, limit: int = 20) -> Dict[str, Any]:
        """Get insider trading activity."""
        ticker = ticker.upper()
        trades = self.db.get_insider_trades(ticker, limit=limit)
        
        if not trades:
            return {"ticker": ticker, "trades": [], "message": "No insider trades found"}
        
        # Filter to open market transactions (P=Purchase, S=Sale)
        open_market_trades = [t for t in trades if t.get("transaction_code") in ("P", "S")]
        
        # Summarize
        buys = [t for t in open_market_trades if t.get("transaction_code") == "P"]
        sells = [t for t in open_market_trades if t.get("transaction_code") == "S"]
        
        return {
            "ticker": ticker,
            "summary": {
                "total_buys": len(buys),
                "total_sells": len(sells),
                "buy_value": sum(t.get("value") or 0 for t in buys),
                "sell_value": sum(t.get("value") or 0 for t in sells),
            },
            "recent_trades": open_market_trades[:10],  # Top 10 most recent
        }
    
    def _search_news(self, ticker: str, limit: int = 10) -> Dict[str, Any]:
        """Search for news articles."""
        ticker = ticker.upper()
        
        if not self.rag_context:
            return {"error": "News search not available: RAGContext not configured"}
        
        articles = self.rag_context._get_news_articles(ticker, limit=limit)
        
        if not articles:
            return {"ticker": ticker, "articles": [], "message": "No news articles found"}
        
        return {
            "ticker": ticker,
            "articles": articles,
        }
    
    def _get_filing_section(self, ticker: str, section: str) -> Dict[str, Any]:
        """Read a section from SEC filings."""
        ticker = ticker.upper()
        
        if not self.rag_context:
            return {"error": "Filing sections not available: RAGContext not configured"}
        
        # Get filing sections (returns dict keyed by section name)
        sections, selected = self.rag_context._get_filing_sections(ticker, user_query=None, max_sections=4)
        
        if section not in sections:
            return {
                "error": f"Section '{section}' not found for {ticker}",
                "available_sections": list(sections.keys()),
            }
        
        section_data = sections[section]
        
        # Truncate content if very long (for context window management)
        content = section_data.get("content", "")
        if len(content) > 10000:
            content = content[:10000] + "\n... [TRUNCATED]"
        
        return {
            "ticker": ticker,
            "section": section,
            "filing_type": section_data.get("filing_type"),
            "filing_date": section_data.get("filing_date"),
            "content": content,
        }
