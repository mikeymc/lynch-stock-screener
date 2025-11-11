# ABOUTME: Generates Peter Lynch-style stock analyses using Gemini AI
# ABOUTME: Handles prompt formatting, API calls, and caching of generated analyses

import os
from typing import Dict, Any, List, Optional
import google.generativeai as genai


class LynchAnalyst:
    def __init__(self, db, api_key: Optional[str] = None, prompt_template_path: str = "lynch_prompt.md", checklist_path: str = "lynch_checklist.md"):
        """
        Initialize the LynchAnalyst with database and Gemini API key

        Args:
            db: Database instance for caching analyses
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            prompt_template_path: Path to the prompt template file
            checklist_path: Path to the Lynch checklist file
        """
        self.db = db
        self.model_version = "gemini-2.5-pro"
        self.prompt_template_path = prompt_template_path
        self.checklist_path = checklist_path

        try:
            with open(prompt_template_path, 'r') as f:
                main_prompt = f.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Prompt template file not found at: {prompt_template_path}") from e

        try:
            with open(checklist_path, 'r') as f:
                checklist_content = f.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Checklist file not found at: {checklist_path}") from e

        self.prompt_template = f"{main_prompt}\n\n---\n\n## Reference: Peter Lynch's Checklist\n\n{checklist_content}"

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

        # Prepare a dictionary of values for formatting
        template_vars = {
            'company_name': stock_data.get('company_name', 'N/A'),
            'symbol': stock_data.get('symbol', 'N/A'),
            'sector': stock_data.get('sector', 'N/A'),
            'exchange': stock_data.get('exchange', 'N/A'),
            'price': stock_data.get('price', 0),
            'pe_ratio': stock_data.get('pe_ratio', 'N/A'),
            'peg_ratio': stock_data.get('peg_ratio', 'N/A'),
            'debt_to_equity': stock_data.get('debt_to_equity', 'N/A'),
            'institutional_ownership': stock_data.get('institutional_ownership', 0) * 100,
            'market_cap_billions': stock_data.get('market_cap', 0) / 1e9,
            'earnings_cagr': stock_data.get('earnings_cagr', 'N/A'),
            'revenue_cagr': stock_data.get('revenue_cagr', 'N/A'),
            'history_text': history_text
        }

        # Format any 'N/A' values for cleaner output
        for key, value in template_vars.items():
            if value is None:
                template_vars[key] = 'N/A'

        # Use str.format() with the loaded template
        return self.prompt_template.format(**template_vars)

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
