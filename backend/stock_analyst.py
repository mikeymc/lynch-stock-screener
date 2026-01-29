# ABOUTME: Character-aware stock analyst that generates analyses using AI
# ABOUTME: Supports multiple investment philosophies (Lynch, Buffett, etc.) via character configs

import os
import json
import re
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import httpx
from google import genai
from google.genai.types import GenerateContentConfig, ToolConfig, FunctionCallingConfig, FunctionCallingConfigMode

logger = logging.getLogger(__name__)

from characters import get_character
from characters.config import CharacterConfig

# Available AI models for analysis generation
AVAILABLE_MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]
DEFAULT_MODEL = "gemini-3-flash-preview"
FALLBACK_MODEL = "gemini-2.5-flash"

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
            # Set explicit granular timeout via client_args to bypass HttpOptions.timeout validation
            # connect=10s (for handshake), read=60s (for long streams), write=10s, pool=10s
            timeout_config = httpx.Timeout(60.0, connect=10.0, read=60.0, write=10.0, pool=10.0)
            http_options = {'client_args': {'timeout': timeout_config}}
            
            if self._api_key:
                self._client = genai.Client(api_key=self._api_key, http_options=http_options)
            else:
                self._client = genai.Client(http_options=http_options)
        return self._client

    @property
    def prompt_template(self):
        """Dynamically return the active character's prompt template."""
        character = self._get_active_character()
        return self._get_prompt_template(character)

    def _get_active_character(self, user_id: Optional[int] = None) -> CharacterConfig:
        """Get the currently active character from user settings or global settings."""
        if user_id is not None:
            character_id = self.db.get_user_character(user_id)
        else:
            # Fallback to global setting (for backwards compatibility)
            character_id = self.db.get_setting('active_character', 'lynch')

        character = get_character(character_id)
        if not character:
            character = get_character('lynch')
        return character

    def _get_expertise_guidance(self, user_id: Optional[int] = None) -> str:
        """Load the appropriate expertise level guidance for the user.

        Returns the guidance section from expertise_levels.md that matches the user's
        expertise level (learning, practicing, or expert).
        """
        # Get user's expertise level
        if user_id is not None:
            expertise_level = self.db.get_user_expertise_level(user_id)
        else:
            expertise_level = 'practicing'  # Default for non-authenticated requests

        # Load the full expertise levels file
        expertise_path = os.path.join(self.script_dir, "prompts", "shared", "expertise_levels.md")
        with open(expertise_path, 'r') as f:
            content = f.read()

        # Extract the section for this expertise level
        # Format: # EXPERTISE_LEVEL: learning\n\n[content]\n\n---\n\n# EXPERTISE_LEVEL: practicing...
        pattern = f"# EXPERTISE_LEVEL: {expertise_level}\\s*\n\n(.*?)(?=\n\n---\n\n# EXPERTISE_LEVEL:|$)"
        match = re.search(pattern, content, re.DOTALL)

        if match:
            return match.group(1).strip()
        else:
            # Fallback to empty string if section not found
            logger.warning(f"Expertise guidance not found for level: {expertise_level}")
            return ""

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

    def _prepare_template_vars(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]], character: Optional[CharacterConfig] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Prepare template variables from stock data and history."""
        # If no character provided, use active character
        if character is None:
            character = self._get_active_character(user_id)

        # Format historical data
        history_lines = []
        for h in sorted(history, key=lambda x: x['year']):
            net_income = h.get('net_income')
            revenue = h.get('revenue')
            ocf = h.get('operating_cash_flow')
            capex = h.get('capital_expenditures')
            fcf = h.get('free_cash_flow')
            
            # New metrics for Buffett analysis
            shares = h.get('shares_outstanding')
            book_value = h.get('book_value_per_share')
            equity = h.get('total_equity')
            total_debt = h.get('total_debt')
            cash = h.get('cash_and_cash_equivalents')
            
            # Calculations
            net_margin_str = f"{net_income/revenue*100:.1f}%" if (net_income and revenue) else "N/A"
            roe_str = f"{net_income/equity*100:.1f}%" if (net_income and equity) else "N/A"
            debt_to_earnings_str = f"{total_debt/net_income:.1f}x" if (total_debt is not None and net_income and net_income > 0) else "N/A"

            net_income_str = f"${net_income/1e9:.2f}B" if net_income is not None else "N/A"
            revenue_str = f"${revenue/1e9:.2f}B" if revenue is not None else "N/A"
            ocf_str = f"${ocf/1e9:.2f}B" if ocf is not None else "N/A"
            capex_str = f"${abs(capex)/1e9:.2f}B" if capex is not None else "N/A"
            fcf_str = f"${fcf/1e9:.2f}B" if fcf is not None else "N/A"
            shares_str = f"{shares/1e9:.2f}B" if shares is not None else "N/A"
            book_value_str = f"${book_value:.2f}" if book_value is not None else "N/A"
            cash_str = f"${cash/1e9:.2f}B" if cash is not None else "N/A"

            history_lines.append(f"  {h['year']}: Revenue={revenue_str}, Net Income={net_income_str} (Margin={net_margin_str}), ROE={roe_str}, "
                                 f"OCF={ocf_str}, FCF={fcf_str}, Debt/Earnings={debt_to_earnings_str}, "
                                 f"Shares={shares_str}, BVPS={book_value_str}, Cash={cash_str}")
        history_text = "\n".join(history_lines)

        price = stock_data.get('price') or 0
        institutional_ownership = stock_data.get('institutional_ownership') or 0
        market_cap = stock_data.get('market_cap') or 0
        beta = stock_data.get('beta', 'N/A')
        short_percent_float = stock_data.get('short_percent_float')


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
        now_est = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York'))
        template_vars = {
            'current_date': now_est.strftime('%B %d, %Y'),
            'current_year': now_est.year,
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
            # Enriched Metrics
            'forward_pe': stock_data.get('forward_pe', 'N/A'),
            'forward_peg': stock_data.get('forward_peg_ratio', 'N/A'),
            'forward_eps': stock_data.get('forward_eps', 'N/A'),
            'beta': beta,
            'short_ratio': stock_data.get('short_ratio', 'N/A'),
            'short_percent_float': f"{short_percent_float * 100:.2f}" if short_percent_float is not None else 'N/A',
            'interest_expense': stock_data.get('interest_expense', 'N/A'),
            'effective_tax_rate': f"{stock_data['effective_tax_rate']*100:.1f}%" if stock_data.get('effective_tax_rate') else 'N/A',
            'gross_margin': f"{stock_data['gross_margin']:.1f}%" if stock_data.get('gross_margin') else 'N/A',
            'insider_net_buying': f"${stock_data.get('insider_net_buying_6m', 0)/1e6:.1f}M" if stock_data.get('insider_net_buying_6m') is not None else 'N/A',
            'analyst_rating': stock_data.get('analyst_rating', 'N/A'),
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
                      material_events: Optional[List[Dict[str, Any]]] = None,
                      transcripts: Optional[List[Dict[str, Any]]] = None,
                      lynch_brief: Optional[str] = None,
                      user_id: Optional[int] = None,
                      character_id: Optional[str] = None) -> str:
        """Format a prompt using the active character's template."""
        # If character_id provided, use it, otherwise fall back to user's setting
        if character_id:
            character = get_character(character_id) or self._get_active_character(user_id)
        else:
            character = self._get_active_character(user_id)

        template = self._get_prompt_template(character)

        # Prepend expertise guidance based on user's level
        expertise_guidance = self._get_expertise_guidance(user_id)
        if expertise_guidance:
            template = f"{expertise_guidance}\n\n---\n\n{template}"

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
            formatted_prompt += transcript_text
            
        # Append prior analysis brief if available
        if lynch_brief:
            char_name = template_vars.get('character_name', 'Peter Lynch')
            brief_text = f"\n\n---\n\n## Prior Investment Analysis\n\n"
            brief_text += f"This is a previously generated {char_name}-style analysis for this company.\n\n"
            brief_text += f"{lynch_brief}\n\n"
            formatted_prompt += brief_text

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
            # Limit each section to ~30k chars to prevent massive payloads (Fly.io OOM / API timeouts)
            SECTION_CHAR_LIMIT = 30000
            
            for key in ['business', 'risk_factors', 'mda', 'market_risk']:
                if key in sections:
                    title = key.replace('_', ' ').title()
                    content = sections[key].get('content', 'Not available')
                    
                    # Truncate if necessary
                    if content and len(content) > SECTION_CHAR_LIMIT:
                        logger.info(f"Truncating {key} section from {len(content)} to {SECTION_CHAR_LIMIT} chars")
                        content = content[:SECTION_CHAR_LIMIT] + "... [TRUNCATED]"
                        
                    sections_text += f"### {title}\n"
                    sections_text += f"{content}\n\n"
            formatted_prompt += sections_text

        return formatted_prompt

    def generate_analysis_stream(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]],
                                  sections: Optional[Dict[str, Any]] = None,
                                  news: Optional[List[Dict[str, Any]]] = None,
                                  material_events: Optional[List[Dict[str, Any]]] = None,
                                  model_version: str = DEFAULT_MODEL,
                                  user_id: Optional[int] = None,
                                  character_id: Optional[str] = None):
        """Legacy stream wrapper"""
        return self.generate_analysis_stream_enriched(
            stock_data, history, sections, news, material_events, 
            None, None, model_version, user_id, character_id
        )

    def generate_analysis_stream_enriched(self, stock_data: Dict[str, Any], history: List[Dict[str, Any]],
                                  sections: Optional[Dict[str, Any]] = None,
                                  news: Optional[List[Dict[str, Any]]] = None,
                                  material_events: Optional[List[Dict[str, Any]]] = None,
                                  transcripts: Optional[List[Dict[str, Any]]] = None,
                                  lynch_brief: Optional[str] = None,
                                  model_version: str = DEFAULT_MODEL,
                                  user_id: Optional[int] = None,
                                  character_id: Optional[str] = None):
        """Stream a new analysis using the active character's voice with retry logic."""
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        t0 = time.time()
        logger.info(f"[Analysis] Constructing prompt for {stock_data.get('symbol')} (Character: {character_id})")
        prompt = self.format_prompt(stock_data, history, sections, news, material_events, 
                                    transcripts=transcripts, lynch_brief=lynch_brief,
                                    user_id=user_id, character_id=character_id)
        t_prompt = (time.time() - t0) * 1000
        prompt_size_bytes = len(prompt.encode('utf-8'))
        logger.info(f"[Analysis][{stock_data.get('symbol')}] Prompt constructed in {t_prompt:.2f}ms. Size: {len(prompt)} chars ({prompt_size_bytes/1024:.2f} KB)")

        # Retry logic with fallback to flash model
        models_to_try = [model_version, FALLBACK_MODEL] if model_version != FALLBACK_MODEL else [model_version]
        response = None

        for model_index, model in enumerate(models_to_try):
            retry_count = 0
            max_retries = 3
            base_delay = 1
            model_success = False

            while retry_count <= max_retries:
                try:
                    logger.info(f"[Analysis] Sending streaming request to {model}...")
                    response = self.client.models.generate_content_stream(
                        model=model,
                        contents=prompt,
                        config=GenerateContentConfig(
                            temperature=0.7,
                            top_p=0.95,
                            top_k=40,
                            max_output_tokens=8192,
                            # Explicitly disable function calling to prevent AFC hangs
                            tool_config=ToolConfig(
                                function_calling_config=FunctionCallingConfig(
                                    mode=FunctionCallingConfigMode.NONE
                                )
                            )
                        )
                    )
                    logger.info(f"[Analysis] Stream initialized. Waiting for first chunk from {model}...")
                    model_success = True
                    
                    # Yield from response, logging first chunk
                    first_chunk_received = False
                    for chunk in response:
                        if chunk.text:
                            if not first_chunk_received:
                                logger.info(f"[Analysis] Received first chunk from {model}")
                                first_chunk_received = True
                            yield chunk.text
                    break
                except Exception as e:
                    is_overloaded = "503" in str(e) or "overloaded" in str(e).lower()

                    # If retries left for this model, wait and retry
                    if is_overloaded and retry_count < max_retries:
                        sleep_time = base_delay * (2 ** retry_count)
                        logger.warning(f"Gemini API ({model}) overloaded. Retrying in {sleep_time}s (attempt {retry_count + 1}/{max_retries})")
                        time.sleep(sleep_time)
                        retry_count += 1
                        continue

                    # If we are here, this model failed all retries (or non-retriable error)
                    # If it's the last model, or not an overload error, raise it
                    if model_index == len(models_to_try) - 1 or not is_overloaded:
                        raise e

                    # Otherwise break inner loop to try next model
                    logger.warning(f"Primary model {model} failed. Switching to fallback...")
                    break

            if model_success:
                break

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
        transcripts: Optional[List[Dict[str, Any]]] = None,
        lynch_brief: Optional[str] = None,
        use_cache: bool = True,
        model_version: str = DEFAULT_MODEL,
        character_id: Optional[str] = None
    ):
        """Get cached analysis or stream a new one."""
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        # Resolve character
        if character_id is None:
            character_id = self.db.get_user_character(user_id)
        
        # Check cache
        if use_cache:
            cached = self.db.get_lynch_analysis(user_id, symbol, character_id=character_id)
            if cached:
                yield cached['analysis_text']
                return

        # Generate new analysis
        full_text_parts = []
        for chunk in self.generate_analysis_stream_enriched(
            stock_data, history, sections, news, material_events, transcripts, lynch_brief,
            model_version, user_id, character_id
        ):
            full_text_parts.append(chunk)
            yield chunk

        # Save to cache
        final_text = "".join(full_text_parts)
        if final_text:
            self.db.save_lynch_analysis(user_id, symbol, final_text, model_version, character_id=character_id)

    def generate_unified_chart_analysis(
        self,
        stock_data: Dict[str, Any],
        history: List[Dict[str, Any]],
        sections: Optional[Dict[str, Any]] = None,
        news: Optional[List[Dict[str, Any]]] = None,
        material_events: Optional[List[Dict[str, Any]]] = None,
        transcripts: Optional[List[Dict[str, Any]]] = None,
        lynch_brief: Optional[str] = None,
        model_version: str = DEFAULT_MODEL,
        user_id: Optional[int] = None,
        character_id: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Generate a unified analysis for chart sections using the active character.

        Returns:
            Dict with 'narrative' key containing analysis text
        """
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        # Resolve character
        if character_id is None and user_id is not None:
            character_id = self.db.get_user_character(user_id)
        
        character = get_character(character_id or 'lynch')

        # Load the unified prompt template
        prompt_path = os.path.join(self.script_dir, "prompts", "analysis", "chart_analysis.md")
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()

        # Prepend expertise guidance based on user's level
        expertise_guidance = self._get_expertise_guidance(user_id)
        if expertise_guidance:
            prompt_template = f"{expertise_guidance}\n\n---\n\n{prompt_template}"

        # Prepare template variables (includes character_name)
        template_vars = self._prepare_template_vars(stock_data, history, character=character, user_id=user_id)

        # Format the prompt
        final_prompt = prompt_template.format(**template_vars)
        
        # Append investment checklist (Reference)
        checklist_path = os.path.join(self.script_dir, "prompts", character.checklist_prompt)
        with open(checklist_path, 'r') as f:
            checklist_content = f.read()
            
        final_prompt += f"\n\n---\n\n## Reference: {character.name}'s Investment Checklist\n\n{checklist_content}"

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
            # Limit each section to ~30k chars to prevent massive payloads (Fly.io OOM / API timeouts)
            SECTION_CHAR_LIMIT = 30000

            for key, title in [('business', 'Business Description'), ('risk_factors', 'Risk Factors'),
                               ('mda', "Management's Discussion & Analysis"), ('market_risk', 'Market Risk')]:
                if key in sections:
                    content = sections[key].get('content', 'Not available')
                    
                    # Truncate if necessary
                    if content and len(content) > SECTION_CHAR_LIMIT:
                        logger.info(f"Truncating {key} section in chart analysis from {len(content)} to {SECTION_CHAR_LIMIT} chars")
                        content = content[:SECTION_CHAR_LIMIT] + "... [TRUNCATED]"

                    sections_text += f"### {title}\n"
                    sections_text += f"Filed: {sections[key].get('filing_date', 'N/A')}\n"
                    sections_text += f"{content}\n\n"
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

        # Generate unified analysis with retry logic
        models_to_try = [model_version, FALLBACK_MODEL] if model_version != FALLBACK_MODEL else [model_version]
        response = None

        for model_index, model in enumerate(models_to_try):
            retry_count = 0
            max_retries = 3
            base_delay = 1
            model_success = False

            while retry_count <= max_retries:
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=final_prompt,
                        config=GenerateContentConfig(
                            temperature=0.7,
                            top_p=0.95,
                            top_k=40,
                            max_output_tokens=8192,
                            # Explicitly disable function calling to prevent AFC hangs
                            tool_config=ToolConfig(
                                function_calling_config=FunctionCallingConfig(
                                    mode=FunctionCallingConfigMode.NONE
                                )
                            )
                        )
                    )
                    model_success = True
                    break
                except Exception as e:
                    is_overloaded = "503" in str(e) or "overloaded" in str(e).lower()

                    # If retries left for this model, wait and retry
                    if is_overloaded and retry_count < max_retries:
                        sleep_time = base_delay * (2 ** retry_count)
                        logger.warning(f"Gemini API ({model}) overloaded. Retrying in {sleep_time}s (attempt {retry_count + 1}/{max_retries})")
                        time.sleep(sleep_time)
                        retry_count += 1
                        continue

                    # If we are here, this model failed all retries (or non-retriable error)
                    # If it's the last model, or not an overload error, raise it
                    if model_index == len(models_to_try) - 1 or not is_overloaded:
                        raise e

                    # Otherwise break inner loop to try next model
                    logger.warning(f"Primary model {model} failed. Switching to fallback...")
                    break

            if model_success:
                break

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
            model=model_version,
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
        model_version: str = DEFAULT_MODEL
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

        now_est = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York'))
        template_vars = {
            'symbol': stock_data.get('symbol', 'N/A'),
            'company_name': stock_data.get('company_name', 'N/A'),
            'sector': stock_data.get('sector', 'N/A'),
            'current_date': now_est.strftime('%B %d, %Y'),
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
