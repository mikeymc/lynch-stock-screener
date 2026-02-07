# ABOUTME: Stock data retrieval endpoints for metrics, history, and search
# ABOUTME: Handles individual stock lookups, batch requests, and insider trades

from flask import Blueprint, jsonify, request, session
from app import deps
from app.helpers import clean_nan_values
from auth import require_user_auth
from characters import get_character
from data_fetcher import DataFetcher
from stock_vectors import DEFAULT_ALGORITHM_CONFIG
from wacc_calculator import calculate_wacc
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import time
import os
import numpy as np
import pandas as pd
import yfinance as yf
import psycopg.rows
from datetime import datetime, timedelta, timezone, date

logger = logging.getLogger(__name__)

stocks_bp = Blueprint('stocks', __name__)


@stocks_bp.route('/api/stock/<symbol>', methods=['GET'])
def get_stock(symbol):
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    algorithm = request.args.get('algorithm', 'weighted')

    stock_data = deps.fetcher.fetch_stock_data(symbol.upper(), force_refresh)
    if not stock_data:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get active character: prefer query param, then fallback to setting, then default
    active_character = request.args.get('character') or deps.db.get_setting('active_character') or 'lynch'

    # Load fresh character-specific config using robust helper
    # Use session.get('user_id') if available, otherwise None for system defaults
    user_id = session.get('user_id')

    # helper method already handles fallback to system default if user-specific config not found
    db_config = deps.db.get_user_algorithm_config(user_id, active_character)

    overrides = None
    if db_config:
        if active_character == 'lynch':
            # Lynch-specific overrides
            overrides = {
                'peg_excellent': db_config.get('peg_excellent'),
                'peg_good': db_config.get('peg_good'),
                'peg_fair': db_config.get('peg_fair'),
                'debt_excellent': db_config.get('debt_excellent'),
                'debt_good': db_config.get('debt_good'),
                'debt_moderate': db_config.get('debt_moderate'),
                'inst_own_min': db_config.get('inst_own_min'),
                'inst_own_max': db_config.get('inst_own_max'),
                'weight_peg': db_config.get('weight_peg'),
                'weight_consistency': db_config.get('weight_consistency'),
                'weight_debt': db_config.get('weight_debt'),
                'weight_ownership': db_config.get('weight_ownership'),
            }
        elif active_character == 'buffett':
            # Buffett-specific overrides
            # Note: StockEvaluator looks for {metric}_excellent where metric matches character config
            overrides = {
                'weight_roe': db_config.get('weight_roe'),
                'weight_earnings_consistency': db_config.get('weight_consistency'),
                'weight_debt_to_earnings': db_config.get('weight_debt_to_earnings'),
                'weight_gross_margin': db_config.get('weight_gross_margin'),
                'roe_excellent': db_config.get('roe_excellent'),
                'roe_good': db_config.get('roe_good'),
                'roe_fair': db_config.get('roe_fair'),
                'debt_to_earnings_excellent': db_config.get('debt_to_earnings_excellent'),
                'debt_to_earnings_good': db_config.get('debt_to_earnings_good'),
                'debt_to_earnings_fair': db_config.get('debt_to_earnings_fair'),
                'gross_margin_excellent': db_config.get('gross_margin_excellent'),
                'gross_margin_good': db_config.get('gross_margin_good'),
                'gross_margin_fair': db_config.get('gross_margin_fair'),
            }

    evaluation = deps.criteria.evaluate_stock(symbol.upper(), algorithm=algorithm, overrides=overrides, character_id=active_character)

    return jsonify({
        'stock_data': clean_nan_values(stock_data),
        'evaluation': clean_nan_values(evaluation)
    })


@stocks_bp.route('/api/stocks/batch', methods=['POST'])
def batch_get_stocks():
    """Batch fetch stock data and evaluations for a list of symbols"""
    try:
        data = request.get_json()
        if not data or 'symbols' not in data:
            return jsonify({'error': 'No symbols provided'}), 400

        symbols = data['symbols']
        algorithm = data.get('algorithm', 'weighted')

        # Limit batch size to prevent abuse
        if len(symbols) > 50:
            symbols = symbols[:50]

        results = []

        # Helper for parallel execution
        def fetch_one(symbol):
            try:
                # Use cached data if available, only fetch if missing
                stock_data = deps.fetcher.fetch_stock_data(symbol.upper(), force_refresh=False)
                if not stock_data:
                    return None

                evaluation = deps.criteria.evaluate_stock(symbol.upper(), algorithm=algorithm)

                # Merge into single object as expected by frontend
                if evaluation:
                    # Prefer evaluation data but fallback to stock_data
                    merged = {**clean_nan_values(stock_data), **clean_nan_values(evaluation)}
                    merged['symbol'] = symbol.upper() # Ensure symbol is present
                    return merged
                return None
            except Exception as e:
                logger.error(f"Error fetching {symbol} in batch: {e}")
                return None

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_symbol = {executor.submit(fetch_one, sym): sym for sym in symbols}

            for future in as_completed(future_to_symbol):
                res = future.result()
                if res:
                    results.append(res)

        return jsonify({'results': results})

    except Exception as e:
        logger.error(f"Batch fetch error: {e}")
        return jsonify({'error': str(e)}), 500

@stocks_bp.route('/api/stock/<symbol>/insider', methods=['GET'])
@require_user_auth
def get_stock_insider_trades(symbol, user_id):
    """
    Get insider trades for a dedicated page.
    """
    symbol = symbol.upper()

    # Get all trades
    trades = deps.db.get_insider_trades(symbol)

    # Calculate net buying (last 6 months)
    six_months_ago = datetime.now() - timedelta(days=180)
    net_buying = 0

    for t in trades:
        t_date = datetime.strptime(t['transaction_date'], '%Y-%m-%d')
        if t_date >= six_months_ago:
            shares = t.get('shares') or 0
            price = t.get('price_per_share') or 0
            value = t.get('value') or (shares * price)

            # Form 4 transaction codes: P=Purchase, S=Sale
            code = t.get('transaction_code', '')
            is_purchase = code == 'P'
            is_sale = code == 'S'

            # Fallback to transaction_type if code missing
            if not code:
                t_type = t.get('transaction_type', '').lower()
                is_purchase = 'buy' in t_type or 'purchase' in t_type
                is_sale = 'sell' in t_type or 'sale' in t_type

            if is_purchase:
                net_buying += value
            elif is_sale:
                net_buying -= value

    return jsonify({
        'symbol': symbol,
        'trades': trades,
        'insider_net_buying_6m': net_buying
    })


@stocks_bp.route('/api/cached', methods=['GET'])
def get_cached_stocks():
    symbols = deps.db.get_all_cached_stocks()

    results = []
    for symbol in symbols:
        evaluation = deps.criteria.evaluate_stock(symbol)
        if evaluation:
            results.append(evaluation)

    results_by_status = {
        'pass': [r for r in results if r['overall_status'] == 'PASS'],
        'close': [r for r in results if r['overall_status'] == 'CLOSE'],
        'fail': [r for r in results if r['overall_status'] == 'FAIL']
    }

    return jsonify({
        'total_analyzed': len(results),
        'pass_count': len(results_by_status['pass']),
        'close_count': len(results_by_status['close']),
        'fail_count': len(results_by_status['fail']),
        'results': results_by_status
    })


@stocks_bp.route('/api/stocks/search', methods=['GET'])
def search_stocks_endpoint():
    """
    Fast search endpoint for stock lookup.
    Avoids heavy screening overhead of /api/sessions/latest.
    """
    try:
        query = request.args.get('q', '')
        limit = request.args.get('limit', 10, type=int)

        # Limit max results to prevent large payloads
        if limit > 50:
            limit = 50

        results = deps.db.search_stocks(query, limit)
        return jsonify({'results': results})
    except Exception as e:
        logger.error(f"Search endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@stocks_bp.route('/api/sessions/latest', methods=['GET'])
@require_user_auth
def get_latest_session(user_id):
    """Get the most recent screening session with paginated, sorted results.

    Uses vectorized scoring for Lynch (performance), falls back to database-based
    character scoring for Buffett and other characters.
    """
    # Get optional query parameters
    search = request.args.get('search', None)
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 100, type=int)
    sort_by = request.args.get('sort_by', 'overall_score')
    sort_dir = request.args.get('sort_dir', 'desc')
    status_filter = request.args.get('status', None)

    # Determine active character for scoring
    # Check query parameter first (for instant character switching), fallback to database
    character_id = request.args.get('character', None) or deps.db.get_user_character(user_id)
    character = get_character(character_id)

    # Check if US-only filter is enabled (default: True for production)
    us_stocks_only = deps.db.get_setting('us_stocks_only', True)
    country_filter = 'US' if us_stocks_only else None

    # HYBRID APPROACH: Use vectorized for Lynch, database for other characters
    if character_id in ['lynch', 'buffett']:
        # --- VECTORIZED PATH (for performance) ---
        # Get user's algorithm config
        configs = deps.db.get_algorithm_configs()

        # Build Config based on Active Character
        if character_id == 'lynch':
            if configs and len(configs) > 0:
                # Filter for Lynch config
                lynch_config = None
                for cfg in configs:
                    if cfg.get('character') == 'lynch':
                        lynch_config = cfg
                        break

                if lynch_config:
                    config = {
                        'peg_excellent': lynch_config.get('peg_excellent', 1.0),
                        'peg_good': lynch_config.get('peg_good', 1.5),
                        'peg_fair': lynch_config.get('peg_fair', 2.0),
                        'debt_excellent': lynch_config.get('debt_excellent', 0.5),
                        'debt_good': lynch_config.get('debt_good', 1.0),
                        'debt_moderate': lynch_config.get('debt_moderate', 2.0),
                        'inst_own_min': lynch_config.get('inst_own_min', 0.20),
                        'inst_own_max': lynch_config.get('inst_own_max', 0.60),
                        'weight_peg': lynch_config.get('weight_peg', 0.50),
                        'weight_consistency': lynch_config.get('weight_consistency', 0.25),
                        'weight_debt': lynch_config.get('weight_debt', 0.15),
                        'weight_ownership': lynch_config.get('weight_ownership', 0.10),
                    }
                else:
                    config = DEFAULT_ALGORITHM_CONFIG
            else:
                config = DEFAULT_ALGORITHM_CONFIG

        elif character_id == 'buffett':
            # Load Buffett config from database
            buffett_config = None
            if configs:
                for cfg in configs:
                    if cfg.get('character') == 'buffett':
                        buffett_config = cfg
                        break

            if buffett_config:
                # Use saved Buffett configuration
                # Note: DB has 'weight_debt_to_earnings' but scoring expects 'weight_debt_earnings'
                config = {
                    'weight_roe': buffett_config.get('weight_roe', 0.35),
                    'weight_consistency': buffett_config.get('weight_consistency', 0.25),
                    'weight_debt_earnings': buffett_config.get('weight_debt_to_earnings', 0.20),  # Map from DB name
                    'weight_gross_margin': buffett_config.get('weight_gross_margin', 0.20),  # Column doesn't exist yet

                    # Zero out Lynch weights
                    'weight_peg': 0.0,
                    'weight_debt': 0.0,
                    'weight_ownership': 0.0,

                    # Thresholds
                    'roe_excellent': buffett_config.get('roe_excellent', 20.0),
                    'roe_good': buffett_config.get('roe_good', 15.0),
                    'roe_fair': buffett_config.get('roe_fair', 10.0),
                    'debt_to_earnings_excellent': buffett_config.get('debt_to_earnings_excellent', 3.0),
                    'debt_to_earnings_good': buffett_config.get('debt_to_earnings_good', 5.0),
                    'debt_to_earnings_fair': buffett_config.get('debt_to_earnings_fair', 8.0),
                    'gross_margin_excellent': buffett_config.get('gross_margin_excellent', 50.0),
                    'gross_margin_good': buffett_config.get('gross_margin_good', 40.0),
                    'gross_margin_fair': buffett_config.get('gross_margin_fair', 30.0),
                }
            else:
                # Fallback to defaults if no config found
                config = {
                    'weight_roe': 0.35,
                    'weight_consistency': 0.25,
                    'weight_debt_earnings': 0.20,  # Fixed: was weight_debt_to_earnings
                    'weight_gross_margin': 0.20,

                    # Zero out Lynch weights
                    'weight_peg': 0.0,
                    'weight_debt': 0.0,
                    'weight_ownership': 0.0,

                    # Thresholds
                    'roe_excellent': 20.0,
                    'roe_good': 15.0,
                    'roe_fair': 10.0,
                    'debt_to_earnings_excellent': 3.0,
                    'debt_to_earnings_good': 5.0,
                    'debt_to_earnings_fair': 8.0,
                    'gross_margin_excellent': 50.0,
                    'gross_margin_good': 40.0,
                    'gross_margin_fair': 30.0,
                }

        try:
            # Load and score using vectorized engine
            df = deps.stock_vectors.load_vectors(country_filter)
            scored_df = deps.criteria.evaluate_batch(df, config)

            # Apply Status Filter
            if status_filter and status_filter.upper() != 'ALL':
                scored_df = scored_df[scored_df['overall_status'] == status_filter.upper()]

            # Apply search filter
            if search:
                search_lower = search.lower()
                mask = (
                    scored_df['symbol'].str.lower().str.contains(search_lower) |
                    scored_df['company_name'].fillna('').str.lower().str.contains(search_lower)
                )
                scored_df = scored_df[mask]

            # Apply Sorting
            if sort_by in scored_df.columns:
                ascending = sort_dir.lower() == 'asc'
                scored_df = scored_df.sort_values(sort_by, ascending=ascending, na_position='last')

            # Pagination
            total_count = len(scored_df)
            offset = (page - 1) * limit
            paginated_df = scored_df.iloc[offset:offset + limit]

            # Convert to records
            results = paginated_df.to_dict(orient='records')

            # Clean NaNs
            cleaned_results = []
            for result in results:
                cleaned = {}
                for key, value in result.items():
                    if pd.isna(value):
                        cleaned[key] = None
                    elif isinstance(value, (np.floating, np.integer)):
                        cleaned[key] = float(value) if np.isfinite(value) else None
                    else:
                        cleaned[key] = value
                cleaned_results.append(cleaned)

            # Count statuses
            status_counts = scored_df['overall_status'].value_counts().to_dict()
            # Ensure all keys exist
            for status in ['STRONG_BUY', 'BUY', 'HOLD', 'CAUTION', 'AVOID']:
                if status not in status_counts:
                    status_counts[status] = 0

            return jsonify({
                'results': cleaned_results,
                'total_count': total_count,
                'total_pages': (total_count + limit - 1) // limit,
                'current_page': page,
                'limit': limit,
                'status_counts': status_counts,
                'active_character': character_id,
                'session_id': 0,  # Dummy ID since this is dynamic
                '_meta': {
                    'source': 'vectorized_engine',
                    'timestamp': datetime.now().isoformat()
                }
            })

        except Exception as e:
            logger.error(f"Error in vectorized session: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    else:
        # --- DATABASE PATH (for character-aware scoring) ---
        # IMPORTANT: For character scoring, we need to fetch ALL results, re-score them,
        # re-sort by the new scores, THEN paginate. Otherwise pagination happens on
        # Lynch scores and we get wrong ordering after Buffett re-scoring.
        session_data = deps.db.get_latest_session(
            search=search,
            page=1,  # Fetch from page 1
            limit=10000,  # Fetch all results (large limit)
            sort_by='overall_score',  # Sort doesn't matter, we'll re-sort after scoring
            sort_dir='desc',
            country_filter=country_filter
        )

        if not session_data:
            return jsonify({'error': 'No screening sessions found'}), 404

        # Enrich results with on-the-fly computed metrics
        if 'results' in session_data:
            # Import character scoring module
            from character_scoring import apply_character_scoring

            for result in session_data['results']:
                symbol = result.get('symbol')

                # Compute P/E range position from cached weekly prices
                pe_range = deps.criteria.metric_calculator.calculate_pe_52_week_range(symbol, result)
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

            # Apply character-specific scoring to all results
            if character:
                session_data['results'] = [
                    apply_character_scoring(result, character)
                    for result in session_data['results']
                ]

                # CRITICAL: Re-sort after character scoring since scores have changed
                # The database sorted by Lynch scores, but we just replaced them with character scores
                reverse = (sort_dir.lower() == 'desc')
                if sort_by == 'overall_score':
                    # Sort by numeric score
                    session_data['results'].sort(
                        key=lambda x: x.get('overall_score') if x.get('overall_score') is not None else -1,
                        reverse=reverse
                    )
                elif sort_by == 'overall_status':
                    # Sort by status rank
                    status_rank = {
                        'STRONG_BUY': 5, 'BUY': 4, 'HOLD': 3, 'CAUTION': 2, 'AVOID': 1
                    }
                    session_data['results'].sort(
                        key=lambda x: status_rank.get(x.get('overall_status'), 0),
                        reverse=reverse
                    )
                else:
                    # Sort by other columns (metric scores, etc.)
                    session_data['results'].sort(
                        key=lambda x: x.get(sort_by) if x.get(sort_by) is not None else -1,
                        reverse=reverse
                    )

            # Clean NaN values in results
            all_results = [clean_nan_values(result) for result in session_data['results']]

            # Calculate status counts from ALL results (before pagination)
            status_counts = {}
            for result in all_results:
                status = result.get('overall_status')
                if status:
                    status_counts[status] = status_counts.get(status, 0) + 1

            # Ensure all status keys exist
            for status in ['STRONG_BUY', 'BUY', 'HOLD', 'CAUTION', 'AVOID']:
                if status not in status_counts:
                    status_counts[status] = 0

            # NOW paginate after re-scoring and re-sorting
            total_count = len(all_results)
            offset = (page - 1) * limit
            paginated_results = all_results[offset:offset + limit]

            session_data['results'] = paginated_results
            session_data['total_count'] = total_count
            session_data['total_pages'] = (total_count + limit - 1) // limit
            session_data['current_page'] = page
            session_data['limit'] = limit
            session_data['status_counts'] = status_counts

        # Include character info in response
        session_data['active_character'] = character_id

        return jsonify(session_data)


@stocks_bp.route('/api/stock/<symbol>/history', methods=['GET'])
def get_stock_history(symbol):
    """Get historical earnings, revenue, price, and P/E ratio data for charting"""

    # Get period_type parameter (default to 'annual' for backward compatibility)
    period_type = request.args.get('period_type', 'annual').lower()
    if period_type not in ['annual', 'quarterly']:
        return jsonify({'error': f'Invalid period_type: {period_type}. Must be annual or quarterly'}), 400

    # Get earnings history from database (filtered by period_type)
    earnings_history = deps.db.get_earnings_history(symbol.upper(), period_type)

    if not earnings_history:
        return jsonify({'error': f'No historical data found for {symbol}'}), 404

    # Backfill missing debt-to-equity data on-demand for annual data
    if period_type == 'annual':
        years_needing_de = [entry['year'] for entry in earnings_history if entry.get('debt_to_equity') is None]
        if years_needing_de:
            logger.info(f"[{symbol}] Backfilling D/E for {len(years_needing_de)} years on-demand")
            try:
                data_fetcher = DataFetcher(deps.db)
                data_fetcher._backfill_debt_to_equity(symbol.upper(), years_needing_de)
                # Re-fetch earnings history to get the updated data
                earnings_history = deps.db.get_earnings_history(symbol.upper(), period_type)
            except Exception as e:
                logger.error(f"[{symbol}] Error backfilling D/E: {e}")

    # Sort by year ascending, then by quarter for charting
    def sort_key(entry):
        year = entry['year']
        period = entry.get('period', 'annual')
        # Sort quarterly data by quarter number
        if period and period.startswith('Q'):
            try:
                quarter = int(period[1])
                return (year, quarter)
            except (ValueError, IndexError):
                return (year, 0)
        # Annual data comes after all quarters for the same year
        return (year, 5)

    earnings_history.sort(key=sort_key)

    labels = []
    eps_values = []
    revenue_values = []
    pe_ratios = []
    prices = []
    debt_to_equity_values = []
    net_income_values = []
    dividend_values = []
    operating_cash_flow_values = []
    capital_expenditures_values = []
    free_cash_flow_values = []
    shareholder_equity_values = []
    shares_outstanding_values = []
    roe_values = []
    book_value_values = []
    debt_to_earnings_values = []

    # Get yfinance ticker for fallback
    ticker = yf.Ticker(symbol.upper())

    for entry in earnings_history:
        year = entry['year']
        eps = entry['eps']
        revenue = entry['revenue']
        fiscal_end = entry.get('fiscal_end')
        debt_to_equity = entry.get('debt_to_equity')
        net_income = entry.get('net_income')
        dividend = entry.get('dividend_amount')
        operating_cash_flow = entry.get('operating_cash_flow')
        capital_expenditures = entry.get('capital_expenditures')
        free_cash_flow = entry.get('free_cash_flow')
        shareholder_equity = entry.get('shareholder_equity')
        shares_outstanding = entry.get('shares_outstanding')
        period = entry.get('period', 'annual')

        # Create label based on period type
        if period == 'annual':
            label = str(year)
        else:
            # Quarterly data: format as "2023 Q1"
            label = f"{year} {period}"

        labels.append(label)
        eps_values.append(eps)
        revenue_values.append(revenue)
        debt_to_equity_values.append(debt_to_equity)
        net_income_values.append(net_income)
        dividend_values.append(dividend)
        operating_cash_flow_values.append(operating_cash_flow)
        capital_expenditures_values.append(capital_expenditures)
        free_cash_flow_values.append(free_cash_flow)
        shareholder_equity_values.append(shareholder_equity)
        shares_outstanding_values.append(shares_outstanding)

        # Calculate ROE (Net Income / Shareholder Equity)
        roe = None
        if net_income is not None and shareholder_equity and shareholder_equity > 0:
             roe = (net_income / shareholder_equity) * 100
        roe_values.append(roe)

        # Calculate Book Value Per Share
        book_value = None
        if shareholder_equity is not None and shares_outstanding and shares_outstanding > 0:
             book_value = shareholder_equity / shares_outstanding
        book_value_values.append(book_value)

        # Calculate Debt-to-Earnings (Years to pay off debt)
        # Total Debt = Debt/Equity * Equity
        # Years = Total Debt / Net Income
        dte = None
        if debt_to_equity is not None and shareholder_equity is not None and net_income is not None and net_income > 0:
            total_debt = debt_to_equity * shareholder_equity
            dte = total_debt / net_income
        debt_to_earnings_values.append(dte)

        price = None

        # Fetch historical price for this year's fiscal year-end
        # Try weekly_prices cache first, fallback to yfinance if not found
        target_date = fiscal_end if fiscal_end else f"{year}-12-31"

        try:
            # Get weekly prices from cache
            weekly_data = deps.db.get_weekly_prices(symbol.upper())

            if weekly_data and weekly_data.get('dates') and weekly_data.get('prices'):
                # Find the closest week to target_date
                target_ts = pd.Timestamp(target_date)
                dates = [pd.Timestamp(d) for d in weekly_data['dates']]

                # Find dates on or before target
                valid_dates = [(i, d) for i, d in enumerate(dates) if d <= target_ts]

                if valid_dates:
                    # Get the closest date (most recent on or before target)
                    closest_idx, closest_date = max(valid_dates, key=lambda x: x[1])
                    price = weekly_data['prices'][closest_idx]
                    logger.debug(f"[{symbol}] Found cached price for {target_date}: ${price:.2f} (from {closest_date.date()})")

            # Fallback to yfinance if not in cache
            if price is None:
                print(f"DEBUG: Fetching price for {symbol} on {target_date}")  # DEBUG
                logger.info(f"[{symbol}] Price not in cache for {target_date}, fetching from yfinance")

                ticker = yf.Ticker(symbol.upper())

                # Fetch a range around the target date to ensure we get data
                # yfinance doesn't work well with start=end for a single day
                target_dt = datetime.fromisoformat(target_date)
                start_date = (target_dt - timedelta(days=7)).strftime('%Y-%m-%d')
                end_date = (target_dt + timedelta(days=1)).strftime('%Y-%m-%d')

                hist = ticker.history(start=start_date, end=end_date)

                if not hist.empty:
                    # Find the closest date on or before target_date
                    hist_dates = pd.to_datetime(hist.index)
                    target_ts = pd.Timestamp(target_date)

                    # yfinance returns timezone-aware data, so we need to make target_ts timezone-aware too
                    if hist_dates.tz is not None and target_ts.tz is None:
                        target_ts = target_ts.tz_localize(hist_dates.tz)

                    # Filter to dates on or before target
                    valid_hist = hist[hist_dates <= target_ts]

                    if not valid_hist.empty:
                        # Get the most recent price on or before target
                        price = float(valid_hist['Close'].iloc[-1])
                        actual_date = valid_hist.index[-1].strftime('%Y-%m-%d')

                        # Cache the fetched price to weekly_prices for future use
                        deps.db.save_weekly_prices(symbol.upper(), {
                            'dates': [actual_date],
                            'prices': [price]
                        })
                        logger.info(f"[{symbol}] Fetched and cached price for {target_date}: ${price:.2f} (from {actual_date})")
                    else:
                        logger.warning(f"[{symbol}] No price data on or before {target_date}")
                else:
                    logger.warning(f"[{symbol}] No price data available from yfinance around {target_date}")

        except Exception as e:
            logger.error(f"Error fetching price for {symbol} on {target_date}: {e}")
            import traceback
            traceback.print_exc()
        # todo: switch pe ratio to market cap / net income
        # Always include price in chart if we have it
        prices.append(price)

        # Calculate P/E ratio only if we have price and positive EPS
        if price is not None and eps is not None and eps > 0:
            pe_ratio = price / eps
            pe_ratios.append(pe_ratio)
        else:
            # Can't calculate P/E (missing price or EPS)
            pe_ratios.append(None)

    # Calculate WACC
    stock_metrics = deps.db.get_stock_metrics(symbol.upper())
    wacc_data = calculate_wacc(stock_metrics) if stock_metrics else None

    # Get weekly price history for granular chart display from DATABASE
    # Use the earliest year in earnings history as start year
    start_year = min(entry['year'] for entry in earnings_history) if earnings_history else None
    weekly_prices = {}
    weekly_pe_ratios = {}
    weekly_dividend_yields = {}
    try:
        # Get weekly prices from cached weekly_prices table
        weekly_prices = deps.db.get_weekly_prices(symbol.upper(), start_year)

        # Calculate weekly P/E ratios using TTM EPS (Trailing Twelve Months)
        # TTM EPS = Rolling sum of last 4 quarters of net income / shares outstanding
        # This ensures the P/E chart matches the current P/E shown on the stock list
        if weekly_prices.get('dates') and weekly_prices.get('prices'):
            # Get quarterly net income data for TTM calculation
            quarterly_history = deps.db.get_earnings_history(symbol.upper(), period_type='quarterly')

            # Build list of (fiscal_end_date, net_income) sorted by date
            quarterly_ni = []
            for entry in quarterly_history:
                ni = entry.get('net_income')
                fiscal_end = entry.get('fiscal_end')
                year = entry.get('year')
                period = entry.get('period', '')

                if ni is not None and year and period:
                    # If fiscal_end is missing, estimate from year and quarter
                    if not fiscal_end:
                        quarter_month_map = {'Q1': 3, 'Q2': 6, 'Q3': 9, 'Q4': 12}
                        month = quarter_month_map.get(period, 12)
                        fiscal_end = f"{year}-{month:02d}-28"  # Approximate

                    quarterly_ni.append({
                        'date': fiscal_end,
                        'net_income': ni,
                        'year': year,
                        'period': period
                    })

            # Sort by date ascending
            quarterly_ni.sort(key=lambda x: x['date'])

            # Get current shares outstanding from market cap / price
            shares_outstanding = None
            if stock_metrics:
                price = stock_metrics.get('price')
                market_cap = stock_metrics.get('market_cap')
                if price and price > 0 and market_cap and market_cap > 0:
                    shares_outstanding = market_cap / price

            # Get the current trailing P/E and EPS from stock metrics
            # This comes from real-time market data (yfinance) and is more accurate than EDGAR
            current_pe = stock_metrics.get('pe_ratio') if stock_metrics else None
            current_price = stock_metrics.get('price') if stock_metrics else None
            current_eps = None
            if current_pe and current_pe > 0 and current_price and current_price > 0:
                current_eps = current_price / current_pe

            # Calculate P/E for each week
            weekly_pe_dates = []
            weekly_pe_values = []

            # Fallback to annual EPS if we don't have quarterly data
            if len(quarterly_ni) >= 4 and shares_outstanding:
                # Use TTM approach for historical data
                for i, date_str in enumerate(weekly_prices['dates']):
                    price = weekly_prices['prices'][i]

                    # Always add the date to keep x-axis aligned with price chart
                    weekly_pe_dates.append(date_str)

                    if not price or price <= 0:
                        weekly_pe_values.append(None)
                        continue

                    # For dates in the current or previous year, use real-time EPS
                    # This handles cases where EDGAR quarterly data lags behind actual results
                    week_year = int(date_str[:4])
                    current_year = datetime.now().year
                    is_recent = week_year >= current_year - 1

                    if is_recent and current_eps and current_eps > 0:
                        # Use real-time EPS for recent weeks
                        pe = price / current_eps
                        weekly_pe_values.append(round(pe, 2))
                    else:
                        # Use TTM calculation for historical weeks
                        # Find the 4 most recent quarters on or before this date
                        relevant_quarters = [q for q in quarterly_ni if q['date'] <= date_str]

                        if len(relevant_quarters) >= 4:
                            # Sum the last 4 quarters
                            last_4q = relevant_quarters[-4:]
                            ttm_net_income = sum(q['net_income'] for q in last_4q)

                            # Calculate TTM EPS
                            ttm_eps = ttm_net_income / shares_outstanding

                            if ttm_eps > 0:
                                pe = price / ttm_eps
                                weekly_pe_values.append(round(pe, 2))
                            else:
                                # Negative EPS - P/E not meaningful
                                weekly_pe_values.append(None)
                        else:
                            # Not enough quarters for TTM calculation
                            weekly_pe_values.append(None)
            else:
                # Fallback: Use annual EPS (original approach)
                eps_by_year = {}
                for entry in earnings_history:
                    if entry.get('eps') and entry.get('eps') > 0:
                        eps_by_year[entry['year']] = entry['eps']

                for i, date_str in enumerate(weekly_prices['dates']):
                    year = int(date_str[:4])
                    price = weekly_prices['prices'][i]

                    # Always add the date
                    weekly_pe_dates.append(date_str)

                    # Use EPS from the current year, or fall back to previous year
                    eps = eps_by_year.get(year) or eps_by_year.get(year - 1)

                    if eps and eps > 0 and price:
                        pe = price / eps
                        weekly_pe_values.append(round(pe, 2))
                    else:
                        weekly_pe_values.append(None)

            weekly_pe_ratios = {
                'dates': weekly_pe_dates,
                'values': weekly_pe_values
            }

            # Calculate weekly dividend yields using dividend amounts from earnings history
            # For each week, use the dividend from the corresponding fiscal year
            dividend_by_year = {}
            for entry in earnings_history:
                if entry.get('dividend_amount') and entry.get('dividend_amount') > 0:
                    dividend_by_year[entry['year']] = entry['dividend_amount']

            # Calculate dividend yield for each week
            weekly_div_dates = []
            weekly_div_values = []
            for i, date_str in enumerate(weekly_prices['dates']):
                year = int(date_str[:4])
                price = weekly_prices['prices'][i]

                # Use dividend from the current year, or fall back to previous year
                dividend = dividend_by_year.get(year) or dividend_by_year.get(year - 1)

                # Always add the date to keep x-axis aligned with other charts
                weekly_div_dates.append(date_str)

                if dividend and dividend > 0 and price and price > 0:
                    div_yield = (dividend / price) * 100
                    weekly_div_values.append(round(div_yield, 2))
                else:
                    weekly_div_values.append(None)

            weekly_dividend_yields = {
                'dates': weekly_div_dates,
                'values': weekly_div_values
            }
    except Exception as e:
        logger.debug(f"Error fetching weekly prices for {symbol}: {e}")

    # Get analyst estimates for forward projections
    analyst_estimates = {}
    try:
        estimates = deps.db.get_analyst_estimates(symbol.upper())
        if estimates:
            # Extract current year and next year estimates for chart projections
            current_year_est = estimates.get('0y', {})
            next_year_est = estimates.get('+1y', {})

            analyst_estimates = {
                'current_year': {
                    'eps_avg': current_year_est.get('eps_avg'),
                    'eps_low': current_year_est.get('eps_low'),
                    'eps_high': current_year_est.get('eps_high'),
                    'eps_growth': current_year_est.get('eps_growth'),
                    'revenue_avg': current_year_est.get('revenue_avg'),
                    'revenue_low': current_year_est.get('revenue_low'),
                    'revenue_high': current_year_est.get('revenue_high'),
                    'revenue_growth': current_year_est.get('revenue_growth'),
                    'num_analysts': current_year_est.get('eps_num_analysts'),
                } if current_year_est else None,
                'next_year': {
                    'eps_avg': next_year_est.get('eps_avg'),
                    'eps_low': next_year_est.get('eps_low'),
                    'eps_high': next_year_est.get('eps_high'),
                    'eps_growth': next_year_est.get('eps_growth'),
                    'revenue_avg': next_year_est.get('revenue_avg'),
                    'revenue_low': next_year_est.get('revenue_low'),
                    'revenue_high': next_year_est.get('revenue_high'),
                    'revenue_growth': next_year_est.get('revenue_growth'),
                    'num_analysts': next_year_est.get('eps_num_analysts'),
                } if next_year_est else None,
                # Include quarterly estimates for more granular projections
                'current_quarter': estimates.get('0q'),
                'next_quarter': estimates.get('+1q'),
            }
    except Exception as e:
        logger.debug(f"Error fetching analyst estimates for {symbol}: {e}")

    # Build recent quarterly breakdown from quarterly earnings history
    # Show quarters that are MORE RECENT than the last annual data point (by fiscal_end date)
    current_year_quarterly = None
    try:
        quarterly_history = deps.db.get_earnings_history(symbol.upper(), period_type='quarterly')
        if quarterly_history and earnings_history:
            # Find the most recent annual fiscal_end date
            annual_entries = [e for e in earnings_history if e.get('period') == 'annual' or e.get('period') is None]
            if annual_entries:
                last_annual_fiscal_end = max(
                    (e.get('fiscal_end') or f"{e['year']}-12-31")
                    for e in annual_entries
                )

                # Get all quarters whose fiscal_end is AFTER the last annual fiscal_end
                recent_quarters = [
                    q for q in quarterly_history
                    if q.get('fiscal_end') and q['fiscal_end'] > last_annual_fiscal_end
                ]

                if recent_quarters:
                    # Sort by fiscal_end date
                    recent_quarters.sort(key=lambda x: x.get('fiscal_end', ''))

                    # Get the year of the most recent quarter for display
                    most_recent_year = recent_quarters[-1]['year'] if recent_quarters else None

                    current_year_quarterly = {
                        'year': most_recent_year,
                        'quarters': [
                            {
                                'q': int(q['period'][1]) if q.get('period') and q['period'].startswith('Q') else 0,
                                'period': q.get('period'),
                                'year': q['year'],
                                'eps': q.get('eps'),
                                'revenue': q.get('revenue'),
                                'net_income': q.get('net_income'),
                                'fiscal_end': q.get('fiscal_end'),
                                'operating_cash_flow': q.get('operating_cash_flow'),
                                'capital_expenditures': q.get('capital_expenditures'),
                                'free_cash_flow': q.get('free_cash_flow'),
                                'debt_to_equity': q.get('debt_to_equity'),
                            }
                            for q in recent_quarters
                        ]
                    }



    except Exception as e:
        logger.debug(f"Error building current year quarterly for {symbol}: {e}")

    # Get price targets from stock metrics
    price_targets = None
    if stock_metrics:
        pt_mean = stock_metrics.get('price_target_mean')
        pt_high = stock_metrics.get('price_target_high')
        pt_low = stock_metrics.get('price_target_low')
        logger.info(f"[{symbol}] Price targets from stock_metrics: mean={pt_mean}, high={pt_high}, low={pt_low}")
        if pt_mean or pt_high or pt_low:
            price_targets = {
                'current': stock_metrics.get('price'),
                'mean': pt_mean,
                'high': pt_high,
                'low': pt_low,
            }
    else:
        logger.info(f"[{symbol}] stock_metrics is None")

    response_data = {
        'labels': labels,
        'eps': eps_values,
        'revenue': revenue_values,
        'price': prices,
        'pe_ratio': pe_ratios,
        'debt_to_equity': debt_to_equity_values,
        'net_income': net_income_values,
        'dividend_amount': dividend_values,
        'operating_cash_flow': operating_cash_flow_values,
        'capital_expenditures': capital_expenditures_values,
        'free_cash_flow': free_cash_flow_values,
        'shareholder_equity': shareholder_equity_values,
        'shares_outstanding': shares_outstanding_values,
        'roe': roe_values,
        'book_value_per_share': book_value_values,
        'debt_to_earnings': debt_to_earnings_values,
        'history': earnings_history,
        'wacc': wacc_data,
        'weekly_prices': weekly_prices,
        'weekly_pe_ratios': weekly_pe_ratios,
        'weekly_dividend_yields': weekly_dividend_yields,
        # NEW: Forward-looking data
        'analyst_estimates': analyst_estimates,
        'current_year_quarterly': current_year_quarterly,
        'price_targets': price_targets,
    }

    # Clean NaN values before returning
    response_data = clean_nan_values(response_data)
    return jsonify(response_data)
