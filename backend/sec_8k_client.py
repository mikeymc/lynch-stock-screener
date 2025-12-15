# ABOUTME: Fetches SEC 8-K material event filings using edgartools library
# ABOUTME: Parses filings into structured events with rate limiting

from edgar import Company, set_identity
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time
import logging

logger = logging.getLogger(__name__)

# Complete SEC 8-K item code descriptions
ITEM_DESCRIPTIONS = {
    '1.01': 'Entry into Material Agreement',
    '1.02': 'Termination of Material Agreement',
    '1.03': 'Bankruptcy or Receivership',
    '1.04': 'Mine Safety Disclosure',
    '1.05': 'Material Cybersecurity Incidents',
    '2.01': 'Completion of Acquisition or Disposition',
    '2.02': 'Results of Operations and Financial Condition',
    '2.03': 'Creation of Direct Financial Obligation',
    '2.04': 'Triggering Events That Accelerate Direct Financial Obligation',
    '2.05': 'Costs Associated with Exit or Disposal Activities',
    '2.06': 'Material Impairments',
    '3.01': 'Notice of Delisting or Failure to Satisfy Listing Rule',
    '3.02': 'Unregistered Sales of Equity Securities',
    '3.03': 'Material Modification to Rights of Security Holders',
    '4.01': 'Changes in Control of Registrant',
    '4.02': 'Non-Reliance on Previously Issued Financial Statements',
    '5.01': 'Changes in Control of Registrant',
    '5.02': 'Departure/Election of Directors or Officers',
    '5.03': 'Amendments to Articles of Incorporation or Bylaws',
    '5.04': 'Temporary Suspension of Trading',
    '5.05': 'Amendments to Code of Ethics',
    '5.06': 'Change in Shell Company Status',
    '5.07': 'Submission of Matters to Vote of Security Holders',
    '5.08': 'Shareholder Nominations',
    '6.01': 'ABS Informational and Computational Material',
    '6.02': 'Change of Servicer or Trustee',
    '6.03': 'Change in Credit Enhancement',
    '6.04': 'Failure to Make Required Distribution',
    '6.05': 'Securities Act Updating Disclosure',
    '7.01': 'Regulation FD Disclosure',
    '8.01': 'Other Events',
    '9.01': 'Financial Statements and Exhibits'
}


class SEC8KClient:
    """Fetches 8-K filings from SEC EDGAR"""

    MIN_REQUEST_INTERVAL = 0.1  # 10 req/sec SEC limit
    LOOKBACK_DAYS = 365  # Default: last year

    def __init__(self, user_agent: str, edgar_fetcher=None):
        """
        Initialize SEC 8-K client

        Args:
            user_agent: SEC requires format "Company email@example.com"
            edgar_fetcher: Optional EdgarFetcher instance for sharing CIK and Company caches
        """
        self.user_agent = user_agent
        self.last_request_time = 0
        self.edgar_fetcher = edgar_fetcher
        set_identity(user_agent)
        logger.info(f"[MaterialEventsFetcher] SEC8KClient initialized with user agent: {user_agent}")

    def _rate_limit(self):
        """Enforce SEC's 10 requests/second limit"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self.last_request_time = time.time()

    def fetch_recent_8ks(
        self,
        symbol: str,
        days_back: int = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch 8-K filings from last N days

        Args:
            symbol: Stock ticker symbol
            days_back: Number of days to look back (default: LOOKBACK_DAYS)

        Returns:
            List of formatted event dicts
        """
        if days_back is None:
            days_back = self.LOOKBACK_DAYS

        self._rate_limit()

        try:
            logger.info(f"[MaterialEventsFetcher] Fetching 8-K filings for {symbol} (last {days_back} days)")
            
            # Use cached Company object if EdgarFetcher is available
            company = None
            if self.edgar_fetcher:
                cik = self.edgar_fetcher.get_cik_for_ticker(symbol)
                if cik:
                    company = self.edgar_fetcher.get_company(cik)
            
            # Fall back to direct Company creation if no EdgarFetcher or CIK not found
            if not company:
                company = Company(symbol.upper())

            # Get 8-K filings
            filings = company.get_filings(form='8-K')

            # Filter by date
            cutoff = datetime.now() - timedelta(days=days_back)
            cutoff_date = cutoff.date()  # Convert to date for comparison
            recent = []

            for filing in filings:
                # Handle different date attribute names
                filing_date = None
                if hasattr(filing, 'filing_date'):
                    filing_date = filing.filing_date
                elif hasattr(filing, 'filed'):
                    filing_date = filing.filed

                if filing_date:
                    # Convert to date if it's a datetime
                    if hasattr(filing_date, 'date'):
                        filing_date_only = filing_date.date() if callable(filing_date.date) else filing_date
                    else:
                        filing_date_only = filing_date

                    if filing_date_only >= cutoff_date:
                        recent.append(filing)

            logger.info(f"[MaterialEventsFetcher] Found {len(recent)} 8-K filings for {symbol}")

            return [self.format_8k_event(filing, symbol) for filing in recent]

        except Exception as e:
            logger.error(f"[MaterialEventsFetcher] Error fetching 8-Ks for {symbol}: {e}")
            return []

    def extract_filing_text(self, filing, max_chars: int = 10000) -> Optional[str]:
        """
        Extract plain text from 8-K filing with intelligent content extraction

        Strategy: Skip header boilerplate, extract the meaty material event content

        Args:
            filing: Filing object from edgartools
            max_chars: Maximum characters to extract (default: 10000)

        Returns:
            Extracted content or None if extraction fails
        """
        try:
            full_text = filing.text()

            if not full_text:
                return None

            if len(full_text) <= max_chars:
                return full_text

            # Strategy 1: Look for Item sections (8-K structure)
            # Item markers indicate start of actual material content
            import re
            item_match = re.search(r'(?i)Item\s+\d+\.\d+', full_text)

            if item_match:
                # Found item marker - extract from there
                start_pos = item_match.start()
                content = full_text[start_pos:start_pos + max_chars]
            else:
                # Strategy 2: Skip first 500 chars (likely header/boilerplate)
                # Then extract max_chars from there
                skip_chars = min(500, len(full_text) // 4)  # Skip first 25% or 500 chars
                content = full_text[skip_chars:skip_chars + max_chars]

            # Truncate at sentence boundary to avoid mid-sentence cutoff
            last_sentence = content.rfind('. ')
            if last_sentence > len(content) * 0.8:  # Only if not losing >20%
                content = content[:last_sentence + 1]

            return content + "\n\n[Content truncated for length]"

        except Exception as e:
            logger.error(f"[MaterialEventsFetcher] Error extracting filing text: {e}")
            return None

    def format_8k_event(self, filing, symbol: str) -> Dict[str, Any]:
        """
        Convert 8-K filing to standardized event format

        Args:
            filing: Filing object from edgartools
            symbol: Stock ticker symbol

        Returns:
            Formatted event dict matching database schema
        """
        # Extract item codes
        item_codes = self._extract_item_codes(filing)

        # Build headline from item descriptions
        headline = self._build_headline(item_codes)

        # Get filing date
        filing_date = None
        if hasattr(filing, 'filing_date'):
            filing_date = filing.filing_date
        elif hasattr(filing, 'filed'):
            filing_date = filing.filed

        if not filing_date:
            filing_date = datetime.now()

        # Convert to datetime if it's a date object
        if hasattr(filing_date, 'timestamp'):
            filing_datetime = int(filing_date.timestamp())
        else:
            # It's a date object, convert to datetime
            filing_datetime = int(datetime.combine(filing_date, datetime.min.time()).timestamp())

        # Get document URL
        doc_url = None
        if hasattr(filing, 'document_url'):
            doc_url = filing.document_url
        elif hasattr(filing, 'url'):
            doc_url = filing.url

        # Get accession number
        accession = None
        if hasattr(filing, 'accession_number'):
            accession = filing.accession_number
        elif hasattr(filing, 'accession_no'):
            accession = filing.accession_no

        # Extract just the date for filing_date field
        if hasattr(filing_date, 'date') and callable(filing_date.date):
            filing_date_only = filing_date.date()
        else:
            filing_date_only = filing_date

        # Get isoformat
        if hasattr(filing_date, 'isoformat'):
            published_iso = filing_date.isoformat()
        else:
            published_iso = str(filing_date)

        # Extract filing text content
        content_text = self.extract_filing_text(filing)

        return {
            'event_type': '8k',
            'headline': headline,
            'description': f"SEC 8-K Filing: {', '.join([f'Item {code}' for code in item_codes])}",
            'source': 'SEC',
            'url': doc_url,
            'filing_date': filing_date_only,
            'datetime': filing_datetime,
            'published_date': published_iso,
            'sec_accession_number': accession,
            'sec_item_codes': item_codes,
            'content_text': content_text
        }

    def _extract_item_codes(self, filing) -> List[str]:
        """
        Extract item codes from filing

        Args:
            filing: Filing object from edgartools

        Returns:
            List of item codes (e.g., ['1.01', '5.02'])
        """
        item_codes = []

        # Try different attribute names that edgartools might use
        if hasattr(filing, 'items'):
            items = filing.items
            if isinstance(items, str):
                # Parse string like "1.01, 5.02, 9.01"
                item_codes = [i.strip() for i in items.split(',')]
            elif isinstance(items, list):
                item_codes = items

        # If no items found, try to get from description
        if not item_codes and hasattr(filing, 'description'):
            desc = filing.description
            if desc:
                # Try to extract item codes from description
                import re
                matches = re.findall(r'\b(\d\.\d{2})\b', desc)
                if matches:
                    item_codes = matches

        # Default to 8.01 (Other Events) if no items found
        if not item_codes:
            item_codes = ['8.01']

        return item_codes

    def _build_headline(self, item_codes: List[str]) -> str:
        """
        Create readable headline from item codes

        Args:
            item_codes: List of SEC item codes

        Returns:
            Human-readable headline
        """
        if not item_codes:
            return "SEC 8-K Material Event"

        # Get descriptions for up to 2 codes (keep it concise)
        descriptions = []
        for code in item_codes[:2]:
            desc = ITEM_DESCRIPTIONS.get(code, f"Item {code}")
            descriptions.append(desc)

        if len(item_codes) > 2:
            descriptions.append(f"+ {len(item_codes) - 2} more")

        return " | ".join(descriptions)
