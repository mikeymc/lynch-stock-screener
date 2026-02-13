# ABOUTME: Dashboard, FRED economic data, alerts, and market overview endpoints
# ABOUTME: Handles market indices, movers, economic indicators, and static file serving

from flask import Blueprint, jsonify, request, session, send_from_directory, current_app
from app import deps
from app.helpers import clean_nan_values
from auth import require_user_auth
from app.scoring import resolve_scoring_config
from fred_service import get_fred_service, SUPPORTED_SERIES, CATEGORIES
from fly_machines import get_fly_manager
from characters import get_character
from character_scoring import apply_character_scoring
from stock_vectors import DEFAULT_ALGORITHM_CONFIG
import json
import logging
import os
import time
from datetime import datetime, timezone, date
import yfinance as yf
import numpy as np
import pandas as pd
import psycopg.rows
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)


# ============================================================
# FRED Economic Data Endpoints
# ============================================================

@dashboard_bp.route('/api/fred/series/<series_id>', methods=['GET'])
def get_fred_series(series_id):
    """Get observations for a FRED series."""
    fred_enabled = deps.db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    fred = get_fred_service()
    if not fred.is_available():
        return jsonify({'error': 'FRED API key not configured'}), 503

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    result = fred.get_series(series_id, start_date=start_date, end_date=end_date)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@dashboard_bp.route('/api/fred/series/<series_id>/info', methods=['GET'])
def get_fred_series_info(series_id):
    """Get metadata for a FRED series."""
    fred_enabled = deps.db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    fred = get_fred_service()
    if not fred.is_available():
        return jsonify({'error': 'FRED API key not configured'}), 503

    result = fred.get_series_info(series_id)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@dashboard_bp.route('/api/fred/dashboard', methods=['GET'])
def get_fred_dashboard():
    """Get all dashboard indicators with recent history."""
    fred_enabled = deps.db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    fred = get_fred_service()
    if not fred.is_available():
        return jsonify({'error': 'FRED API key not configured'}), 503

    result = fred.get_dashboard_data()

    if 'error' in result:
        return jsonify(result), 500

    return jsonify(result)


@dashboard_bp.route('/api/fred/summary', methods=['GET'])
def get_fred_summary():
    """Get current values of all economic indicators."""
    fred_enabled = deps.db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    fred = get_fred_service()
    if not fred.is_available():
        return jsonify({'error': 'FRED API key not configured'}), 503

    result = fred.get_economic_summary()

    if 'error' in result:
        return jsonify(result), 500

    return jsonify(result)


@dashboard_bp.route('/api/fred/indicators', methods=['GET'])
def get_fred_indicators():
    """Get list of supported FRED indicators."""
    fred_enabled = deps.db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    return jsonify({
        'indicators': SUPPORTED_SERIES,
        'categories': CATEGORIES
    })


# ============================================================
# Catch-all Route for SPA Client-Side Routing
# ============================================================

@dashboard_bp.route('/', defaults={'path': ''})
@dashboard_bp.route('/<path:path>')
def serve(path):
    """
    Catch-all route to serve the React frontend app.
    If the path exists as a static file, serve it.
    Otherwise, serve index.html and let React Router handle the route.
    """
    if path != "" and os.path.exists(current_app.static_folder + '/' + path):
        return send_from_directory(current_app.static_folder, path)
    else:
        return send_from_directory(current_app.static_folder, 'index.html')


# ============================================================
# Alerts API Endpoints
# ============================================================

@dashboard_bp.route('/api/alerts', methods=['GET'])
@require_user_auth
def get_alerts(user_id):
    """Get all alerts for the current user."""
    try:
        alerts = deps.db.get_alerts(user_id)

        # Check for sync since timestamp for real-time price updates
        since = request.args.get('since')
        updates = []
        if since:
            try:
                updates = deps.db.get_recently_updated_stocks(since)
            except Exception as ex:
                logger.warning(f"Error fetching updates: {ex}")
                updates = []

        return jsonify({
            'alerts': alerts,
            'updates': clean_nan_values(updates),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/alerts', methods=['POST'])
@require_user_auth
def create_alert(user_id):
    """Create a new alert."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        symbol = data.get('symbol')
        condition_type = data.get('condition_type')
        condition_params = data.get('condition_params')
        frequency = data.get('frequency', 'daily')

        if not symbol or not condition_type or not condition_params:
            return jsonify({'error': 'Missing required fields'}), 400

        alert_id = deps.db.create_alert(user_id, symbol, condition_type, condition_params, frequency)

        return jsonify({
            'success': True,
            'alert_id': alert_id,
            'message': 'Alert created successfully'
        })
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@require_user_auth
def delete_alert(alert_id, user_id):
    """Delete an alert."""
    try:
        success = deps.db.delete_alert(alert_id, user_id)
        if success:
            return jsonify({'success': True, 'message': 'Alert deleted'})
        else:
            return jsonify({'error': 'Alert not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting alert: {e}")
        return jsonify({'error': str(e)}), 500



@dashboard_bp.route('/api/feedback', methods=['POST'])
@require_user_auth
def submit_feedback(user_id=None):
    """Submit application feedback"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        feedback_text = data.get('feedback_text')
        if not feedback_text:
            return jsonify({'error': 'Feedback text is required'}), 400

        # Create localized metadata including user info if available
        meta = data.get('metadata', {})

        # Handle 'dev-user-bypass' from auth middleware
        if user_id == 'dev-user-bypass':
            user_id = None
            email = data.get('email', 'dev-user@localhost')
        elif user_id:
            user = deps.db.get_user_by_id(user_id)
            email = user['email'] if user else None
        else:
            email = data.get('email')

        feedback_id = deps.db.create_feedback(
            user_id=user_id,
            email=email,
            feedback_text=feedback_text,
            screenshot_data=data.get('screenshot_data'),
            page_url=data.get('page_url'),
            metadata=meta
        )

        return jsonify({'message': 'Feedback submitted successfully', 'id': feedback_id})

    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# Dashboard & Market Data Endpoints
# ============================================================

SUPPORTED_INDICES = {
    '^GSPC': 'S&P 500',
    '^IXIC': 'Nasdaq Composite',
    '^DJI': 'Dow Jones Industrial Average'
}


@dashboard_bp.route('/api/market/index/<symbols>', methods=['GET'])
def get_market_index(symbols):
    """Get index price history for charting.

    Supported symbols: ^GSPC (S&P 500), ^IXIC (Nasdaq), ^DJI (Dow Jones)
    Query params: period (1d, 5d, 1mo, 3mo, ytd, 1y) - defaults to 1mo
    Multiple symbols can be provided comma-separated.
    """
    symbol_list = [s.strip() for s in symbols.split(',')]
    invalid_symbols = [s for s in symbol_list if s not in SUPPORTED_INDICES]
    if invalid_symbols:
        return jsonify({
            'error': f'Unsupported indices: {invalid_symbols}. Supported: {list(SUPPORTED_INDICES.keys())}'
        }), 400

    period = request.args.get('period', '1mo')
    valid_periods = ['1d', '5d', '1mo', '3mo', 'ytd', '1y']
    if period not in valid_periods:
        return jsonify({'error': f'Invalid period. Valid: {valid_periods}'}), 400

    try:
        # Use interval based on period for appropriate granularity
        if period == '1d':
            interval = '5m'
        elif period == '5d':
            interval = '15m'
        else:
            interval = '1d'

        # Fetch data for all symbols
        if len(symbol_list) > 1:
            # Multi-symbol download
            # Note: yf.download can return a DataFrame with a MultiIndex where some tickers are missing if they fail
            hist_data = yf.download(symbol_list, period=period, interval=interval, group_by='ticker', progress=False)
        else:
            # Single symbol - keep behavior consistent
            ticker = yf.Ticker(symbol_list[0])
            hist_data = ticker.history(period=period, interval=interval)

        results = {}
        for symbol in symbol_list:
            try:
                if len(symbol_list) > 1:
                    # Check if symbol exists in the downloaded columns to avoid KeyError
                    if symbol not in hist_data.columns.get_level_values(0):
                        logger.warning(f"Symbol {symbol} not found in yfinance download results")
                        results[symbol] = {'error': f'No data available for {symbol}'}
                        continue
                    hist = hist_data[symbol]
                else:
                    hist = hist_data

                if hist.empty:
                    results[symbol] = {'error': 'No data available'}
                    continue

                # Format data for chart
                data_points = []
                for idx, row in hist.iterrows():
                    # Handle potential missing Close column if ticker was partially returned but failed
                    if 'Close' not in row or pd.isna(row['Close']):
                        continue
                    data_points.append({
                        'timestamp': idx.isoformat(),
                        'close': float(row['Close']),
                        'open': float(row['Open']) if 'Open' in row else None,
                        'high': float(row['High']) if 'High' in row else None,
                        'low': float(row['Low']) if 'Low' in row else None,
                        'volume': int(row['Volume']) if 'Volume' in row and pd.notna(row['Volume']) else None
                    })

                if not data_points:
                    results[symbol] = {'error': 'No valid data points'}
                    continue

                # Calculate change from first to last
                first_close = data_points[0]['close']
                last_close = data_points[-1]['close']
                change = last_close - first_close
                change_pct = (change / first_close * 100) if first_close else 0

                results[symbol] = {
                    'symbol': symbol,
                    'name': SUPPORTED_INDICES[symbol],
                    'period': period,
                    'data': data_points,
                    'current_price': last_close,
                    'change': change,
                    'change_pct': round(change_pct, 2)
                }
            except Exception as item_err:
                logger.error(f"Error processing symbol {symbol}: {item_err}")
                results[symbol] = {'error': f'Internal error processing {symbol}'}

        # If only one symbol was requested, return it directly for backward compatibility
        if len(symbol_list) == 1:
            return jsonify(results[symbol_list[0]])

        return jsonify(results)

    except Exception as e:
        logger.error(f"Error fetching indices {symbols}: {e}")
        return jsonify({'error': str(e)}), 500


from stock_vectors import DEFAULT_ALGORITHM_CONFIG

@dashboard_bp.route('/api/market/movers', methods=['GET'])
def get_market_movers():
    """Get top gainers and losers from screened stocks.
    
    Uses vectorized scoring for all characters (Lynch, Buffett, etc.) to 
    ensure movers represent high-quality stocks.
    
    Query params:
      - period: 1d, 1w, 1m, ytd (default: 1d)
      - limit: number of stocks per category (default: 5)
      - character: optional character override (default: user's active character)
    """
    period = request.args.get('period', '1d')
    limit = min(int(request.args.get('limit', 5)), 20)
    
    try:
        # 1. Resolve character and scoring configuration using the shared helper
        user_id = session.get('user_id')
        character_id, config = resolve_scoring_config(user_id, request.args.get('character'))
        
        # 2. Get Stock Pool & Score (Vectorized)
        df = deps.stock_vectors.load_vectors(country_filter='US')
        scored_df = deps.criteria.evaluate_batch(df, config)
        
        # Filter: Exclude weak stocks (CAUTION or AVOID)
        quality_df = scored_df[~scored_df['overall_status'].isin(['CAUTION', 'AVOID'])].copy()
        
        # 3. Calculate Movers
        if period == '1d':
            # Use real-time daily change from stock_metrics (loaded into df already)
            # Ensure we filter out NaNs or errors
            valid_df = quality_df[quality_df['price_change_pct'].notna()].copy()
            
            gainers_pool = valid_df[valid_df['price_change_pct'] > 0]
            losers_pool = valid_df[valid_df['price_change_pct'] < 0]
            
            gainers = gainers_pool.sort_values('price_change_pct', ascending=False).head(limit)
            losers = losers_pool.sort_values('price_change_pct', ascending=True).head(limit)
            
            # Rename for frontend compatibility
            gainers = gainers.rename(columns={'price_change_pct': 'change_pct'})
            losers = losers.rename(columns={'price_change_pct': 'change_pct'})
            
        else:
            # Long periods (1w, 1m, ytd) require historical prices
            if period == '1w': days_back = 7
            elif period == '1m': days_back = 30
            elif period == 'ytd': days_back = (datetime.now() - datetime(datetime.now().year, 1, 1)).days
            else: days_back = 7
            
            symbols = quality_df['symbol'].tolist()
            if not symbols:
                return jsonify({'period': period, 'gainers': [], 'losers': []})
                
            conn = deps.db.get_connection()
            try:
                cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
                cursor.execute("""
                    SELECT DISTINCT ON (symbol)
                        symbol,
                        price as historical_price
                    FROM weekly_prices
                    WHERE symbol = ANY(%s)
                      AND week_ending <= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY symbol, week_ending DESC
                """ % ("%s", "%s"), (symbols, f"{days_back} days"))
                hist_prices = cursor.fetchall()
                
                # Convert to DataFrame for merging
                hist_df = pd.DataFrame(hist_prices)
                if hist_df.empty:
                    return jsonify({'period': period, 'gainers': [], 'losers': []})
                    
                # Merge and compute change
                merged = quality_df.merge(hist_df, on='symbol', how='inner')
                merged['change_pct'] = (merged['price'] - merged['historical_price']) / merged['historical_price'] * 100
                
                # Filter valid
                valid_df = merged[merged['change_pct'].notna()].copy()
                
                gainers_pool = valid_df[valid_df['change_pct'] > 0]
                losers_pool = valid_df[valid_df['change_pct'] < 0]
                
                gainers = gainers_pool.sort_values('change_pct', ascending=False).head(limit)
                losers = losers_pool.sort_values('change_pct', ascending=True).head(limit)
            finally:
                deps.db.return_connection(conn)
                
        # 4. Format Results
        # 4. Format and Character Score Results
        def process_movers(df):
            if df.empty:
                return []
            # Results from evaluate_batch already have overall_score and overall_status
            return [clean_nan_values(r) for r in df.to_dict(orient='records')]

        return jsonify({
            'period': period,
            'gainers': process_movers(gainers),
            'losers': process_movers(losers)
        })

    except Exception as e:
        logger.error(f"Error getting market movers: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500



@dashboard_bp.route('/api/dashboard/portfolios', methods=['GET'])
@require_user_auth
def get_dashboard_portfolios(user_id):
    """Get portfolio summaries for the dashboard."""
    try:
        portfolios = deps.db.get_user_portfolios(user_id)
        all_portfolio_symbols = set()
        for p in portfolios:
            try:
                holdings = deps.db.get_portfolio_holdings(p['id'])
                for symbol in holdings.keys():
                    all_portfolio_symbols.add(symbol)
            except Exception:
                pass

        portfolio_prices = {}
        if all_portfolio_symbols:
            from portfolio_service import fetch_current_prices_batch
            portfolio_prices = fetch_current_prices_batch(list(all_portfolio_symbols), db=deps.db)

        portfolio_summaries = []
        for p in portfolios:
            try:
                summary = deps.db.get_portfolio_summary(p['id'], prices_map=portfolio_prices)
                portfolio_summaries.append({
                    'id': p['id'],
                    'name': p['name'],
                    'total_value': summary.get('total_value', 0),
                    'total_gain_loss': summary.get('gain_loss', 0),
                    'total_gain_loss_pct': summary.get('gain_loss_percent', 0),
                    'top_holdings': summary.get('holdings_detailed', [])[:3],
                    'strategy_id': summary.get('strategy_id')
                })
            except Exception as e:
                logger.warning(f"Error getting portfolio summary for {p['id']}: {e}")

        total_count = len(portfolio_summaries)
        logger.info(f"Returning {len(portfolio_summaries[:5])} portfolios for dashboard (total available: {total_count})")
        return jsonify({
            'portfolios': portfolio_summaries[:5],
            'total_count': total_count
        })
    except Exception as e:
        logger.error(f"Error getting dashboard portfolios: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/watchlist', methods=['GET'])
@require_user_auth
def get_dashboard_watchlist(user_id):
    """Get watchlist items for the dashboard."""
    try:
        watchlist_symbols = deps.db.get_watchlist(user_id)
        watchlist_data = []
        if watchlist_symbols:
            conn = deps.db.get_connection()
            try:
                cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
                cursor.execute("""
                    SELECT
                        sm.symbol,
                        s.company_name,
                        sm.price,
                        sm.price_change_pct
                    FROM stock_metrics sm
                    JOIN stocks s ON sm.symbol = s.symbol
                    WHERE sm.symbol = ANY(%s)
                """, (watchlist_symbols,))
                watchlist_data = [dict(row) for row in cursor.fetchall()]
            finally:
                deps.db.return_connection(conn)
        return jsonify({'watchlist': watchlist_data})
    except Exception as e:
        logger.error(f"Error getting dashboard watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/alerts', methods=['GET'])
@require_user_auth
def get_dashboard_alerts(user_id):
    """Get alert summary for the dashboard."""
    try:
        alerts = deps.db.get_alerts(user_id)
        alert_summary = {
            'triggered': [a for a in alerts if a.get('status') == 'triggered'][:5],
            'pending': [a for a in alerts if a.get('status') == 'active'][:5],
            'total_triggered': len([a for a in alerts if a.get('status') == 'triggered']),
            'total_pending': len([a for a in alerts if a.get('status') == 'active'])
        }
        return jsonify({'alerts': alert_summary})
    except Exception as e:
        logger.error(f"Error getting dashboard alerts: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/strategies', methods=['GET'])
@require_user_auth
def get_dashboard_strategies(user_id):
    """Get strategy summaries for the dashboard."""
    try:
        strategies = deps.db.get_user_strategies(user_id)
        
        # We need portfolio values for these
        portfolios = deps.db.get_user_portfolios(user_id)
        portfolio_summaries = {}
        
        # Batch fetch prices for all portfolio symbols
        all_symbols = set()
        for p in portfolios:
            try:
                holdings = deps.db.get_portfolio_holdings(p['id'])
                for symbol in holdings.keys():
                    all_symbols.add(symbol)
            except Exception:
                pass
        
        prices_map = {}
        if all_symbols:
            from portfolio_service import fetch_current_prices_batch
            prices_map = fetch_current_prices_batch(list(all_symbols), db=deps.db)
            
        for p in portfolios:
            try:
                summary = deps.db.get_portfolio_summary(p['id'], prices_map=prices_map)
                portfolio_summaries[p['id']] = summary
            except Exception:
                pass

        strategy_summaries = [
            {
                'id': s['id'],
                'name': s['name'],
                'enabled': s.get('enabled', True),
                'last_run': s.get('last_run_at'),
                'last_status': s.get('last_run_status'),
                'portfolio_value': portfolio_summaries.get(s['portfolio_id'], {}).get('total_value', 0),
                'portfolio_return_pct': portfolio_summaries.get(s['portfolio_id'], {}).get('gain_loss_percent', 0)
            }
            for s in strategies if s.get('enabled', True)
        ][:5]
        
        return jsonify({'strategies': strategy_summaries})
    except Exception as e:
        logger.error(f"Error getting dashboard strategies: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/earnings', methods=['GET'])
@require_user_auth
def get_dashboard_earnings(user_id):
    """Get upcoming earnings for the dashboard."""
    try:
        watchlist_symbols = deps.db.get_watchlist(user_id)
        portfolios = deps.db.get_user_portfolios(user_id)
        portfolio_symbols = set()
        for p in portfolios:
            try:
                holdings = deps.db.get_portfolio_holdings(p['id'])
                portfolio_symbols.update(holdings.keys())
            except Exception:
                pass
        
        all_symbols = set(watchlist_symbols) | portfolio_symbols
        upcoming_earnings_list = []
        total_upcoming_earnings = 0
        
        # Get days and scope from query params
        days = int(request.args.get('days', 14))
        scope = request.args.get('scope', 'user') # 'user' (watchlist+portfolio) or 'all'
        
        # Increase limit if we're looking at a longer timeframe
        limit = 10 if days <= 14 else 100


        # Build query conditions
        where_clause = "WHERE sm.next_earnings_date IS NOT NULL AND sm.next_earnings_date BETWEEN CURRENT_DATE AND CURRENT_DATE + (%s * INTERVAL '1 day')"
        query_params = [days]

        if scope == 'user':
            if not all_symbols:
                return jsonify({
                    'upcoming_earnings': {
                        'earnings': [],
                        'total_count': 0
                    }
                })
            where_clause += " AND sm.symbol = ANY(%s)"
            query_params.append(list(all_symbols))
        else:
            # For 'all' scope, we just filter by date
            pass

        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            
            # Count query
            count_sql = f"SELECT COUNT(*) as total FROM stock_metrics sm {where_clause}"
            cursor.execute(count_sql, tuple(query_params))
            total_upcoming_earnings = cursor.fetchone()['total']

            # Results query
            results_sql = f"""
                SELECT
                    sm.symbol,
                    s.company_name,
                    sm.next_earnings_date
                FROM stock_metrics sm
                JOIN stocks s ON sm.symbol = s.symbol
                {where_clause}
                ORDER BY sm.next_earnings_date ASC
                LIMIT %s
            """
            cursor.execute(results_sql, tuple(query_params + [limit]))
            raw_earnings = cursor.fetchall()
                
            ticker_date_pairs = [(row['symbol'], row['next_earnings_date'].isoformat()) for row in raw_earnings]
            has_8k_map = deps.db.get_earnings_8k_status_batch(ticker_date_pairs)

            for row in raw_earnings:
                symbol = row['symbol']
                earnings_date = row['next_earnings_date'].isoformat()
                upcoming_earnings_list.append({
                    'symbol': symbol,
                    'company_name': row['company_name'],
                    'earnings_date': earnings_date,
                    'days_until': (row['next_earnings_date'] - date.today()).days,
                    'has_8k': has_8k_map.get(f"{symbol}:{earnings_date}", False)
                })
        finally:
            deps.db.return_connection(conn)

        return jsonify({
            'upcoming_earnings': {
                'earnings': upcoming_earnings_list,
                'total_count': total_upcoming_earnings
            }
        })
    except Exception as e:
        logger.error(f"Error getting dashboard earnings: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/news', methods=['GET'])
@require_user_auth
def get_dashboard_news(user_id):
    """Get recent news for the dashboard."""
    try:
        watchlist_symbols = deps.db.get_watchlist(user_id)
        portfolios = deps.db.get_user_portfolios(user_id)
        portfolio_symbols = set()
        for p in portfolios:
            try:
                holdings = deps.db.get_portfolio_holdings(p['id'])
                portfolio_symbols.update(holdings.keys())
            except Exception:
                pass
        
        all_symbols = list(set(watchlist_symbols) | portfolio_symbols)
        news_articles = []
        if all_symbols:
            news_articles = deps.db.get_news_articles_multi(all_symbols, limit=10)
            
        return jsonify({'news': news_articles})
    except Exception as e:
        logger.error(f"Error getting dashboard news: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard/theses', methods=['GET'])
@require_user_auth
def get_dashboard_theses(user_id):
    """Get recent theses for the dashboard."""
    try:
        recent_theses_data = deps.db.get_recent_theses(user_id, days=1, limit=10)
        return jsonify({'recent_theses': recent_theses_data})
    except Exception as e:
        logger.error(f"Error getting dashboard theses: {e}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/dashboard', methods=['GET'])
@require_user_auth
def get_dashboard(user_id):
    """Get aggregated dashboard data for the current user.

    Returns:
      - portfolios: User's portfolio summaries
      - watchlist: Watchlist symbols with current prices
      - alerts: Recent alerts (triggered + pending)
      - strategies: Active strategy summaries
      - upcoming_earnings: Next 2 weeks of earnings for watched/held stocks
      - news: 10 recent articles across watchlist/portfolio symbols
    """
    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)

            # 1. Portfolio summaries (batched price retrieval)
            portfolios = deps.db.get_user_portfolios(user_id)

            # Gather all symbols across all portfolios for a single batch fetch
            all_portfolio_symbols = set()
            portfolio_holdings_map = {}
            for p in portfolios:
                try:
                    holdings = deps.db.get_portfolio_holdings(p['id'])
                    portfolio_holdings_map[p['id']] = holdings
                    for symbol in holdings.keys():
                        all_portfolio_symbols.add(symbol)
                except Exception:
                    pass

            # Perform single batch fetch for all portfolio symbols
            portfolio_prices = {}
            if all_portfolio_symbols:
                from portfolio_service import fetch_current_prices_batch
                portfolio_prices = fetch_current_prices_batch(list(all_portfolio_symbols), db=deps.db)

            portfolio_summaries = []
            for p in portfolios:
                try:
                    summary = deps.db.get_portfolio_summary(p['id'], prices_map=portfolio_prices)
                    portfolio_summaries.append({
                        'id': p['id'],
                        'name': p['name'],
                        'total_value': summary.get('total_value', 0),
                        'total_gain_loss': summary.get('gain_loss', 0),
                        'total_gain_loss_pct': summary.get('gain_loss_percent', 0),
                        'top_holdings': summary.get('holdings_detailed', [])[:3],
                        'strategy_id': summary.get('strategy_id')
                    })
                except Exception as e:
                    logger.warning(f"Error getting portfolio summary for {p['id']}: {e}")

            # 2. Watchlist with prices
            watchlist_symbols = deps.db.get_watchlist(user_id)
            watchlist_data = []
            if watchlist_symbols:
                cursor.execute("""
                    SELECT
                        sm.symbol,
                        s.company_name,
                        sm.price,
                        sm.price_change_pct
                    FROM stock_metrics sm
                    JOIN stocks s ON sm.symbol = s.symbol
                    WHERE sm.symbol = ANY(%s)
                """, (watchlist_symbols,))
                watchlist_data = [dict(row) for row in cursor.fetchall()]

            # 3. Alerts (recent triggered + pending/active)
            alerts = deps.db.get_alerts(user_id)
            alert_summary = {
                'triggered': [a for a in alerts if a.get('status') == 'triggered'][:5],
                'pending': [a for a in alerts if a.get('status') == 'active'][:5],
                'total_triggered': len([a for a in alerts if a.get('status') == 'triggered']),
                'total_pending': len([a for a in alerts if a.get('status') == 'active'])
            }

            # 4. Active strategies
            strategies = deps.db.get_user_strategies(user_id)
            
            # Create a map for quick lookup of portfolio performance
            portfolio_map = {p['id']: p for p in portfolio_summaries}
            
            strategy_summaries = [
                {
                    'id': s['id'],
                    'name': s['name'],
                    'enabled': s.get('enabled', True),
                    'last_run': s.get('last_run_at'),
                    'last_status': s.get('last_run_status'),
                    'portfolio_value': portfolio_map.get(s['portfolio_id'], {}).get('total_value', 0),
                    'portfolio_return_pct': portfolio_map.get(s['portfolio_id'], {}).get('total_gain_loss_pct', 0)
                }
                for s in strategies if s.get('enabled', True)
            ][:5]

            # 5. Upcoming earnings (watchlist + portfolio symbols)
            # Gather all symbols from watchlist and portfolios (reusing already gathered portfolio symbols)
            all_symbols = set(watchlist_symbols) | all_portfolio_symbols

            upcoming_earnings_list = []
            total_upcoming_earnings = 0
            if all_symbols:
                # Get the count first
                cursor.execute("""
                    SELECT COUNT(*) as total
                    FROM stock_metrics sm
                    WHERE sm.symbol = ANY(%s)
                      AND sm.next_earnings_date IS NOT NULL
                      AND sm.next_earnings_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '14 days'
                """, (list(all_symbols),))
                total_upcoming_earnings = cursor.fetchone()['total']

                # Now get the items
                cursor.execute("""
                    SELECT
                        sm.symbol,
                        s.company_name,
                        sm.next_earnings_date
                    FROM stock_metrics sm
                    JOIN stocks s ON sm.symbol = s.symbol
                    WHERE sm.symbol = ANY(%s)
                      AND sm.next_earnings_date IS NOT NULL
                      AND sm.next_earnings_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '14 days'
                    ORDER BY sm.next_earnings_date ASC
                    LIMIT 10
                """, (list(all_symbols),))
                
                raw_earnings = cursor.fetchall()
                
                # Check for 8-K filings (Item 2.02) for these earnings dates
                ticker_date_pairs = [
                    (row['symbol'], row['next_earnings_date'].isoformat())
                    for row in raw_earnings
                ]
                has_8k_map = deps.db.get_earnings_8k_status_batch(ticker_date_pairs)

                for row in raw_earnings:
                    symbol = row['symbol']
                    earnings_date = row['next_earnings_date'].isoformat() if row['next_earnings_date'] else None
                    upcoming_earnings_list.append({
                        'symbol': symbol,
                        'company_name': row['company_name'],
                        'earnings_date': earnings_date,
                        'days_until': (row['next_earnings_date'] - date.today()).days if row['next_earnings_date'] else None,
                        'has_8k': has_8k_map.get(f"{symbol}:{earnings_date}", False)
                    })

            upcoming_earnings = {
                'earnings': upcoming_earnings_list,
                'total_count': total_upcoming_earnings
            }

            # 6. Aggregated news (from database cache)
            news_articles = []
            if all_symbols:
                news_articles = deps.db.get_news_articles_multi(list(all_symbols), limit=10)

            # 7. Recent investment theses (character generated, past 1 day)
            # Returns {'theses': [], 'total_count': int}
            recent_theses_data = deps.db.get_recent_theses(user_id, days=1, limit=10)

            return jsonify({
                'portfolios': portfolio_summaries[:5],
                'portfolio_total_count': len(portfolio_summaries),
                'watchlist': watchlist_data,
                'alerts': alert_summary,
                'strategies': strategy_summaries,
                'upcoming_earnings': upcoming_earnings,
                'news': news_articles,
                'recent_theses': recent_theses_data
            })

        finally:
            deps.db.return_connection(conn)

    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        return jsonify({'error': str(e)}), 500
