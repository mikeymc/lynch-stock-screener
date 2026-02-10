# ABOUTME: Deliberation mixin for consensus building via Gemini AI
# ABOUTME: Handles Phase 4 of strategy execution with parallel deliberation

import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai

logger = logging.getLogger(__name__)


class DeliberationMixin:
    """Phase 4: Consensus building via Gemini deliberation."""

    def _conduct_deliberation(
        self,
        user_id: int,
        symbol: str,
        lynch_thesis: str,
        lynch_verdict: str,
        buffett_thesis: str,
        buffett_verdict: str,
        lynch_timestamp: Optional[datetime] = None,
        buffett_timestamp: Optional[datetime] = None
    ) -> tuple[str, str]:
        """Conduct deliberation between Lynch and Buffett to reach consensus.

        Args:
            user_id: User ID (ignored, uses System User 0 for shared cache)
            symbol: Stock symbol
            lynch_thesis: Lynch's full thesis text
            lynch_verdict: Lynch's verdict (BUY/WATCH/AVOID)
            buffett_thesis: Buffett's full thesis text
            buffett_verdict: Buffett's verdict (BUY/WATCH/AVOID)
            lynch_timestamp: Timestamp when Lynch thesis was generated
            buffett_timestamp: Timestamp when Buffett thesis was generated

        Returns:
            Tuple of (deliberation_text, final_verdict)
        """
        import os
        import time
        from google.genai.types import GenerateContentConfig

        # Check cache first (Force System User 0)
        cached = self.db.get_deliberation(0, symbol)
        if cached:
            # Check for invalidation based on timestamps
            is_stale = False
            cached_time = cached['generated_at']

            # Ensure timezone awareness for comparison if needed
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=None) # Assume naive if inputs are naive

            invalidation_reason = ""

            if lynch_timestamp:
                if lynch_timestamp.tzinfo is None:
                    lynch_timestamp = lynch_timestamp.replace(tzinfo=None)
                if cached_time < lynch_timestamp:
                    is_stale = True
                    invalidation_reason = f"Lynch thesis newer ({lynch_timestamp} > {cached_time})"

            if not is_stale and buffett_timestamp:
                if buffett_timestamp.tzinfo is None:
                    buffett_timestamp = buffett_timestamp.replace(tzinfo=None)
                if cached_time < buffett_timestamp:
                    is_stale = True
                    invalidation_reason = f"Buffett thesis newer ({buffett_timestamp} > {cached_time})"

            if not is_stale:
                logger.info(f"[Deliberation] Using cached deliberation for {symbol}")
                print(f"    Using cached deliberation from {cached['generated_at']}")
                return cached['deliberation_text'], cached['final_verdict']
            else:
                logger.info(f"[Deliberation] Cache invalid for {symbol}: {invalidation_reason}")
                print(f"    Cache invalid: {invalidation_reason}")
                print(f"    Regenerating deliberation...")

        print(f"    No cached deliberation found, generating new one...")

        # Load deliberation prompt from file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_path = os.path.join(current_dir, 'deliberation_prompt.md')
        
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()

        prompt = prompt_template.format(
            symbol=symbol,
            lynch_verdict=lynch_verdict,
            lynch_thesis=lynch_thesis,
            buffett_verdict=buffett_verdict,
            buffett_thesis=buffett_thesis
        )

        # Retry configuration
        models = ['gemini-3-flash-preview', 'gemini-2.5-flash']
        max_retries = 3
        base_delay = 2  # Initialize base delay for exponential backoff
        client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

        for model in models:
            retry_count = 0
            while retry_count < max_retries:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=GenerateContentConfig(temperature=0.7)
                    )
                    
                    text = response.text
                    
                    # Extract verdict
                    import re
                    match = re.search(r'\*\*\[?(BUY|WATCH|AVOID)\]?\*\*', text, re.IGNORECASE)
                    verdict = match.group(1).upper() if match else "WATCH" # Default to WATCH if unclear

                    # Save to cache (Force System User 0)
                    self.db.save_deliberation(0, symbol, text, verdict, model)
                    
                    return text, verdict

                except Exception as e:
                    error_msg = str(e)  # Capture error message for logging
                    logger.warning(f"[Deliberation] {model} failed (attempt {retry_count+1}/{max_retries + 1}): {error_msg}. Retrying in {2 * (retry_count + 1)}s...")
                    retry_count += 1

                    if retry_count <= max_retries:
                        delay = base_delay * (2 ** (retry_count - 1))
                        logger.warning(f"[Deliberation] {model} failed (attempt {retry_count}/{max_retries + 1}): {error_msg}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.warning(f"[Deliberation] {model} failed after {max_retries + 1} attempts: {error_msg}")
                        break

        # All models failed
        raise Exception(f"Deliberation failed for {symbol} after trying all models with retries")

    def _deliberate(
        self,
        enriched: List[Dict[str, Any]],
        run_id: int,
        conditions: Dict[str, Any] = None,
        user_id: int = None,
        job_id: Optional[int] = None,
        held_symbols: set = None,
        holdings: Dict[str, Any] = None,
        symbols_of_held_stocks_with_failing_scores: set = None
    ) -> tuple[List[Dict[str, Any]], List]:
        """Apply consensus logic to determine final decisions (Parallelized).

        For stocks with theses, conducts deliberation between Lynch and Buffett.
        Otherwise, uses score-based consensus evaluation.

        Args:
            enriched: Stocks with scores and optional thesis data
            run_id: Current run ID for logging
            conditions: Strategy conditions (for thesis_verdict_required filtering)
            user_id: User ID who owns the strategy
            job_id: Optional job ID for progress reporting
            held_symbols: Set of symbols currently held in the portfolio
            holdings: Dict of current holdings (symbol → holding data) for exit sizing
            exit_only_symbols: Symbols that are held but failed addition scoring — BUY
                verdicts for these are treated as HOLD (not added to buy decisions)

        Returns:
            Tuple of (buy_decisions, deliberation_exits) where deliberation_exits
            contains ExitSignal objects for held positions that received AVOID.
        """
        from strategy_executor.models import ExitSignal

        decisions = []
        deliberation_exits = []
        held_symbols = held_symbols or set()
        holdings = holdings or {}
        conditions = conditions or {}
        symbols_of_held_stocks_with_failing_scores = symbols_of_held_stocks_with_failing_scores or set()
        thesis_verdicts_required = conditions.get('thesis_verdict_required', [])
        
        total = len(enriched)
        
        # Helper for parallel execution
        def process_deliberation(stock):
            symbol = stock['symbol']

            # If we have both theses, conduct deliberation
            lynch_thesis = stock.get('lynch_thesis')
            buffett_thesis = stock.get('buffett_thesis')

            if lynch_thesis and buffett_thesis:
                # print(f"  Conducting deliberation for {symbol}...") # Reduced logging noise

                try:
                    deliberation_text, final_verdict = self._conduct_deliberation(
                        user_id=user_id,
                        symbol=symbol,
                        lynch_thesis=lynch_thesis,
                        lynch_verdict=stock.get('lynch_thesis_verdict', 'UNKNOWN'),
                        buffett_thesis=buffett_thesis,
                        buffett_verdict=stock.get('buffett_thesis_verdict', 'UNKNOWN'),
                        lynch_timestamp=stock.get('lynch_thesis_timestamp'),
                        buffett_timestamp=stock.get('buffett_thesis_timestamp')
                    )

                    stock['deliberation'] = deliberation_text
                    stock['final_verdict'] = final_verdict
                    # print(f"    Final verdict after deliberation: {final_verdict}")

                except Exception as e:
                    logger.error(f"Deliberation failed for {symbol}: {e}")
                    stock['final_verdict'] = None
                    stock['deliberation'] = None
                    # print(f"    Deliberation FAILED: {e}")

                # Check if final verdict meets requirements
                if thesis_verdicts_required:
                    final_verdict = stock.get('final_verdict')
                    if final_verdict not in thesis_verdicts_required:
                        # Record as SKIP
                        self.db.create_strategy_decision(
                            run_id=run_id,
                            symbol=symbol,
                            lynch_score=stock.get('lynch_score'),
                            lynch_status=stock.get('lynch_status'),
                            buffett_score=stock.get('buffett_score'),
                            buffett_status=stock.get('buffett_status'),
                            consensus_score=None,
                            consensus_verdict=None,  # Was 'SKIP' - violated constraint
                            thesis_verdict=final_verdict,
                            thesis_summary=stock.get('deliberation', '')[:500] if stock.get('deliberation') else None,
                            thesis_full=stock.get('deliberation'),
                            final_decision='SKIP',
                            decision_reasoning=f"Deliberation verdict '{final_verdict}' not in required: {thesis_verdicts_required}"
                        )
                        return None # Not a BUY decision

                # If verdict is BUY, return it
                final_decision = 'SKIP'
                if stock.get('final_verdict') == 'BUY':
                    final_decision = 'BUY'

                # Record decision
                decision_id = self.db.create_strategy_decision(
                    run_id=run_id,
                    symbol=symbol,
                    lynch_score=stock.get('lynch_score'),
                    lynch_status=stock.get('lynch_status'),
                    buffett_score=stock.get('buffett_score'),
                    buffett_status=stock.get('buffett_status'),
                    consensus_score=None,
                    consensus_verdict=stock.get('final_verdict'),
                    thesis_verdict=stock.get('final_verdict'),
                    thesis_summary=stock.get('deliberation', '')[:500] if stock.get('deliberation') else None,
                    thesis_full=stock.get('deliberation'),
                    final_decision=final_decision,
                    decision_reasoning=f"Deliberation result: {stock.get('final_verdict')}"
                )

                if final_decision == 'BUY':
                    if symbol in symbols_of_held_stocks_with_failing_scores:
                        # Held stock that failed addition scoring — BUY means HOLD, not an addition
                        return None
                    stock['id'] = decision_id
                    stock['decision_id'] = decision_id
                    return stock

                # Emit an exit signal for held positions that received AVOID
                if stock.get('final_verdict') == 'AVOID' and symbol in held_symbols:
                    holding = holdings.get(symbol, {})
                    quantity = holding.get('quantity', 0)
                    current_value = holding.get('current_value', 0.0)
                    gain_pct = holding.get('gain_pct', 0.0)
                    return {'_exit_signal': ExitSignal(
                        symbol=symbol,
                        quantity=quantity,
                        reason=f"Deliberation AVOID: {stock.get('deliberation', '')[:200]}",
                        current_value=current_value,
                        gain_pct=gain_pct
                    )}

                return None

            else:
                # No theses available - SKIP
                # We now strictly require AI deliberation to trade.
                # print(f"    ⚠ Skipping {symbol}: No theses generated for deliberation")
                self.db.create_strategy_decision(
                    run_id=run_id,
                    symbol=symbol,
                    lynch_score=stock.get('lynch_score'),
                    lynch_status=stock.get('lynch_status'),
                    buffett_score=stock.get('buffett_score'),
                    buffett_status=stock.get('buffett_status'),
                    consensus_score=None,
                    consensus_verdict=None,  # Was 'SKIP' - violated constraint
                    thesis_verdict=None,
                    thesis_summary=None,
                    thesis_full=None,
                    final_decision='SKIP',
                    decision_reasoning="Skipped: No theses generated for AI deliberation"
                )
                return None

        # Execute in parallel
        completed = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_deliberation, stock): stock for stock in enriched}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        if '_exit_signal' in result:
                            deliberation_exits.append(result['_exit_signal'])
                        else:
                            decisions.append(result)
                except Exception as e:
                    logger.error(f"Deliberation worker failed: {e}")

                completed += 1

                # Report progress every 10 items
                if job_id and (completed % 10 == 0 or completed == total):
                    pct = 60 + int((completed / total) * 30) # Phase 4 is 60-90% of total job
                    self.db.update_job_progress(
                        job_id,
                        progress_pct=pct,
                        progress_message=f'Deliberated on {completed}/{total} stocks ({len(decisions)} BUYs)',
                        processed_count=completed,
                        total_count=total
                    )
                    # Log every 10 completions
                    print(f"  Deliberated on {completed}/{total} stocks")

        return decisions, deliberation_exits
