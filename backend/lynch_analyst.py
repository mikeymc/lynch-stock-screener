# ABOUTME: Generates Peter Lynch-style stock analyses using Gemini AI
# ABOUTME: Handles prompt formatting, API calls, and caching of generated analyses

import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from google import genai

# Available AI models for analysis generation
AVAILABLE_MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]
DEFAULT_MODEL = "gemini-2.5-flash"


class LynchAnalyst:
    def __init__(self, db, api_key: Optional[str] = None, prompt_template_path: Optional[str] = None, checklist_path: Optional[str] = None):
        """
        Initialize the LynchAnalyst with database and Gemini API key

        Args:
            db: Database instance for caching analyses
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            prompt_template_path: Path to the prompt template file
            checklist_path: Path to the Lynch checklist file
        """
        self.db = db

        # Use absolute paths relative to this file's location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.prompt_template_path = prompt_template_path or os.path.join(script_dir, "lynch_prompt.md")
        self.checklist_path = checklist_path or os.path.join(script_dir, "lynch_checklist.md")

        try:
            with open(self.prompt_template_path, 'r') as f:
                main_prompt = f.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Prompt template file not found at: {self.prompt_template_path}") from e

        try:
            with open(self.checklist_path, 'r') as f:
                checklist_content = f.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Checklist file not found at: {self.checklist_path}") from e

        self.prompt_template = f"{main_prompt}\n\n---\n\n## Reference: Peter Lynch's Checklist\n\n{checklist_content}"

        # Store API key for lazy client initialization
        self._api_key = api_key or os.getenv('GEMINI_API_KEY')
        self._client = None

    @property
    def client(self):
        """Lazy initialization of Gemini client - only created when first accessed."""
        if self._client is None:
            if self._api_key:
                self._client = genai.Client(api_key=self._api_key)
            else:
                # This will raise an error if no credentials are configured,
                # but only when the client is actually used (not at import time)
                self._client = genai.Client()
        return self._client

    def _prepare_template_vars(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Helper to prepare template variables from stock data and history"""
        # Format historical data for the prompt
        history_lines = []
        for h in sorted(history, key=lambda x: x['year']):
            net_income = h.get('net_income')
            revenue = h.get('revenue')
            ocf = h.get('operating_cash_flow')
            capex = h.get('capital_expenditures')
            fcf = h.get('free_cash_flow')
            
            net_income_str = f"${net_income/1e9:.2f}B" if net_income is not None else "N/A"
            revenue_str = f"${revenue/1e9:.2f}B" if revenue is not None else "N/A"
            ocf_str = f"${ocf/1e9:.2f}B" if ocf is not None else "N/A"
            capex_str = f"${abs(capex)/1e9:.2f}B" if capex is not None else "N/A"
            fcf_str = f"${fcf/1e9:.2f}B" if fcf is not None else "N/A"
            
            history_lines.append(f"  {h['year']}: Net Income={net_income_str}, Revenue={revenue_str}, OCF={ocf_str}, CapEx={capex_str}, FCF={fcf_str}")
        history_text = "\n".join(history_lines)

        # Prepare a dictionary of values for formatting
        # Ensure numeric values are never None to avoid format string errors
        price = stock_data.get('price') or 0
        institutional_ownership = stock_data.get('institutional_ownership') or 0
        market_cap = stock_data.get('market_cap') or 0
        
        template_vars = {
            'current_date': datetime.now().strftime('%B %d, %Y'),
            'current_year': datetime.now().year,
            'company_name': stock_data.get('company_name', 'N/A'),
            'symbol': stock_data.get('symbol', 'N/A'),
            'sector': stock_data.get('sector', 'N/A'),
            'exchange': stock_data.get('exchange', 'N/A'),
            'price': price,
            'pe_ratio': stock_data.get('pe_ratio', 'N/A'),
            'peg_ratio': stock_data.get('peg_ratio', 'N/A'),
            'debt_to_equity': stock_data.get('debt_to_equity', 'N/A'),
            'institutional_ownership': institutional_ownership * 100,
            'market_cap_billions': market_cap / 1e9,
            'earnings_cagr': stock_data.get('earnings_cagr', 'N/A'),
            'revenue_cagr': stock_data.get('revenue_cagr', 'N/A'),
            'history_text': history_text
        }

        # Format any 'N/A' values for cleaner output
        for key, value in template_vars.items():
            if value is None:
                template_vars[key] = 'N/A'
                
        return template_vars

    def format_prompt(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]], sections: Optional[Dict[str, Any]] = None, news: Optional[List[Dict[str, Any]]] = None, material_events: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Format a prompt for Gemini to generate a Peter Lynch-style analysis

        Args:
            stock_data: Dict containing current stock metrics
            history: List of historical earnings/revenue data
            sections: Optional dict of filing sections
            news: Optional list of news articles
            material_events: Optional list of material events (8-K filings)
        """
        template_vars = self._prepare_template_vars(stock_data, history)

        # Debug: print template vars to see what's None
        print(f"DEBUG: template_vars for {stock_data.get('symbol')}: {template_vars}")

        # Use str.format() with the loaded template
        try:
            formatted_prompt = self.prompt_template.format(**template_vars)
        except Exception as e:
            import traceback
            print(f"ERROR formatting prompt: {e}")
            print(f"Template vars: {template_vars}")
            print(f"Traceback:")
            traceback.print_exc()
            raise

        # Append material events (8-K filings) if available - prioritize these before news
        if material_events and len(material_events) > 0:
            events_text = "\n\n---\n\n## Material Corporate Events (SEC 8-K Filings)\n\n"
            events_text += "The following are official SEC 8-K filings disclosing material corporate events. These are highly significant and should be weighted heavily in your analysis.\n\n"

            # Include up to 10 most recent events
            for i, event in enumerate(material_events[:10], 1):
                from datetime import datetime
                filing_date = event.get('filing_date', 'Unknown date')
                if filing_date != 'Unknown date':
                    try:
                        # Format the date nicely if it's a string
                        if isinstance(filing_date, str):
                            dt = datetime.fromisoformat(filing_date.replace('Z', '+00:00'))
                            filing_date = dt.strftime('%B %d, %Y')
                    except:
                        pass

                headline = event.get('headline', 'No headline')
                content_text = event.get('content_text', '')
                item_codes = event.get('sec_item_codes', [])
                accession = event.get('sec_accession_number', 'N/A')

                events_text += f"**{i}. {headline}** (Filed: {filing_date})\n"
                events_text += f"   SEC Form 8-K | Accession: {accession}\n"
                if item_codes:
                    events_text += f"   Item Codes: {', '.join(item_codes)}\n\n"

                # Include actual filing content if available
                if content_text:
                    events_text += f"{content_text}\n\n"
                else:
                    # Fallback to description if no content
                    description = event.get('description', '')
                    if description:
                        events_text += f"   {description}\n\n"

                events_text += "---\n\n"

            formatted_prompt += events_text

        # Append news articles if available
        if news and len(news) > 0:
            news_text = "\n\n---\n\n## Recent News Articles\n\n"
            news_text += "Consider the following news when forming your analysis. Look for trends, catalysts, risks, and how they align with the financial data.\n\n"
            
            # Include up to 20 most recent articles
            for i, article in enumerate(news[:20], 1):
                from datetime import datetime
                pub_date = article.get('published_date', 'Unknown date')
                if pub_date != 'Unknown date':
                    try:
                        # Format the date nicely
                        dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                        pub_date = dt.strftime('%B %d, %Y')
                    except:
                        pass
                
                headline = article.get('headline', 'No headline')
                summary = article.get('summary', '')
                source = article.get('source', 'Unknown source')
                
                news_text += f"**{i}. {headline}** ({source} - {pub_date})\n"
                if summary:
                    news_text += f"   {summary}\n\n"
                else:
                    news_text += "\n"
            
            formatted_prompt += news_text

        # Append SEC filing sections if available
        if sections:
            sections_text = "\n\n---\n\n## Additional Context from SEC Filings\n\n"

            if 'business' in sections:
                sections_text += f"### Business Description (Item 1 from 10-K)\n"
                sections_text += f"Filed: {sections['business'].get('filing_date', 'N/A')}\n"
                sections_text += f"{sections['business'].get('content', 'Not available')}\n\n"

            if 'risk_factors' in sections:
                sections_text += f"### Risk Factors (Item 1A from 10-K)\n"
                sections_text += f"Filed: {sections['risk_factors'].get('filing_date', 'N/A')}\n"
                sections_text += f"{sections['risk_factors'].get('content', 'Not available')}\n\n"

            if 'mda' in sections:
                filing_type = sections['mda'].get('filing_type', '10-K')
                item_num = '7' if filing_type == '10-K' else '2'
                sections_text += f"### Management's Discussion & Analysis (Item {item_num} from {filing_type})\n"
                sections_text += f"Filed: {sections['mda'].get('filing_date', 'N/A')}\n"
                sections_text += f"{sections['mda'].get('content', 'Not available')}\n\n"

            if 'market_risk' in sections:
                filing_type = sections['market_risk'].get('filing_type', '10-K')
                item_num = '7A' if filing_type == '10-K' else '3'
                sections_text += f"### Market Risk Disclosures (Item {item_num} from {filing_type})\n"
                sections_text += f"Filed: {sections['market_risk'].get('filing_date', 'N/A')}\n"
                sections_text += f"{sections['market_risk'].get('content', 'Not available')}\n\n"

            formatted_prompt += sections_text

        return formatted_prompt

    def generate_analysis(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]], sections: Optional[Dict[str, Any]] = None, news: Optional[List[Dict[str, Any]]] = None, material_events: Optional[List[Dict[str, Any]]] = None, model_version: str = DEFAULT_MODEL) -> str:
        """
        Generate a new Peter Lynch-style analysis using Gemini AI

        Args:
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data
            sections: Optional dict of filing sections
            news: Optional list of news articles
            material_events: Optional list of material events (8-K filings)
            model_version: Gemini model to use for generation

        Returns:
            Generated analysis text

        Raises:
            Exception: If API call fails
            ValueError: If model_version is not in AVAILABLE_MODELS
        """
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        prompt = self.format_prompt(stock_data, history, sections, news, material_events)

        response = self.client.models.generate_content(
            model=model_version,
            contents=prompt
        )

        # Check if response was blocked or has no content
        if not response.parts:
            error_msg = "Gemini API returned no content. "

            # Check prompt feedback for blocking
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                error_msg += f"Prompt feedback: {feedback}"

            # Check finish reason
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    error_msg += f" Finish reason: {candidate.finish_reason}"
                if hasattr(candidate, 'safety_ratings'):
                    error_msg += f" Safety ratings: {candidate.safety_ratings}"

            raise Exception(error_msg)

        return response.text

    def generate_unified_chart_analysis(
        self,
        stock_data: Dict[str, Any],
        history: List[Dict[str, Any]],
        sections: Optional[Dict[str, Any]] = None,
        news: Optional[List[Dict[str, Any]]] = None,
        material_events: Optional[List[Dict[str, Any]]] = None,
        model_version: str = DEFAULT_MODEL
    ) -> Dict[str, str]:
        """
        Generate a unified Peter Lynch-style analysis for all three chart sections.
        The analysis will be cohesive with shared context across sections.

        Args:
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data
            sections: Optional dict of filing sections
            news: Optional list of news articles
            material_events: Optional list of material events (8-K filings)
            model_version: Gemini model to use for generation

        Returns:
            Dict with keys 'growth', 'cash', 'valuation' containing analysis text for each section

        Raises:
            ValueError: If model_version is not in AVAILABLE_MODELS
        """
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")
        # Load the unified prompt template
        script_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(script_dir, "chart_analysis_prompt.md")

        with open(prompt_path, 'r') as f:
            prompt_template = f.read()

        # Prepare template variables
        template_vars = self._prepare_template_vars(stock_data, history)

        # Format the prompt
        final_prompt = prompt_template.format(**template_vars)

        # Append material events (8-K filings) if available - prioritize these before news
        if material_events and len(material_events) > 0:
            events_text = "\n\n---\n\n## Material Corporate Events (SEC 8-K Filings)\n\n"
            events_text += "The following are official SEC 8-K filings disclosing material corporate events. These are highly significant and should be weighted heavily in your analysis.\n\n"

            # Include up to 10 most recent events
            for i, event in enumerate(material_events[:10], 1):
                from datetime import datetime
                filing_date = event.get('filing_date', 'Unknown date')
                if filing_date != 'Unknown date':
                    try:
                        # Format the date nicely if it's a string
                        if isinstance(filing_date, str):
                            dt = datetime.fromisoformat(filing_date.replace('Z', '+00:00'))
                            filing_date = dt.strftime('%B %d, %Y')
                    except:
                        pass

                headline = event.get('headline', 'No headline')
                content_text = event.get('content_text', '')
                item_codes = event.get('sec_item_codes', [])
                accession = event.get('sec_accession_number', 'N/A')

                events_text += f"**{i}. {headline}** (Filed: {filing_date})\n"
                events_text += f"   SEC Form 8-K | Accession: {accession}\n"
                if item_codes:
                    events_text += f"   Item Codes: {', '.join(item_codes)}\n\n"

                # Include actual filing content if available
                if content_text:
                    events_text += f"{content_text}\n\n"
                else:
                    # Fallback to description if no content
                    description = event.get('description', '')
                    if description:
                        events_text += f"   {description}\n\n"

                events_text += "---\n\n"

            final_prompt += events_text

        # Append news articles if available
        if news and len(news) > 0:
            news_text = "\n\n---\n\n## Recent News Articles\n\n"
            news_text += "Consider the following news when forming your analysis. Look for trends, catalysts, risks, and how they align with the financial data. Maintain a neutral analytical tone while referencing or discussing sentiment observed in the news.\n\n"

            # Include up to 20 most recent articles
            for i, article in enumerate(news[:20], 1):
                from datetime import datetime
                pub_date = article.get('published_date', 'Unknown date')
                if pub_date != 'Unknown date':
                    try:
                        # Format the date nicely
                        dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                        pub_date = dt.strftime('%B %d, %Y')
                    except:
                        pass

                headline = article.get('headline', 'No headline')
                summary = article.get('summary', '')
                source = article.get('source', 'Unknown source')

                news_text += f"**{i}. {headline}** ({source} - {pub_date})\n"
                if summary:
                    news_text += f"   {summary}\n\n"
                else:
                    news_text += "\n"

            final_prompt += news_text

        # Append SEC filing sections if available
        if sections:
            sections_text = "\n\n---\n\n## Additional Context from SEC Filings\n\n"

            if 'business' in sections:
                sections_text += f"### Business Description (Item 1 from 10-K)\n"
                sections_text += f"Filed: {sections['business'].get('filing_date', 'N/A')}\n"
                sections_text += f"{sections['business'].get('content', 'Not available')}\n\n"

            if 'risk_factors' in sections:
                sections_text += f"### Risk Factors (Item 1A from 10-K)\n"
                sections_text += f"Filed: {sections['risk_factors'].get('filing_date', 'N/A')}\n"
                sections_text += f"{sections['risk_factors'].get('content', 'Not available')}\n\n"

            if 'mda' in sections:
                filing_type = sections['mda'].get('filing_type', '10-K')
                item_num = '7' if filing_type == '10-K' else '2'
                sections_text += f"### Management's Discussion & Analysis (Item {item_num} from {filing_type})\n"
                sections_text += f"Filed: {sections['mda'].get('filing_date', 'N/A')}\n"
                sections_text += f"{sections['mda'].get('content', 'Not available')}\n\n"

            if 'market_risk' in sections:
                filing_type = sections['market_risk'].get('filing_type', '10-K')
                item_num = '7A' if filing_type == '10-K' else '3'
                sections_text += f"### Market Risk Disclosures (Item {item_num} from {filing_type})\n"
                sections_text += f"Filed: {sections['market_risk'].get('filing_date', 'N/A')}\n"
                sections_text += f"{sections['market_risk'].get('content', 'Not available')}\n\n"

            final_prompt += sections_text

        # Generate unified analysis
        response = self.client.models.generate_content(
            model=model_version,
            contents=final_prompt
        )

        # Check if response was blocked or has no content
        if not response.parts:
            error_msg = "Gemini API returned no content. "

            # Check prompt feedback for blocking
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                error_msg += f"Prompt feedback: {feedback}"

            # Check finish reason
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    error_msg += f" Finish reason: {candidate.finish_reason}"
                if hasattr(candidate, 'safety_ratings'):
                    error_msg += f" Safety ratings: {candidate.safety_ratings}"

            raise Exception(error_msg)

        analysis_text = response.text
        
        # Parse the response into three sections
        # Look for markdown headers to split sections
        sections = {'growth': '', 'cash': '', 'valuation': ''}
        
        # Split by section headers
        import re
        growth_match = re.search(r'###\s*Growth\s*&\s*Profitability\s*\n(.*?)(?=###|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        cash_match = re.search(r'###\s*Cash\s*Flow\s*\n(.*?)(?=###|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        valuation_match = re.search(r'###\s*Valuation\s*\n(.*?)(?=###|$)', analysis_text, re.DOTALL | re.IGNORECASE)
        
        if growth_match:
            sections['growth'] = growth_match.group(1).strip()
        if cash_match:
            sections['cash'] = cash_match.group(1).strip()
        if valuation_match:
            sections['valuation'] = valuation_match.group(1).strip()
            
        return sections

    def get_or_generate_analysis(
        self,
        user_id: int,
        symbol: str,
        stock_data: Dict[str, Any],
        history: List[Dict[str, Any]],
        sections: Optional[Dict[str, Any]] = None,
        news: Optional[List[Dict[str, Any]]] = None,
        material_events: Optional[List[Dict[str, Any]]] = None,
        use_cache: bool = True,
        model_version: str = DEFAULT_MODEL
    ) -> str:
        """
        Get cached analysis or generate a new one

        Args:
            user_id: User ID for scoping the analysis
            symbol: Stock symbol
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data
            sections: Optional dict of filing sections
            news: Optional list of news articles
            material_events: Optional list of material events (8-K filings)
            use_cache: Whether to use cached analysis if available
            model_version: Gemini model to use for generation

        Returns:
            Analysis text (from cache or freshly generated)

        Raises:
            ValueError: If model_version is not in AVAILABLE_MODELS
        """
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        # Check cache first
        if use_cache:
            cached = self.db.get_lynch_analysis(user_id, symbol)
            if cached:
                return cached['analysis_text']

        # Generate new analysis
        analysis_text = self.generate_analysis(stock_data, history, sections, news, material_events, model_version)

        # Save to cache for this user
        self.db.save_lynch_analysis(user_id, symbol, analysis_text, model_version)

        return analysis_text

    def generate_dcf_recommendations(
        self,
        stock_data: Dict[str, Any],
        history: List[Dict[str, Any]],
        wacc_data: Optional[Dict[str, Any]] = None,
        sections: Optional[Dict[str, Any]] = None,
        news: Optional[List[Dict[str, Any]]] = None,
        material_events: Optional[List[Dict[str, Any]]] = None,
        model_version: str = "gemini-3-pro-preview"
    ) -> Dict[str, Any]:
        """
        Generate DCF model recommendations using AI.
        Returns three scenarios (conservative, base, optimistic) with reasoning.

        Args:
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data
            wacc_data: Optional dict with WACC calculation details
            sections: Optional dict of filing sections
            news: Optional list of news articles
            material_events: Optional list of material events (8-K filings)
            model_version: Gemini model to use for generation

        Returns:
            Dict with 'scenarios' and 'reasoning' keys

        Raises:
            ValueError: If model_version is not in AVAILABLE_MODELS
        """
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        # Load the DCF prompt template
        script_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(script_dir, "dcf_analysis_prompt.md")

        with open(prompt_path, 'r') as f:
            prompt_template = f.read()

        # Filter for annual history with FCF
        annual_history = [h for h in history if h.get('period') == 'annual' and h.get('free_cash_flow') is not None]
        annual_history.sort(key=lambda x: x['year'], reverse=True)

        # Build FCF history text
        fcf_lines = []
        for h in sorted(annual_history, key=lambda x: x['year']):
            fcf = h.get('free_cash_flow')
            fcf_str = f"${fcf/1e9:.2f}B" if fcf is not None else "N/A"
            fcf_lines.append(f"  {h['year']}: {fcf_str}")
        fcf_history_text = "\n".join(fcf_lines) if fcf_lines else "No FCF history available"

        # Calculate FCF CAGRs
        def calc_cagr(start_val, end_val, years):
            if not start_val or not end_val or years <= 0 or start_val <= 0:
                return None
            return ((end_val / start_val) ** (1 / years) - 1) * 100

        fcf_values = [h.get('free_cash_flow') for h in annual_history]
        fcf_cagr_3yr = "N/A"
        fcf_cagr_5yr = "N/A"
        fcf_cagr_10yr = "N/A"

        if len(fcf_values) >= 4:
            cagr = calc_cagr(fcf_values[3], fcf_values[0], 3)
            if cagr is not None:
                fcf_cagr_3yr = f"{cagr:.1f}%"
        if len(fcf_values) >= 6:
            cagr = calc_cagr(fcf_values[5], fcf_values[0], 5)
            if cagr is not None:
                fcf_cagr_5yr = f"{cagr:.1f}%"
        if len(fcf_values) >= 11:
            cagr = calc_cagr(fcf_values[10], fcf_values[0], 10)
            if cagr is not None:
                fcf_cagr_10yr = f"{cagr:.1f}%"

        # Format WACC text
        wacc_text = "WACC data not available"
        if wacc_data:
            wacc_text = f"""- **Calculated WACC**: {wacc_data.get('wacc', 'N/A')}%
- **Cost of Equity**: {wacc_data.get('cost_of_equity', 'N/A')}% (Beta: {wacc_data.get('beta', 'N/A')})
- **After-Tax Cost of Debt**: {wacc_data.get('after_tax_cost_of_debt', 'N/A')}%
- **Capital Structure**: {wacc_data.get('equity_weight', 'N/A')}% Equity / {wacc_data.get('debt_weight', 'N/A')}% Debt"""

        # Prepare template variables
        price = stock_data.get('price') or 0
        market_cap = stock_data.get('market_cap') or 0

        template_vars = {
            'symbol': stock_data.get('symbol', 'N/A'),
            'company_name': stock_data.get('company_name', 'N/A'),
            'sector': stock_data.get('sector', 'N/A'),
            'current_date': datetime.now().strftime('%B %d, %Y'),
            'price': price,
            'market_cap_billions': market_cap / 1e9,
            'pe_ratio': stock_data.get('pe_ratio', 'N/A'),
            'forward_pe': stock_data.get('forward_pe', 'N/A'),
            'forward_peg': stock_data.get('forward_peg_ratio', 'N/A'),
            'forward_eps': stock_data.get('forward_eps', 'N/A'),
            'fcf_history_text': fcf_history_text,
            'fcf_cagr_3yr': fcf_cagr_3yr,
            'fcf_cagr_5yr': fcf_cagr_5yr,
            'fcf_cagr_10yr': fcf_cagr_10yr,
            'wacc_text': wacc_text,
            'news_text': '',
            'events_text': '',
            'business_text': '',
            'mda_text': ''
        }

        # Add news context
        if news and len(news) > 0:
            news_lines = []
            for article in news[:10]:
                headline = article.get('headline', 'No headline')
                source = article.get('source', 'Unknown')
                news_lines.append(f"- {headline} ({source})")
            template_vars['news_text'] = "\n".join(news_lines)
        else:
            template_vars['news_text'] = "No recent news available"

        # Add material events context
        if material_events and len(material_events) > 0:
            events_lines = []
            for event in material_events[:5]:
                headline = event.get('headline', 'No headline')
                filing_date = event.get('filing_date', 'Unknown date')
                events_lines.append(f"- {headline} ({filing_date})")
            template_vars['events_text'] = "\n".join(events_lines)
        else:
            template_vars['events_text'] = "No recent 8-K filings available"

        # Add SEC filing context
        if sections:
            if 'business' in sections:
                content = sections['business'].get('content', '')
                # Truncate to avoid token limits
                template_vars['business_text'] = content[:2000] + "..." if len(content) > 2000 else content
            else:
                template_vars['business_text'] = "Not available"

            if 'mda' in sections:
                content = sections['mda'].get('content', '')
                template_vars['mda_text'] = content[:2000] + "..." if len(content) > 2000 else content
            else:
                template_vars['mda_text'] = "Not available"
        else:
            template_vars['business_text'] = "Not available"
            template_vars['mda_text'] = "Not available"

        # Format the prompt
        final_prompt = prompt_template.format(**template_vars)

        # Generate response
        response = self.client.models.generate_content(
            model=model_version,
            contents=final_prompt
        )

        # Check if response was blocked or has no content
        if not response.parts:
            error_msg = "Gemini API returned no content. "
            if hasattr(response, 'prompt_feedback'):
                error_msg += f"Prompt feedback: {response.prompt_feedback}"
            raise Exception(error_msg)

        response_text = response.text

        # Parse JSON from response
        import json
        import re

        # Try to extract JSON from the response (may be wrapped in markdown code block)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                raise Exception(f"Could not parse JSON from response: {response_text[:500]}")

        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON in response: {e}. Response: {json_str[:500]}")

        # Validate response structure
        if 'scenarios' not in result:
            raise Exception(f"Response missing 'scenarios' key: {result}")

        for scenario in ['conservative', 'base', 'optimistic']:
            if scenario not in result['scenarios']:
                raise Exception(f"Response missing '{scenario}' scenario: {result}")

        return result
