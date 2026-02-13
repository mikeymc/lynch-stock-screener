# ABOUTME: Defines atomic tools for the Smart Chat Agent using Gemini Native format
# ABOUTME: Contains all FunctionDeclaration objects, TOOL_DECLARATIONS list, and AGENT_TOOLS Tool object

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
            "pe_max": Schema(type=Type.NUMBER, description="Maximum P/E ratio (e.g., 15 for value stocks). For Forward P/E search, use forward_pe_max instead."),
            "pe_min": Schema(type=Type.NUMBER, description="Minimum P/E ratio (e.g., 5 to exclude distressed stocks)"),
            "forward_pe_max": Schema(type=Type.NUMBER, description="Maximum Forward P/E ratio (e.g., 15). Use this for 'cheapest by forward P/E'."),
            "forward_pe_min": Schema(type=Type.NUMBER, description="Minimum Forward P/E ratio."),
            "dividend_yield_min": Schema(type=Type.NUMBER, description="Minimum dividend yield percentage (e.g., 3.0 for income stocks)"),
            "market_cap_min": Schema(type=Type.NUMBER, description="Minimum market cap in billions (e.g., 10 for large caps)"),
            "market_cap_max": Schema(type=Type.NUMBER, description="Maximum market cap in billions (e.g., 2 for small caps)"),
            "revenue_growth_min": Schema(type=Type.NUMBER, description="Minimum annual revenue growth percentage (e.g., 10 for 10% YoY growth)"),
            "eps_growth_min": Schema(type=Type.NUMBER, description="Minimum annual EPS/earnings growth percentage (e.g., 15 for 15% YoY growth)"),
            "short_interest_min": Schema(type=Type.NUMBER, description="Minimum Short Interest as % of Float (e.g., 10 for highly shorted stocks). Use with sort_by='short_percent_float'."),
            "analyst_rating_min": Schema(type=Type.NUMBER, description="Minimum Analyst Rating Score (1.0=Strong Buy, 5.0=Sell). Note: Higher score is WORSE. Use sort_by='analyst_rating_score' asc for best rated. Filter: rating <= X to get better stocks (e.g. <= 2.0)."),
            "analyst_upside_min": Schema(type=Type.NUMBER, description="Minimum Analyst Target Upside % (e.g. 20 for 20% upside)."),
            "revisions_up_min": Schema(type=Type.INTEGER, description="Minimum number of Upward EPS revisions in the last 30 days."),
            "revisions_down_min": Schema(type=Type.INTEGER, description="Minimum number of Downward EPS revisions in the last 30 days."),
            "sector": Schema(type=Type.STRING, description="Filter by sector. Valid values: 'Technology', 'Healthcare', 'Finance', 'Financial Services', 'Consumer Cyclical', 'Consumer Defensive', 'Energy', 'Industrials', 'Basic Materials', 'Real Estate', 'Utilities', 'Communication Services'"),
            "peg_max": Schema(type=Type.NUMBER, description="Maximum PEG ratio (P/E divided by growth rate)"),
            "peg_min": Schema(type=Type.NUMBER, description="Minimum PEG ratio (e.g., 2.0 to find potentially overvalued stocks)"),
            "debt_to_equity_max": Schema(type=Type.NUMBER, description="Maximum debt-to-equity ratio"),
            "profit_margin_min": Schema(type=Type.NUMBER, description="Minimum Net Profit Margin percentage (e.g., 20.0 for high margin businesses)"),
            "target_upside_min": Schema(type=Type.NUMBER, description="Minimum analyst target upside percentage (e.g. 20 for 20% upside based on mean price target)"),
            "has_transcript": Schema(type=Type.BOOLEAN, description="If true, only return stocks that have an earnings call transcript available"),
            "has_fcf": Schema(type=Type.BOOLEAN, description="If true, only return stocks that have Free Cash Flow data available (useful for dividend coverage analysis)"),
            "has_recent_insider_activity": Schema(type=Type.BOOLEAN, description="If true, only return stocks with insider BUY transactions in the last 90 days"),
            "sort_by": Schema(type=Type.STRING, description="Sort results by: 'pe', 'forward_pe', 'dividend_yield', 'market_cap', 'revenue_growth', 'eps_growth', 'peg', 'debt_to_equity', 'gross_margin', 'target_upside', 'short_percent_float', 'analyst_rating_score', 'revisions_up', 'revisions_down' (default: 'market_cap')"),
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


get_strategy_templates_decl = FunctionDeclaration(
    name="get_strategy_templates",
    description="""Get available strategy templates that users can use as starting points.
    Each template includes pre-configured filters for different investment approaches like
    value investing, growth at reasonable price, dividend stocks, etc. Use this to help
    users discover proven strategy patterns.""",
    parameters=Schema(
        type=Type.OBJECT,
        properties={},
    ),
)


create_strategy_decl = FunctionDeclaration(
    name="create_strategy",
    description="""Create a new autonomous investment strategy for the user.

    The strategy will automatically screen stocks, score them using Lynch and Buffett criteria,
    and optionally execute trades in a paper trading portfolio.

    You can create a strategy by:
    1. Using a template (get_strategy_templates first to see options)
    2. Custom filters specified by the user
    3. A mix of template + custom modifications

    The strategy can create a new portfolio or use an existing one.""",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "name": Schema(type=Type.STRING, description="Name for the strategy (e.g., 'My GARP Strategy')"),
            "template_id": Schema(type=Type.STRING, description="Optional: ID of template to use as base (e.g., 'growth_at_reasonable_price')"),
            "filters": Schema(
                type=Type.ARRAY,
                items=Schema(type=Type.OBJECT),
                description="Optional: Custom filters array. Each filter has field, operator, value."
            ),
            "portfolio_id": Schema(type=Type.STRING, description="Portfolio ID or 'new' to create one. Default: 'new'"),
            "portfolio_name": Schema(type=Type.STRING, description="Name for new portfolio (only if portfolio_id='new')"),
            "initial_cash": Schema(type=Type.NUMBER, description="Initial cash for new portfolio (default: 100000)"),
            "enable_now": Schema(type=Type.BOOLEAN, description="Whether to enable the strategy immediately (default: false)"),
            "consensus_mode": Schema(
                type=Type.STRING,
                description="How Lynch and Buffett must agree: 'both_agree' (both must approve), 'weighted_confidence' (weighted average), 'veto_power' (either can block). Default: 'both_agree'"
            ),
            "consensus_threshold": Schema(type=Type.NUMBER, description="Minimum score (0-100) for a consensus 'BUY'. Default: 70.0"),
            "veto_score_threshold": Schema(type=Type.NUMBER, description="Score below which a character triggers an automatic VETO. Default: 30.0"),
            "position_sizing_method": Schema(
                type=Type.STRING,
                description="How to size positions: 'equal_weight' (equal allocation), 'conviction_weighted' (scale by confidence), 'fixed_pct' (fixed %), 'kelly_criterion' (Kelly formula). Default: 'equal_weight'"
            ),
            "max_position_pct": Schema(type=Type.NUMBER, description="Maximum % of portfolio per position (e.g., 10.0 for 10%). Default: 10.0"),
            "fixed_position_pct": Schema(type=Type.NUMBER, description="Fixed % of portfolio for each position (if method is 'fixed_pct')"),
            "max_positions": Schema(type=Type.INTEGER, description="Maximum number of holdings in the portfolio. Default: 50"),
            "profit_target_pct": Schema(type=Type.NUMBER, description="Optional: Sell when position gains this % (e.g., 50 for +50%)"),
            "stop_loss_pct": Schema(type=Type.NUMBER, description="Optional: Sell when position loses this % (e.g., -20 for -20%)"),
            "min_position_value": Schema(type=Type.NUMBER, description="Minimum dollar amount for a position. Trades below this value are skipped. Default: 100.0"),
            "addition_lynch_min": Schema(type=Type.NUMBER, description="Minimum Lynch score for adding to existing positions (default: base+10)"),
            "addition_buffett_min": Schema(type=Type.NUMBER, description="Minimum Buffett score for adding to existing positions (default: base+10)"),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["name"],
    ),
)


# =============================================================================
# Strategy Management Tools
# =============================================================================

get_my_strategies_decl = FunctionDeclaration(
    name="get_my_strategies",
    description="List all of the user's investment strategies with their status (enabled/disabled), alpha vs SPY, and last run date/status. Use this to give a quick overview of what strategies exist before diving into details.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=[],
    ),
)

get_strategy_decl = FunctionDeclaration(
    name="get_strategy",
    description="Get the full configuration of a specific strategy including its screening filters, consensus mode, position sizing rules, exit conditions, and schedule. Use this when the user asks how a strategy works or wants to review its settings.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "strategy_id": Schema(type=Type.INTEGER, description="ID of the strategy to retrieve"),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["strategy_id"],
    ),
)

update_strategy_decl = FunctionDeclaration(
    name="update_strategy",
    description="""Modify an existing strategy conversationally. You can change any combination of fields.

    Examples:
    - "disable strategy 3" → enabled=false
    - "raise the stop loss to 25%" → stop_loss_pct=-25
    - "switch to conviction-weighted sizing" → position_sizing_method='conviction_weighted'
    - "add a filter for P/E under 20" → pass updated filters array

    position_sizing and exit_conditions are merged (unmentioned fields preserved).
    filters fully replaces the existing filter list.""",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "strategy_id": Schema(type=Type.INTEGER, description="ID of the strategy to update"),
            "name": Schema(type=Type.STRING, description="New name for the strategy"),
            "description": Schema(type=Type.STRING, description="New description"),
            "enabled": Schema(type=Type.BOOLEAN, description="Enable (true) or disable (false) the strategy"),
            "consensus_mode": Schema(
                type=Type.STRING,
                description="How Lynch and Buffett must agree: 'both_agree', 'weighted_confidence', or 'veto_power'",
                enum=["both_agree", "weighted_confidence", "veto_power"],
            ),
            "consensus_threshold": Schema(type=Type.NUMBER, description="Minimum score for a consensus 'BUY' (0-100)"),
            "veto_score_threshold": Schema(type=Type.NUMBER, description="Score below which a character triggers an automatic VETO (0-100)"),
            "position_sizing_method": Schema(
                type=Type.STRING,
                description="Position sizing approach: 'equal_weight', 'conviction_weighted', 'fixed_pct', or 'kelly_criterion'",
                enum=["equal_weight", "conviction_weighted", "fixed_pct", "kelly_criterion"],
            ),
            "max_position_pct": Schema(type=Type.NUMBER, description="Maximum % of portfolio per position (e.g., 10.0 for 10%)"),
            "max_positions": Schema(type=Type.INTEGER, description="Maximum number of holdings in the portfolio"),
            "profit_target_pct": Schema(type=Type.NUMBER, description="Sell when position gains this % (e.g., 50 for +50%)"),
            "stop_loss_pct": Schema(type=Type.NUMBER, description="Sell when position loses this % (e.g., -20 for -20%)"),
            "min_position_value": Schema(type=Type.NUMBER, description="Minimum dollar amount for a position. Trades below this value are skipped."),
            "addition_lynch_min": Schema(type=Type.NUMBER, description="Minimum Lynch score for adding to existing positions"),
            "addition_buffett_min": Schema(type=Type.NUMBER, description="Minimum Buffett score for adding to existing positions"),
            "filters": Schema(
                type=Type.ARRAY,
                items=Schema(type=Type.OBJECT),
                description="Replacement filter list. Each filter has 'field', 'operator', and 'value'.",
            ),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["strategy_id"],
    ),
)

get_strategy_activity_decl = FunctionDeclaration(
    name="get_strategy_activity",
    description="Get recent run history for a strategy including trade counts, stocks screened, run status, and performance vs SPY. Use this when the user asks what a strategy has been doing or how it has performed recently.",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "strategy_id": Schema(type=Type.INTEGER, description="ID of the strategy"),
            "limit": Schema(type=Type.INTEGER, description="Number of recent runs to return (default: 5)"),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["strategy_id"],
    ),
)

get_strategy_decisions_decl = FunctionDeclaration(
    name="get_strategy_decisions",
    description="""Get per-symbol scoring and reasoning from a strategy run. Shows why each stock was bought, sold, or skipped — including Lynch and Buffett scores, thesis summary, and trade details.

    Defaults to the most recent run. Use filter to narrow results:
    - 'all': every symbol evaluated
    - 'trades': only BUYs and SELLs
    - 'buys': only BUY decisions
    - 'sells': only SELL decisions

    Use this to answer "why did you buy X?" or "what did the strategy skip last time?".""",
    parameters=Schema(
        type=Type.OBJECT,
        properties={
            "strategy_id": Schema(type=Type.INTEGER, description="ID of the strategy"),
            "run_id": Schema(type=Type.INTEGER, description="Specific run ID to inspect (default: latest run)"),
            "filter": Schema(
                type=Type.STRING,
                description="Which decisions to return: 'all', 'trades', 'buys', or 'sells' (default: 'all')",
                enum=["all", "trades", "buys", "sells"],
            ),
            "user_id": Schema(type=Type.INTEGER, description="Internal User ID (automatically injected)"),
        },
        required=["strategy_id"],
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
                description="FRED series ID. Key Series: GDPC1/GDP (GDP), UNRATE (Unemployment), CPIAUCSL/PPIACO (Inflation), FEDFUNDS/DGS10/T10Y2Y (Rates/Yields), VIXCLS (Volatility), ICSA (Claims), HOUST (Housing Starts), RSXFS/TOTALSA (Retail/Auto Sales), UMCSENT (Sentiment), CP (Corp Profits), M2SL (Money Supply), DRSFRMACBS (Mortgage Delinq), DRCLACBS (Consumer Loan Delinq)"
            ),
            "start_date": Schema(type=Type.STRING, description="Start date in YYYY-MM-DD format (optional, defaults to 2 years ago)"),
            "end_date": Schema(type=Type.STRING, description="End date in YYYY-MM-DD format (optional, defaults to today)"),
        },
        required=["series_id"],
    ),
)

get_economic_indicators_decl = FunctionDeclaration(
    name="get_economic_indicators",
    description="Get current values of key macroeconomic indicators including GDP, unemployment, inflation (CPI/PPI), rates (Fed Funds/10Y), VIX, jobless claims, housing starts, retail sales, auto sales, consumer sentiment, and corporate profits. Use this for a comprehensive economic overview.",
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
    # Strategy management tools
    get_strategy_templates_decl,
    create_strategy_decl,
    get_my_strategies_decl,
    get_strategy_decl,
    update_strategy_decl,
    get_strategy_activity_decl,
    get_strategy_decisions_decl,
]

# Create the Tool object for Gemini API
AGENT_TOOLS = Tool(function_declarations=TOOL_DECLARATIONS)
