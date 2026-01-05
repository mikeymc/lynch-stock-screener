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
