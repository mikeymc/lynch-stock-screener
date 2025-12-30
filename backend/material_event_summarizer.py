# ABOUTME: Generates AI summaries for high-value SEC 8-K material events
# ABOUTME: Supports earnings (2.02), M&A (2.01), agreements (1.01), cybersecurity (1.05), impairments (2.06), and accounting issues (4.02)

import os
from typing import Dict, Any, Optional
from google import genai

# Item types that warrant AI summarization
SUMMARIZABLE_ITEM_CODES = {
    '2.02': 'Results of Operations and Financial Condition',
    '2.01': 'Completion of Acquisition or Disposition',
    '1.01': 'Entry into Material Agreement',
    '1.05': 'Material Cybersecurity Incidents',
    '2.06': 'Material Impairments',
    '4.02': 'Non-Reliance on Previously Issued Financial Statements',
}

# Default model for fast summaries
DEFAULT_MODEL = "gemini-2.5-flash"


class MaterialEventSummarizer:
    """Generates AI summaries for SEC 8-K material events."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the summarizer.
        
        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
        """
        self._api_key = api_key or os.getenv('GEMINI_API_KEY')
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            if self._api_key:
                self._client = genai.Client(api_key=self._api_key)
            else:
                self._client = genai.Client()
        return self._client
    
    def should_summarize(self, item_codes: list) -> bool:
        """
        Check if an event should be summarized based on its item codes.
        
        Args:
            item_codes: List of SEC item codes (e.g., ['2.02', '9.01'])
            
        Returns:
            True if any item code is in SUMMARIZABLE_ITEM_CODES
        """
        if not item_codes:
            return False
        return any(code in SUMMARIZABLE_ITEM_CODES for code in item_codes)
    
    def get_primary_item_type(self, item_codes: list) -> Optional[str]:
        """
        Get the primary summarizable item code from a list.
        
        Args:
            item_codes: List of SEC item codes
            
        Returns:
            The first summarizable item code found, or None
        """
        if not item_codes:
            return None
        for code in item_codes:
            if code in SUMMARIZABLE_ITEM_CODES:
                return code
        return None
    
    def generate_summary(
        self,
        event_data: Dict[str, Any],
        company_name: str,
        model_version: str = DEFAULT_MODEL
    ) -> str:
        """
        Generate an AI summary for a material event.
        
        Args:
            event_data: Event dict containing content_text, headline, sec_item_codes, etc.
            company_name: Name of the company
            model_version: Gemini model to use
            
        Returns:
            Summary text (250-500 words)
            
        Raises:
            ValueError: If event has no summarizable content
        """
        content_text = event_data.get('content_text', '')
        if not content_text:
            raise ValueError("Event has no content_text to summarize")
        
        item_codes = event_data.get('sec_item_codes', [])
        primary_code = self.get_primary_item_type(item_codes)
        
        if not primary_code:
            raise ValueError(f"Event item codes {item_codes} are not summarizable")
        
        item_description = SUMMARIZABLE_ITEM_CODES[primary_code]
        headline = event_data.get('headline', 'No headline')
        filing_date = event_data.get('filing_date', 'Unknown date')
        
        # Build tailored prompt based on item type
        prompt = self._build_prompt(
            content_text=content_text,
            company_name=company_name,
            item_code=primary_code,
            item_description=item_description,
            headline=headline,
            filing_date=filing_date
        )
        
        # Generate summary
        response = self.client.models.generate_content(
            model=model_version,
            contents=prompt
        )
        
        if not response.parts:
            error_msg = "Gemini API returned no content for event summary."
            if hasattr(response, 'prompt_feedback'):
                error_msg += f" Prompt feedback: {response.prompt_feedback}"
            raise Exception(error_msg)
        
        return response.text.strip()
    
    def _build_prompt(
        self,
        content_text: str,
        company_name: str,
        item_code: str,
        item_description: str,
        headline: str,
        filing_date: str
    ) -> str:
        """Build a tailored prompt based on the item type."""
        
        # Truncate content to avoid token limits (keep first ~80K chars)
        max_content_len = 80000
        if len(content_text) > max_content_len:
            content_text = content_text[:max_content_len] + "\n\n[Content truncated for length]"
        
        # Base instructions
        base_instruction = f"""You are a financial analyst summarizing an SEC 8-K filing for investors.

**Company**: {company_name}
**Filing Type**: SEC Form 8-K (Item {item_code}: {item_description})
**Headline**: {headline}
**Filing Date**: {filing_date}

**Instructions**:
Provide a clear, investor-focused summary in 250-500 words. Write in prose (not bullet points). 
Be specific and quantitative where possible. Focus on what matters to investors.

"""
        
        # Add item-specific guidance
        if item_code == '2.02':
            # Earnings / Results of Operations
            specific_instruction = """For this earnings announcement, focus on:
- Key financial metrics: Revenue, net income, EPS (actual vs estimates if mentioned)
- Year-over-year and quarter-over-quarter comparisons
- Segment or product line performance highlights
- Forward guidance or outlook (if provided)
- Notable callouts from management (acquisitions, investments, challenges)
"""
        elif item_code == '2.01':
            # M&A / Acquisition or Disposition
            specific_instruction = """For this M&A announcement, focus on:
- What was acquired/disposed and from whom
- Transaction value and structure (cash, stock, etc.)
- Strategic rationale and expected synergies
- Expected closing timeline and conditions
- Impact on financials (revenue, earnings accretion/dilution)
"""
        elif item_code == '1.01':
            # Material Agreement
            specific_instruction = """For this material agreement, focus on:
- Parties involved and nature of the agreement
- Key terms: value, duration, exclusivity
- Strategic significance for the company
- Any material conditions or contingencies
- Expected financial impact
"""
        elif item_code == '1.05':
            # Cybersecurity Incident
            specific_instruction = """For this cybersecurity disclosure, focus on:
- Nature and scope of the incident
- What data/systems were affected
- Current status (contained, ongoing investigation)
- Estimated financial impact or remediation costs
- Steps taken to prevent future incidents
"""
        elif item_code == '2.06':
            # Material Impairments
            specific_instruction = """For this impairment disclosure, focus on:
- What assets were impaired (goodwill, intangibles, PP&E, etc.)
- Impairment amount and impact on earnings
- Reason for the impairment (market conditions, strategic change, etc.)
- Which segment or business unit was affected
- Any restructuring plans mentioned
"""
        elif item_code == '4.02':
            # Non-Reliance on Financial Statements
            specific_instruction = """For this accounting issue disclosure, focus on:
- Which financial statements can no longer be relied upon
- Nature of the error or misstatement
- Periods affected
- Expected restatement timeline
- Any internal control issues mentioned
- Impact on audit opinion or auditor relationship
"""
        else:
            specific_instruction = """Summarize the key points that investors should know about."""
        
        prompt = base_instruction + specific_instruction + f"""

**Filing Content**:
{content_text}

**Your Summary**:
"""
        
        return prompt
