# ABOUTME: Generates Peter Lynch-style stock analyses using Gemini AI
# ABOUTME: Handles prompt formatting, API calls, and caching of generated analyses

import os
from typing import Dict, Any, List, Optional
import google.generativeai as genai


class LynchAnalyst:
    def __init__(self, db, api_key: Optional[str] = None):
        """
        Initialize the LynchAnalyst with database and Gemini API key

        Args:
            db: Database instance for caching analyses
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
        """
        self.db = db
        self.model_version = "gemini-2.5-flash"

        # Configure Gemini API
        api_key = api_key or os.getenv('GEMINI_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)

    def format_prompt(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
        """
        Format a prompt for Gemini to generate a Peter Lynch-style analysis

        Args:
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data

        Returns:
            Formatted prompt string
        """
        # Format historical data for the prompt
        history_text = "\n".join([
            f"  {h['year']}: EPS=${h['eps']:.2f}, Revenue=${h['revenue']/1e9:.2f}B"
            for h in sorted(history, key=lambda x: x['year'])
        ])

        prompt = f"""You are Peter Lynch, the legendary investor known for your practical, straightforward approach to stock analysis. Analyze the following stock in your characteristic style, focusing on the key principles from "One Up on Wall Street":

**Company:** {stock_data['company_name']} ({stock_data['symbol']})
**Sector:** {stock_data.get('sector', 'N/A')}
**Exchange:** {stock_data.get('exchange', 'N/A')}

**Current Metrics:**
- Price: ${stock_data.get('price', 0):.2f}
- P/E Ratio: {stock_data.get('pe_ratio', 'N/A')}
- PEG Ratio: {stock_data.get('peg_ratio', 'N/A')}
- Debt-to-Equity: {stock_data.get('debt_to_equity', 'N/A')}
- Institutional Ownership: {stock_data.get('institutional_ownership', 0)*100:.1f}%
- Market Cap: ${stock_data.get('market_cap', 0)/1e9:.2f}B

**Growth Metrics:**
- 5-Year Earnings CAGR: {stock_data.get('earnings_cagr', 'N/A')}%
- 5-Year Revenue CAGR: {stock_data.get('revenue_cagr', 'N/A')}%

**Historical Performance (Last 5 Years):**
{history_text}

Write a 200-300 word analysis in Peter Lynch's voice. Focus on:
1. Whether this is a "growth stock," "stalwart," "fast grower," "cyclical," "turnaround," or "asset play"
2. The PEG ratio and what it tells us about valuation relative to growth
3. Earnings consistency and growth trajectory
4. Debt levels and financial health
5. Whether this passes your key screens (PEG < 1-2, manageable debt, earnings growth)
6. A straightforward verdict: would you invest in this, and why or why not?

Be honest, practical, and avoid jargon. Speak like you're explaining it to an amateur investor over coffee."""

        return prompt

    def generate_analysis(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
        """
        Generate a new Peter Lynch-style analysis using Gemini AI

        Args:
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data

        Returns:
            Generated analysis text

        Raises:
            Exception: If API call fails
        """
        prompt = self.format_prompt(stock_data, history)

        model = genai.GenerativeModel(self.model_version)
        response = model.generate_content(prompt)

        return response.text

    def get_or_generate_analysis(
        self,
        symbol: str,
        stock_data: Dict[str, Any],
        history: List[Dict[str, Any]],
        use_cache: bool = True
    ) -> str:
        """
        Get cached analysis or generate a new one

        Args:
            symbol: Stock symbol
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data
            use_cache: Whether to use cached analysis if available

        Returns:
            Analysis text (from cache or freshly generated)
        """
        # Check cache first
        if use_cache:
            cached = self.db.get_lynch_analysis(symbol)
            if cached:
                return cached['analysis_text']

        # Generate new analysis
        analysis_text = self.generate_analysis(stock_data, history)

        # Save to cache
        self.db.save_lynch_analysis(symbol, analysis_text, self.model_version)

        return analysis_text
