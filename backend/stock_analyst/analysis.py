# ABOUTME: Streaming analysis generation and cache management for stock analyses
# ABOUTME: Handles AI model retry logic with fallback for analysis streaming

import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from google.genai.types import GenerateContentConfig, ToolConfig, FunctionCallingConfig, FunctionCallingConfigMode

logger = logging.getLogger(__name__)

from stock_analyst.core import AVAILABLE_MODELS, DEFAULT_MODEL, FALLBACK_MODEL


class AnalysisMixin:
    """Streaming analysis generation and cache management."""

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
        symbol = stock_data.get('symbol', 'UNKNOWN')
        t0 = time.time()
        symbol = stock_data.get('symbol', 'UNKNOWN')
        logger.info(f"[Thesis][{symbol}] (Character: {character_id}) Constructing prompt (Model: {model_version})")
        prompt = self.format_prompt(stock_data, history, sections, news, material_events,
                                    transcripts=transcripts, lynch_brief=lynch_brief,
                                    user_id=user_id, character_id=character_id)
        t_prompt = (time.time() - t0) * 1000
        prompt_size_bytes = len(prompt.encode('utf-8'))
        logger.info(f"[Thesis][{symbol}] (Character: {character_id}) Prompt constructed in {t_prompt:.2f}ms. Size: {len(prompt)} chars ({prompt_size_bytes/1024:.2f} KB)")

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
                    logger.info(f"[Analysis][{symbol}] (Character: {character_id}) Sending streaming request to {model}...")
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
                    logger.info(f"[Analysis][{symbol}] (Character: {character_id}) Stream initialized. Waiting for first chunk from {model}...")
                    model_success = True

                    # Yield from response, logging first chunk
                    first_chunk_received = False
                    for chunk in response:
                        if chunk.text:
                            if not first_chunk_received:
                                logger.info(f"[Analysis][{symbol}] (Character: {character_id}) Received first chunk from {model}")
                                first_chunk_received = True
                            yield chunk.text
                    break
                except Exception as e:
                    is_overloaded = "503" in str(e) or "overloaded" in str(e).lower()

                    # If retries left for this model, wait and retry
                    if is_overloaded and retry_count < max_retries:
                        sleep_time = base_delay * (2 ** retry_count)
                    if is_overloaded and retry_count < max_retries:
                        sleep_time = base_delay * (2 ** retry_count)
                        logger.warning(f"[Analysis][{symbol}] (Character: {character_id}) Gemini API ({model}) overloaded. Retrying in {sleep_time}s (attempt {retry_count + 1}/{max_retries})")
                        time.sleep(sleep_time)
                        retry_count += 1
                        continue

                    # If we are here, this model failed all retries (or non-retriable error)
                    # If it's the last model, or not an overload error, raise it
                    if model_index == len(models_to_try) - 1 or not is_overloaded:
                        raise e

                    # Otherwise break inner loop to try next model
                    logger.warning(f"[Analysis][{symbol}] (Character: {character_id}) Primary model {model} failed. Switching to fallback...")
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
        max_age_days: Optional[float] = None,
        model_version: str = DEFAULT_MODEL,
        character_id: Optional[str] = None
    ):
        """Get cached analysis or stream a new one.

        Args:
            max_age_days: If provided, cached analysis older than this (in days) is considered stale.
                          Float allowed (e.g., 0.5 = 12 hours).
        """
        if model_version not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid model: {model_version}. Must be one of {AVAILABLE_MODELS}")

        # Resolve character
        if character_id is None:
            character_id = self.db.get_user_character(user_id)

        # Check cache
        if use_cache:
            cached = self.db.get_lynch_analysis(user_id, symbol, character_id=character_id, allow_fallback=True)
            if cached:
                is_stale = False

                # Check 1: Max Age
                if max_age_days is not None:
                    age_delta = datetime.now(timezone.utc) - cached['generated_at'].replace(tzinfo=timezone.utc)
                    age_days = age_delta.total_seconds() / 86400
                    if age_days > max_age_days:
                        logger.info(f"[{symbol}] Cached analysis stale (Age: {age_days:.1f}d > Limit: {max_age_days}d)")
                        is_stale = True

                # Check 2: Data Freshness (Event Trigger)
                # If we have stock_data.last_updated, check if analysis is older than new data
                if not is_stale and stock_data.get('last_updated'):
                    # Ensure timezone awareness for comparison
                    last_data_update = stock_data['last_updated']
                    if last_data_update.tzinfo is None:
                        last_data_update = last_data_update.replace(tzinfo=timezone.utc)

                    analysis_date = cached['generated_at'].replace(tzinfo=timezone.utc)

                    # Only trigger if data is significantly newer (e.g. > 1 hour buffer to avoid race conditions)
                    # or if specifically requested via max_age_days
                    if last_data_update > analysis_date:
                        # Log but don't force invalidate unless max_age_days is also set/breached
                        # This prevents constant regeneration just because price ticked
                        pass

                if not is_stale:
                    logger.info(f"[Analysis][{symbol}] (Character: {character_id}) Found fresh cached analysis. Skipping generation.")
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
