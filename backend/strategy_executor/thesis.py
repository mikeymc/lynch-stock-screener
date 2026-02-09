# ABOUTME: Thesis generation mixin for AI investment analysis
# ABOUTME: Handles Phase 3 of strategy execution with parallel thesis generation

import logging
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from strategy_executor.utils import log_event

logger = logging.getLogger(__name__)


class ThesisMixin:
    """Phase 3: AI thesis generation and verdict extraction."""

    def _generate_theses(
        self,
        scored: List[Dict[str, Any]],
        run_id: int,
        user_id: int,
        job_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Generate investment theses for scored stocks (Parallelized).

        Generates theses from BOTH Lynch and Buffett characters, each with
        their own verdict (BUY/WATCH/AVOID).

        Args:
            scored: List of scored stock data
            run_id: Current run ID for logging
            user_id: User ID (ignored, uses System User 0 for shared cache)
            job_id: Optional job ID for progress reporting

        Returns:
            List of stocks enriched with thesis data from both characters
        """
        total = len(scored)
        log_event(self.db, run_id, f"Generating theses for {total} stocks")
        enriched = []

        if not scored:
            return []
            
        # Helper function for parallel execution
        def process_stock(stock):
            symbol = stock['symbol']
            try:
                # Get stock data for thesis generation
                stock_metrics = self.db.get_stock_metrics(symbol)
                if not stock_metrics:
                    logger.warning(f"No metrics for {symbol}, skipping thesis")
                    stock['lynch_thesis_verdict'] = None
                    stock['buffett_thesis_verdict'] = None
                    return stock

                # Get earnings history
                history = self.db.get_earnings_history(symbol)

                # Generate Lynch thesis (Force System User 0)
                lynch_thesis_text = ""
                for chunk in self.analyst.get_or_generate_analysis(
                    user_id=0, # Force System User for shared cache
                    symbol=symbol,
                    stock_data=stock_metrics,
                    history=history or [],
                    use_cache=True,
                    character_id='lynch'
                ):
                    lynch_thesis_text += chunk

                lynch_verdict = self._extract_thesis_verdict(lynch_thesis_text)
                stock['lynch_thesis'] = lynch_thesis_text
                stock['lynch_thesis_verdict'] = lynch_verdict

                # Fetch timestamp for cache invalidation (Force System User 0)
                lynch_meta = self.db.get_lynch_analysis(0, symbol, character_id='lynch')
                stock['lynch_thesis_timestamp'] = lynch_meta.get('generated_at') if lynch_meta else None

                # Generate Buffett thesis (Force System User 0)
                buffett_thesis_text = ""
                for chunk in self.analyst.get_or_generate_analysis(
                    user_id=0, # Force System User for shared cache
                    symbol=symbol,
                    stock_data=stock_metrics,
                    history=history or [],
                    use_cache=True,
                    character_id='buffett'
                ):
                    buffett_thesis_text += chunk

                buffett_verdict = self._extract_thesis_verdict(buffett_thesis_text)
                stock['buffett_thesis'] = buffett_thesis_text
                stock['buffett_thesis_verdict'] = buffett_verdict

                # Fetch timestamp for cache invalidation (Force System User 0)
                buffett_meta = self.db.get_lynch_analysis(0, symbol, character_id='buffett')
                stock['buffett_thesis_timestamp'] = buffett_meta.get('generated_at') if buffett_meta else None

                logger.debug(f"{symbol}: Lynch={lynch_verdict}, Buffett={buffett_verdict}")
                return stock

            except Exception as e:
                logger.warning(f"Failed to generate thesis for {symbol}: {e}")
                stock['lynch_thesis_verdict'] = None
                stock['buffett_thesis_verdict'] = None
                return stock

        # Execute in parallel
        completed = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_stock, stock): stock for stock in scored}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    enriched.append(result)
                except Exception as e:
                    logger.error(f"Thesis generation worker failed: {e}")
                
                completed += 1
                
                # Report progress every 10 items
                if job_id and (completed % 10 == 0 or completed == total):
                    pct = 20 + int((completed / total) * 40) # Phase 3 is 20-60% of total job
                    self.db.update_job_progress(
                        job_id,
                        progress_pct=pct,
                        progress_message=f'Generated theses for {completed}/{total} stocks',
                        processed_count=completed,
                        total_count=total
                    )
                    # Log every 10 completions
                    print(f"  Generated theses for {completed}/{total} stocks")

        log_event(self.db, run_id, f"Thesis generation complete for {len(enriched)} stocks")
        return enriched

    def _extract_thesis_verdict(self, thesis_text: str) -> Optional[str]:
        """Extract BUY/WATCH/AVOID verdict from thesis text.

        The thesis typically starts with '## Bottom Line' followed by
        **BUY**, **WATCH**, or **AVOID**.
        """
        if not thesis_text:
            print("      WARNING: No thesis text to extract verdict from")
            return None

        # Look for verdict markers
        text_upper = thesis_text.upper()

        # Check for explicit verdict patterns
        if '**BUY**' in thesis_text or 'VERDICT: BUY' in text_upper:
            print("      Found BUY verdict (explicit)")
            return 'BUY'
        elif '**WATCH**' in thesis_text or 'VERDICT: WATCH' in text_upper:
            print("      Found WATCH verdict (explicit)")
            return 'WATCH'
        elif '**AVOID**' in thesis_text or 'VERDICT: AVOID' in text_upper:
            print("      Found AVOID verdict (explicit)")
            return 'AVOID'

        # Fallback: look in first 500 chars for verdict keywords
        first_section = text_upper[:500]
        if 'BUY' in first_section and 'AVOID' not in first_section:
            print("      Found BUY verdict (fallback in first 500 chars)")
            return 'BUY'
        elif 'AVOID' in first_section:
            print("      Found AVOID verdict (fallback in first 500 chars)")
            return 'AVOID'
        elif 'WATCH' in first_section or 'HOLD' in first_section:
            print("      Found WATCH verdict (fallback in first 500 chars)")
            return 'WATCH'

        print(f"      WARNING: Could not extract verdict. First 200 chars: {thesis_text[:200]}")
        return None
