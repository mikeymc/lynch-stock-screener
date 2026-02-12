# ABOUTME: Dashboard, FRED economic data, alerts, and market overview endpoints
# ABOUTME: Handles market indices, movers, economic indicators, and static file serving

from flask import Blueprint, jsonify, request, session, send_from_directory, current_app
from app import deps
from app.helpers import clean_nan_values
from auth import require_user_auth
from fred_service import get_fred_service, SUPPORTED_SERIES, CATEGORIES
from fly_machines import get_fly_manager
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


@dashboard_bp.route('/api/market/movers', methods=['GET'])
def get_market_movers():
    """Get top gainers and losers from screened stocks.

    Query params:
      - period: 1d, 1w, 1m, ytd (default: 1d)
      - limit: number of stocks per category (default: 5)
    """
    period = request.args.get('period', '1d')
    limit = min(int(request.args.get('limit', 5)), 20)

    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)

            if period == '1d':
                # Use price_change_pct from stock_metrics
                cursor.execute("""
                    SELECT
                        sm.symbol,
                        s.company_name,
                        sm.price,
                        sm.price_change_pct as change_pct
                    FROM stock_metrics sm
                    JOIN stocks s ON sm.symbol = s.symbol
                    WHERE sm.price_change_pct IS NOT NULL
                      AND sm.price IS NOT NULL
                      AND NOT (sm.price_change_pct = 'NaN')
                      AND s.country = 'US'
                    ORDER BY sm.price_change_pct DESC
                    LIMIT %s
                """, (limit,))
                gainers = cursor.fetchall()

                cursor.execute("""
                    SELECT
                        sm.symbol,
                        s.company_name,
                        sm.price,
                        sm.price_change_pct as change_pct
                    FROM stock_metrics sm
                    JOIN stocks s ON sm.symbol = s.symbol
                    WHERE sm.price_change_pct IS NOT NULL
                      AND sm.price IS NOT NULL
                      AND NOT (sm.price_change_pct = 'NaN')
                      AND s.country = 'US'
                    ORDER BY sm.price_change_pct ASC
                    LIMIT %s
                """, (limit,))
                losers = cursor.fetchall()

            else:
                # Calculate from weekly_prices for longer periods
                if period == '1w':
                    days_back = 7
                elif period == '1m':
                    days_back = 30
                elif period == 'ytd':
                    days_back = (datetime.now() - datetime(datetime.now().year, 1, 1)).days
                else:
                    days_back = 7

                cursor.execute("""
                    WITH latest_reference_prices AS (
                        SELECT DISTINCT ON (symbol)
                            symbol,
                            price as historical_price
                        FROM weekly_prices
                        WHERE week_ending <= CURRENT_DATE - INTERVAL '%s days'
                        ORDER BY symbol, week_ending DESC
                    ),
                    price_change AS (
                        SELECT
                            rp.symbol,
                            s.company_name,
                            sm.price,
                            (sm.price - rp.historical_price) / rp.historical_price * 100 as change_pct
                        FROM latest_reference_prices rp
                        JOIN stocks s ON rp.symbol = s.symbol
                        JOIN stock_metrics sm ON rp.symbol = sm.symbol
                        WHERE sm.price IS NOT NULL
                        AND s.country = 'US'
                    )
                    SELECT * FROM price_change
                    WHERE change_pct IS NOT NULL
                    ORDER BY change_pct DESC
                    LIMIT %s
                """, (days_back, limit))
                gainers = cursor.fetchall()

                cursor.execute("""
                    WITH latest_reference_prices AS (
                        SELECT DISTINCT ON (symbol)
                            symbol,
                            price as historical_price
                        FROM weekly_prices
                        WHERE week_ending <= CURRENT_DATE - INTERVAL '%s days'
                        ORDER BY symbol, week_ending DESC
                    ),
                    price_change AS (
                        SELECT
                            rp.symbol,
                            s.company_name,
                            sm.price,
                            (sm.price - rp.historical_price) / rp.historical_price * 100 as change_pct
                        FROM latest_reference_prices rp
                        JOIN stocks s ON rp.symbol = s.symbol
                        JOIN stock_metrics sm ON rp.symbol = sm.symbol
                        WHERE sm.price IS NOT NULL
                        AND s.country = 'US'
                    )
                    SELECT * FROM price_change
                    WHERE change_pct IS NOT NULL
                    ORDER BY change_pct ASC
                    LIMIT %s
                """, (days_back, limit))
                losers = cursor.fetchall()

            return jsonify({
                'period': period,
                'gainers': [dict(g) for g in gainers],
                'losers': [dict(l) for l in losers]
            })

        finally:
            deps.db.return_connection(conn)

    except Exception as e:
        logger.error(f"Error getting market movers: {e}")
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
                        'top_holdings': summary.get('holdings_detailed', [])[:3]
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

            upcoming_earnings = []
            if all_symbols:
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
                for row in cursor.fetchall():
                    upcoming_earnings.append({
                        'symbol': row['symbol'],
                        'company_name': row['company_name'],
                        'earnings_date': row['next_earnings_date'].isoformat() if row['next_earnings_date'] else None,
                        'days_until': (row['next_earnings_date'] - date.today()).days if row['next_earnings_date'] else None
                    })

            # 6. Aggregated news (from database cache)
            news_articles = []
            if all_symbols:
                news_articles = deps.db.get_news_articles_multi(list(all_symbols), limit=10)

            return jsonify({
                'portfolios': portfolio_summaries,
                'watchlist': watchlist_data,
                'alerts': alert_summary,
                'strategies': strategy_summaries,
                'upcoming_earnings': upcoming_earnings,
                'news': news_articles
            })

        finally:
            deps.db.return_connection(conn)

    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        return jsonify({'error': str(e)}), 500
