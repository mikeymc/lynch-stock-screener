# ABOUTME: MarketBeat earnings call transcript scraper using Playwright
# ABOUTME: Fetches full transcripts with Q&A content for any stock covered by Quartr

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class TranscriptScraper:
    """
    Scraper for earnings call transcripts from MarketBeat.
    
    MarketBeat provides free transcripts powered by Quartr.
    Uses Playwright to bypass Cloudflare protection.
    """
    
    BASE_URL = "https://www.marketbeat.com"
    EARNINGS_URL_TEMPLATE = "{base}/stocks/{exchange}/{symbol}/earnings/"
    REQUEST_DELAY = 2.0  # Seconds between requests to avoid rate limiting
    PAGE_TIMEOUT = 60000  # 60 seconds
    
    def __init__(self):
        """Initialize the transcript scraper."""
        self._browser: Optional[Browser] = None
        self._playwright = None
        self._last_request_time = 0
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._start_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_browser()
    
    async def _start_browser(self):
        """Start the Playwright browser."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            logger.info("[TranscriptScraper] Browser started")
    
    async def _close_browser(self):
        """Close the Playwright browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            logger.info("[TranscriptScraper] Browser closed")
    
    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self.REQUEST_DELAY:
            await asyncio.sleep(self.REQUEST_DELAY - time_since_last)
        
        self._last_request_time = asyncio.get_event_loop().time()
    
    def _get_exchange(self, symbol: str) -> str:
        """
        Determine the exchange for a symbol.
        Default to NASDAQ, but could be extended with a lookup.
        """
        # Common NYSE symbols
        nyse_symbols = {'JPM', 'BAC', 'WMT', 'JNJ', 'PG', 'KO', 'DIS', 'V', 'MA', 'HD'}
        if symbol.upper() in nyse_symbols:
            return 'NYSE'
        return 'NASDAQ'
    
    async def fetch_latest_transcript(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch the most recent earnings call transcript for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Dict with transcript data or None if not found
        """
        await self._start_browser()
        await self._rate_limit()
        
        exchange = self._get_exchange(symbol)
        earnings_url = self.EARNINGS_URL_TEMPLATE.format(
            base=self.BASE_URL,
            exchange=exchange,
            symbol=symbol.upper()
        )
        
        logger.info(f"[TranscriptScraper] Fetching transcript for {symbol}")
        
        page = await self._browser.new_page()
        
        try:
            # Set realistic user agent
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            # Navigate to earnings page
            await page.goto(earnings_url, wait_until='domcontentloaded', timeout=self.PAGE_TIMEOUT)
            await page.wait_for_timeout(3000)  # Wait for dynamic content
            
            # Find transcript link
            transcript_link = await self._find_transcript_link(page)
            
            if not transcript_link:
                logger.warning(f"[TranscriptScraper] No transcript link found for {symbol}")
                return None
            
            # Navigate to transcript page
            await page.goto(transcript_link, wait_until='domcontentloaded', timeout=self.PAGE_TIMEOUT)
            await page.wait_for_timeout(4000)  # Wait for transcript to load
            
            # Close any modals that may appear
            await self._close_modals(page)
            
            # Extract transcript content
            transcript_data = await self._extract_transcript(page, symbol)
            transcript_data['source_url'] = transcript_link
            
            logger.info(f"[TranscriptScraper] Successfully extracted transcript for {symbol}: {len(transcript_data.get('transcript_text', ''))} chars")
            
            return transcript_data
            
        except PlaywrightTimeout as e:
            logger.error(f"[TranscriptScraper] Timeout fetching transcript for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"[TranscriptScraper] Error fetching transcript for {symbol}: {e}")
            return None
        finally:
            await page.close()
    
    async def _find_transcript_link(self, page: Page) -> Optional[str]:
        """Find the transcript link on the earnings page."""
        try:
            # Look for links containing "transcript" text
            links = await page.query_selector_all('a')
            
            for link in links:
                text = await link.inner_text()
                if 'conference call transcript' in text.lower():
                    href = await link.get_attribute('href')
                    if href:
                        if not href.startswith('http'):
                            href = self.BASE_URL + href
                        return href
            
            # Fallback: Look for links with transcript in href
            for link in links:
                href = await link.get_attribute('href')
                if href and '#transcript' in href:
                    if not href.startswith('http'):
                        href = self.BASE_URL + href
                    return href
            
            return None
            
        except Exception as e:
            logger.error(f"[TranscriptScraper] Error finding transcript link: {e}")
            return None
    
    async def _close_modals(self, page: Page):
        """Close any modal dialogs that may appear."""
        try:
            # Look for common close button patterns
            close_buttons = await page.query_selector_all('[aria-label="Close"], .close, .modal-close, button:has-text("×")')
            for btn in close_buttons:
                try:
                    if await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(500)
                except:
                    pass
        except:
            pass
    
    async def _extract_transcript(self, page: Page, symbol: str) -> Dict[str, Any]:
        """
        Extract transcript content from the transcript page.
        
        Returns dict with:
        - symbol: Stock symbol
        - quarter: e.g., "Q4 2025"
        - earnings_date: Date of earnings call
        - transcript_text: Full transcript text
        - has_qa: Whether Q&A section was found
        - participants: List of participant names
        """
        result = {
            'symbol': symbol.upper(),
            'quarter': None,
            'fiscal_year': None,
            'earnings_date': None,
            'transcript_text': '',
            'has_qa': False,
            'participants': [],
        }
        
        try:
            # Extract quarter info from page title
            title = await page.title()
            quarter_match = re.search(r'(Q[1-4])\s+(\d{4})', title)
            if quarter_match:
                result['quarter'] = quarter_match.group(1)
                result['fiscal_year'] = int(quarter_match.group(2))
            
            # Extract date from URL or page
            url = page.url
            date_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', url)
            if date_match:
                result['earnings_date'] = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"
            
            # Get full page text content
            # First, try to expand any collapsed sections
            await self._expand_all_sections(page)
            
            # Extract text from transcript sections
            transcript_text = await self._extract_transcript_text(page)
            result['transcript_text'] = transcript_text
            
            # Check for Q&A section
            text_lower = transcript_text.lower()
            result['has_qa'] = (
                'question' in text_lower and 'answer' in text_lower
            ) or 'q&a' in text_lower
            
            # Extract participant names
            result['participants'] = await self._extract_participants(page)
            
        except Exception as e:
            logger.error(f"[TranscriptScraper] Error extracting transcript content: {e}")
        
        return result
    
    async def _expand_all_sections(self, page: Page):
        """Expand any collapsed/hidden sections in the transcript."""
        try:
            # Click "Read More" buttons
            read_more_buttons = await page.query_selector_all('button:has-text("Read More"), a:has-text("Read More"), [aria-expanded="false"]')
            for btn in read_more_buttons:
                try:
                    if await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(300)
                except:
                    pass
        except:
            pass
    
    async def _extract_transcript_text(self, page: Page) -> str:
        """Extract the main transcript text content using targeted selectors."""
        try:
            # Use JavaScript to extract transcript content more precisely
            # MarketBeat/Quartr embeds transcripts in specific div structures
            transcript = await page.evaluate('''() => {
                // Strategy 1: Find Quartr transcript sections
                // They typically have speech/speaker containers
                const speechDivs = document.querySelectorAll('[class*="speech"], [class*="Speaker"], [class*="transcript"]');
                
                if (speechDivs.length > 0) {
                    let text = [];
                    speechDivs.forEach(div => {
                        const innerText = div.innerText.trim();
                        if (innerText.length > 100) {
                            text.push(innerText);
                        }
                    });
                    if (text.join('\\n').length > 1000) {
                        return text.join('\\n\\n');
                    }
                }
                
                // Strategy 2: Look for the main content area
                // Find sections after "Presentation" or "Participants" headers
                const body = document.body.innerText;
                
                // Try to find the start of actual transcript content
                const markers = ['Presentation', 'Opening Remarks', 'Conference Call', 'Good morning', 'Good afternoon'];
                let startPos = -1;
                
                for (const marker of markers) {
                    const pos = body.indexOf(marker);
                    if (pos > 0 && (startPos === -1 || pos < startPos)) {
                        startPos = pos;
                    }
                }
                
                // Try to find end of transcript (before footer content)
                const endMarkers = ['Related Articles', 'More Earnings', 'Popular Articles', 'About MarketBeat'];
                let endPos = body.length;
                
                for (const marker of endMarkers) {
                    const pos = body.indexOf(marker);
                    if (pos > startPos && pos < endPos) {
                        endPos = pos;
                    }
                }
                
                if (startPos > 0) {
                    return body.substring(startPos, endPos);
                }
                
                // Strategy 3: Just return main content area
                const main = document.querySelector('main, article, .content-wrapper, [role="main"]');
                if (main) {
                    return main.innerText;
                }
                
                return body;
            }''')
            
            if transcript:
                return self._clean_transcript_text(transcript)
            
            return ''
            
        except Exception as e:
            logger.error(f"[TranscriptScraper] Error extracting transcript text: {e}")
            return ''
    
    def _clean_transcript_text(self, text: str) -> str:
        """Clean up transcript text by removing navigation, ads, etc."""
        lines = text.split('\n')
        cleaned_lines = []
        
        # Skip navigation/header content
        skip_patterns = [
            'sign up', 'sign in', 'subscribe', 'newsletter',
            'advertisement', 'sponsored', 'cookie', 'privacy policy',
            'terms of service', 'contact us', 'about us'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            line_lower = line.lower()
            if any(pattern in line_lower for pattern in skip_patterns):
                continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    async def _extract_participants(self, page: Page) -> List[str]:
        """Extract list of call participants."""
        participants = []
        
        try:
            # Look for participant section
            text = await page.evaluate('''() => {
                const body = document.body.innerText;
                const match = body.match(/Participants[\\s\\S]*?(?=Presentation|Call Participants|$)/i);
                return match ? match[0] : '';
            }''')
            
            if text:
                # Extract names (format: "Name - Title" or "Name, Title")
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if ' - ' in line or ', ' in line:
                        # Likely a participant entry
                        name = line.split(' - ')[0].split(',')[0].strip()
                        if name and len(name) > 2 and len(name) < 50:
                            participants.append(name)
            
        except Exception as e:
            logger.debug(f"[TranscriptScraper] Error extracting participants: {e}")
        
        return participants[:20]  # Limit to first 20


async def fetch_transcript(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to fetch a transcript.
    
    Usage:
        transcript = await fetch_transcript('AAPL')
    """
    async with TranscriptScraper() as scraper:
        return await scraper.fetch_latest_transcript(symbol)


# CLI for testing
if __name__ == '__main__':
    import sys
    
    async def main():
        symbol = sys.argv[1] if len(sys.argv) > 1 else 'AAPL'
        print(f"Fetching transcript for {symbol}...")
        
        result = await fetch_transcript(symbol)
        
        if result:
            print(f"\nSymbol: {result['symbol']}")
            print(f"Quarter: {result['quarter']} {result['fiscal_year']}")
            print(f"Date: {result['earnings_date']}")
            print(f"Has Q&A: {result['has_qa']}")
            print(f"Participants: {result['participants'][:5]}")
            print(f"Transcript length: {len(result['transcript_text']):,} chars")
            print(f"\nFirst 1000 chars:")
            print(result['transcript_text'][:1000])
        else:
            print("No transcript found")
    
    asyncio.run(main())
