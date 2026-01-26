# ABOUTME: Defines atomic tools for the Smart Chat Agent using Gemini Native format
# ABOUTME: Each tool wraps an existing data fetcher for use in ReAct loops

from typing import Dict, Any, List, Optional, Callable
from google.genai.types import FunctionDeclaration, Schema, Type, Tool
from fred_service import get_fred_service, SUPPORTED_SERIES
import portfolio_service


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
    description="Get historical financial metrics for a stock. Returns annual data including revenue, EPS, net income, cash flows, capital expenditures, dividends, debt ratios, and shareholder equity.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "metric": Schema(
                type=Type.STRING,
                description="The specific financial metric to retrieve",
                enum=["revenue", "eps", "net_income", "free_cash_flow", "operating_cash_flow", "capital_expenditures", "dividend_amount", "debt_to_equity", "shareholder_equity", "shares_outstanding", "cash_and_cash_equivalents"]
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

get_roe_metrics_decl = FunctionDeclaration(
    name="get_roe_metrics",
    description="Calculate Return on Equity (ROE) metrics for a stock. Returns current ROE, 5-year average ROE, 10-year average ROE, and historical ROE by year. ROE = Net Income / Shareholders Equity. Useful for Buffett-style analysis (target: >15% consistently).",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_owner_earnings_decl = FunctionDeclaration(
    name="get_owner_earnings",
    description="Calculate Owner Earnings (Buffett's preferred cash flow metric). Owner Earnings = Operating Cash Flow - Maintenance CapEx (estimated as 70% of total capex). This represents the real cash the owner could extract from the business. More meaningful than accounting earnings.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_debt_to_earnings_ratio_decl = FunctionDeclaration(
    name="get_debt_to_earnings_ratio",
    description="Calculate how many years it would take to pay off all debt with current earnings. Debt-to-Earnings = Total Debt / Annual Net Income. Buffett prefers companies that can pay off debt in 3-4 years or less. Measures financial strength and flexibility.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_gross_margin_decl = FunctionDeclaration(
    name="get_gross_margin",
    description="Calculate Gross Margin metrics for a stock. Gross Margin = Gross Profit / Revenue. Returns current margin, 5-year average, trend (stable/improving/declining), and historical margins. High and stable gross margins (>40-50%) indicate pricing power and a durable competitive moat.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_earnings_consistency_decl = FunctionDeclaration(
    name="get_earnings_consistency",
    description="Calculate earnings consistency score (0-100) based on historical earnings stability. Higher scores indicate more predictable earnings. Both Lynch and Buffett value consistent, predictable earnings over volatile ones. Scores above 80 are excellent, 60+ is good.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_price_to_book_ratio_decl = FunctionDeclaration(
    name="get_price_to_book_ratio",
    description="Calculate Price-to-Book (P/B) ratio. P/B = Market Cap / Shareholders Equity. Shows how much investors are paying relative to book value. Buffett mentions this metric - value stocks often have lower P/B ratios. Returns current P/B and historical book value per share.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_share_buyback_activity_decl = FunctionDeclaration(
    name="get_share_buyback_activity",
    description="Analyze share buyback/issuance activity over time. Shows year-over-year changes in shares outstanding. Lynch says 'Look for companies that consistently buy back their own shares.' Decreasing shares = buybacks (positive signal). Increasing shares = dilution (negative signal).",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_cash_position_decl = FunctionDeclaration(
    name="get_cash_position",
    description="Get cash and cash equivalents position over time. Lynch says 'The cash position. That's the floor on the stock.' Shows historical cash levels and cash per share. High cash relative to market cap provides downside protection.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_peers_decl = FunctionDeclaration(
    name="get_peers",
    description="Get peer companies in the same sector with their financial metrics. Returns other stocks in the same sector/industry with key metrics (P/E, PEG, growth rates, debt) for direct comparison.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol to find peers for"),
            "limit": Schema(type=Type.INTEGER, description="Maximum number of peers to return (default: 10)"),
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
    description="Get analyst consensus estimates for future earnings and revenue. Returns EPS and revenue projections for current quarter (0q), next quarter (+1q), current year (0y), and next year (+1y). Each period includes low/avg/high estimate ranges, YoY growth %, and number of analysts. Use this to understand Wall Street's expectations and the spread of analyst opinions.",
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
            "revenue_growth_min": Schema(type=Type.NUMBER, description="Minimum annual revenue growth percentage (e.g., 10 for 10% YoY growth)"),
            "eps_growth_min": Schema(type=Type.NUMBER, description="Minimum annual EPS/earnings growth percentage (e.g., 15 for 15% YoY growth)"),
            "sector": Schema(type=Type.STRING, description="Filter by sector. Valid values: 'Technology', 'Healthcare', 'Finance' (banks like JPM/BAC/GS), 'Financial Services' (fintech), 'Consumer Cyclical', 'Consumer Defensive', 'Energy', 'Industrials', 'Basic Materials', 'Real Estate', 'Utilities', 'Communication Services'"),
            "peg_max": Schema(type=Type.NUMBER, description="Maximum PEG ratio (P/E divided by growth rate)"),
            "peg_min": Schema(type=Type.NUMBER, description="Minimum PEG ratio (e.g., 2.0 to find potentially overvalued stocks)"),
            "debt_to_equity_max": Schema(type=Type.NUMBER, description="Maximum debt-to-equity ratio"),
            "profit_margin_min": Schema(type=Type.NUMBER, description="Minimum Net Profit Margin percentage (e.g., 20.0 for high margin businesses)"),
            "target_upside_min": Schema(type=Type.NUMBER, description="Minimum analyst target upside percentage (e.g. 20 for 20% upside based on mean price target)"),
            "has_transcript": Schema(type=Type.BOOLEAN, description="If true, only return stocks that have an earnings call transcript available"),
            "has_fcf": Schema(type=Type.BOOLEAN, description="If true, only return stocks that have Free Cash Flow data available (useful for dividend coverage analysis)"),
            "has_recent_insider_activity": Schema(type=Type.BOOLEAN, description="If true, only return stocks with insider BUY transactions in the last 90 days"),
            "sort_by": Schema(type=Type.STRING, description="Sort results by: 'pe', 'dividend_yield', 'market_cap', 'revenue_growth', 'eps_growth', 'peg', 'debt_to_equity', 'gross_margin', 'target_upside' (default: 'market_cap')"),
            "sort_order": Schema(type=Type.STRING, description="Sort order: 'asc' or 'desc' (default: 'desc')"),
            "top_n_by_market_cap": Schema(type=Type.INTEGER, description="UNIVERSE FILTER: Only consider the top N companies by market cap (within sector if specified). Use this when asked for 'top 50 by market cap' or similar. Apply this BEFORE other sorts like 'lowest P/E'."),
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


manage_alerts_decl = FunctionDeclaration(
    name="manage_alerts",
    description="""Manage user alerts for stock metrics. Supports flexible natural language alert conditions.
    
    You can create alerts for ANY stock metric or condition, including:
    - Price movements (e.g., "notify when AAPL drops below $150")
    - Valuation metrics (e.g., "alert when P/E ratio falls below 15")
    - Financial ratios (e.g., "notify when gross margin exceeds 40%")
    - Market metrics (e.g., "alert when market cap reaches $1B")
    - Complex conditions (e.g., "notify when debt-to-equity is below 0.5 and P/E is under 20")
    
    Use this tool to create new alerts with natural language conditions, list existing alerts, or delete unwanted alerts.""",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "action": Schema(
                type=Type.STRING, 
                description="The operation to perform",
                enum=["create", "list", "delete"]
            ),
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol (required for 'create')"),
            "condition_description": Schema(
                type=Type.STRING, 
                description="Natural language description of the alert condition (required for 'create'). Be specific about the metric and threshold. Examples: 'notify me when the price drops below $145', 'alert when gross margin exceeds 35%', 'notify when P/E ratio is below 15'"
            ),
            "alert_id": Schema(type=Type.INTEGER, description="ID of the alert to delete (required for 'delete')"),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected by system, do not prompt for this)"),
            # Automated Trading Parameters
            "action_type": Schema(
                type=Type.STRING,
                description="Optional: Automated trading action to take when alert triggers. Use 'market_buy' to buy shares or 'market_sell' to sell shares.",
                enum=["market_buy", "market_sell"]
            ),
            "action_quantity": Schema(
                type=Type.INTEGER,
                description="Optional: Number of shares to buy or sell if action_type is specified."
            ),
            "portfolio_name": Schema(
                type=Type.STRING,
                description="Optional: Name of the paper trading portfolio to execute the trade in (e.g., 'Tech Growth'). Required if action_type is specified."
            ),
            "action_note": Schema(
                type=Type.STRING,
                description="Optional: Note to attach to the automated trade."
            ),
        },
        required=["action"],
    ),
)


create_portfolio_decl = FunctionDeclaration(
    name="create_portfolio",
    description="Create a new paper trading portfolio for the user.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "name": Schema(type=Type.STRING, description="Name for the portfolio (e.g., 'Tech Growth', 'Retirement Mockup')"),
            "initial_cash": Schema(type=Type.NUMBER, description="Starting cash amount (default: 100,000)"),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["name"],
    ),
)


get_my_portfolios_decl = FunctionDeclaration(
    name="get_my_portfolios",
    description="Get a list of all paper trading portfolios owned by the user.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=[],
    ),
)


get_portfolio_status_decl = FunctionDeclaration(
    name="get_portfolio_status",
    description="Get detailed status of a specific portfolio, including cash balance, current holdings, and total value.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "portfolio_id": Schema(type=Type.INTEGER, description="ID of the portfolio to check"),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["portfolio_id"],
    ),
)


buy_stock_decl = FunctionDeclaration(
    name="buy_stock",
    description="Buy shares of a stock in a paper trading portfolio. Uses current market price.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "portfolio_id": Schema(type=Type.INTEGER, description="ID of the portfolio to trade in"),
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol (e.g., 'AAPL')"),
            "quantity": Schema(type=Type.INTEGER, description="Number of shares to buy"),
            "note": Schema(type=Type.STRING, description="Optional note describing why you are buying this stock"),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["portfolio_id", "ticker", "quantity"],
    ),
)


sell_stock_decl = FunctionDeclaration(
    name="sell_stock",
    description="Sell shares of a stock in a paper trading portfolio. Uses current market price.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "portfolio_id": Schema(type=Type.INTEGER, description="ID of the portfolio to trade in"),
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol (e.g., 'AAPL')"),
            "quantity": Schema(type=Type.INTEGER, description="Number of shares to sell"),
            "note": Schema(type=Type.STRING, description="Optional note describing why you are selling this stock"),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["portfolio_id", "ticker", "quantity"],
    ),
)


# =============================================================================
# FRED Macroeconomic Data Tools
# =============================================================================

get_fred_series_decl = FunctionDeclaration(
    name="get_fred_series",
    description="Get historical observations for a FRED economic data series. Use this to analyze trends in macroeconomic indicators like GDP, unemployment, inflation, interest rates, etc.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "series_id": Schema(
                type=Type.STRING,
                description="FRED series ID. Common series: GDPC1 (Real GDP), UNRATE (Unemployment), CPIAUCSL (CPI), FEDFUNDS (Fed Funds Rate), DGS10 (10-Year Treasury), T10Y2Y (Yield Curve), VIXCLS (VIX), ICSA (Jobless Claims)"
            ),
            "start_date": Schema(type=Type.STRING, description="Start date in YYYY-MM-DD format (optional, defaults to 2 years ago)"),
            "end_date": Schema(type=Type.STRING, description="End date in YYYY-MM-DD format (optional, defaults to today)"),
        },
        required=["series_id"],
    ),
)

get_economic_indicators_decl = FunctionDeclaration(
    name="get_economic_indicators",
    description="Get current values of key macroeconomic indicators including GDP, unemployment rate, inflation (CPI), Fed funds rate, 10-year Treasury yield, yield curve spread, VIX volatility index, and initial jobless claims. Use this for a quick economic overview.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={},
        required=[],
    ),
)

get_analyst_sentiment_decl = FunctionDeclaration(
    name="get_analyst_sentiment",
    description="Get comprehensive Wall Street analyst sentiment for a stock. Includes EPS estimate trends (how estimates changed over 30/60/90 days), revision momentum (up vs down revisions), recommendation history (buy/hold/sell counts), and growth estimates vs index. Use this to understand analyst bullishness and growth expectations relative to the market.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
        },
        required=["ticker"],
    ),
)

get_average_pe_ratio_decl = FunctionDeclaration(
    name="get_average_pe_ratio",
    description="Calculate average P/E (Price-to-Earnings) ratios over time for a stock. Returns P/E ratios for each period (quarterly or annual) along with the overall average. Useful for understanding typical valuation ranges and how P/E has trended over time.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "ticker": Schema(type=Type.STRING, description="Stock ticker symbol"),
            "period_type": Schema(
                type=Type.STRING, 
                description="Type of periods to analyze: 'quarterly' for quarterly P/E ratios, 'annual' for annual P/E ratios (default: 'annual')",
                enum=["quarterly", "annual"]
            ),
            "periods": Schema(type=Type.INTEGER, description="Number of periods to include in the average (default: 5 for annual, 12 for quarterly)"),
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
    get_roe_metrics_decl,
    get_owner_earnings_decl,
    get_debt_to_earnings_ratio_decl,
    get_gross_margin_decl,
    get_earnings_consistency_decl,
    get_price_to_book_ratio_decl,
    get_share_buyback_activity_decl,
    get_cash_position_decl,
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
    manage_alerts_decl,
    # FRED macroeconomic tools
    get_fred_series_decl,
    get_economic_indicators_decl,
    get_analyst_sentiment_decl,
    get_average_pe_ratio_decl,
    # Portfolio management tools
    create_portfolio_decl,
    get_my_portfolios_decl,
    get_portfolio_status_decl,
    buy_stock_decl,
    sell_stock_decl,
]

# Create the Tool object for Gemini API
AGENT_TOOLS = Tool(function_declarations=TOOL_DECLARATIONS)


# =============================================================================
# Tool Executors: Actual Python functions that execute the tools
# =============================================================================

class ToolExecutor:
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
        }
        
        executor = executor_map.get(tool_name)
        if not executor:
            return {"error": f"Unknown tool: {tool_name}"}
        
        try:
            return executor(**args)
        except Exception as e:
            return {"error": str(e)}
    
    def _get_stock_metrics(self, ticker: str) -> Dict[str, Any]:
        """Get all available stock metrics including calculated growth rates."""
        ticker = ticker.upper()
        result = self.db.get_stock_metrics(ticker)
        if not result:
            return {"error": f"No data found for {ticker}"}

        # Calculate 5-year growth rates from earnings_history (matches screener behavior)
        earnings_growth = None
        revenue_growth = None
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            # Get last 5 years of annual data, ordered by year
            cursor.execute("""
                SELECT year, net_income, revenue
                FROM earnings_history
                WHERE symbol = %s AND period = 'annual'
                  AND net_income IS NOT NULL AND revenue IS NOT NULL
                ORDER BY year DESC
                LIMIT 5
            """, (ticker,))
            rows = cursor.fetchall()
            if len(rows) >= 3:  # Need at least 3 years for meaningful growth
                # Rows are in DESC order, reverse to get oldest first
                rows = list(reversed(rows))
                start_income, end_income = rows[0][1], rows[-1][1]
                start_revenue, end_revenue = rows[0][2], rows[-1][2]
                years = len(rows) - 1
                # Linear growth: ((end - start) / |start|) / years * 100
                if start_income and start_income != 0 and end_income:
                    earnings_growth = round(((end_income - start_income) / abs(start_income)) / years * 100, 1)
                if start_revenue and start_revenue != 0 and end_revenue:
                    revenue_growth = round(((end_revenue - start_revenue) / abs(start_revenue)) / years * 100, 1)
        except Exception:
            pass  # Growth rates will remain None
        finally:
            if conn:
                self.db.return_connection(conn)

        # Calculate PEG ratio the same way the screener does: P/E / earnings_growth
        pe_ratio = result.get("pe_ratio")
        peg_ratio = None
        if pe_ratio and earnings_growth and earnings_growth > 0:
            peg_ratio = round(pe_ratio / earnings_growth, 2)

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
            "pe_ratio": pe_ratio,
            "forward_pe": result.get("forward_pe"),
            "peg_ratio": peg_ratio,  # Calculated: P/E / earnings_growth
            "forward_peg_ratio": result.get("forward_peg_ratio"),  # From data provider
            "forward_eps": result.get("forward_eps"),
            # Growth rates (calculated from earnings_history)
            "earnings_growth": earnings_growth,
            "revenue_growth": revenue_growth,
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
            "shareholder_equity": "shareholder_equity",
            "shares_outstanding": "shares_outstanding",
            "cash_and_cash_equivalents": "cash_and_cash_equivalents",
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

    def _get_roe_metrics(self, ticker: str) -> Dict[str, Any]:
        """Calculate Return on Equity (ROE) metrics."""
        ticker = ticker.upper()

        # Use MetricCalculator to compute ROE
        from metric_calculator import MetricCalculator
        calc = MetricCalculator(self.db)
        roe_data = calc.calculate_roe(ticker)

        if not roe_data or not roe_data.get('roe_history'):
            return {
                "error": f"Could not calculate ROE for {ticker}",
                "suggestion": "ROE requires historical net income and shareholder equity data. Check if the stock has complete financial history."
            }

        return {
            "ticker": ticker,
            "current_roe": roe_data.get('current_roe'),
            "avg_roe_5yr": roe_data.get('avg_roe_5yr'),
            "avg_roe_10yr": roe_data.get('avg_roe_10yr'),
            "roe_history": roe_data.get('roe_history'),
            "interpretation": (
                f"Current ROE: {roe_data.get('current_roe')}%. "
                f"Buffett typically looks for ROE consistently above 15%, ideally 20%+. "
                f"5-year average: {roe_data.get('avg_roe_5yr')}%. "
                f"{'10-year average: ' + str(roe_data.get('avg_roe_10yr')) + '%.' if roe_data.get('avg_roe_10yr') else 'Insufficient data for 10-year average.'}"
            )
        }

    def _get_owner_earnings(self, ticker: str) -> Dict[str, Any]:
        """Calculate Owner Earnings (Buffett's preferred metric)."""
        ticker = ticker.upper()

        from metric_calculator import MetricCalculator
        calc = MetricCalculator(self.db)
        owner_data = calc.calculate_owner_earnings(ticker)

        if not owner_data or owner_data.get('owner_earnings') is None:
            return {
                "error": f"Could not calculate Owner Earnings for {ticker}",
                "suggestion": "Owner Earnings requires operating cash flow and capital expenditure data."
            }

        return {
            "ticker": ticker,
            "owner_earnings_millions": owner_data.get('owner_earnings'),
            "owner_earnings_per_share": owner_data.get('owner_earnings_per_share'),
            "fcf_to_owner_earnings_ratio": owner_data.get('fcf_to_owner_earnings_ratio'),
            "interpretation": (
                f"Owner Earnings: ${owner_data.get('owner_earnings')}M. "
                f"This represents the real cash the owner could extract from the business. "
                f"Buffett prefers this over accounting earnings as it accounts for maintenance capital expenditures."
            )
        }

    def _get_debt_to_earnings_ratio(self, ticker: str) -> Dict[str, Any]:
        """Calculate years to pay off debt with current earnings."""
        ticker = ticker.upper()

        from metric_calculator import MetricCalculator
        calc = MetricCalculator(self.db)
        debt_data = calc.calculate_debt_to_earnings(ticker)

        if not debt_data or debt_data.get('debt_to_earnings_years') is None:
            return {
                "error": f"Could not calculate Debt-to-Earnings for {ticker}",
                "suggestion": "Requires total debt and net income data."
            }

        years = debt_data.get('debt_to_earnings_years')
        return {
            "ticker": ticker,
            "debt_to_earnings_years": years,
            "total_debt": debt_data.get('total_debt'),
            "net_income": debt_data.get('net_income'),
            "interpretation": (
                f"It would take {years:.1f} years to pay off all debt with current earnings. "
                f"Buffett prefers companies that can pay off debt in 3-4 years or less. "
                f"{'Excellent financial strength.' if years < 3 else 'Good.' if years < 4 else 'Acceptable.' if years < 7 else 'High debt burden - risky.'}"
            )
        }

    def _get_gross_margin(self, ticker: str) -> Dict[str, Any]:
        """Calculate Gross Margin metrics."""
        ticker = ticker.upper()

        from metric_calculator import MetricCalculator
        calc = MetricCalculator(self.db)
        margin_data = calc.calculate_gross_margin(ticker)

        if not margin_data or margin_data.get('current') is None:
            return {
                "error": f"Could not calculate Gross Margin for {ticker}",
                "suggestion": "Requires revenue and gross profit data from income statement."
            }

        current = margin_data.get('current')
        avg = margin_data.get('average')
        trend = margin_data.get('trend')

        return {
            "ticker": ticker,
            "current_margin_pct": current,
            "avg_margin_5yr_pct": avg,
            "trend": trend,
            "margin_history": margin_data.get('history', []),
            "interpretation": (
                f"Current gross margin: {current}%. "
                f"5-year average: {avg}%. "
                f"Trend: {trend}. "
                f"High margins (>40-50%) indicate pricing power and a durable moat. "
                f"{'Excellent margins, suggests strong competitive advantage.' if current > 50 else 'Good margins.' if current > 40 else 'Moderate margins.' if current > 30 else 'Low margins - commodity-like business.'}"
            )
        }

    def _get_earnings_consistency(self, ticker: str) -> Dict[str, Any]:
        """Calculate earnings consistency score."""
        ticker = ticker.upper()

        from earnings_analyzer import EarningsAnalyzer
        analyzer = EarningsAnalyzer(self.db)
        growth_data = analyzer.calculate_earnings_growth(ticker)

        if not growth_data or growth_data.get('income_consistency_score') is None:
            return {
                "error": f"Could not calculate earnings consistency for {ticker}",
                "suggestion": "Requires historical earnings data with at least 3 years of data."
            }

        # Normalize consistency score to 0-100 scale (same as stock_evaluator.py)
        raw_score = growth_data.get('income_consistency_score')
        consistency_score = max(0.0, 100.0 - (raw_score * 2.0))

        return {
            "ticker": ticker,
            "consistency_score": round(consistency_score, 1),
            "raw_consistency_score": raw_score,
            "interpretation": (
                f"Earnings consistency score: {consistency_score:.1f}/100. "
                f"{'Excellent - highly predictable earnings.' if consistency_score >= 80 else 'Good - reasonably consistent.' if consistency_score >= 60 else 'Fair - some volatility.' if consistency_score >= 40 else 'Poor - highly volatile earnings.'} "
                f"Both Lynch and Buffett value predictable earnings."
            )
        }

    def _get_price_to_book_ratio(self, ticker: str) -> Dict[str, Any]:
        """Calculate Price-to-Book ratio."""
        ticker = ticker.upper()

        # Get market cap and shareholder equity
        stock_metrics = self.db.get_stock_metrics(ticker)
        if not stock_metrics:
            return {"error": f"No data found for {ticker}"}

        market_cap = stock_metrics.get('market_cap')
        if not market_cap:
            return {"error": f"Market cap not available for {ticker}"}

        # Get latest shareholder equity
        earnings_history = self.db.get_earnings_history(ticker, 'annual')
        if not earnings_history:
            return {"error": f"No financial history found for {ticker}"}

        latest = earnings_history[0]
        equity = latest.get('shareholder_equity')

        if not equity or equity <= 0:
            return {
                "error": f"Shareholder equity not available or negative for {ticker}",
                "suggestion": "P/B ratio cannot be calculated for companies with negative book value."
            }

        pb_ratio = market_cap / equity
        book_value_per_share = None

        # Calculate book value per share if we have shares outstanding
        price = stock_metrics.get('price')
        if price and price > 0:
            shares_outstanding = market_cap / price
            book_value_per_share = equity / shares_outstanding

        return {
            "ticker": ticker,
            "price_to_book_ratio": round(pb_ratio, 2),
            "market_cap": market_cap,
            "shareholder_equity": equity,
            "book_value_per_share": round(book_value_per_share, 2) if book_value_per_share else None,
            "interpretation": (
                f"Price-to-Book ratio: {pb_ratio:.2f}. "
                f"{'Low P/B - trading below book value, potential value play.' if pb_ratio < 1 else 'Reasonable valuation.' if pb_ratio < 3 else 'Premium valuation.' if pb_ratio < 5 else 'Very high P/B - investors paying significant premium to book value.'} "
                f"Buffett uses this to assess if price is reasonable relative to assets."
            )
        }

    def _get_share_buyback_activity(self, ticker: str) -> Dict[str, Any]:
        """Analyze share buyback/issuance activity over time."""
        ticker = ticker.upper()

        # Get historical shares outstanding
        earnings_history = self.db.get_earnings_history(ticker, 'annual')
        if not earnings_history:
            return {"error": f"No financial history found for {ticker}"}

        # Extract shares_outstanding by year
        shares_by_year = []
        for entry in earnings_history:
            year = entry.get('year')
            shares = entry.get('shares_outstanding')
            if year and shares:
                shares_by_year.append({'year': year, 'shares': shares})

        if len(shares_by_year) < 2:
            return {
                "error": f"Insufficient shares outstanding data for {ticker}",
                "suggestion": "Need at least 2 years of data to calculate buyback activity. Stock may need to be refreshed with force=true to fetch EDGAR data."
            }

        # Sort by year
        shares_by_year.sort(key=lambda x: x['year'])

        # Calculate year-over-year changes
        buyback_history = []
        for i in range(1, len(shares_by_year)):
            prev_year_data = shares_by_year[i-1]
            curr_year_data = shares_by_year[i]

            prev_shares = prev_year_data['shares']
            curr_shares = curr_year_data['shares']

            change_abs = curr_shares - prev_shares
            change_pct = (change_abs / prev_shares) * 100

            buyback_history.append({
                'year': curr_year_data['year'],
                'shares_outstanding': curr_shares,
                'change_from_prior_year': change_abs,
                'change_pct': round(change_pct, 2),
                'activity': 'buyback' if change_pct < 0 else 'issuance' if change_pct > 0 else 'no change'
            })

        # Calculate statistics
        buyback_years = sum(1 for h in buyback_history if h['activity'] == 'buyback')
        issuance_years = sum(1 for h in buyback_history if h['activity'] == 'issuance')
        total_change_pct = ((shares_by_year[-1]['shares'] - shares_by_year[0]['shares']) / shares_by_year[0]['shares']) * 100

        consistent_buybacks = buyback_years >= (len(buyback_history) * 0.7)  # 70%+ of years

        return {
            "ticker": ticker,
            "years_analyzed": len(buyback_history),
            "buyback_years": buyback_years,
            "issuance_years": issuance_years,
            "total_share_change_pct": round(total_change_pct, 2),
            "consistent_buybacks": consistent_buybacks,
            "buyback_history": buyback_history[-10:],  # Last 10 years
            "interpretation": (
                f"Over {len(buyback_history)} years: {buyback_years} years of buybacks, {issuance_years} years of share issuance. "
                f"Total shares outstanding {'decreased' if total_change_pct < 0 else 'increased'} by {abs(total_change_pct):.1f}%. "
                f"{'✓ Consistent buybacks - Lynch loves this!' if consistent_buybacks and total_change_pct < 0 else '⚠ Dilution detected - issuing shares reduces ownership value.' if total_change_pct > 5 else 'Neutral - minimal share count changes.'}"
            )
        }

    def _get_cash_position(self, ticker: str) -> Dict[str, Any]:
        """Get cash and cash equivalents position for a company.

        Lynch says: 'The cash position. That's the floor on the stock.'
        High cash provides downside protection and flexibility.
        """
        ticker = ticker.upper()

        # Get historical cash positions
        earnings_history = self.db.get_earnings_history(ticker)
        if not earnings_history:
            return {
                "error": f"No earnings history found for {ticker}",
                "suggestion": "Cash position data requires EDGAR filings."
            }

        # Filter for entries with cash data and sort by year
        cash_history = [
            entry for entry in earnings_history
            if entry.get('cash_and_cash_equivalents') is not None
        ]

        if not cash_history:
            return {
                "error": f"No cash position data available for {ticker}",
                "suggestion": "Cash data may need to be refreshed from EDGAR filings."
            }

        cash_history.sort(key=lambda x: x['year'])

        # Get latest cash position
        latest = cash_history[-1]
        latest_cash_dollars = latest['cash_and_cash_equivalents']
        latest_cash = latest_cash_dollars / 1_000_000  # Convert to millions
        latest_year = latest['year']

        # Build historical cash data
        cash_by_year = [
            {
                "year": entry['year'],
                "cash_millions": round(entry['cash_and_cash_equivalents'] / 1_000_000, 2),
                "period": entry.get('period', 'annual')
            }
            for entry in cash_history[-10:]  # Last 10 periods
        ]

        # Get current stock info for cash per share and cash/market cap
        conn = None
        cash_per_share = None
        cash_to_market_cap_pct = None

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # Get current price and market cap
            cursor.execute("""
                SELECT m.price, m.market_cap
                FROM stock_metrics m
                WHERE m.symbol = %s
            """, (ticker,))

            metrics_row = cursor.fetchone()
            if metrics_row:
                current_price = metrics_row[0]
                market_cap = metrics_row[1]

                # Calculate cash per share using shares outstanding
                shares_outstanding = latest.get('shares_outstanding')
                if shares_outstanding and shares_outstanding > 0:
                    cash_per_share = (latest_cash_dollars / shares_outstanding)
                elif market_cap and market_cap > 0 and current_price and current_price > 0:
                    # Fallback: estimate shares from market cap / price
                    estimated_shares = market_cap / current_price
                    cash_per_share = (latest_cash_dollars / estimated_shares)

                # Calculate cash as % of market cap
                if market_cap and market_cap > 0:
                    cash_to_market_cap_pct = (latest_cash_dollars / market_cap) * 100

        except Exception as e:
            print(f"Error calculating cash metrics: {e}")
        finally:
            if conn:
                conn.close()

        # Calculate cash trend (increasing, decreasing, stable)
        if len(cash_history) >= 3:
            recent_cash_values = [entry['cash_and_cash_equivalents'] for entry in cash_history[-3:]]
            if recent_cash_values[-1] > recent_cash_values[0] * 1.1:
                cash_trend = "increasing"
            elif recent_cash_values[-1] < recent_cash_values[0] * 0.9:
                cash_trend = "decreasing"
            else:
                cash_trend = "stable"
        else:
            cash_trend = "insufficient_data"

        # Lynch-style interpretation
        interpretation_parts = [
            f"Cash Position ({latest_year}): ${latest_cash:.0f}M."
        ]

        if cash_per_share:
            interpretation_parts.append(f"Cash per share: ${cash_per_share:.2f}.")

        if cash_to_market_cap_pct:
            if cash_to_market_cap_pct > 20:
                interpretation_parts.append(f"Cash is {cash_to_market_cap_pct:.1f}% of market cap - substantial downside protection! This is Lynch's 'floor' on the stock.")
            elif cash_to_market_cap_pct > 10:
                interpretation_parts.append(f"Cash is {cash_to_market_cap_pct:.1f}% of market cap - good downside protection.")
            else:
                interpretation_parts.append(f"Cash is {cash_to_market_cap_pct:.1f}% of market cap - moderate cash position.")

        if cash_trend == "increasing":
            interpretation_parts.append("Cash position is growing - building financial strength.")
        elif cash_trend == "decreasing":
            interpretation_parts.append("Cash position is declining - monitor for financial stress or strategic investments.")

        return {
            "ticker": ticker,
            "latest_cash_millions": round(latest_cash, 2),
            "latest_year": latest_year,
            "cash_per_share": round(cash_per_share, 2) if cash_per_share else None,
            "cash_to_market_cap_pct": round(cash_to_market_cap_pct, 2) if cash_to_market_cap_pct else None,
            "cash_trend": cash_trend,
            "cash_history": cash_by_year,
            "interpretation": " ".join(interpretation_parts)
        }

    # =========================================================================
    # Portfolio Management Executor Methods
    # =========================================================================

    def _create_portfolio(self, name: str, user_id: int, initial_cash: float = 100000.0) -> Dict[str, Any]:
        """Create a new paper trading portfolio."""
        try:
            portfolio_id = self.db.create_portfolio(user_id=user_id, name=name, initial_cash=initial_cash)
            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "name": name,
                "initial_cash": initial_cash,
                "message": f"Portfolio '{name}' created successfully with ${initial_cash:,.2f}."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_my_portfolios(self, user_id: int) -> Dict[str, Any]:
        """List all portfolios for a user."""
        try:
            portfolios = self.db.get_user_portfolios(user_id)
            summaries = []
            for p in portfolios:
                summary = self.db.get_portfolio_summary(p['id'], use_live_prices=False) # fast summary
                summaries.append(summary)
            
            return {
                "success": True,
                "portfolios": summaries
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_portfolio_status(self, portfolio_id: int, user_id: int) -> Dict[str, Any]:
        """Get detailed status of a specific portfolio."""
        try:
            # Verify ownership
            portfolio = self.db.get_portfolio(portfolio_id)
            if not portfolio or portfolio['user_id'] != user_id:
                return {"success": False, "error": "Portfolio not found or unauthorized access."}
            
            summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=True)
            return {
                "success": True,
                "status": summary
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _buy_stock(self, portfolio_id: int, ticker: str, quantity: int, user_id: int, note: str = None) -> Dict[str, Any]:
        """Buy stock in a portfolio."""
        try:
            # Verify ownership
            portfolio = self.db.get_portfolio(portfolio_id)
            if not portfolio or portfolio['user_id'] != user_id:
                return {"success": False, "error": "Portfolio not found or unauthorized access."}
            
            result = portfolio_service.execute_trade(
                db=self.db,
                portfolio_id=portfolio_id,
                symbol=ticker.upper(),
                transaction_type='BUY',
                quantity=quantity,
                note=note
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _sell_stock(self, portfolio_id: int, ticker: str, quantity: int, user_id: int, note: str = None) -> Dict[str, Any]:
        """Sell stock from a portfolio."""
        try:
            # Verify ownership
            portfolio = self.db.get_portfolio(portfolio_id)
            if not portfolio or portfolio['user_id'] != user_id:
                return {"success": False, "error": "Portfolio not found or unauthorized access."}
            
            result = portfolio_service.execute_trade(
                db=self.db,
                portfolio_id=portfolio_id,
                symbol=ticker.upper(),
                transaction_type='SELL',
                quantity=quantity,
                note=note
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_peers(self, ticker: str, limit: int = 10) -> Dict[str, Any]:
        """Get peer companies in the same sector with their financial metrics."""
        ticker = ticker.upper()
        limit = min(limit or 10, 25)

        def safe_round(val, digits=2):
            if val is None:
                return None
            try:
                float_val = float(val)
                if float_val != float_val:  # NaN check
                    return None
                return round(float_val, digits)
            except (TypeError, ValueError):
                return None

        conn = None
        try:
            # Get target stock info from stocks + stock_metrics tables
            target_query = """
                SELECT s.symbol, s.company_name, s.sector,
                       m.price, m.pe_ratio, m.market_cap, m.debt_to_equity,
                       m.dividend_yield, m.forward_pe, m.forward_peg_ratio
                FROM stocks s
                LEFT JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.symbol = %s
            """
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(target_query, (ticker,))
            target_row = cursor.fetchone()

            if not target_row:
                return {"error": f"Stock {ticker} not found in database"}

            sector = target_row[2]

            if not sector:
                return {"error": f"Sector information not available for {ticker}"}

            target_market_cap = target_row[5]
            target_metrics = {
                "symbol": target_row[0],
                "company_name": target_row[1],
                "sector": sector,
                "price": safe_round(target_row[3]),
                "pe_ratio": safe_round(target_row[4]),
                "market_cap_b": safe_round(target_row[5] / 1e9, 1) if target_row[5] else None,
                "debt_to_equity": safe_round(target_row[6]),
                "dividend_yield": safe_round(target_row[7]),
                "forward_pe": safe_round(target_row[8]),
                "forward_peg": safe_round(target_row[9])
            }

            # Find peers in the same sector with valid metrics
            # Order by market cap proximity to target
            peers_query = """
                SELECT s.symbol, s.company_name,
                       m.price, m.pe_ratio, m.market_cap, m.debt_to_equity,
                       m.dividend_yield, m.forward_pe, m.forward_peg_ratio
                FROM stocks s
                JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.sector = %s
                  AND s.symbol != %s
                  AND m.market_cap IS NOT NULL
                  AND m.pe_ratio IS NOT NULL
                ORDER BY ABS(m.market_cap - COALESCE(%s, 0)) ASC
                LIMIT %s
            """
            cursor.execute(peers_query, (sector, ticker, target_market_cap, limit))
            peer_rows = cursor.fetchall()

            if not peer_rows:
                return {
                    "ticker": ticker,
                    "target": target_metrics,
                    "peers": [],
                    "message": f"No peers found in {sector} sector"
                }

            peers = []
            for row in peer_rows:
                peers.append({
                    "symbol": row[0],
                    "company_name": row[1],
                    "price": safe_round(row[2]),
                    "pe_ratio": safe_round(row[3]),
                    "market_cap_b": safe_round(row[4] / 1e9, 1) if row[4] else None,
                    "debt_to_equity": safe_round(row[5]),
                    "dividend_yield": safe_round(row[6]),
                    "forward_pe": safe_round(row[7]),
                    "forward_peg": safe_round(row[8])
                })

            return {
                "ticker": ticker,
                "sector": sector,
                "target": target_metrics,
                "peers": peers,
                "peer_count": len(peers)
            }

        except Exception as e:
            import traceback
            return {
                "error": f"Failed to get peers for {ticker}: {str(e)}",
                "details": traceback.format_exc()
            }
        finally:
            if conn:
                self.db.return_connection(conn)
    
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
        
        if not self.stock_context:
            return {"error": "News search not available: StockContext not configured"}
        
        articles = self.stock_context._get_news_articles(ticker, limit=limit)
        
        if not articles:
            return {"ticker": ticker, "articles": [], "message": "No news articles found"}
        
        return {
            "ticker": ticker,
            "articles": articles,
        }
    
    def _get_filing_section(self, ticker: str, section: str) -> Dict[str, Any]:
        """Read a section from SEC filings."""
        ticker = ticker.upper()
        
        if not self.stock_context:
            return {"error": "Filing sections not available: StockContext not configured"}
        
        # Get filing sections (returns dict keyed by section name)
        sections, selected = self.stock_context._get_filing_sections(ticker, user_query=None, max_sections=4)
        
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
    
    def _get_average_pe_ratio(self, ticker: str, period_type: str = 'annual', periods: int = None) -> Dict[str, Any]:
        """Calculate average P/E ratios over time (quarterly or annual)."""
        ticker = ticker.upper()
        
        # Set default periods based on period_type
        if periods is None:
            periods = 12 if period_type == 'quarterly' else 5
        
        # Get earnings history (quarterly or annual)
        earnings = self.db.get_earnings_history(ticker, period_type=period_type)
        
        if not earnings:
            return {
                "error": f"No {period_type} earnings history found for {ticker}",
                "suggestion": "Try using get_stock_metrics for current P/E ratio."
            }
        
        # Get price history
        price_data = self.db.get_weekly_prices(ticker)
        
        if not price_data or not price_data.get('dates'):
            return {
                "error": f"No price history found for {ticker}",
            }
        
        # Build a dict of date -> price for lookup
        price_by_date = {}
        for date_str, price in zip(price_data['dates'], price_data['prices']):
            price_by_date[date_str] = price
        
        # Calculate P/E for each period
        pe_data = []
        
        for record in earnings[:periods]:  # Limit to requested number of periods
            year = record.get('year')
            period = record.get('period')
            eps = record.get('eps')
            fiscal_end = record.get('fiscal_end')
            
            if not year or not eps or eps <= 0:
                continue
            
            # Find the appropriate price for this period
            price = None
            
            if period_type == 'annual':
                # For annual: use year-end price (December of that year)
                for date_str in price_by_date:
                    if date_str.startswith(f"{year}-12"):
                        price = price_by_date[date_str]
                        break
                # If no December price, try fiscal_end date or closest date
                if not price and fiscal_end:
                    fiscal_year = fiscal_end[:4]
                    fiscal_month = fiscal_end[5:7]
                    for date_str in price_by_date:
                        if date_str.startswith(f"{fiscal_year}-{fiscal_month}"):
                            price = price_by_date[date_str]
                            break
            else:  # quarterly
                # For quarterly: use price at quarter end
                # Q1 = March (03), Q2 = June (06), Q3 = September (09), Q4 = December (12)
                quarter_months = {'Q1': '03', 'Q2': '06', 'Q3': '09', 'Q4': '12'}
                target_month = quarter_months.get(period)
                
                if target_month:
                    for date_str in price_by_date:
                        if date_str.startswith(f"{year}-{target_month}"):
                            price = price_by_date[date_str]
                            break
                
                # Fallback to fiscal_end if available
                if not price and fiscal_end:
                    fiscal_year = fiscal_end[:4]
                    fiscal_month = fiscal_end[5:7]
                    for date_str in price_by_date:
                        if date_str.startswith(f"{fiscal_year}-{fiscal_month}"):
                            price = price_by_date[date_str]
                            break
            
            if price and eps > 0:
                pe = round(price / eps, 2)
                period_label = f"{year}" if period_type == 'annual' else f"{year} {period}"
                pe_data.append({
                    "period": period_label,
                    "year": year,
                    "quarter": period if period_type == 'quarterly' else None,
                    "eps": round(eps, 2),
                    "price": round(price, 2),
                    "pe_ratio": pe
                })
        
        if not pe_data:
            return {
                "ticker": ticker,
                "period_type": period_type,
                "pe_data": [],
                "message": f"Could not calculate P/E ratios - missing price or EPS data for {period_type} periods."
            }
        
        # Sort by year and period (most recent first)
        pe_data.sort(key=lambda x: (x['year'], x.get('quarter') or ''), reverse=True)
        
        # Calculate average P/E
        pe_values = [entry['pe_ratio'] for entry in pe_data]
        average_pe = round(sum(pe_values) / len(pe_values), 2)
        
        # Calculate min, max, and median
        min_pe = round(min(pe_values), 2)
        max_pe = round(max(pe_values), 2)
        sorted_pe = sorted(pe_values)
        median_pe = round(sorted_pe[len(sorted_pe) // 2], 2) if sorted_pe else None
        
        return {
            "ticker": ticker,
            "period_type": period_type,
            "periods_analyzed": len(pe_data),
            "average_pe": average_pe,
            "min_pe": min_pe,
            "max_pe": max_pe,
            "median_pe": median_pe,
            "pe_data": pe_data,
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
        """Analyze dividend history, trends, and FCF coverage."""
        ticker = ticker.upper()
        
        # Get current stock metrics (price, market cap for shares calculation)
        stock_metrics = self.db.get_stock_metrics(ticker)
        current_yield = stock_metrics.get('dividend_yield') if stock_metrics else None
        price = stock_metrics.get('price') if stock_metrics else None
        market_cap = stock_metrics.get('market_cap') if stock_metrics else None
        
        # Calculate shares outstanding for total dividend computation
        shares_outstanding = None
        if price and market_cap and price > 0:
            shares_outstanding = market_cap / price
        
        # Get historical dividend data
        earnings = self.db.get_earnings_history(ticker, period_type='annual')
        if not earnings:
            return {
                "error": f"No earnings history for {ticker}",
                "suggestion": "This stock may not pay dividends or data is unavailable."
            }
        
        dividend_data = []
        current_year = 2026  # Updated for current year
        
        for record in earnings:
            year = record.get('year')
            if not year or year < current_year - years:
                continue
            
            dividend = record.get('dividend_amount')
            eps = record.get('eps')
            fcf = record.get('free_cash_flow')
            
            # Calculate payout ratio vs EPS
            eps_payout_ratio = (dividend / eps * 100) if dividend and eps and eps > 0 else None
            
            # Calculate payout ratio vs FCF (using total dividends)
            fcf_payout_ratio = None
            total_dividend = None
            if dividend and shares_outstanding and fcf:
                total_dividend = dividend * shares_outstanding
                if fcf > 0:
                    fcf_payout_ratio = (total_dividend / fcf) * 100
            
            if dividend:  # Only include years with dividend data
                entry = {
                    "year": year,
                    "dividend_per_share": round(dividend, 2),
                    "eps": round(eps, 2) if eps else None,
                    "payout_ratio_vs_eps_pct": round(eps_payout_ratio, 1) if eps_payout_ratio else None,
                }
                
                # Add FCF coverage data if available
                if fcf:
                    entry["free_cash_flow"] = fcf
                    entry["free_cash_flow_formatted"] = f"${fcf/1e9:.2f}B" if abs(fcf) >= 1e9 else f"${fcf/1e6:.0f}M"
                if total_dividend:
                    entry["total_dividend_paid"] = total_dividend
                    entry["total_dividend_formatted"] = f"${total_dividend/1e9:.2f}B" if total_dividend >= 1e9 else f"${total_dividend/1e6:.0f}M"
                if fcf_payout_ratio is not None:
                    entry["dividend_to_fcf_ratio_pct"] = round(fcf_payout_ratio, 1)
                elif fcf and fcf < 0:
                    entry["dividend_to_fcf_ratio_pct"] = "N/A (Negative FCF)"
                
                dividend_data.append(entry)
        
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
        
        # Add FCF coverage summary for most recent year with positive FCF
        fcf_coverage_summary = None
        for entry in reversed(dividend_data):
            if entry.get('dividend_to_fcf_ratio_pct') and isinstance(entry['dividend_to_fcf_ratio_pct'], (int, float)):
                fcf_coverage_summary = {
                    "year": entry['year'],
                    "total_dividend_paid": entry.get('total_dividend_formatted'),
                    "free_cash_flow": entry.get('free_cash_flow_formatted'),
                    "payout_ratio_pct": entry['dividend_to_fcf_ratio_pct'],
                    "assessment": "Sustainable" if entry['dividend_to_fcf_ratio_pct'] < 70 else "High" if entry['dividend_to_fcf_ratio_pct'] < 100 else "Unsustainable (>100%)"
                }
                break
        
        return {
            "ticker": ticker,
            "current_yield_pct": round(current_yield, 2) if current_yield else None,
            "shares_outstanding": f"{shares_outstanding/1e9:.2f}B" if shares_outstanding else None,
            "years_of_data": len(dividend_data),
            "dividend_history": dividend_data,
            "dividend_growth": growth_rates,
            "fcf_coverage_summary": fcf_coverage_summary
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
        """Find stocks similar to the given ticker based on sector and market cap."""
        ticker = ticker.upper()

        def safe_round(val, digits=2):
            if val is None:
                return None
            try:
                float_val = float(val)
                if float_val != float_val:
                    return None
                return round(float_val, digits)
            except (TypeError, ValueError):
                return None

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Get reference stock info
            cursor.execute("""
                SELECT s.symbol, s.company_name, s.sector, m.market_cap, m.pe_ratio
                FROM stocks s
                LEFT JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.symbol = %s
            """, (ticker,))
            ref_row = cursor.fetchone()

            if not ref_row:
                return {"error": f"Stock {ticker} not found"}

            ref_sector = ref_row[2]
            ref_market_cap = ref_row[3]

            if not ref_sector:
                return {"error": f"Sector information not available for {ticker}"}
            if not ref_market_cap:
                return {"error": f"Market cap not available for {ticker}"}

            # Find stocks in same sector with similar market cap (0.3x - 3x range)
            cursor.execute("""
                SELECT s.symbol, s.company_name, m.market_cap, m.pe_ratio,
                       m.forward_peg_ratio, m.debt_to_equity, m.dividend_yield
                FROM stocks s
                JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.sector = %s
                  AND s.symbol != %s
                  AND m.market_cap BETWEEN %s AND %s
                  AND m.pe_ratio IS NOT NULL
                ORDER BY ABS(m.market_cap - %s) ASC
                LIMIT %s
            """, (
                ref_sector,
                ticker,
                ref_market_cap * 0.3,
                ref_market_cap * 3.0,
                ref_market_cap,
                limit
            ))

            similar_stocks = []
            for row in cursor.fetchall():
                similar_stocks.append({
                    "symbol": row[0],
                    "company_name": row[1],
                    "market_cap_b": safe_round(row[2] / 1e9, 1) if row[2] else None,
                    "pe_ratio": safe_round(row[3]),
                    "peg_ratio": safe_round(row[4]),
                    "debt_to_equity": safe_round(row[5]),
                    "dividend_yield": safe_round(row[6]),
                })

            return {
                "reference_ticker": ticker,
                "reference_sector": ref_sector,
                "reference_market_cap_b": safe_round(ref_market_cap / 1e9, 1),
                "similar_stocks": similar_stocks,
                "count": len(similar_stocks)
            }
        except Exception as e:
            import traceback
            return {
                "error": f"Failed to find similar stocks for {ticker}: {str(e)}",
                "details": traceback.format_exc()
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

        def safe_round(val, digits=2):
            """Safely round a value, handling None, NaN, and Decimal types."""
            if val is None:
                return None
            try:
                float_val = float(val)
                if float_val != float_val:  # NaN check
                    return None
                return round(float_val, digits)
            except (TypeError, ValueError):
                return None

        conn = None
        try:
            # Get stock details from stocks + stock_metrics tables
            stock_query = """
                SELECT s.symbol, s.company_name, s.sector,
                       m.pe_ratio, m.forward_peg_ratio, m.dividend_yield,
                       m.debt_to_equity, m.forward_pe, m.market_cap
                FROM stocks s
                LEFT JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.symbol = %s
            """
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(stock_query, (ticker,))
            stock_row = cursor.fetchone()

            if not stock_row:
                return {"error": f"Stock {ticker} not found in database"}

            company_name = stock_row[1]
            sector = stock_row[2]

            if not sector:
                return {"error": f"Sector information not available for {ticker}"}

            stock_metrics = {
                "pe_ratio": safe_round(stock_row[3]),
                "peg_ratio": safe_round(stock_row[4]),
                "dividend_yield": safe_round(stock_row[5]),
                "debt_to_equity": safe_round(stock_row[6]),
                "forward_pe": safe_round(stock_row[7]),
                "market_cap_b": safe_round(stock_row[8] / 1e9, 1) if stock_row[8] else None
            }

            # Calculate sector statistics from stock_metrics
            sector_stats_query = """
                SELECT
                    COUNT(*) as stock_count,
                    AVG(m.pe_ratio) FILTER (WHERE m.pe_ratio > 0 AND m.pe_ratio < 200) as avg_pe,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.pe_ratio)
                        FILTER (WHERE m.pe_ratio > 0 AND m.pe_ratio < 200) as median_pe,
                    AVG(m.forward_peg_ratio) FILTER (WHERE m.forward_peg_ratio > 0 AND m.forward_peg_ratio < 10) as avg_peg,
                    AVG(m.dividend_yield) FILTER (WHERE m.dividend_yield IS NOT NULL) as avg_yield,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.dividend_yield)
                        FILTER (WHERE m.dividend_yield IS NOT NULL) as median_yield,
                    AVG(m.debt_to_equity) FILTER (WHERE m.debt_to_equity >= 0 AND m.debt_to_equity < 50) as avg_debt_equity,
                    AVG(m.forward_pe) FILTER (WHERE m.forward_pe > 0 AND m.forward_pe < 200) as avg_forward_pe
                FROM stocks s
                JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.sector = %s AND s.symbol != %s
            """

            cursor.execute(sector_stats_query, (sector, ticker))
            stats = cursor.fetchone()

            if not stats or stats[0] < 3:
                return {
                    "ticker": ticker,
                    "company_name": company_name,
                    "sector": sector,
                    "peer_count": stats[0] if stats else 0,
                    "message": f"Only {stats[0] if stats else 0} peers found in {sector} sector. Need at least 3 for meaningful comparison.",
                    "stock_metrics": stock_metrics
                }

            # Calculate percentage differences safely
            pe_diff = None
            if stock_metrics["pe_ratio"] and stats[1]:
                try:
                    pe_diff = round((float(stock_metrics["pe_ratio"]) - float(stats[1])) / float(stats[1]) * 100, 1)
                except (TypeError, ValueError, ZeroDivisionError):
                    pe_diff = None

            return {
                "ticker": ticker,
                "company_name": company_name,
                "sector": sector,
                "peer_count": stats[0],
                "comparison": {
                    "pe_ratio": {
                        "stock": stock_metrics["pe_ratio"],
                        "sector_avg": safe_round(stats[1]),
                        "sector_median": safe_round(stats[2]),
                        "diff_percent": pe_diff
                    },
                    "peg_ratio": {
                        "stock": stock_metrics["peg_ratio"],
                        "sector_avg": safe_round(stats[3])
                    },
                    "dividend_yield": {
                        "stock": stock_metrics["dividend_yield"],
                        "sector_avg": safe_round(stats[4]),
                        "sector_median": safe_round(stats[5])
                    },
                    "debt_to_equity": {
                        "stock": stock_metrics["debt_to_equity"],
                        "sector_avg": safe_round(stats[6])
                    },
                    "forward_pe": {
                        "stock": stock_metrics["forward_pe"],
                        "sector_avg": safe_round(stats[7])
                    }
                }
            }

        except Exception as e:
            import traceback
            return {
                "error": f"Failed to get sector comparison for {ticker}: {str(e)}",
                "details": traceback.format_exc()
            }
        finally:
            if conn:
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
        peg_min: float = None,
        debt_to_equity_max: float = None,
        profit_margin_min: float = None,
        target_upside_min: float = None,
        has_transcript: bool = None,
        has_fcf: bool = None,
        has_recent_insider_activity: bool = None,
        sort_by: str = "market_cap",
        sort_order: str = "desc",
        top_n_by_market_cap: int = None,
        limit: int = 20,
        exclude_tickers: list = None
    ) -> Dict[str, Any]:
        """Screen stocks based on various criteria."""

        def safe_round(val, digits=2):
            if val is None:
                return None
            try:
                float_val = float(val)
                if float_val != float_val:
                    return None
                return round(float_val, digits)
            except (TypeError, ValueError):
                return None

        # Cap limit at 50
        limit = min(limit or 20, 50)

        # Build dynamic WHERE clause
        conditions = []
        params = []

        # Track if we need growth CTE
        needs_growth_cte = (revenue_growth_min is not None or eps_growth_min is not None or
                           sort_by in ('revenue_growth', 'eps_growth'))

        # Exclude tickers
        if exclude_tickers:
            excluded = [t.upper() for t in exclude_tickers if isinstance(t, str)]
            if excluded:
                placeholders = ', '.join(['%s'] * len(excluded))
                conditions.append(f"s.symbol NOT IN ({placeholders})")
                params.extend(excluded)

        # P/E filters
        if pe_max is not None:
            conditions.append("m.pe_ratio <= %s")
            params.append(pe_max)
        if pe_min is not None:
            conditions.append("m.pe_ratio >= %s")
            params.append(pe_min)

        # Dividend yield filter
        if dividend_yield_min is not None:
            conditions.append("m.dividend_yield >= %s")
            params.append(dividend_yield_min)

        # Market cap filters (convert billions to actual value)
        if market_cap_min is not None:
            conditions.append("m.market_cap >= %s")
            params.append(market_cap_min * 1_000_000_000)
        if market_cap_max is not None:
            conditions.append("m.market_cap <= %s")
            params.append(market_cap_max * 1_000_000_000)

        # Growth filters (calculated from earnings_history)
        if revenue_growth_min is not None:
            conditions.append("g.revenue_growth >= %s")
            params.append(revenue_growth_min)
        if eps_growth_min is not None:
            conditions.append("g.eps_growth >= %s")
            params.append(eps_growth_min)

        # Sector filter with aliasing for common synonyms
        if sector:
            sector_lower = sector.lower().strip()
            if 'financ' in sector_lower:
                conditions.append("(LOWER(s.sector) = 'finance' OR LOWER(s.sector) = 'financial services')")
            else:
                conditions.append("LOWER(s.sector) LIKE LOWER(%s)")
                params.append(f"%{sector}%")

        # PEG filter (using forward_peg_ratio from stock_metrics)
        if peg_max is not None:
            conditions.append("m.forward_peg_ratio <= %s")
            params.append(peg_max)
        if peg_min is not None:
            conditions.append("m.forward_peg_ratio >= %s")
            params.append(peg_min)

        # Debt to equity filter
        if debt_to_equity_max is not None:
            conditions.append("m.debt_to_equity <= %s")
            params.append(debt_to_equity_max)

        # Transcript filter
        if has_transcript:
            conditions.append("""EXISTS (
                SELECT 1 FROM earnings_transcripts et
                WHERE et.symbol = s.symbol
                AND et.transcript_text IS NOT NULL
                AND LENGTH(et.transcript_text) > 100
            )""")

        # FCF filter
        if has_fcf:
            conditions.append("""EXISTS (
                SELECT 1 FROM earnings_history eh
                WHERE eh.symbol = s.symbol
                AND eh.free_cash_flow IS NOT NULL
                AND eh.free_cash_flow > 0
            )""")

        # Insider Activity Filter
        if has_recent_insider_activity:
            conditions.append("""EXISTS (
                SELECT 1 FROM insider_trades it
                WHERE it.symbol = s.symbol
                AND (it.transaction_type = 'Buy' OR it.transaction_type = 'Purchase')
                AND it.transaction_date >= (CURRENT_DATE - INTERVAL '90 days')
            )""")

        # Profit Margin Filter
        join_clause = ""
        if profit_margin_min is not None:
            join_clause = """
                JOIN (
                    SELECT DISTINCT ON (symbol) symbol, net_income, revenue
                    FROM earnings_history
                    WHERE period='annual' AND revenue > 0
                    ORDER BY symbol, year DESC
                ) eh ON s.symbol = eh.symbol
            """
            conditions.append("(eh.net_income::float / eh.revenue::float * 100) >= %s")
            params.append(profit_margin_min)

        # Target Upside Filter
        if target_upside_min is not None:
            conditions.append("""
                m.price > 0 
                AND m.price_target_mean IS NOT NULL 
                AND ((m.price_target_mean - m.price) / m.price * 100) >= %s
            """)
            params.append(target_upside_min)

        # Always require valid P/E and market cap
        conditions.append("m.pe_ratio IS NOT NULL")
        conditions.append("m.pe_ratio > 0")
        conditions.append("m.market_cap > 0")

        # Ensure company has quarterly earnings history
        conditions.append("""EXISTS (
            SELECT 1 FROM earnings_history eh
            WHERE eh.symbol = s.symbol
            AND eh.period != 'annual'
            AND eh.net_income IS NOT NULL
        )""")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Build ORDER BY clause
        sort_columns = {
            "pe": "m.pe_ratio",
            "dividend_yield": "m.dividend_yield",
            "market_cap": "m.market_cap",
            "debt_to_equity": "m.debt_to_equity",
            "peg": "m.forward_peg_ratio",
            "revenue_growth": "g.revenue_growth",
            "eps_growth": "g.eps_growth",
            "target_upside": "((m.price_target_mean - m.price) / m.price)",
            "gross_margin": "m.gross_margin",
        }
        order_column = sort_columns.get(sort_by, "m.market_cap")
        order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"
        null_handling = "NULLS LAST" if order_dir == "DESC" else "NULLS FIRST"

        # Growth CTE calculates 5-year linear growth rates from earnings_history
        # Formula: ((end - start) / |start|) / years * 100
        # Uses last 5 years of data to match screener behavior
        growth_cte = """
            ranked_earnings AS (
                SELECT symbol, year, net_income, revenue,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY year DESC) as rn,
                       COUNT(*) OVER (PARTITION BY symbol) as total_years
                FROM earnings_history
                WHERE period = 'annual'
                  AND net_income IS NOT NULL AND revenue IS NOT NULL
            ),
            growth_rates AS (
                SELECT
                    r1.symbol,
                    CASE
                        WHEN r5.revenue IS NOT NULL AND r5.revenue != 0 AND r1.revenue IS NOT NULL
                        THEN ((r1.revenue - r5.revenue) / ABS(r5.revenue)) / LEAST(4, r5.rn - 1) * 100
                        ELSE NULL
                    END as revenue_growth,
                    CASE
                        WHEN r5.net_income IS NOT NULL AND r5.net_income != 0 AND r1.net_income IS NOT NULL
                        THEN ((r1.net_income - r5.net_income) / ABS(r5.net_income)) / LEAST(4, r5.rn - 1) * 100
                        ELSE NULL
                    END as eps_growth
                FROM ranked_earnings r1
                JOIN ranked_earnings r5 ON r1.symbol = r5.symbol AND r5.rn = LEAST(5, r5.total_years)
                WHERE r1.rn = 1 AND r5.rn >= 3
            )
        """

        # Build join clause for growth if needed
        growth_join = "LEFT JOIN growth_rates g ON s.symbol = g.symbol" if needs_growth_cte else ""

        # Build query using stocks + stock_metrics + optional growth
        if top_n_by_market_cap:
            query = f"""
                WITH {growth_cte if needs_growth_cte else ''}
                {',' if needs_growth_cte else 'WITH'} universe AS (
                    SELECT s.symbol, s.company_name, s.sector,
                           m.market_cap, m.pe_ratio, m.forward_peg_ratio,
                           m.dividend_yield, m.debt_to_equity,
                           m.price, m.price_target_mean, m.gross_margin,
                           {'g.revenue_growth, g.eps_growth' if needs_growth_cte else 'NULL as revenue_growth, NULL as eps_growth'}
                    FROM stocks s
                    JOIN stock_metrics m ON s.symbol = m.symbol
                    {growth_join}
                    {join_clause}
                    WHERE {where_clause}
                    ORDER BY m.market_cap DESC NULLS LAST
                    LIMIT {top_n_by_market_cap}
                )
                SELECT * FROM universe
                ORDER BY {order_column.replace('m.', '').replace('g.', '')} {order_dir} {null_handling}
                LIMIT %s
            """
        else:
            if needs_growth_cte:
                query = f"""
                    WITH {growth_cte}
                    SELECT s.symbol, s.company_name, s.sector,
                           m.market_cap, m.pe_ratio, m.forward_peg_ratio,
                           m.dividend_yield, m.debt_to_equity,
                           m.price, m.price_target_mean, m.gross_margin,
                           g.revenue_growth, g.eps_growth
                    FROM stocks s
                    JOIN stock_metrics m ON s.symbol = m.symbol
                    {growth_join}
                    {join_clause}
                    WHERE {where_clause}
                    ORDER BY {order_column} {order_dir} {null_handling}
                    LIMIT %s
                """
            else:
                query = f"""
                    SELECT s.symbol, s.company_name, s.sector,
                           m.market_cap, m.pe_ratio, m.forward_peg_ratio,
                           m.dividend_yield, m.debt_to_equity,
                           m.price, m.price_target_mean, m.gross_margin,
                           NULL as revenue_growth, NULL as eps_growth
                    FROM stocks s
                    JOIN stock_metrics m ON s.symbol = m.symbol
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
                    "pe_ratio": safe_round(row[4], 1),
                    "peg_ratio": safe_round(row[5], 2),
                    "dividend_yield": safe_round(row[6], 2),
                    "debt_to_equity": safe_round(row[7], 2),
                    "gross_margin": safe_round(row[10], 1),
                    "revenue_growth": safe_round(row[11], 1),
                    "eps_growth": safe_round(row[12], 1),
                    "target_upside": safe_round((row[9] - row[8]) / row[8] * 100, 1) if row[8] and row[8] > 0 and row[9] else None,
                    "current_price": safe_round(row[8], 2),
                    "target_mean": safe_round(row[9], 2),
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
            if revenue_growth_min is not None:
                filters_applied.append(f"Revenue Growth >= {revenue_growth_min}%")
            if eps_growth_min is not None:
                filters_applied.append(f"EPS Growth >= {eps_growth_min}%")
            if sector:
                filters_applied.append(f"Sector: {sector}")
            if peg_max is not None:
                filters_applied.append(f"PEG <= {peg_max}")
            if target_upside_min is not None:
                filters_applied.append(f"Target Upside >= {target_upside_min}%")

            return {
                "filters_applied": filters_applied if filters_applied else ["None (showing all stocks)"],
                "sort": f"{sort_by} {sort_order}",
                "count": len(results),
                "stocks": results
            }
        except Exception as e:
            import traceback
            return {
                "error": f"Failed to screen stocks: {str(e)}",
                "details": traceback.format_exc()
            }
        finally:
            self.db.return_connection(conn)

    def _manage_alerts(self, action: str, ticker: str = None, condition_description: str = None,
                      condition_type: str = None, threshold: float = None, operator: str = None, 
                      alert_id: int = None, user_id: int = None,
                      action_type: str = None, action_quantity: int = None,
                      portfolio_name: str = None, action_note: str = None) -> Dict[str, Any]:
        """
        Manage user alerts: create, list, or delete.
        
        Supports two modes:
        1. Flexible natural language conditions (recommended): Use condition_description parameter
        2. Legacy hardcoded conditions: Use condition_type, threshold, operator parameters
        
        Args:
            action: Action to perform ('create', 'list', or 'delete')
            ticker: Stock symbol (for create)
            condition_description: Natural language description of alert condition (e.g., "notify me when AAPL drops below $145")
            condition_type: Legacy condition type ('price', 'pe_ratio')
            threshold: Legacy threshold value
            operator: Legacy operator ('above' or 'below')
            alert_id: Alert ID (for delete)
            user_id: User ID
        """
        if not user_id:
            return {"error": "Authentication required. Cannot manage alerts without a valid user session."}
            
        if action == "create":
            if not ticker:
                return {"error": "Missing required parameter 'ticker' for creating an alert."}
            
            # Helper: Resolve portfolio if trading action requested
            portfolio_id = None
            action_payload = None
            
            if action_type:
                if not action_quantity or action_quantity <= 0:
                    return {"error": "Trading action requires a positive 'action_quantity'."}
                if not portfolio_name:
                    return {"error": "Trading action requires 'portfolio_name'."}
                
                portfolio = self.db.get_portfolio_by_name(user_id, portfolio_name)
                if not portfolio:
                    return {"error": f"Portfolio '{portfolio_name}' not found."}
                
                portfolio_id = portfolio['id']
                action_payload = {"quantity": action_quantity}
            
            ticker = ticker.upper()
            
            # Prefer condition_description (flexible LLM-based alerts)
            if condition_description:
                try:
                    # Create flexible LLM-based alert
                    alert_id = self.db.create_alert(
                        user_id=user_id,
                        symbol=ticker,
                        condition_type='custom',  # Mark as LLM-evaluated
                        condition_params={},  # Empty params for custom alerts
                        condition_description=condition_description,
                        action_type=action_type,
                        action_payload=action_payload,
                        portfolio_id=portfolio_id,
                        action_note=action_note
                    )
                    return {
                        "message": f"Successfully created alert for {ticker}.",
                        "alert_details": {
                            "id": alert_id,
                            "ticker": ticker,
                            "condition": condition_description
                        }
                    }
                except Exception as e:
                    return {"error": f"Failed to create alert: {str(e)}"}
            
            # Fallback to legacy hardcoded alerts
            elif condition_type and threshold is not None and operator:
                condition_params = {
                    "threshold": threshold,
                    "operator": operator
                }
                
                try:
                    alert_id = self.db.create_alert(
                        user_id=user_id,
                        symbol=ticker,
                        condition_type=condition_type,
                        condition_params=condition_params
                    )
                    return {
                        "message": f"Successfully created alert for {ticker}.",
                        "alert_details": {
                            "id": alert_id,
                            "ticker": ticker,
                            "condition": f"{condition_type} {operator} {threshold}"
                        }
                    }
                except Exception as e:
                    return {"error": f"Failed to create alert: {str(e)}"}
            else:
                return {"error": "Must provide either 'condition_description' for flexible alerts or all of (condition_type, threshold, operator) for legacy alerts."}
            
        elif action == "list":
            try:
                alerts = self.db.get_alerts(user_id)
                if not alerts:
                    return {"message": "You have no active alerts."}
                
                # Format for display
                formatted_alerts = []
                for a in alerts:
                    # Prefer condition_description if available
                    if a.get('condition_description'):
                        condition_str = a['condition_description']
                    else:
                        # Fallback to legacy format
                        params = a['condition_params']
                        condition_str = f"{a['condition_type']} {params.get('operator')} {params.get('threshold')}"
                    
                    formatted_alerts.append({
                        "id": a['id'],
                        "symbol": a['symbol'],
                        "condition": condition_str,
                        "status": a['status'],
                        "created_at": a['created_at'].strftime('%Y-%m-%d')
                    })
                    
                return {"alerts": formatted_alerts}
            except Exception as e:
                return {"error": f"Failed to list alerts: {str(e)}"}
                
        elif action == "delete":
            if not alert_id:
                return {"error": "Missing required parameter 'alert_id' for delete action."}
                
            try:
                success = self.db.delete_alert(alert_id, user_id)
                if success:
                    return {"message": f"Successfully deleted alert {alert_id}."}
                else:
                    return {"error": f"Alert {alert_id} not found or could not be deleted."}
            except Exception as e:
                return {"error": f"Failed to delete alert: {str(e)}"}

        else:
            return {"error": f"Unknown action: {action}"}

    # =========================================================================
    # FRED Macroeconomic Data Tools
    # =========================================================================

    def _get_fred_series(self, series_id: str, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """Get historical observations for a FRED economic data series."""
        fred = get_fred_service()
        if not fred.is_available():
            return {"error": "FRED API key not configured"}

        result = fred.get_series(series_id, start_date=start_date, end_date=end_date)

        if 'error' in result:
            return result

        # Limit observations for chat context (last 24 data points)
        observations = result.get('observations', [])
        if len(observations) > 24:
            observations = observations[-24:]

        return {
            "series_id": result['series_id'],
            "name": result['name'],
            "frequency": result['frequency'],
            "units": result['units'],
            "description": result['description'],
            "latest_value": result['latest']['value'] if result['latest'] else None,
            "latest_date": result['latest']['date'] if result['latest'] else None,
            "observations": observations,
            "observation_count": len(observations),
            "total_available": result['observation_count']
        }

    def _get_economic_indicators(self) -> Dict[str, Any]:
        """Get current values of key macroeconomic indicators."""
        fred = get_fred_service()
        if not fred.is_available():
            return {"error": "FRED API key not configured"}

        result = fred.get_economic_summary()

        if 'error' in result:
            return result

        # Format for easy reading by the LLM
        indicators = result.get('indicators', {})
        formatted = {}
        for series_id, data in indicators.items():
            formatted[data['name']] = {
                "value": data['value'],
                "units": data['units'],
                "date": data['date'],
                "change": data.get('change'),
                "series_id": series_id
            }

        return {
            "indicators": formatted,
            "fetched_at": result.get('fetched_at'),
            "available_series": list(SUPPORTED_SERIES.keys())
        }

    def _get_analyst_sentiment(self, ticker: str) -> Dict[str, Any]:
        """Get comprehensive analyst sentiment data including trends, revisions, and recommendation history."""
        ticker = ticker.upper()
        
        # Get all sentiment data from database
        eps_trends = self.db.get_eps_trends(ticker)
        eps_revisions = self.db.get_eps_revisions(ticker)
        recommendations = self.db.get_analyst_recommendations(ticker)
        growth = self.db.get_growth_estimates(ticker)
        metrics = self.db.get_stock_metrics(ticker)
        
        if not eps_trends and not eps_revisions and not recommendations and not growth:
            return {"error": f"No analyst sentiment data found for {ticker}"}
        
        # Calculate trend direction for key periods
        trend_summary = {}
        for period in ['0q', '+1q', '0y', '+1y']:
            if period in eps_trends:
                trend = eps_trends[period]
                current = trend.get('current')
                ago_30 = trend.get('30_days_ago')
                if current and ago_30:
                    change_pct = round(((current - ago_30) / abs(ago_30)) * 100, 1)
                    trend_summary[period] = {
                        "current_estimate": round(current, 2),
                        "30_days_ago": round(ago_30, 2),
                        "change_pct": change_pct,
                        "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
                    }
        
        # Calculate revision momentum
        revision_summary = {}
        for period in ['0q', '+1q', '0y', '+1y']:
            if period in eps_revisions:
                rev = eps_revisions[period]
                up = rev.get('up_30d') or 0
                down = rev.get('down_30d') or 0
                net = up - down
                if up > 0 or down > 0:
                    revision_summary[period] = {
                        "up_revisions": up,
                        "down_revisions": down,
                        "net": net,
                        "sentiment": "bullish" if net > 0 else "bearish" if net < 0 else "neutral"
                    }
        
        # Format recommendation history (last 3 months)
        rec_history = []
        for rec in recommendations[:3]:
            total = (rec.get('strong_buy') or 0) + (rec.get('buy') or 0) + (rec.get('hold') or 0) + (rec.get('sell') or 0) + (rec.get('strong_sell') or 0)
            if total > 0:
                bullish = (rec.get('strong_buy') or 0) + (rec.get('buy') or 0)
                bearish = (rec.get('sell') or 0) + (rec.get('strong_sell') or 0)
                rec_history.append({
                    "period": rec.get('period'),
                    "strong_buy": rec.get('strong_buy'),
                    "buy": rec.get('buy'),
                    "hold": rec.get('hold'),
                    "sell": rec.get('sell'),
                    "strong_sell": rec.get('strong_sell'),
                    "bullish_pct": round((bullish / total) * 100, 1),
                    "bearish_pct": round((bearish / total) * 100, 1)
                })
        
        return {
            "ticker": ticker,
            "recommendation_key": metrics.get('recommendation_key') if metrics else None,
            "analyst_count": metrics.get('analyst_count') if metrics else None,
            "eps_trends": trend_summary,
            "revision_momentum": revision_summary,
            "recommendation_history": rec_history,
            "growth_estimates": growth
        }
