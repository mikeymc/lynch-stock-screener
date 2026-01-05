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

get_earnings_transcript_decl = FunctionDeclaration(
    name="get_earnings_transcript",
    description="Get the most recent earnings call transcript for a stock. Contains management's prepared remarks and Q&A with analysts. Useful for understanding forward guidance, margin commentary, and strategic priorities.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_material_events_decl = FunctionDeclaration(
    name="get_material_events",
    description="Get recent material events (8-K SEC filings) for a stock. These include significant corporate announcements like acquisitions, leadership changes, guidance updates, restructuring, and other material developments. Returns headline, description, and AI summary for each event.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "limit": Schema(type=Type.INTEGER, description="Maximum number of events to return (default: 10)"),
        },
        required=["ticker"],
    ),
)

get_price_history_decl = FunctionDeclaration(
    name="get_price_history",
    description="Get historical weekly stock prices for trend analysis. Returns dates and prices for the specified time period. Useful for analyzing stock performance over time.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "start_year": Schema(type=Type.INTEGER, description="Optional start year to filter data (e.g., 2020)"),
        },
        required=["ticker"],
    ),
)

get_historical_pe_decl = FunctionDeclaration(
    name="get_historical_pe",
    description="Get historical annual P/E (Price-to-Earnings) ratios for a stock over multiple years. Calculates P/E by dividing year-end stock price by annual EPS. Useful for comparing valuations over time or across companies.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "years": Schema(type=Type.INTEGER, description="Number of years of history (default: 5)"),
        },
        required=["ticker"],
    ),
)

get_growth_rates_decl = FunctionDeclaration(
    name="get_growth_rates",
    description="Calculate revenue and earnings growth rates (CAGR) over multiple time periods. Returns 1-year, 3-year, and 5-year compound annual growth rates for both revenue and earnings.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_cash_flow_analysis_decl = FunctionDeclaration(
    name="get_cash_flow_analysis",
    description="Analyze cash flow trends over multiple years. Returns operating cash flow, free cash flow, capital expenditures, FCF margin, and CapEx as percentage of revenue.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "years": Schema(type=Type.INTEGER, description="Number of years of history (default: 5)"),
        },
        required=["ticker"],
    ),
)

get_dividend_analysis_decl = FunctionDeclaration(
    name="get_dividend_analysis",
    description="Analyze dividend history and trends. Returns dividend payments over time, dividend growth rates (CAGR), payout ratios, and current yield. Useful for income-focused analysis.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "years": Schema(type=Type.INTEGER, description="Number of years of history (default: 5)"),
        },
        required=["ticker"],
    ),
)

get_analyst_estimates_decl = FunctionDeclaration(
    name="get_analyst_estimates",
    description="Get analyst consensus estimates for future earnings and revenue. Returns EPS and revenue projections for current/next quarter and year, along with growth expectations and analyst counts.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

compare_stocks_decl = FunctionDeclaration(
    name="compare_stocks",
    description="Compare key metrics across 2-5 stocks side-by-side. Returns valuation ratios, profitability metrics, growth rates, and financial health indicators for easy comparison.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "tickers": Schema(
                type=Type.ARRAY,
                items=Schema(type=Type.STRING),
                description="List of 2-5 stock ticker symbols to compare"
            ),
        },
        required=["tickers"],
    ),
)

find_similar_stocks_decl = FunctionDeclaration(
    name="find_similar_stocks",
    description="Find stocks with similar characteristics to a given stock. Matches based on sector, market cap, growth rates, and valuation metrics. Useful for discovering alternatives or peers.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Reference stock ticker symbol"),
            "limit": Schema(type=Type.INTEGER, description="Maximum number of similar stocks to return (default: 5)"),
        },
        required=["ticker"],
    ),
)

search_company_decl = FunctionDeclaration(
    name="search_company",
    description="Search for a company by name and get its ticker symbol. Use this when the user mentions a company name instead of a ticker. Returns matching ticker symbols and company names.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "company_name": Schema(type=Type.STRING, description="Company name to search for (e.g., 'Apple', 'Figma', 'Microsoft')"),
            "limit": Schema(type=Type.INTEGER, description="Maximum number of results to return (default: 5)"),
        },
        required=["company_name"],
    ),
)

screen_stocks_decl = FunctionDeclaration(
    name="screen_stocks",
    description="Screen and filter stocks based on various criteria. Use this to find stocks matching specific requirements like low P/E, high dividend yield, large market cap, strong growth, etc. Returns a list of matching stocks with key metrics.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "pe_max": Schema(type=Type.NUMBER, description="Maximum P/E ratio (e.g., 15 for value stocks)"),
            "pe_min": Schema(type=Type.NUMBER, description="Minimum P/E ratio (e.g., 5 to exclude distressed stocks)"),
            "dividend_yield_min": Schema(type=Type.NUMBER, description="Minimum dividend yield percentage (e.g., 3.0 for income stocks)"),
            "market_cap_min": Schema(type=Type.NUMBER, description="Minimum market cap in billions (e.g., 10 for large caps)"),
            "market_cap_max": Schema(type=Type.NUMBER, description="Maximum market cap in billions (e.g., 2 for small caps)"),
            "revenue_growth_min": Schema(type=Type.NUMBER, description="Minimum revenue growth percentage YoY"),
            "eps_growth_min": Schema(type=Type.NUMBER, description="Minimum EPS growth percentage YoY"),
            "sector": Schema(type=Type.STRING, description="Filter by sector (e.g., 'Technology', 'Healthcare', 'Financials')"),
            "peg_max": Schema(type=Type.NUMBER, description="Maximum PEG ratio (P/E divided by growth rate)"),
            "debt_to_equity_max": Schema(type=Type.NUMBER, description="Maximum debt-to-equity ratio"),
            "profit_margin_min": Schema(type=Type.NUMBER, description="Minimum Net Profit Margin percentage (e.g., 20.0 for high margin businesses)"),
            "has_transcript": Schema(type=Type.BOOLEAN, description="If true, only return stocks that have an earnings call transcript available"),
            "sort_by": Schema(type=Type.STRING, description="Sort results by: 'pe', 'dividend_yield', 'market_cap', 'revenue_growth', 'eps_growth', 'debt_to_equity' (default: 'market_cap')"),
            "sort_order": Schema(type=Type.STRING, description="Sort order: 'asc' or 'desc' (default: 'desc')"),
            "limit": Schema(type=Type.INTEGER, description="Maximum number of results to return (default: 20, max: 50)"),
            "exclude_tickers": Schema(
                type=Type.ARRAY, 
                items=Schema(type=Type.STRING), 
                description="List of tickers to exclude from results (e.g., ['NVDA'] to find *other* stocks)"
            ),
        },
        required=[],  # All filters are optional
    ),
)

get_sector_comparison_decl = FunctionDeclaration(
    name="get_sector_comparison",
    description="Compare a stock relative to its industry peers. Returns detailed comparison against sector averages and medians for P/E, PEG, Yield, Growth, and Debt. Use this tool when asked to compare against 'peers', 'competitors', or 'industry', especially when specific competitor names are not provided.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Ticker symbol of the stock to compare (e.g., 'AAPL', 'MSFT')"),
        },
        required=["ticker"],
    ),
)


get_earnings_history_decl = FunctionDeclaration(
    name="get_earnings_history",
    description="Get historical financial data including EPS, Revenue, and Net Income (Quarterly/Annual), plus Free Cash Flow (Annual). Returns trend data to analyze growth, profitability, and cash flow. Note: FCF is typically Annual-only.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Ticker symbol (e.g., 'AAPL')"),
            "period_type": Schema(type=Type.STRING, description="Type of periods to return: 'quarterly', 'annual', or 'both' (default: 'quarterly')"),
            "limit": Schema(type=Type.INTEGER, description="Maximum number of periods to return (default: 12)"),
        },
        required=["ticker"],
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
    get_earnings_transcript_decl,
    get_material_events_decl,
    get_price_history_decl,
    get_historical_pe_decl,
    get_growth_rates_decl,
    get_cash_flow_analysis_decl,
    get_dividend_analysis_decl,
    get_analyst_estimates_decl,
    compare_stocks_decl,
    find_similar_stocks_decl,
    search_company_decl,
    screen_stocks_decl,
    get_sector_comparison_decl,
    get_earnings_history_decl,
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
            "get_earnings_history": self._get_earnings_history,
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
        
        # Filter to open market transactions (P=Purchase, S=Sale) or explicit Buy/Sell types
        open_market_trades = []
        for t in trades:
            code = t.get("transaction_code")
            type_label = t.get("transaction_type") or ""
            
            # Check for P/S code OR explicit Buy/Sell/Purchase/Sale type
            if code in ("P", "S"):
                open_market_trades.append(t)
            elif type_label.lower() in ("buy", "purchase", "sell", "sale"):
                open_market_trades.append(t)
        
        # Summarize
        buys = [t for t in open_market_trades if t.get("transaction_code") == "P" or t.get("transaction_type", "").lower() in ("buy", "purchase")]
        sells = [t for t in open_market_trades if t.get("transaction_code") == "S" or t.get("transaction_type", "").lower() in ("sell", "sale")]
        
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
    
    def _get_earnings_transcript(self, ticker: str) -> Dict[str, Any]:
        """Get the most recent earnings call transcript."""
        ticker = ticker.upper()
        
        transcript = self.db.get_latest_earnings_transcript(ticker)
        
        if not transcript:
            return {
                "error": f"No earnings transcript found for {ticker}",
                "suggestion": "Try using get_filing_section to read the 10-K or 10-Q instead."
            }
        
        # Return transcript with truncated text if very long
        text = transcript.get('transcript_text', '')
        if len(text) > 15000:
            text = text[:15000] + "\n... [TRUNCATED - see full transcript for more]"
        
        return {
            "ticker": ticker,
            "quarter": transcript.get('quarter'),
            "fiscal_year": transcript.get('fiscal_year'),
            "earnings_date": transcript.get('earnings_date'),
            "has_qa": transcript.get('has_qa'),
            "participants": transcript.get('participants', []),
            "summary": transcript.get('summary'),
            "transcript_text": text,
        }
    
    def _get_material_events(self, ticker: str, limit: int = 10) -> Dict[str, Any]:
        """Get recent material events (8-K filings)."""
        ticker = ticker.upper()
        
        events = self.db.get_material_events(ticker, limit=limit)
        
        if not events:
            return {
                "ticker": ticker,
                "events": [],
                "message": "No material events (8-K filings) found for this stock."
            }
        
        # Clean up events for output (exclude very long content_text)
        cleaned_events = []
        for event in events:
            cleaned_events.append({
                "event_type": event.get('event_type'),
                "headline": event.get('headline'),
                "description": event.get('description'),
                "filing_date": event.get('filing_date'),
                "sec_item_codes": event.get('sec_item_codes', []),
                "summary": event.get('summary'),  # AI-generated summary if available
            })
        
        return {
            "ticker": ticker,
            "event_count": len(cleaned_events),
            "events": cleaned_events,
        }
    
    def _get_price_history(self, ticker: str, start_year: int = None) -> Dict[str, Any]:
        """Get historical weekly stock prices."""
        ticker = ticker.upper()
        
        price_data = self.db.get_weekly_prices(ticker, start_year=start_year)
        
        if not price_data or not price_data.get('dates'):
            return {
                "error": f"No price history found for {ticker}",
                "suggestion": "Price data may not be available for this symbol."
            }
        
        dates = price_data.get('dates', [])
        prices = price_data.get('prices', [])
        
        # Calculate some basic stats
        if prices:
            current_price = prices[-1]
            first_price = prices[0]
            pct_change = ((current_price - first_price) / first_price * 100) if first_price else 0
            high = max(prices)
            low = min(prices)
        else:
            current_price = pct_change = high = low = None
        
        return {
            "ticker": ticker,
            "data_points": len(dates),
            "date_range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
            "summary": {
                "current_price": current_price,
                "period_high": high,
                "period_low": low,
                "total_return_pct": round(pct_change, 2) if pct_change else None,
            },
            # Return sampled data if too many points
            "prices": prices[-52:] if len(prices) > 52 else prices,  # Last 52 weeks
            "dates": dates[-52:] if len(dates) > 52 else dates,
        }
    
    def _get_historical_pe(self, ticker: str, years: int = 5) -> Dict[str, Any]:
        """Get historical annual P/E ratios."""
        ticker = ticker.upper()
        
        # Get earnings history (annual EPS)
        earnings = self.db.get_earnings_history(ticker, period_type='annual')
        
        if not earnings:
            return {
                "error": f"No earnings history found for {ticker}",
                "suggestion": "Try using get_stock_metrics for current P/E ratio."
            }
        
        # Get price history
        price_data = self.db.get_weekly_prices(ticker)
        
        if not price_data or not price_data.get('dates'):
            return {
                "error": f"No price history found for {ticker}",
            }
        
        # Build a dict of year -> year-end price (use last week of December)
        year_end_prices = {}
        for date_str, price in zip(price_data['dates'], price_data['prices']):
            # Parse date (format: YYYY-MM-DD)
            year = int(date_str[:4])
            month = int(date_str[5:7])
            # Use December prices as year-end
            if month == 12:
                year_end_prices[year] = price
        
        # Calculate P/E for each year
        pe_data = []
        current_year = 2025  # Current year
        
        for record in earnings:
            year = record.get('year')
            eps = record.get('eps')
            
            if not year or not eps or year < current_year - years:
                continue
            
            # Get year-end price (use previous year for annual EPS announced in Q1)
            price = year_end_prices.get(year)
            
            if price and eps and eps > 0:
                pe = round(price / eps, 2)
                pe_data.append({
                    "year": year,
                    "eps": eps,
                    "year_end_price": round(price, 2),
                    "pe_ratio": pe
                })
        
        # Sort by year ascending
        pe_data.sort(key=lambda x: x['year'])
        
        if not pe_data:
            return {
                "ticker": ticker,
                "pe_history": [],
                "message": "Could not calculate P/E ratios - missing price or EPS data for matched years."
            }
        
        return {
            "ticker": ticker,
            "years_of_data": len(pe_data),
            "pe_history": pe_data,
        }
    
    def _get_growth_rates(self, ticker: str) -> Dict[str, Any]:
        """Calculate revenue and earnings growth rates (CAGR)."""
        ticker = ticker.upper()
        
        earnings = self.db.get_earnings_history(ticker, period_type='annual')
        if not earnings or len(earnings) < 2:
            return {
                "error": f"Insufficient data for {ticker}",
                "suggestion": "Need at least 2 years of data to calculate growth rates."
            }
        
        # Sort by year descending (most recent first)
        earnings.sort(key=lambda x: x['year'], reverse=True)
        
        def calculate_cagr(start_val, end_val, years):
            """Calculate compound annual growth rate."""
            if not start_val or not end_val or start_val <= 0:
                return None
            return ((end_val / start_val) ** (1 / years) - 1) * 100
        
        # Get most recent year
        latest = earnings[0]
        
        # Calculate growth rates for different periods
        growth_data = {
            "ticker": ticker,
            "latest_year": latest['year'],
            "revenue_growth": {},
            "earnings_growth": {}
        }
        
        for period, years_back in [("1_year", 1), ("3_year", 3), ("5_year", 5)]:
            if len(earnings) > years_back:
                past = earnings[years_back]
                
                rev_cagr = calculate_cagr(past.get('revenue'), latest.get('revenue'), years_back)
                eps_cagr = calculate_cagr(past.get('eps'), latest.get('eps'), years_back)
                
                growth_data["revenue_growth"][period] = {
                    "cagr_pct": round(rev_cagr, 1) if rev_cagr else None,
                    "start_year": past['year'],
                    "end_year": latest['year']
                }
                growth_data["earnings_growth"][period] = {
                    "cagr_pct": round(eps_cagr, 1) if eps_cagr else None,
                    "start_year": past['year'],
                    "end_year": latest['year']
                }
        
        return growth_data
    
    def _get_cash_flow_analysis(self, ticker: str, years: int = 5) -> Dict[str, Any]:
        """Analyze cash flow trends over multiple years."""
        ticker = ticker.upper()
        
        earnings = self.db.get_earnings_history(ticker, period_type='annual')
        if not earnings:
            return {
                "error": f"No earnings history for {ticker}",
                "suggestion": "Try using get_financials for current cash flow data."
            }
        
        cash_flow_data = []
        current_year = 2025
        
        for record in earnings:
            year = record.get('year')
            if not year or year < current_year - years:
                continue
            
            revenue = record.get('revenue')
            ocf = record.get('operating_cash_flow')
            capex = record.get('capital_expenditures')
            fcf = record.get('free_cash_flow')
            
            # Calculate metrics
            fcf_margin = (fcf / revenue * 100) if fcf and revenue else None
            capex_pct = (abs(capex) / revenue * 100) if capex and revenue else None
            
            cash_flow_data.append({
                "year": year,
                "operating_cash_flow_b": round(ocf / 1e9, 2) if ocf else None,  # Billions
                "capital_expenditures_b": round(abs(capex) / 1e9, 2) if capex else None,
                "free_cash_flow_b": round(fcf / 1e9, 2) if fcf else None,
                "fcf_margin_pct": round(fcf_margin, 1) if fcf_margin else None,
                "capex_as_pct_revenue": round(capex_pct, 1) if capex_pct else None,
            })
        
        # Sort by year ascending
        cash_flow_data.sort(key=lambda x: x['year'])
        
        if not cash_flow_data:
            return {
                "ticker": ticker,
                "cash_flow_trends": [],
                "message": "No cash flow data available for the specified period."
            }
        
        return {
            "ticker": ticker,
            "years_of_data": len(cash_flow_data),
            "cash_flow_trends": cash_flow_data
        }
    
    def _get_dividend_analysis(self, ticker: str, years: int = 5) -> Dict[str, Any]:
        """Analyze dividend history and trends."""
        ticker = ticker.upper()
        
        # Get current dividend yield
        stock_metrics = self.db.get_stock_metrics(ticker)
        current_yield = stock_metrics.get('dividend_yield') if stock_metrics else None
        
        # Get historical dividend data
        earnings = self.db.get_earnings_history(ticker, period_type='annual')
        if not earnings:
            return {
                "error": f"No earnings history for {ticker}",
                "suggestion": "This stock may not pay dividends or data is unavailable."
            }
        
        dividend_data = []
        current_year = 2025
        
        for record in earnings:
            year = record.get('year')
            if not year or year < current_year - years:
                continue
            
            dividend = record.get('dividend_amount')
            eps = record.get('eps')
            
            # Calculate payout ratio
            payout_ratio = (dividend / eps * 100) if dividend and eps and eps > 0 else None
            
            if dividend:  # Only include years with dividend data
                dividend_data.append({
                    "year": year,
                    "dividend_per_share": round(dividend, 2),
                    "eps": round(eps, 2) if eps else None,
                    "payout_ratio_pct": round(payout_ratio, 1) if payout_ratio else None,
                })
        
        # Sort by year ascending
        dividend_data.sort(key=lambda x: x['year'])
        
        if not dividend_data:
            return {
                "ticker": ticker,
                "current_yield_pct": round(current_yield, 2) if current_yield else None,
                "dividend_history": [],
                "message": "No dividend payments found in the specified period."
            }
        
        # Calculate dividend growth rates
        def calculate_cagr(start_val, end_val, years):
            if not start_val or not end_val or start_val <= 0:
                return None
            return ((end_val / start_val) ** (1 / years) - 1) * 100
        
        growth_rates = {}
        latest = dividend_data[-1]
        
        for period, years_back in [("1_year", 1), ("3_year", 3), ("5_year", 5)]:
            if len(dividend_data) > years_back:
                past = dividend_data[-(years_back + 1)]
                cagr = calculate_cagr(
                    past['dividend_per_share'],
                    latest['dividend_per_share'],
                    years_back
                )
                if cagr is not None:
                    growth_rates[period] = {
                        "cagr_pct": round(cagr, 1),
                        "start_year": past['year'],
                        "end_year": latest['year']
                    }
        
        return {
            "ticker": ticker,
            "current_yield_pct": round(current_yield, 2) if current_yield else None,
            "years_of_data": len(dividend_data),
            "dividend_history": dividend_data,
            "dividend_growth": growth_rates
        }
    
    def _get_analyst_estimates(self, ticker: str) -> Dict[str, Any]:
        """Get analyst consensus estimates for future earnings and revenue."""
        ticker = ticker.upper()
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT period, eps_avg, eps_low, eps_high, eps_growth, eps_num_analysts,
                       revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_num_analysts
                FROM analyst_estimates
                WHERE symbol = %s
                ORDER BY period
            """, (ticker,))
            
            estimates = {}
            for row in cursor.fetchall():
                period = row[0]
                estimates[period] = {
                    "eps": {
                        "avg": round(row[1], 2) if row[1] else None,
                        "low": round(row[2], 2) if row[2] else None,
                        "high": round(row[3], 2) if row[3] else None,
                        "growth_pct": round(row[4], 1) if row[4] else None,
                        "num_analysts": row[5]
                    },
                    "revenue": {
                        "avg_b": round(row[6] / 1e9, 2) if row[6] else None,
                        "low_b": round(row[7] / 1e9, 2) if row[7] else None,
                        "high_b": round(row[8] / 1e9, 2) if row[8] else None,
                        "growth_pct": round(row[9], 1) if row[9] else None,
                        "num_analysts": row[10]
                    }
                }
            
            if not estimates:
                return {"error": f"No analyst estimates found for {ticker}"}
            
            return {
                "ticker": ticker,
                "estimates": estimates
            }
        finally:
            self.db.return_connection(conn)
    
    def _compare_stocks(self, tickers: list) -> Dict[str, Any]:
        """Compare multiple stocks side-by-side."""
        if not tickers or len(tickers) < 2:
            return {"error": "Need at least 2 tickers to compare"}
        if len(tickers) > 5:
            return {"error": "Maximum 5 stocks can be compared at once"}
        
        tickers = [t.upper() for t in tickers]
        comparison = {"tickers": tickers, "metrics": {}}
        
        # Get metrics for each stock
        for ticker in tickers:
            metrics = self.db.get_stock_metrics(ticker)
            if not metrics:
                comparison["metrics"][ticker] = {"error": "Not found"}
                continue
            
            comparison["metrics"][ticker] = {
                "company_name": metrics.get('company_name'),
                "sector": metrics.get('sector'),
                "price": round(metrics.get('price'), 2) if metrics.get('price') else None,
                "market_cap_b": round(metrics.get('market_cap') / 1e9, 2) if metrics.get('market_cap') else None,
                "pe_ratio": round(metrics.get('pe_ratio'), 1) if metrics.get('pe_ratio') else None,
                "forward_pe": round(metrics.get('forward_pe'), 1) if metrics.get('forward_pe') else None,
                "peg_ratio": round(metrics.get('forward_peg_ratio'), 2) if metrics.get('forward_peg_ratio') else None,
                "debt_to_equity": round(metrics.get('debt_to_equity'), 2) if metrics.get('debt_to_equity') else None,
                "dividend_yield_pct": round(metrics.get('dividend_yield'), 2) if metrics.get('dividend_yield') else None,
                "beta": round(metrics.get('beta'), 2) if metrics.get('beta') else None,
            }
        
        return comparison
    
    def _find_similar_stocks(self, ticker: str, limit: int = 5) -> Dict[str, Any]:
        """Find stocks similar to the given ticker."""
        ticker = ticker.upper()
        
        # Get reference stock metrics
        ref_metrics = self.db.get_stock_metrics(ticker)
        if not ref_metrics:
            return {"error": f"Stock {ticker} not found"}
        
        ref_sector = ref_metrics.get('sector')
        ref_market_cap = ref_metrics.get('market_cap')
        
        if not ref_sector or not ref_market_cap:
            return {"error": f"Insufficient data for {ticker} to find similar stocks"}
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Find stocks in same sector with similar market cap
            cursor.execute("""
                SELECT DISTINCT symbol, sector, market_cap, peg_ratio, 
                       earnings_cagr, revenue_cagr, overall_score
                FROM screening_results
                WHERE sector = %s
                  AND symbol != %s
                  AND market_cap BETWEEN %s AND %s
                  AND overall_score IS NOT NULL
                ORDER BY overall_score DESC
                LIMIT %s
            """, (
                ref_sector,
                ticker,
                ref_market_cap * 0.3,  # 30% to 300% of reference market cap
                ref_market_cap * 3.0,
                limit
            ))
            
            similar_stocks = []
            for row in cursor.fetchall():
                similar_stocks.append({
                    "symbol": row[0],
                    "sector": row[1],
                    "market_cap_b": round(row[2] / 1e9, 2) if row[2] else None,
                    "peg_ratio": round(row[3], 2) if row[3] else None,
                    "earnings_cagr_pct": round(row[4], 1) if row[4] else None,
                    "revenue_cagr_pct": round(row[5], 1) if row[5] else None,
                    "lynch_score": round(row[6], 1) if row[6] else None,
                })
            
            return {
                "reference_ticker": ticker,
                "reference_sector": ref_sector,
                "reference_market_cap_b": round(ref_market_cap / 1e9, 2),
                "similar_stocks": similar_stocks,
                "count": len(similar_stocks)
            }
        finally:
            self.db.return_connection(conn)
    
    def _search_company(self, company_name: str, limit: int = 5) -> Dict[str, Any]:
        """Search for companies by name using fuzzy matching."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Use ILIKE for case-insensitive partial matching
            cursor.execute("""
                SELECT symbol, company_name, sector, exchange
                FROM stocks
                WHERE company_name ILIKE %s
                ORDER BY 
                    CASE 
                        WHEN company_name ILIKE %s THEN 1  -- Exact match first
                        WHEN company_name ILIKE %s THEN 2  -- Starts with
                        ELSE 3                              -- Contains
                    END,
                    company_name
                LIMIT %s
            """, (
                f'%{company_name}%',  # Contains
                company_name,          # Exact
                f'{company_name}%',   # Starts with
                limit
            ))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "ticker": row[0],
                    "company_name": row[1],
                    "sector": row[2],
                    "exchange": row[3]
                })
            
            if not results:
                return {
                    "error": f"No companies found matching '{company_name}'",
                    "suggestion": "Try a different spelling or use the ticker symbol directly"
                }
            
            return {
                "query": company_name,
                "matches": results,
                "count": len(results)
            }
        finally:
            self.db.return_connection(conn)
    
    def _get_sector_comparison(self, ticker: str) -> Dict[str, Any]:
        """Compare a stock's metrics to its sector averages."""
        ticker = ticker.upper()
        
        # 1. Get the stock's details and sector
        stock_query = """
            SELECT 
                s.symbol, sr.company_name, sr.sector,
                sr.pe_ratio, sr.peg_ratio, sr.dividend_yield, 
                sr.revenue_cagr, sr.earnings_cagr, sr.debt_to_equity
            FROM stocks s
            LEFT JOIN screening_results sr ON s.symbol = sr.symbol
            WHERE s.symbol = %s
            ORDER BY sr.scored_at DESC
            LIMIT 1
        """
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(stock_query, (ticker,))
            stock_row = cursor.fetchone()
            
            if not stock_row:
                return {"error": f"Stock {ticker} not found"}
            
            sector = stock_row[2]
            if not sector:
                return {"error": f"Sector information not available for {ticker}"}
            
            stock_metrics = {
                "pe_ratio": stock_row[3],
                "peg_ratio": stock_row[4],
                "dividend_yield": stock_row[5],
                "revenue_growth": stock_row[6],
                "eps_growth": stock_row[7],
                "debt_to_equity": stock_row[8]
            }
            
            # 2. Calculate sector statistics
            # We filter for outliers to get a more representative average (e.g., exclude P/E > 200)
            sector_stats_query = """
                WITH sector_stocks AS (
                    SELECT DISTINCT ON (s.symbol) 
                        sr.pe_ratio, sr.peg_ratio, sr.dividend_yield, 
                        sr.revenue_cagr, sr.earnings_cagr, sr.debt_to_equity
                    FROM stocks s
                    JOIN screening_results sr ON s.symbol = sr.symbol
                    WHERE sr.sector = %s AND s.symbol != %s
                    ORDER BY s.symbol, sr.scored_at DESC
                )
                SELECT
                    COUNT(*) as stock_count,
                    AVG(pe_ratio) FILTER (WHERE pe_ratio > 0 AND pe_ratio < 200) as avg_pe,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pe_ratio) FILTER (WHERE pe_ratio > 0 AND pe_ratio < 200) as median_pe,
                    
                    AVG(peg_ratio) FILTER (WHERE peg_ratio > 0 AND peg_ratio < 10) as avg_peg,
                    
                    AVG(dividend_yield) FILTER (WHERE dividend_yield != 'NaN') as avg_yield,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dividend_yield) FILTER (WHERE dividend_yield != 'NaN') as median_yield,
                    
                    AVG(revenue_cagr) FILTER (WHERE revenue_cagr BETWEEN -50 AND 200 AND revenue_cagr != 'NaN') as avg_rev_growth,
                    
                    AVG(earnings_cagr) FILTER (WHERE earnings_cagr BETWEEN -50 AND 200 AND earnings_cagr != 'NaN') as avg_eps_growth,
                    
                    AVG(debt_to_equity) FILTER (WHERE debt_to_equity < 50 AND debt_to_equity != 'NaN') as avg_debt_equity
                FROM sector_stocks
            """
            
            cursor.execute(sector_stats_query, (sector, ticker))
            stats = cursor.fetchone()
            
            if not stats or stats[0] < 3: # Need at least a few peers for valid comparison
                return {
                    "ticker": ticker,
                    "company_name": stock_row[1],
                    "sector": sector,
                    "message": "Not enough data in this sector for a meaningful comparison.",
                    "stock_metrics": stock_metrics
                }

            return {
                "ticker": ticker,
                "company_name": stock_row[1],
                "sector": sector,
                "peer_count": stats[0],
                "comparison": {
                    "pe_ratio": {
                        "stock": round(stock_metrics["pe_ratio"], 2) if stock_metrics["pe_ratio"] else None,
                        "sector_avg": round(stats[1], 2) if stats[1] else None,
                        "sector_median": round(stats[2], 2) if stats[2] else None,
                        "diff_percent": round((stock_metrics["pe_ratio"] - stats[1]) / stats[1] * 100, 1) if stock_metrics["pe_ratio"] and stats[1] else None
                    },
                    "peg_ratio": {
                        "stock": round(stock_metrics["peg_ratio"], 2) if stock_metrics["peg_ratio"] else None,
                        "sector_avg": round(stats[3], 2) if stats[3] else None
                    },
                    "dividend_yield": {
                        "stock": round(stock_metrics["dividend_yield"], 2) if stock_metrics["dividend_yield"] else None,
                        "sector_avg": round(stats[4], 2) if stats[4] else None,
                        "sector_median": round(stats[5], 2) if stats[5] else None
                    },
                    "revenue_growth": {
                        "stock": round(stock_metrics["revenue_growth"], 2) if stock_metrics["revenue_growth"] else None,
                        "sector_avg": round(stats[6], 2) if stats[6] else None
                    },
                    "eps_growth": {
                        "stock": round(stock_metrics["eps_growth"], 2) if stock_metrics["eps_growth"] else None,
                        "sector_avg": round(stats[7], 2) if stats[7] else None
                    },
                    "debt_to_equity": {
                        "stock": round(stock_metrics["debt_to_equity"], 2) if stock_metrics["debt_to_equity"] else None,
                        "sector_avg": round(stats[8], 2) if stats[8] else None
                    }
                }
            }
            
        finally:
            self.db.return_connection(conn)

    def _get_earnings_history(self, ticker: str, period_type: str = "quarterly", limit: int = 12) -> Dict[str, Any]:
        """Get historical earnings and revenue data."""
        ticker = ticker.upper()
        limit = min(limit or 12, 40)
        
        conditions = ["symbol = %s"]
        params = [ticker]
        
        if period_type == "quarterly":
            conditions.append("period != 'annual'")
        elif period_type == "annual":
            conditions.append("period = 'annual'")
            
        where_clause = " AND ".join(conditions)
        
        # Sort by year descending, then period (Annual > Q4 > Q3 > Q2 > Q1)
        # Note: We treat 'annual' as coming after Q4 of the same year
        order_case = """
            CASE period 
                WHEN 'annual' THEN 5 
                WHEN 'Q4' THEN 4 
                WHEN 'Q3' THEN 3 
                WHEN 'Q2' THEN 2 
                WHEN 'Q1' THEN 1 
                ELSE 0 
            END DESC
        """
        query = f"""
            SELECT 
                year, period, earnings_per_share, revenue, net_income,
                free_cash_flow, operating_cash_flow, capital_expenditures
            FROM earnings_history
            WHERE {where_clause}
            ORDER BY year DESC, {order_case}
            LIMIT %s
        """
        params.append(limit)
        
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            
            history = []
            for row in cursor.fetchall():
                # Only include rows with meaningful data
                if row[2] is None and row[3] is None and row[4] is None:
                    continue
                    
                history.append({
                    "year": row[0],
                    "period": row[1],
                    "eps": float(row[2]) if row[2] is not None else None,
                    "revenue": float(row[3]) if row[3] is not None else None,
                    "net_income": float(row[4]) if row[4] is not None else None,
                    "free_cash_flow": float(row[5]) if row[5] is not None else None,
                    "operating_cash_flow": float(row[6]) if row[6] is not None else None,
                    "capex": float(row[7]) if row[7] is not None else None
                })
            
            if not history:
                return {
                    "ticker": ticker,
                    "message": "No earnings history found."
                }
                
            # Check if quarterly FCF is all null - if so, fetch annual FCF for context
            annual_fcf_context = None
            if period_type == "quarterly":
                has_quarterly_fcf = any(h.get("free_cash_flow") is not None for h in history)
                if not has_quarterly_fcf:
                    # Fetch latest annual FCF for context
                    cursor.execute("""
                        SELECT year, free_cash_flow, operating_cash_flow, capital_expenditures
                        FROM earnings_history
                        WHERE symbol = %s AND period = 'annual' AND free_cash_flow IS NOT NULL
                        ORDER BY year DESC
                        LIMIT 2
                    """, (ticker,))
                    annual_rows = cursor.fetchall()
                    if annual_rows:
                        annual_fcf_context = [
                            {
                                "year": r[0],
                                "free_cash_flow": float(r[1]) if r[1] else None,
                                "operating_cash_flow": float(r[2]) if r[2] else None,
                                "capex": float(r[3]) if r[3] else None
                            }
                            for r in annual_rows
                        ]
            
            result = {
                "ticker": ticker,
                "period_type": period_type,
                "count": len(history),
                "history": history
            }
            
            if annual_fcf_context:
                result["annual_fcf_context"] = annual_fcf_context
                result["note"] = "Quarterly Free Cash Flow data is unavailable. Annual FCF provided for context."
            
            return result
        finally:
            self.db.return_connection(conn)

    def _screen_stocks(
        self,
        pe_max: float = None,
        pe_min: float = None,
        dividend_yield_min: float = None,
        market_cap_min: float = None,
        market_cap_max: float = None,
        revenue_growth_min: float = None,
        eps_growth_min: float = None,
        sector: str = None,
        peg_max: float = None,
        debt_to_equity_max: float = None,
        profit_margin_min: float = None,
        has_transcript: bool = None,
        sort_by: str = "market_cap",
        sort_order: str = "desc",
        limit: int = 20,
        exclude_tickers: list = None
    ) -> Dict[str, Any]:
        """Screen stocks based on various criteria."""
        
        # Cap limit at 50
        limit = min(limit or 20, 50)
        
        # Build dynamic WHERE clause
        conditions = []
        params = []
        
        # Exclude tickers
        if exclude_tickers:
            # Format inputs to uppercase
            excluded = [t.upper() for t in exclude_tickers if isinstance(t, str)]
            if excluded:
                placeholders = ', '.join(['%s'] * len(excluded))
                conditions.append(f"s.symbol NOT IN ({placeholders})")
                params.extend(excluded)
        
        # P/E filters
        if pe_max is not None:
            conditions.append("sr.pe_ratio <= %s AND sr.pe_ratio != 'NaN'")
            params.append(pe_max)
        if pe_min is not None:
            conditions.append("sr.pe_ratio >= %s AND sr.pe_ratio != 'NaN'")
            params.append(pe_min)
        
        # Dividend yield filter
        if dividend_yield_min is not None:
            conditions.append("sr.dividend_yield >= %s AND sr.dividend_yield != 'NaN'")
            params.append(dividend_yield_min)
        
        # Market cap filters (convert billions to actual value)
        if market_cap_min is not None:
            conditions.append("sr.market_cap >= %s AND sr.market_cap != 'NaN'")
            params.append(market_cap_min * 1_000_000_000)
        if market_cap_max is not None:
            conditions.append("sr.market_cap <= %s AND sr.market_cap != 'NaN'")
            params.append(market_cap_max * 1_000_000_000)
        
        # Growth filters (table uses _cagr suffix)
        if revenue_growth_min is not None:
            conditions.append("sr.revenue_cagr >= %s AND sr.revenue_cagr != 'NaN'")
            params.append(revenue_growth_min)
        if eps_growth_min is not None:
            conditions.append("sr.earnings_cagr >= %s AND sr.earnings_cagr != 'NaN'")
            params.append(eps_growth_min)
        
        # Sector filter
        if sector:
            conditions.append("LOWER(s.sector) LIKE LOWER(%s)")
            params.append(f"%{sector}%")
        
        # PEG filter
        if peg_max is not None:
            conditions.append("sr.peg_ratio <= %s AND sr.peg_ratio != 'NaN'")
            params.append(peg_max)
        
        # Debt to equity filter
        if debt_to_equity_max is not None:
            conditions.append("sr.debt_to_equity <= %s AND sr.debt_to_equity != 'NaN'")
            params.append(debt_to_equity_max)
        
        # Transcript filter - only show stocks with earnings call transcripts
        if has_transcript:
            conditions.append("""EXISTS (
                SELECT 1 FROM earnings_transcripts et 
                WHERE et.symbol = s.symbol 
                AND et.transcript_text IS NOT NULL 
                AND LENGTH(et.transcript_text) > 100
            )""")

        # Profit Margin Filter
        join_clause = ""
        if profit_margin_min is not None:
            # Join with latest annual earnings to get net income and revenue
            join_clause = """
                JOIN (
                    SELECT DISTINCT ON (symbol) symbol, net_income, revenue 
                    FROM earnings_history 
                    WHERE period='annual' AND revenue > 0
                    ORDER BY symbol, year DESC
                ) eh ON s.symbol = eh.symbol
            """
            # Calculate margin: (Net Income / Revenue) * 100
            conditions.append("(eh.net_income::float / eh.revenue::float * 100) >= %s")
            params.append(profit_margin_min)

        
        # Always exclude null P/E and require positive metrics
        conditions.append("sr.pe_ratio IS NOT NULL")
        conditions.append("sr.pe_ratio > 0")
        conditions.append("sr.market_cap > 0")
        
        # Ensure company has quarterly earnings history (so it can be analyzed further)
        conditions.append("""EXISTS (
            SELECT 1 FROM earnings_history eh 
            WHERE eh.symbol = s.symbol 
            AND eh.period != 'annual' 
            AND eh.net_income IS NOT NULL
        )""")
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Build ORDER BY clause
        sort_columns = {
            "pe": "sr.pe_ratio",
            "dividend_yield": "sr.dividend_yield",
            "market_cap": "sr.market_cap",
            "revenue_growth": "sr.revenue_cagr",
            "eps_growth": "sr.earnings_cagr",
            "debt_to_equity": "sr.debt_to_equity",
        }
        order_column = sort_columns.get(sort_by, "sr.market_cap")
        order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"
        
        # Handle nulls in sorting
        null_handling = "NULLS LAST" if order_dir == "DESC" else "NULLS FIRST"
        
        query = f"""
            WITH latest_screening AS (
                SELECT DISTINCT ON (symbol) *
                FROM screening_results
                ORDER BY symbol, scored_at DESC
            )
            SELECT 
                s.symbol,
                s.company_name,
                s.sector,
                sr.market_cap,
                sr.pe_ratio,
                sr.peg_ratio,
                sr.dividend_yield,
                sr.revenue_cagr,
                sr.earnings_cagr,
                sr.debt_to_equity
            FROM stocks s
            JOIN latest_screening sr ON s.symbol = sr.symbol
            {join_clause}
            WHERE {where_clause}
            ORDER BY {order_column} {order_dir} {null_handling}
            LIMIT %s
        """
        params.append(limit)
        
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            
            results = []
            for row in cursor.fetchall():
                # Format market cap for readability
                market_cap = row[3]
                if market_cap:
                    if market_cap >= 1_000_000_000_000:
                        market_cap_str = f"${market_cap / 1_000_000_000_000:.1f}T"
                    elif market_cap >= 1_000_000_000:
                        market_cap_str = f"${market_cap / 1_000_000_000:.1f}B"
                    else:
                        market_cap_str = f"${market_cap / 1_000_000:.0f}M"
                else:
                    market_cap_str = "N/A"
                
                results.append({
                    "ticker": row[0],
                    "company_name": row[1],
                    "sector": row[2],
                    "market_cap": market_cap_str,
                    "pe_ratio": round(row[4], 1) if row[4] else None,
                    "peg_ratio": round(row[5], 2) if row[5] else None,
                    "dividend_yield": round(row[6], 2) if row[6] else None,
                    "revenue_growth": round(row[7], 1) if row[7] else None,
                    "eps_growth": round(row[8], 1) if row[8] else None,
                    "debt_to_equity": round(row[9], 2) if row[9] else None,
                })
            
            # Build filter summary
            filters_applied = []
            if pe_max is not None:
                filters_applied.append(f"P/E <= {pe_max}")
            if pe_min is not None:
                filters_applied.append(f"P/E >= {pe_min}")
            if dividend_yield_min is not None:
                filters_applied.append(f"Div Yield >= {dividend_yield_min}%")
            if market_cap_min is not None:
                filters_applied.append(f"Market Cap >= ${market_cap_min}B")
            if market_cap_max is not None:
                filters_applied.append(f"Market Cap <= ${market_cap_max}B")
            if sector:
                filters_applied.append(f"Sector: {sector}")
            if peg_max is not None:
                filters_applied.append(f"PEG <= {peg_max}")
            
            return {
                "filters_applied": filters_applied if filters_applied else ["None (showing all stocks)"],
                "sort": f"{sort_by} {sort_order}",
                "count": len(results),
                "stocks": results
            }
        finally:
            self.db.return_connection(conn)
