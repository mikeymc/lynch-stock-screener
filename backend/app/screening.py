# ABOUTME: Stock screening endpoints for running and monitoring screen sessions
# ABOUTME: Supports both legacy and v2 screening with configurable algorithms

from flask import Blueprint, jsonify, request, Response, stream_with_context, session
from app import deps
from app.helpers import clean_nan_values
from auth import require_user_auth
from stock_rescorer import StockRescorer
from stock_vectors import DEFAULT_ALGORITHM_CONFIG
import json
import logging
import time
import threading
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

screening_bp = Blueprint('screening', __name__)


@screening_bp.route('/api/screen/progress/<int:session_id>', methods=['GET'])
def get_screening_progress(session_id):
    """Get current progress of a screening session"""
    try:
        progress = deps.db.get_session_progress(session_id)
        if not progress:
            return jsonify({'error': 'Session not found'}), 404

        return jsonify(progress)

    except Exception as e:
        print(f"Error getting progress: {e}")
        return jsonify({'error': str(e)}), 500


@screening_bp.route('/api/screen/results/<int:session_id>', methods=['GET'])
def get_screening_results(session_id):
    """Get results for a screening session"""
    try:
        results = deps.db.get_session_results(session_id)

        # Enrich results with on-the-fly computed metrics
        for result in results:
            symbol = result.get('symbol')

            # Compute P/E range position from cached weekly prices
            pe_range = deps.criteria._calculate_pe_52_week_range(symbol, result.get('pe_ratio'))
            result['pe_52_week_min'] = pe_range.get('pe_52_week_min')
            result['pe_52_week_max'] = pe_range.get('pe_52_week_max')
            result['pe_52_week_position'] = pe_range.get('pe_52_week_position')

            # Compute consistency scores from earnings history
            growth_data = deps.analyzer.calculate_earnings_growth(symbol)
            if growth_data:
                # Normalize to 0-100 scale (100 = best consistency)
                raw_income = growth_data.get('income_consistency_score')
                raw_revenue = growth_data.get('revenue_consistency_score')
                result['income_consistency_score'] = max(0.0, 100.0 - (raw_income * 2.0)) if raw_income is not None else None
                result['revenue_consistency_score'] = max(0.0, 100.0 - (raw_revenue * 2.0)) if raw_revenue is not None else None
            else:
                result['income_consistency_score'] = None
                result['revenue_consistency_score'] = None

        # Clean NaN values before returning
        clean_results = [clean_nan_values(result) for result in results]
        return jsonify({'results': clean_results})
    except Exception as e:
        print(f"Error getting results: {e}")
        return jsonify({'error': str(e)}), 500


@screening_bp.route('/api/screen/stop/<int:session_id>', methods=['POST'])
def stop_screening(session_id):
    """Stop an active screening session"""
    try:
        # Check if session exists
        progress = deps.db.get_session_progress(session_id)

        if not progress:
            # Session doesn't exist (likely database was reset)


            return jsonify({
                'status': 'not_found',
                'message': f'Session {session_id} not found (database may have been reset)',
                'progress': None
            }), 404

        # Mark session as cancelled
        deps.db.cancel_session(session_id)



        return jsonify({
            'status': 'cancelled',
            'message': f'Screening stopped at {progress["processed_count"]}/{progress["total_count"]} stocks',
            'progress': progress
        })
    except Exception as e:
        print(f"Error stopping screening: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@screening_bp.route('/api/screen/v2', methods=['GET'])
def screen_stocks_v2():
    """
    Vectorized stock screening endpoint.

    Loads all stocks from database, applies user-specific scoring config,
    and returns paginated, sorted results instantly (no SSE streaming).

    Query params:
        - page: Page number (default 1)
        - limit: Results per page (default 100)
        - sort_by: Column to sort by (default 'overall_score')
        - sort_dir: Sort direction 'asc' or 'desc' (default 'desc')
        - search: Filter by symbol or company name
    """
    start_time = time.time()

    # Parse query params
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 100, type=int)
    sort_by = request.args.get('sort_by', 'overall_score')
    sort_dir = request.args.get('sort_dir', 'desc')
    search = request.args.get('search', None)

    # Check if US-only filter is enabled
    us_stocks_only = deps.db.get_setting('us_stocks_only', True)
    country_filter = 'US' if us_stocks_only else None

    # Get active character to load appropriate config
    active_character = deps.db.get_setting('active_character') or 'lynch'

    # Get user's algorithm config filtered by character
    configs = deps.db.get_algorithm_configs()
    char_configs = [c for c in configs if c.get('character') == active_character]
    db_config = char_configs[0] if char_configs else (configs[0] if configs else None)

    if db_config:
        # Build config with both Lynch and Buffett keys (evaluate_batch handles both)
        config = {
            # Lynch keys
            'peg_excellent': db_config.get('peg_excellent', 1.0),
            'peg_good': db_config.get('peg_good', 1.5),
            'peg_fair': db_config.get('peg_fair', 2.0),
            'debt_excellent': db_config.get('debt_excellent', 0.5),
            'debt_good': db_config.get('debt_good', 1.0),
            'debt_moderate': db_config.get('debt_moderate', 2.0),
            'inst_own_min': db_config.get('inst_own_min', 0.20),
            'inst_own_max': db_config.get('inst_own_max', 0.60),
            'weight_peg': db_config.get('weight_peg', 0.50),
            'weight_consistency': db_config.get('weight_consistency', 0.25),
            'weight_debt': db_config.get('weight_debt', 0.15),
            'weight_ownership': db_config.get('weight_ownership', 0.10),
            # Buffett keys
            'weight_roe': db_config.get('weight_roe', 0.0),
            'weight_debt_earnings': db_config.get('weight_debt_to_earnings', 0.0),
            'weight_gross_margin': db_config.get('weight_gross_margin', 0.0),
            'roe_excellent': db_config.get('roe_excellent', 20.0),
            'roe_good': db_config.get('roe_good', 15.0),
            'roe_fair': db_config.get('roe_fair', 10.0),
            'de_excellent': db_config.get('debt_to_earnings_excellent', 2.0),
            'de_good': db_config.get('debt_to_earnings_good', 4.0),
            'de_fair': db_config.get('debt_to_earnings_fair', 7.0),
            'gm_excellent': db_config.get('gross_margin_excellent', 50.0),
            'gm_good': db_config.get('gross_margin_good', 40.0),
            'gm_fair': db_config.get('gross_margin_fair', 30.0),
        }
    else:
        config = DEFAULT_ALGORITHM_CONFIG

    try:
        # Load all stocks into DataFrame
        df = deps.stock_vectors.load_vectors(country_filter=country_filter)
        load_time = time.time() - start_time

        # Score all stocks using vectorized method
        score_start = time.time()
        scored_df = deps.criteria.evaluate_batch(df, config)
        score_time = time.time() - score_start

        # Apply search filter if provided
        if search:
            search_lower = search.lower()
            mask = (
                scored_df['symbol'].str.lower().str.contains(search_lower) |
                scored_df['company_name'].fillna('').str.lower().str.contains(search_lower)
            )
            scored_df = scored_df[mask]

        # Apply custom sorting (if different from default)
        if sort_by != 'overall_score' or sort_dir != 'desc':
            ascending = sort_dir.lower() == 'asc'
            if sort_by in scored_df.columns:
                scored_df = scored_df.sort_values(sort_by, ascending=ascending, na_position='last')

        # Calculate pagination
        total_count = len(scored_df)
        offset = (page - 1) * limit
        paginated_df = scored_df.iloc[offset:offset + limit]

        # Convert to list of dicts for JSON response
        results = paginated_df.to_dict(orient='records')

        # Clean NaN values
        for result in results:
            for key, value in result.items():
                if pd.isna(value):
                    result[key] = None
                elif isinstance(value, (np.floating, np.integer)):
                    result[key] = float(value) if np.isfinite(value) else None

        total_time = time.time() - start_time

        # Count by status for summary
        status_counts = scored_df['overall_status'].value_counts().to_dict()

        logger.info(f"[screen/v2] Scored {total_count} stocks in {total_time*1000:.0f}ms "
                   f"(load: {load_time*1000:.0f}ms, score: {score_time*1000:.0f}ms)")

        return jsonify({
            'results': results,
            'total_count': total_count,
            'page': page,
            'limit': limit,
            'total_pages': (total_count + limit - 1) // limit,
            'status_counts': status_counts,
            'timing': {
                'load_ms': round(load_time * 1000),
                'score_ms': round(score_time * 1000),
                'total_ms': round(total_time * 1000)
            }
        })

    except Exception as e:
        logger.error(f"[screen/v2] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@screening_bp.route('/api/screen', methods=['GET'])
def screen_stocks():
    """Fetch raw stock data for all NYSE/NASDAQ symbols.

    This endpoint ONLY fetches fundamental data and saves it to the database.
    Scoring happens separately via /api/sessions/latest using vectorized evaluation.
    """
    limit_param = request.args.get('limit')
    limit = int(limit_param) if limit_param else None
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'

    def generate():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Fetching stock list...'})}\\n\\n"

            symbols = deps.fetcher.get_nyse_nasdaq_symbols()
            if not symbols:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Unable to fetch stock symbols'})}\\n\\n"
                return

            if limit:
                symbols = symbols[:limit]

            total = len(symbols)
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Found {total} stocks to fetch data for...'})}\\n\\n"

            # Worker function to fetch data for a single stock
            def fetch_stock(symbol):
                try:
                    stock_data = deps.fetcher.fetch_stock_data(symbol, force_refresh)
                    if stock_data:
                        return {'symbol': symbol, 'success': True}
                    else:
                        return {'symbol': symbol, 'success': False, 'error': 'No data returned'}
                except Exception as e:
                    return {'symbol': symbol, 'success': False, 'error': str(e)}

            fetched_count = 0
            success_count = 0
            failed_symbols = []

            # Process stocks in batches using parallel workers
            BATCH_SIZE = 10
            MAX_WORKERS = 20  # Reduced from 40 to prevent DB pool exhaustion
            BATCH_DELAY = 0.5

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                for batch_start in range(0, total, BATCH_SIZE):
                    batch_end = min(batch_start + BATCH_SIZE, total)
                    batch = symbols[batch_start:batch_end]

                    # Submit batch to thread pool
                    future_to_symbol = {executor.submit(fetch_stock, symbol): symbol for symbol in batch}

                    # Collect results as they complete
                    for future in as_completed(future_to_symbol):
                        symbol = future_to_symbol[future]
                        fetched_count += 1

                        try:
                            result = future.result()
                            if result['success']:
                                success_count += 1
                            else:
                                failed_symbols.append(symbol)

                            # Send progress update
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'Fetched {symbol} ({fetched_count}/{total})...'})}\\n\\n"

                            # Keep-alive heartbeat
                            yield f": keep-alive\\n\\n"

                        except Exception as e:
                            print(f"Error getting result for {symbol}: {e}")
                            failed_symbols.append(symbol)
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'Error with {symbol} ({fetched_count}/{total})'})}\\n\\n"

                    # Rate limiting delay between batches
                    if batch_end < total:
                        time.sleep(BATCH_DELAY)
                        yield f": heartbeat-batch-delay\\n\\n"

            # Retry failed stocks
            if failed_symbols:
                retry_count = len(failed_symbols)
                yield f"data: {json.dumps({'type': 'progress', 'message': f'Retrying {retry_count} failed stocks...'})}\\n\\n"

                time.sleep(5)

                for i, symbol in enumerate(failed_symbols, 1):
                    try:
                        yield f"data: {json.dumps({'type': 'progress', 'message': f'Retry {i}/{retry_count}: {symbol}...'})}\\n\\n"

                        result = fetch_stock(symbol)
                        if result['success']:
                            success_count += 1
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'✓ Retry succeeded for {symbol}'})}\\n\\n"
                        else:
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'✗ Retry failed for {symbol}'})}\\n\\n"

                        yield f": keep-alive-retry\\n\\n"
                        time.sleep(2)
                    except Exception as e:
                        print(f"Retry error for {symbol}: {e}")
                        yield f"data: {json.dumps({'type': 'progress', 'message': f'✗ Retry error for {symbol}'})}\\n\\n"
                        time.sleep(2)

            # Send completion message
            completion_payload = {
                'type': 'complete',
                'total_symbols': total,
                'success_count': success_count,
                'failed_count': total - success_count,
                'message': f'Data fetching complete. {success_count}/{total} stocks updated.'
            }
            yield f"data: {json.dumps(completion_payload)}\\n\\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\\n\\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')
