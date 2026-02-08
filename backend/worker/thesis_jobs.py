# ABOUTME: Thesis refresh job mixin for the background worker
# ABOUTME: Handles investment thesis generation and refresh for prioritized stocks

import logging
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class ThesisJobsMixin:
    """Mixin for thesis_refresher job type"""

    def _run_thesis_refresher(self, job_id: int, params: Dict[str, Any]):
        """
        Dedicated job to refresh investment theses for high-priority stocks.

        Orchestrates the 'Funnel & Cache' strategy:
        1. Aggregates candidates from signals (Portfolio, Earnings, Movers, Quality).
        2. Populates `thesis_refresh_queue`.
        3. Processes top PENDING items in parallel.
        """
        logger.info(f"Running thesis_refresher job {job_id}")

        limit = params.get('limit')  # Default to None (unlimited)
        force_refresh = params.get('force_refresh', False)
        targeted_symbols = params.get('symbols') # List of symbols from CLI

        # Import Analyst (will be instantiated per thread)
        from stock_analyst import StockAnalyst

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # --- STEP 1: SIGNAL AGGREGATION & QUEUE POPULATION ---

            if targeted_symbols:
                logger.info(f"Targeted refresh for {len(targeted_symbols)} symbols: {targeted_symbols}")
                # Insert targeted symbols with highest priority
                # Use executemany for efficiency
                cursor.executemany("""
                    INSERT INTO thesis_refresh_queue (symbol, reason, priority, status)
                    VALUES (%s, 'manual_cli', 200, 'PENDING')
                    ON CONFLICT (symbol) DO UPDATE SET
                        priority = 200,
                        reason = 'manual_cli',
                        status = 'PENDING',
                        updated_at = CURRENT_TIMESTAMP
                """, [(s,) for s in targeted_symbols])
                conn.commit()

            else:
                # Normal Auto-Aggregation

                # 1. User Interest: Stocks in Portfolios (Priority 100)
                self.db.update_job_progress(job_id, progress_message='Aggregating candidates from Portfolios...')
                logger.info("Aggregating Portfolio Signal...")
                cursor.execute("""
                    INSERT INTO thesis_refresh_queue (symbol, reason, priority, status)
                    SELECT DISTINCT symbol, 'portfolio', 100, 'PENDING'
                    FROM portfolio_transactions
                    WHERE quantity > 0
                    ON CONFLICT (symbol) DO UPDATE SET
                        priority = GREATEST(thesis_refresh_queue.priority, EXCLUDED.priority),
                        reason = CASE WHEN thesis_refresh_queue.priority < EXCLUDED.priority
                                 THEN EXCLUDED.reason ELSE thesis_refresh_queue.reason END,
                        status = CASE WHEN thesis_refresh_queue.status IN ('COMPLETED', 'FAILED')
                                 THEN 'PENDING' ELSE thesis_refresh_queue.status END,
                        updated_at = CURRENT_TIMESTAMP
                """)

                # 2. Market Activity: Upcoming Earnings < 7 days (Priority 50)
                # Filter: Price >= $10.00 AND Market Cap >= $500M
                self.db.update_job_progress(job_id, progress_message='Aggregating candidates from upcoming earnings...')
                logger.info("Aggregating Earnings Signal...")
                cursor.execute("""
                    INSERT INTO thesis_refresh_queue (symbol, reason, priority, status)
                    SELECT symbol, 'earnings_soon', 50, 'PENDING'
                    FROM stock_metrics
                    WHERE next_earnings_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '7 days')
                    AND price >= 10.0
                    AND market_cap >= 500000000
                    ON CONFLICT (symbol) DO UPDATE SET
                        priority = GREATEST(thesis_refresh_queue.priority, EXCLUDED.priority),
                        updated_at = CURRENT_TIMESTAMP
                """)

                # 3. Market Activity: Big Movers > 5% DROP (Priority 50)
                # Filter: Price > $10.00 AND Market Cap >= $500M (Avoid junk/penny stocks)
                # Logic: Only care about drops
                self.db.update_job_progress(job_id, progress_message='Aggregating candidates from big movers...')
                logger.info("Aggregating Big Movers Signal...")

                # Pruning: Remove stale movers that no longer meet criteria
                cursor.execute("""
                    DELETE FROM thesis_refresh_queue
                    WHERE reason = 'big_mover'
                    AND status = 'PENDING'
                    AND symbol IN (
                        SELECT symbol FROM stock_metrics
                        WHERE NOT (
                            price_change_pct <= -5.0
                            AND price >= 10.0
                            AND market_cap >= 500000000
                        )
                    )
                """)
                if cursor.rowcount > 0:
                    logger.info(f"Pruned {cursor.rowcount} stale movers from queue")

                cursor.execute("""
                    INSERT INTO thesis_refresh_queue (symbol, reason, priority, status)
                    SELECT symbol, 'big_mover', 50, 'PENDING'
                    FROM stock_metrics
                    WHERE price_change_pct <= -5.0
                    AND price >= 10.0
                    AND market_cap >= 500000000
                    ON CONFLICT (symbol) DO UPDATE SET
                        priority = GREATEST(thesis_refresh_queue.priority, EXCLUDED.priority),
                        updated_at = CURRENT_TIMESTAMP
                """)

                # 4. Quality: High Scores (Priority 10)
                # Need to join with stocks table to ensure symbol exists
                self.db.update_job_progress(job_id, progress_message='Analyzing quality scores (Lynch/Buffett)...')
                logger.info("Aggregating Quality Signal...")
                # Note: We assume 'overall_status' is in a table we can join, but stock_vectors is separate.
                # We'll use a python-side fetch for vectors since it might be complex JSON or separate logic
                from stock_vectors import StockVectors
                vectors = StockVectors(self.db)
                # Load vectors but strictly limit to avoid memory bloat
                try:
                    # Optimized vector load if possible, or just standard
                    df_vectors = vectors.load_vectors(country_filter='US')

                    # Apply Global Universe Filters (Price >= $10, Cap >= $500M)
                    # We do this BEFORE scoring to save compute and filter the queue
                    if df_vectors is not None and not df_vectors.empty:
                        original_len = len(df_vectors)
                        cursor.execute("SELECT symbol, price, market_cap FROM stock_metrics WHERE price >= 10.0 AND market_cap >= 500000000")
                        valid_universe = {row[0] for row in cursor.fetchall()}

                        # Set intersection to filter the dataframe
                        df_vectors = df_vectors[df_vectors['symbol'].isin(valid_universe)]
                        logger.info(f"Filtered Quality Universe: {original_len} -> {len(df_vectors)} stocks (Price >= $10, Cap >= $500M)")

                    if df_vectors is not None and not df_vectors.empty:
                        from lynch_criteria import LynchCriteria
                        from stock_vectors import DEFAULT_ALGORITHM_CONFIG
                        from characters.buffett import BUFFETT

                        criteria = LynchCriteria(self.db, None)

                        # 1. Lynch Scoring
                        scored_lynch = criteria.evaluate_batch(df_vectors, DEFAULT_ALGORITHM_CONFIG)

                        lynch_exc = scored_lynch[scored_lynch['overall_status'] == 'STRONG_BUY']['symbol'].tolist()
                        lynch_good = scored_lynch[scored_lynch['overall_status'] == 'BUY']['symbol'].tolist()

                        logger.info(f"Found {len(lynch_exc)} Excellent / {len(lynch_good)} Good Lynch stocks")

                        # 2. Buffett Scoring
                        # Map Buffett config to evaluate_batch expected format
                        buffett_config = {}
                        for sw in BUFFETT.scoring_weights:
                            if sw.metric == 'roe':
                                buffett_config['weight_roe'] = sw.weight
                                buffett_config['roe_excellent'] = sw.threshold.excellent
                                buffett_config['roe_good'] = sw.threshold.good
                                buffett_config['roe_fair'] = sw.threshold.fair
                            elif sw.metric == 'debt_to_earnings':
                                buffett_config['weight_debt_earnings'] = sw.weight
                                buffett_config['de_excellent'] = sw.threshold.excellent
                                buffett_config['de_good'] = sw.threshold.good
                                buffett_config['de_fair'] = sw.threshold.fair
                            elif sw.metric == 'gross_margin':
                                buffett_config['weight_gross_margin'] = sw.weight
                                buffett_config['gm_excellent'] = sw.threshold.excellent
                                buffett_config['gm_good'] = sw.threshold.good
                                buffett_config['gm_fair'] = sw.threshold.fair
                            elif sw.metric == 'earnings_consistency':
                                buffett_config['weight_consistency'] = sw.weight # Maps to shared consistency metric

                        scored_buffett = criteria.evaluate_batch(df_vectors, buffett_config)

                        buffett_exc = scored_buffett[scored_buffett['overall_status'] == 'STRONG_BUY']['symbol'].tolist()
                        buffett_good = scored_buffett[scored_buffett['overall_status'] == 'BUY']['symbol'].tolist()

                        logger.info(f"Found {len(buffett_exc)} Excellent / {len(buffett_good)} Good Buffett stocks")

                        # 3. Merge & Insert with Tiered Reasons

                        # Set arithmetic to combine sources
                        # Explicitly ensure disjoint sets: Excellent trumps Good
                        excellent_set = set(lynch_exc + buffett_exc)
                        good_set = set(lynch_good + buffett_good)

                        # Remove any excellent stocks from good set (upgrade logic)
                        good_set = good_set - excellent_set

                        all_excellent = list(excellent_set)
                        all_good = list(good_set)

                        # Insert Excellent (Priority 10) -> Force 'quality_excellent'
                        if all_excellent:
                            cursor.executemany("""
                                INSERT INTO thesis_refresh_queue (symbol, reason, priority, status)
                                VALUES (%s, 'quality_excellent', 10, 'PENDING')
                                ON CONFLICT (symbol) DO UPDATE SET
                                    priority = GREATEST(thesis_refresh_queue.priority, EXCLUDED.priority),
                                    reason = 'quality_excellent',
                                    updated_at = CURRENT_TIMESTAMP
                            """, [(s,) for s in all_excellent])

                        # Insert Good (Priority 10) -> Force 'quality_good'
                        # Since sets are disjoint, we can safely force 'quality_good' here.
                        # Any stock in this list is by definition NOT Excellent.
                        if all_good:
                            cursor.executemany("""
                                INSERT INTO thesis_refresh_queue (symbol, reason, priority, status)
                                VALUES (%s, 'quality_good', 10, 'PENDING')
                                ON CONFLICT (symbol) DO UPDATE SET
                                    priority = GREATEST(thesis_refresh_queue.priority, EXCLUDED.priority),
                                    reason = 'quality_good',
                                    updated_at = CURRENT_TIMESTAMP
                            """, [(s,) for s in all_good])

                        logger.info(f"Queued {len(all_excellent)} Excellent / {len(all_good)} Good unique stocks")

                except Exception as e:
                    logger.error(f"Error aggregating quality stocks: {e}")

                conn.commit()

            # --- STEP 2: PROCESS QUEUE ---

            # Select top N pending items
            if targeted_symbols:
                # Targeted Mode: Only process the requested symbols
                # We just updated them to PENDING/200, so they should be ready.
                cursor.execute("""
                    SELECT id, symbol, reason, priority
                    FROM thesis_refresh_queue
                    WHERE symbol = ANY(%s) AND status = 'PENDING'
                    ORDER BY priority DESC
                """, (targeted_symbols,))
                logger.info(f"Targeted mode: Selecting specific symbols {targeted_symbols}")
            else:
                # Default Mode: Process highest priority pending items up to limit
                cursor.execute("""
                    SELECT id, symbol, reason, priority
                    FROM thesis_refresh_queue
                    WHERE status = 'PENDING'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT %s
                """, (limit,))
                limit_log = f"top {limit}" if limit else "ALL"
                logger.info(f"Default mode: Selecting {limit_log} pending items")

            batch = cursor.fetchall()

            logger.info(f"Processing {len(batch)} items from thesis queue")

            if not batch:
                self.db.complete_job(job_id, result={'processed': 0, 'message': 'Queue empty or targeted symbols validation failed'})
                return

            # Mark as PROCESSING
            ids = [item[0] for item in batch]
            cursor.execute("""
                UPDATE thesis_refresh_queue
                SET status = 'PROCESSING', updated_at = CURRENT_TIMESTAMP
                WHERE id = ANY(%s)
            """, (ids,))
            conn.commit()

            # Initial progress for processing phase
            total_items = len(batch)
            self.db.update_job_progress(job_id, total_count=total_items, processed_count=0, progress_pct=0, progress_message=f'Processing {total_items} stocks (Parallel)...')

        finally:
            self.db.return_connection(conn)

        # Parallel Execution
        processed_count = 0
        error_count = 0

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_item = {
                executor.submit(
                    self._refresh_thesis_for_symbol,
                    item[1], # symbol
                    item[2], # reason
                    force_refresh
                ): item for item in batch
            }

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                symbol = item[1]
                item_id = item[0]

                try:
                    success, message = future.result()

                    # Update status
                    status = 'COMPLETED' if success else 'FAILED'
                    self.db.write_queue.put((
                        """
                        UPDATE thesis_refresh_queue
                        SET status = %s, error_message = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (status, message, item_id)
                    ))

                    self._send_heartbeat(job_id)
                    if success:
                        processed_count += 1
                    else:
                        error_count += 1

                    # Periodic progress update
                    current_done = processed_count + error_count
                    total_items = len(batch)
                    if total_items > 0 and (current_done % 5 == 0 or current_done == total_items):
                        pct = int((current_done / total_items) * 100)
                        self.db.update_job_progress(job_id, progress_pct=pct, processed_count=current_done)

                except Exception as e:
                    logger.error(f"Worker thread error key={symbol}: {e}")
                    self.db.write_queue.put((
                        "UPDATE thesis_refresh_queue SET status = 'FAILED', error_message = %s WHERE id = %s",
                        (str(e), item_id)
                    ))
                    error_count += 1

        # Flush status updates
        self.db.flush()

        result_msg = f"Processed {processed_count} stocks, {error_count} errors"
        self.db.complete_job(job_id, result={'processed': processed_count, 'errors': error_count, 'message': result_msg})

    def _refresh_thesis_for_symbol(self, symbol: str, reason: str, force_refresh: bool) -> tuple[bool, str]:
        """Process a single symbol for thesis refresh"""
        from stock_analyst import StockAnalyst
        analyst = StockAnalyst(self.db)
        try:
            # Determine max_age based on reason
            # - Portfolio: 7 days
            # - Earnings/Movers: 1 day (Force fresh)
            # - Quality Excellent: 14 days
            # - Quality Good (default fallback): 30 days

            if reason in ('earnings_soon', 'big_mover'):
                max_age_days = 1.0
            elif reason == 'portfolio':
                max_age_days = 7.0
            elif reason == 'quality_excellent':
                max_age_days = 14.0
            elif reason == 'quality_good':
                max_age_days = 30.0
            else:
                max_age_days = 30.0 # Default fallback for 'good' or unknown

            if force_refresh:
                max_age_days = 0  # Force regeneration

            # Fetch necessary data
            stock_data = self.db.get_stock_metrics(symbol)
            if not stock_data:
                return False, "Stock metrics not found"

            history = self.db.get_earnings_history(symbol)

            # Generate BOTH characters (Lynch & Buffett)
            # We consume the generator to ensure it runs

            # 1. Lynch
            for _ in analyst.get_or_generate_analysis(
                user_id=0, # System User 0 for shared cache
                symbol=symbol,
                stock_data=stock_data,
                history=history or [],
                use_cache=True, # We use cache but control staleness via max_age_days
                max_age_days=max_age_days,
                character_id='lynch'
            ):
                pass

            # 2. Buffett
            for _ in analyst.get_or_generate_analysis(
                user_id=0, # System User 0 for shared cache
                symbol=symbol,
                stock_data=stock_data,
                history=history or [],
                use_cache=True,
                max_age_days=max_age_days,
                character_id='buffett'
            ):
                pass

            return True, "Refreshed"

        except Exception as e:
            logger.error(f"Error refreshing thesis for {symbol}: {e}")
            return False, str(e)
