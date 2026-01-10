# ABOUTME: Character-aware stock analyst that generates analyses using AI
# ABOUTME: Supports multiple investment philosophies (Lynch, Buffett, etc.) via character configs

import os
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from google import genai
from google.genai.types import GenerateContentConfig

from characters import get_character
from characters.config import CharacterConfig

# Available AI models for analysis generation
AVAILABLE_MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]
DEFAULT_MODEL = "gemini-2.5-flash"


class StockAnalyst:
    """Character-aware stock analyst that generates analyses using AI.

    Loads prompts and configuration based on the active character setting.
    Supports Lynch, Buffett, and other investment philosophy characters.
    """

    def __init__(self, db, api_key: Optional[str] = None):
        """
        Initialize the StockAnalyst with database connection.

        Args:
            db: Database instance for caching analyses and getting settings
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
        """
        self.db = db
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

        # Store API key for lazy client initialization
        self._api_key = api_key or os.getenv('GEMINI_API_KEY')
        self._client = None

        # Cache for loaded prompts by character
        self._prompt_cache: Dict[str, str] = {}

    @property
    def client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            if self._api_key:
                self._client = genai.Client(api_key=self._api_key)
            else:
                self._client = genai.Client()
        return self._client

    @property
    def prompt_template(self):
        """Dynamically return the active character's prompt template."""
        character = self._get_active_character()
        return self._get_prompt_template(character)

    def _get_active_character(self) -> CharacterConfig:
        """Get the currently active character from settings."""
        character_id = self.db.get_setting('active_character', 'lynch')
        character = get_character(character_id)
        if not character:
            character = get_character('lynch')
        return character

    def _get_prompt_template(self, character: CharacterConfig) -> str:
        """Get the prompt template for a character, with caching."""
        if character.id in self._prompt_cache:
            return self._prompt_cache[character.id]

        # Load analysis template
        template_path = os.path.join(self.script_dir, "prompts", character.analysis_template)
        with open(template_path, 'r') as f:
            main_prompt = f.read()

        # Load checklist
        checklist_path = os.path.join(self.script_dir, "prompts", character.checklist_prompt)
        with open(checklist_path, 'r') as f:
            checklist_content = f.read()

        # Combine into full template
        full_template = f"{main_prompt}\n\n---\n\n## Reference: {character.name}'s Investment Checklist\n\n{checklist_content}"

        self._prompt_cache[character.id] = full_template
        return full_template

    def _prepare_template_vars(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]], character: Optional[CharacterConfig] = None) -> Dict[str, Any]:
        """Prepare template variables from stock data and history."""
        # If no character provided, use active character
        if character is None:
            character = self._get_active_character()

        # Format historical data
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

        price = stock_data.get('price') or 0
        institutional_ownership = stock_data.get('institutional_ownership') or 0
        market_cap = stock_data.get('market_cap') or 0

        # Format analyst estimates
        analyst_estimates = stock_data.get('analyst_estimates', {})
        analyst_estimates_text = "Not available"
        if analyst_estimates:
            estimates_lines = []
            for period, data in analyst_estimates.items():
                eps_avg = data.get('eps_avg')
                revenue_avg = data.get('revenue_avg')
                if eps_avg or revenue_avg:
                    eps_str = f"EPS ${eps_avg:.2f}" if eps_avg else ""
                    rev_str = f"Revenue ${revenue_avg/1e9:.2f}B" if revenue_avg else ""
                    line_parts = [p for p in [eps_str, rev_str] if p]
                    if line_parts:
                        estimates_lines.append(f"- **{period}**: {', '.join(line_parts)}")
            if estimates_lines:
                analyst_estimates_text = "\n".join(estimates_lines)

        # Format price targets
        price_targets = stock_data.get('price_targets', {})
        price_targets_text = "Not available"
        if price_targets and (price_targets.get('mean') or price_targets.get('high') or price_targets.get('low')):
            pt_lines = []
            if price_targets.get('mean'):
                pt_lines.append(f"- **Mean Target**: ${price_targets['mean']:.2f}")
            if price_targets.get('high'):
                pt_lines.append(f"- **High Target**: ${price_targets['high']:.2f}")
            if price_targets.get('low'):
                pt_lines.append(f"- **Low Target**: ${price_targets['low']:.2f}")
            if pt_lines:
                price_targets_text = "\n".join(pt_lines)

        # Base template vars
        template_vars = {
            'current_date': datetime.now().strftime('%B %d, %Y'),
            'current_year': datetime.now().year,
            'character_name': character.name,
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
            'history_text': history_text,
            'analyst_estimates_text': analyst_estimates_text,
            'price_targets_text': price_targets_text,
        }

        # Add Buffett-specific vars if needed
        if character.id == 'buffett':
            from metric_calculator import MetricCalculator
            calc = MetricCalculator(self.db)

            symbol = stock_data.get('symbol')
            roe_data = calc.calculate_roe(symbol) if symbol else {}
            oe_data = calc.calculate_owner_earnings(symbol) if symbol else {}
            debt_data = calc.calculate_debt_to_earnings(symbol) if symbol else {}

            template_vars.update({
                'current_roe': roe_data.get('current_roe', 'N/A'),
                'avg_roe_5yr': roe_data.get('avg_roe_5yr', 'N/A'),
                'avg_roe_10yr': roe_data.get('avg_roe_10yr', 'N/A'),
                'owner_earnings': oe_data.get('owner_earnings', 'N/A'),
                'free_cash_flow': stock_data.get('free_cash_flow', 'N/A'),
                'earnings_consistency': stock_data.get('consistency_score', 'N/A'),
                'total_debt': debt_data.get('total_debt', 'N/A'),
                'net_income': debt_data.get('annual_net_income', 'N/A'),
                'debt_to_earnings_years': debt_data.get('debt_to_earnings_years', 'N/A'),
            })

        # Handle N/A values
        for key, value in template_vars.items():
            if value is None:
                template_vars[key] = 'N/A'

        return template_vars

    def format_prompt(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]],
                      sections: Optional[Dict[str, Any]] = None,
                      news: Optional[List[Dict[str, Any]]] = None,
                      material_events: Optional[List[Dict[str, Any]]] = None) -> str:
        """Format a prompt using the active character's template."""
        character = self._get_active_character()
        template = self._get_prompt_template(character)
        template_vars = self._prepare_template_vars(stock_data, history, character)

        try:
            formatted_prompt = template.format(**template_vars)
        except KeyError as e:
            print(f"Missing template var for {character.id}: {e}")
            raise

        # Append material events if available
        if material_events and len(material_events) > 0:
            events_text = "\n\n---\n\n## Material Corporate Events (SEC 8-K Filings)\n\n"
            events_text += "The following are official SEC 8-K filings disclosing material corporate events.\n\n"
            for i, event in enumerate(material_events[:10], 1):
                headline = event.get('headline', 'No headline')
                filing_date = event.get('filing_date', 'Unknown date')
                if filing_date != 'Unknown date' and isinstance(filing_date, str):
                    try:
                        dt = datetime.fromisoformat(filing_date.replace('Z', '+00:00'))
                        filing_date = dt.strftime('%B %d, %Y')
                    except:
                        pass
                content_text = event.get('content_text', '')
                item_codes = event.get('sec_item_codes', [])
                accession = event.get('sec_accession_number', 'N/A')

                events_text += f"**{i}. {headline}** (Filed: {filing_date})\n"
                events_text += f"   SEC Form 8-K | Accession: {accession}\n"
                if item_codes:
                    events_text += f"   Item Codes: {', '.join(item_codes)}\n\n"
                if content_text:
                    events_text += f"{content_text}\n\n"
                events_text += "---\n\n"
            formatted_prompt += events_text

        # Append news if available
        if news and len(news) > 0:
            news_text = "\n\n---\n\n## Recent News Articles\n\n"
            for i, article in enumerate(news[:20], 1):
                headline = article.get('headline', 'No headline')
                source = article.get('source', 'Unknown')
                summary = article.get('summary', '')
                pub_date = article.get('published_date', 'Unknown date')
                if pub_date != 'Unknown date' and isinstance(pub_date, str):
                    try:
                        dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                        pub_date = dt.strftime('%B %d, %Y')
                    except:
                        pass
                news_text += f"**{i}. {headline}** ({source} - {pub_date})\n"
                if summary:
                    news_text += f"   {summary}\n\n"
            formatted_prompt += news_text

        # Append SEC sections if available
        if sections:
            sections_text = "\n\n---\n\n## Additional Context from SEC Filings\n\n"
            for key in ['business', 'risk_factors', 'mda', 'market_risk']:
                if key in sections:
                    sections_text += f"### {key.replace('_', ' ').title()}\n"
                    sections_text += f"{sections[key].get('content', 'Not available')}\n\n"
            formatted_prompt += sections_text

        return formatted_prompt

    def generate_analysis_stream(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]],
                                  sections: Optional[Dict[str, Any]] = None,
                                  news: Optional[List[Dict[str, Any]]] = None,
                                  material_events: Optional[List[Dict[str, Any]]] = None,
                                  model_version: str = DEFAULT_MODEL):
        """Stream a new analysis using the active character's voice."""
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        prompt = self.format_prompt(stock_data, history, sections, news, material_events)

        response = self.client.models.generate_content_stream(
            model=model_version,
            contents=prompt
        )

        for chunk in response:
            try:
                if chunk.text:
                    yield chunk.text
            except Exception:
                pass

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
    ):
        """Get cached analysis or stream a new one."""
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        # Check cache (note: cache is per user/symbol, not per character currently)
        if use_cache:
            cached = self.db.get_lynch_analysis(user_id, symbol)
            if cached:
                yield cached['analysis_text']
                return

        # Generate new analysis
        full_text_parts = []
        for chunk in self.generate_analysis_stream(stock_data, history, sections, news, material_events, model_version):
            full_text_parts.append(chunk)
            yield chunk

        # Save to cache
        final_text = "".join(full_text_parts)
        if final_text:
            self.db.save_lynch_analysis(user_id, symbol, final_text, model_version)

    def generate_unified_chart_analysis(
        self,
        stock_data: Dict[str, Any],
        history: List[Dict[str, Any]],
        sections: Optional[Dict[str, Any]] = None,
        news: Optional[List[Dict[str, Any]]] = None,
        material_events: Optional[List[Dict[str, Any]]] = None,
        transcripts: Optional[List[Dict[str, Any]]] = None,
        lynch_brief: Optional[str] = None,
        model_version: str = DEFAULT_MODEL
    ) -> Dict[str, str]:
        """
        Generate a unified analysis for chart sections using the active character.

        Returns:
            Dict with 'narrative' key containing analysis text
        """
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        # Load the unified prompt template
        prompt_path = os.path.join(self.script_dir, "prompts", "analysis", "chart_analysis.md")
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()

        # Prepare template variables (includes character_name)
        template_vars = self._prepare_template_vars(stock_data, history)

        # Format the prompt
        final_prompt = prompt_template.format(**template_vars)

        # Append material events if available
        if material_events and len(material_events) > 0:
            events_text = "\n\n---\n\n## Material Corporate Events (SEC 8-K Filings)\n\n"
            for i, event in enumerate(material_events[:10], 1):
                filing_date = event.get('filing_date', 'Unknown date')
                if filing_date != 'Unknown date' and isinstance(filing_date, str):
                    try:
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
                if content_text:
                    events_text += f"{content_text}\n\n"
                events_text += "---\n\n"
            final_prompt += events_text

        # Append news articles if available
        if news and len(news) > 0:
            news_text = "\n\n---\n\n## Recent News Articles\n\n"
            for i, article in enumerate(news[:20], 1):
                pub_date = article.get('published_date', 'Unknown date')
                if pub_date != 'Unknown date' and isinstance(pub_date, str):
                    try:
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
            final_prompt += news_text

        # Append SEC filing sections if available
        if sections:
            sections_text = "\n\n---\n\n## Additional Context from SEC Filings\n\n"
            for key, title in [('business', 'Business Description'), ('risk_factors', 'Risk Factors'),
                               ('mda', "Management's Discussion & Analysis"), ('market_risk', 'Market Risk')]:
                if key in sections:
                    sections_text += f"### {title}\n"
                    sections_text += f"Filed: {sections[key].get('filing_date', 'N/A')}\n"
                    sections_text += f"{sections[key].get('content', 'Not available')}\n\n"
            final_prompt += sections_text

        # Append earnings transcripts if available
        if transcripts and len(transcripts) > 0:
            transcript_text = "\n\n---\n\n## Recent Earnings Call Transcripts\n\n"
            for transcript in transcripts[:2]:
                quarter = transcript.get('quarter', 'Q?')
                fiscal_year = transcript.get('fiscal_year', 'N/A')
                earnings_date = transcript.get('earnings_date', 'Unknown date')
                summary = transcript.get('summary')
                if summary:
                    content = summary
                else:
                    full_text = transcript.get('transcript_text', '')
                    content = full_text[:5000] + "..." if len(full_text) > 5000 else full_text
                transcript_text += f"### {quarter} {fiscal_year} Earnings Call ({earnings_date})\n\n"
                transcript_text += f"{content}\n\n"
            final_prompt += transcript_text

        # Append prior analysis brief if available
        if lynch_brief:
            char_name = template_vars.get('character_name', 'Peter Lynch')
            brief_text = f"\n\n---\n\n## Prior Investment Analysis\n\n"
            brief_text += f"This is a previously generated {char_name}-style analysis for this company.\n\n"
            brief_text += f"{lynch_brief}\n\n"
            final_prompt += brief_text

        # Generate unified analysis
        response = self.client.models.generate_content(
            model=model_version,
            contents=final_prompt
        )

        if not response.parts:
            error_msg = "Gemini API returned no content."
            if hasattr(response, 'prompt_feedback'):
                error_msg += f" Prompt feedback: {response.prompt_feedback}"
            raise Exception(error_msg)

        analysis_text = response.text
        if not analysis_text or not analysis_text.strip():
            raise Exception("Gemini API returned empty text content")

        return {'narrative': analysis_text.strip()}

    def generate_filing_section_summary(
        self,
        section_name: str,
        section_content: str,
        company_name: str,
        filing_type: str = "10-K",
        model_version: str = DEFAULT_MODEL
    ) -> str:
        """Generate an AI summary of a SEC filing section."""
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        section_titles = {
            'business': 'Business Description (Item 1)',
            'risk_factors': 'Risk Factors (Item 1A)',
            'mda': "Management's Discussion & Analysis",
            'market_risk': 'Market Risk Disclosures'
        }
        section_title = section_titles.get(section_name, section_name)

        prompt_path = os.path.join(self.script_dir, "prompts", "summarization", "filing_section.md")
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()

        prompt = prompt_template.format(
            company_name=company_name,
            filing_type=filing_type,
            section_title=section_title,
            section_content=section_content[:20000]
        )

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        if not response.parts:
            error_msg = "Gemini API returned no content for section summary."
            if hasattr(response, 'prompt_feedback'):
                error_msg += f" Prompt feedback: {response.prompt_feedback}"
            raise Exception(error_msg)

        return response.text.strip()

    def generate_dcf_recommendations(
        self,
        stock_data: Dict[str, Any],
        history: List[Dict[str, Any]],
        wacc_data: Optional[Dict[str, Any]] = None,
        sections: Optional[Dict[str, Any]] = None,
        news: Optional[List[Dict[str, Any]]] = None,
        material_events: Optional[List[Dict[str, Any]]] = None,
        model_version: str = "gemini-2.5-flash"
    ) -> Dict[str, Any]:
        """Generate DCF model recommendations using AI."""
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        prompt_path = os.path.join(self.script_dir, "prompts", "analysis", "dcf_analysis.md")
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
            news_lines = [f"- {a.get('headline', 'No headline')} ({a.get('source', 'Unknown')})" for a in news[:10]]
            template_vars['news_text'] = "\n".join(news_lines)
        else:
            template_vars['news_text'] = "No recent news available"

        # Add material events context
        if material_events and len(material_events) > 0:
            events_lines = [f"- {e.get('headline', 'No headline')} ({e.get('filing_date', 'Unknown date')})" for e in material_events[:5]]
            template_vars['events_text'] = "\n".join(events_lines)
        else:
            template_vars['events_text'] = "No recent 8-K filings available"

        # Add SEC filing context
        if sections:
            if 'business' in sections:
                content = sections['business'].get('content', '')
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

        final_prompt = prompt_template.format(**template_vars)

        response = self.client.models.generate_content(
            model=model_version,
            contents=final_prompt,
            config=GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=8192
            )
        )

        if not response.parts:
            error_msg = "Gemini API returned no content."
            if hasattr(response, 'prompt_feedback'):
                error_msg += f" Prompt feedback: {response.prompt_feedback}"
            raise Exception(error_msg)

        response_text = response.text

        # Parse JSON from response
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                raise Exception(f"Could not parse JSON from response: {response_text[:500]}")

        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON in response: {e}. Response: {json_str[:500]}")

        if 'scenarios' not in result:
            raise Exception(f"Response missing 'scenarios' key: {result}")

        for scenario in ['conservative', 'base', 'optimistic']:
            if scenario not in result['scenarios']:
                raise Exception(f"Response missing '{scenario}' scenario: {result}")

        return result

    def generate_transcript_summary(
        self,
        transcript_text: str,
        company_name: str,
        quarter: str,
        fiscal_year: int,
        model_version: str = "gemini-2.5-flash"
    ) -> str:
        """Generate an AI summary of an earnings call transcript."""
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        prompt_path = os.path.join(self.script_dir, "prompts", "summarization", "transcript_summary.md")
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()

        prompt = prompt_template.format(
            company_name=company_name,
            quarter=quarter,
            fiscal_year=fiscal_year,
            transcript_text=transcript_text
        )

        response = self.client.models.generate_content(
            model=model_version,
            contents=prompt
        )

        if not response.parts:
            error_msg = "Gemini API returned no content for transcript summary."
            if hasattr(response, 'prompt_feedback'):
                error_msg += f" Prompt feedback: {response.prompt_feedback}"
            raise Exception(error_msg)

        return response.text.strip()
