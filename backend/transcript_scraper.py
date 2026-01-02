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

    def _is_browser_alive(self) -> bool:
        """Check if browser is still connected."""
        return self._browser is not None and self._browser.is_connected
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._start_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_browser()
    
    async def _start_browser(self):
        """Start the Playwright browser, restarting if dead."""
        if not self._is_browser_alive():
            # Clean up dead browser if exists
            if self._browser is not None:
                logger.warning("[TranscriptScraper] Browser died, restarting...")
                try:
                    await self._browser.close()
                except Exception:
                    pass  # Already dead
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            logger.info("[TranscriptScraper] Browser started")
    
    async def _close_browser(self):
        """Close the Playwright browser (tolerant of already-dead browsers)."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass  # Already dead, ignore
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
            logger.info("[TranscriptScraper] Browser closed")

    async def restart_browser(self):
        """Force restart the browser (for periodic cleanup to prevent memory buildup)."""
        logger.info("[TranscriptScraper] Restarting browser...")
        await self._close_browser()
        await self._start_browser()

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
        logger.info(f"[TranscriptScraper] [{symbol}] Step 1: Ensuring browser is started...")
        await self._start_browser()
        
        logger.info(f"[TranscriptScraper] [{symbol}] Step 2: Rate limiting...")
        await self._rate_limit()
        
        exchange = self._get_exchange(symbol)
        earnings_url = self.EARNINGS_URL_TEMPLATE.format(
            base=self.BASE_URL,
            exchange=exchange,
            symbol=symbol.upper()
        )
        
        logger.info(f"[TranscriptScraper] [{symbol}] Step 3: Opening new page...")
        try:
            page = await self._browser.new_page()
        except Exception as e:
            if "Connection closed" in str(e):
                logger.warning(f"[TranscriptScraper] [{symbol}] Browser connection lost, restarting...")
                await self._close_browser()
                await self._start_browser()
                page = await self._browser.new_page()
            else:
                raise

        try:
            # Set realistic user agent
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            # Navigate to earnings page
            logger.info(f"[TranscriptScraper] [{symbol}] Step 4: Navigating to earnings page: {earnings_url}")
            await page.goto(earnings_url, wait_until='domcontentloaded', timeout=self.PAGE_TIMEOUT)
            
            logger.info(f"[TranscriptScraper] [{symbol}] Step 5: Waiting 3s for dynamic content...")
            await page.wait_for_timeout(3000)
            
            # Find transcript link
            logger.info(f"[TranscriptScraper] [{symbol}] Step 6: Searching for transcript link...")
            transcript_link = await self._find_transcript_link(page)
            
            if not transcript_link:
                logger.warning(f"[TranscriptScraper] [{symbol}] No transcript link found")
                return None
            
            logger.info(f"[TranscriptScraper] [{symbol}] Step 7: Found link, navigating to: {transcript_link}")
            await page.goto(transcript_link, wait_until='domcontentloaded', timeout=self.PAGE_TIMEOUT)
            
            logger.info(f"[TranscriptScraper] [{symbol}] Step 8: Waiting 4s for transcript to load...")
            await page.wait_for_timeout(4000)
            
            # Close any modals
            logger.info(f"[TranscriptScraper] [{symbol}] Step 9: Closing modals...")
            await self._close_modals(page)
            
            # Extract transcript content
            logger.info(f"[TranscriptScraper] [{symbol}] Step 10: Extracting transcript text...")
            transcript_data = await self._extract_transcript(page, symbol)
            transcript_data['source_url'] = transcript_link
            
            logger.info(f"[TranscriptScraper] [{symbol}] DONE: Extracted {len(transcript_data.get('transcript_text', ''))} chars")
            
            return transcript_data
            
        except PlaywrightTimeout as e:
            logger.error(f"[TranscriptScraper] [{symbol}] TIMEOUT: {e}")
            return None
        except Exception as e:
            logger.error(f"[TranscriptScraper] [{symbol}] ERROR: {e}")
            return None
        finally:
            logger.info(f"[TranscriptScraper] [{symbol}] Closing page...")
            await page.close()
    
    async def _find_transcript_link(self, page: Page) -> Optional[str]:
        """Find the transcript link on the earnings page using fast JS evaluation."""
        import asyncio
        
        try:
            # Use JavaScript to find link in a single call instead of slow Python loop
            # Add timeout to prevent hanging on problematic pages
            async def evaluate_with_timeout():
                return await page.evaluate('''() => {
                    // Look for links containing "conference call transcript" text
                    const links = Array.from(document.querySelectorAll('a'));
                    
                    for (const link of links) {
                        const text = (link.innerText || '').toLowerCase();
                        if (text.includes('conference call transcript')) {
                            return link.href;
                        }
                    }
                    
                    // Fallback: Look for links with #transcript in href
                    for (const link of links) {
                        if (link.href && link.href.includes('#transcript')) {
                            return link.href;
                        }
                    }
                    
                    return null;
                }''')
            
            # 10 second timeout for the JS evaluation
            transcript_link = await asyncio.wait_for(evaluate_with_timeout(), timeout=10.0)
            return transcript_link
            
        except asyncio.TimeoutError:
            logger.warning(f"[TranscriptScraper] Timeout during link search (10s)")
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
            # Use JavaScript to extract transcript content using verified DOM structure
            # MarketBeat structure: div#transcriptPresentation > section.transcript-line-* > speaker/content
            transcript = await page.evaluate('''() => {
                // Strategy 1: Use precise MarketBeat selectors (verified working)
                const container = document.querySelector('div#transcriptPresentation');
                
                if (container) {
                    const sections = container.querySelectorAll('section.transcript-line-left, section.transcript-line-right');
                    
                    if (sections.length > 0) {
                        const turns = [];
                        
                        sections.forEach(section => {
                            const speakerDiv = section.querySelector('div.transcript-line-speaker');
                            let name = '';
                            let title = '';
                            let timestamp = '';
                            
                            if (speakerDiv) {
                                // Get speaker name (exclude nested title element)
                                const nameEl = speakerDiv.querySelector('div.font-weight-bold');
                                if (nameEl) {
                                    const clone = nameEl.cloneNode(true);
                                    const secondary = clone.querySelector('.secondary-title');
                                    if (secondary) secondary.remove();
                                    name = clone.innerText.trim();
                                }
                                
                                // Get title if present
                                const titleEl = speakerDiv.querySelector('div.secondary-title');
                                if (titleEl) title = titleEl.innerText.trim();
                                
                                // Get timestamp
                                const timeEl = speakerDiv.querySelector('time');
                                if (timeEl) timestamp = timeEl.innerText.trim();
                            }
                            
                            // Get content
                            const contentEl = section.querySelector('p');
                            const content = contentEl ? contentEl.innerText.trim() : '';
                            
                            if (name && content) {
                                // Format: [timestamp] Speaker Name (Title)\\nContent
                                let header = `[${timestamp}] ${name}`;
                                if (title) header += ` (${title})`;
                                turns.push(header + '\\n' + content);
                            }
                        });
                        
                        if (turns.length > 0) {
                            // Join with double newlines for clear separation
                            return turns.join('\\n\\n');
                        }
                    }
                }
                
                // Strategy 2: Fallback - look for common transcript class patterns
                const fallbackSelectors = [
                    '[class*="transcript-content"]',
                    '[class*="TranscriptContent"]',
                    'main article'
                ];
                
                for (const selector of fallbackSelectors) {
                    const el = document.querySelector(selector);
                    if (el && el.innerText.length > 1000) {
                        return el.innerText;
                    }
                }
                
                // Strategy 3: Body text between markers
                const body = document.body.innerText;
                const markers = ['Presentation', 'Opening Remarks', 'Conference Call'];
                let startPos = -1;
                
                for (const marker of markers) {
                    const pos = body.indexOf(marker);
                    if (pos > 0 && (startPos === -1 || pos < startPos)) {
                        startPos = pos;
                    }
                }
                
                const endMarkers = ['Related Articles', 'More Earnings', 'About MarketBeat'];
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
