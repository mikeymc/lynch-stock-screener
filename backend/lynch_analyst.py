# ABOUTME: Generates Peter Lynch-style stock analyses using Gemini AI
# ABOUTME: Handles prompt formatting, API calls, and caching of generated analyses

import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import google.generativeai as genai


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
        self.model_version = "gemini-2.5-flash"

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

        # Configure Gemini API
        api_key = api_key or os.getenv('GEMINI_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)

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

    def generate_analysis(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]], sections: Optional[Dict[str, Any]] = None, news: Optional[List[Dict[str, Any]]] = None, material_events: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Generate a new Peter Lynch-style analysis using Gemini AI

        Args:
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data
            sections: Optional dict of filing sections
            news: Optional list of news articles
            material_events: Optional list of material events (8-K filings)

        Returns:
            Generated analysis text

        Raises:
            Exception: If API call fails
        """
        prompt = self.format_prompt(stock_data, history, sections, news, material_events)

        model = genai.GenerativeModel(self.model_version)
        response = model.generate_content(prompt)
        
        return response.text

    def generate_chart_analysis(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]], section: str) -> str:
        """
        Generate a short (200 words) Peter Lynch-style analysis for a specific chart section.

        Args:
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data
            section: One of 'growth', 'cash', or 'valuation'

        Returns:
            Generated analysis text
        """
        # Prepare data
        template_vars = self._prepare_template_vars(stock_data, history)

        # Simplified prompt template for chart analysis
        chart_prompt_template = """
You are Peter Lynch. Analyze the following stock data for {company_name} ({symbol}).

Current Metrics:
Price: ${price}
P/E Ratio: {pe_ratio}
PEG Ratio: {peg_ratio}
Debt-to-Equity: {debt_to_equity}
Institutional Ownership: {institutional_ownership}%
Market Cap: ${market_cap_billions:.2f}B
Earnings CAGR (5y): {earnings_cagr}
Revenue CAGR (5y): {revenue_cagr}

Historical Data:
{history_text}

---

**TASK:**
{instruction}
"""

        # Section-specific instructions
        section_instructions = {
            'growth': """
Focus ONLY on the **Growth & Profitability** metrics: **Revenue**, **Net Income**, and **Operating Cash Flow**.
Analyze the trends. Is the company growing? Is it profitable? Is the cash flow from operations healthy and consistent with earnings?
Write a ~200 word analysis in the style of Peter Lynch. Be conversational, insightful, and look for the story behind the numbers.
""",
            'cash': """
Focus ONLY on the **Cash Management** metrics: **Capital Expenditures**, **Free Cash Flow**, and **Dividend Yield**.
Analyze how the company uses its cash. Are they reinvesting heavily (high CapEx)? Do they have plenty of Free Cash Flow left over? Are they returning cash to shareholders via dividends?
Write a ~200 word analysis in the style of Peter Lynch. Be conversational, insightful, and look for the story behind the numbers.
""",
            'valuation': """
Focus ONLY on the **Market Valuation & Risk** metrics: **Stock Price**, **P/E Ratio**, and **Debt-to-Equity**.
Analyze the valuation and financial health. Is the stock expensive relative to earnings? Is the debt load concerning? How has the price moved relative to fundamentals?
Write a ~200 word analysis in the style of Peter Lynch. Be conversational, insightful, and look for the story behind the numbers.
"""
        }

        instruction = section_instructions.get(section)
        if not instruction:
            raise ValueError(f"Invalid section: {section}. Must be one of 'growth', 'cash', 'valuation'.")

        # Format the prompt
        final_prompt = chart_prompt_template.format(instruction=instruction, **template_vars)

        model = genai.GenerativeModel(self.model_version)
        response = model.generate_content(final_prompt)
        
        return response.text

    def generate_unified_chart_analysis(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Generate a unified Peter Lynch-style analysis for all three chart sections.
        The analysis will be cohesive with shared context across sections.

        Args:
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data

        Returns:
            Dict with keys 'growth', 'cash', 'valuation' containing analysis text for each section
        """
        # Load the unified prompt template
        script_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(script_dir, "chart_analysis_prompt.md")
        
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()

        # Prepare template variables
        template_vars = self._prepare_template_vars(stock_data, history)
        
        # Format the prompt
        final_prompt = prompt_template.format(**template_vars)
        
        # Generate unified analysis
        model = genai.GenerativeModel(self.model_version)
        response = model.generate_content(final_prompt)
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
        symbol: str,
        stock_data: Dict[str, Any],
        history: List[Dict[str, Any]],
        sections: Optional[Dict[str, Any]] = None,
        news: Optional[List[Dict[str, Any]]] = None,
        material_events: Optional[List[Dict[str, Any]]] = None,
        use_cache: bool = True
    ) -> str:
        """
        Get cached analysis or generate a new one

        Args:
            symbol: Stock symbol
            stock_data: Dict containing current stock metrics
            history: List of dicts containing historical earnings/revenue data
            sections: Optional dict of filing sections
            news: Optional list of news articles
            material_events: Optional list of material events (8-K filings)
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
        analysis_text = self.generate_analysis(stock_data, history, sections, news, material_events)

        # Save to cache
        self.db.save_lynch_analysis(symbol, analysis_text, self.model_version)

        return analysis_text
