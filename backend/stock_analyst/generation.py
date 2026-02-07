# ABOUTME: Generates specialized AI analyses for charts, filings, DCF models, and transcripts
# ABOUTME: Non-streaming generation methods with retry logic and JSON parsing

import os
import json
import re
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from google.genai.types import GenerateContentConfig, ToolConfig, FunctionCallingConfig, FunctionCallingConfigMode

logger = logging.getLogger(__name__)

from characters import get_character
from stock_analyst.core import AVAILABLE_MODELS, DEFAULT_MODEL, FALLBACK_MODEL


class GenerationMixin:
    """Specialized generation methods for charts, filings, DCF, and transcripts."""

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
