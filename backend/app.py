# ABOUTME: Flask REST API for Lynch stock screener
# ABOUTME: Provides endpoints for screening stocks and retrieving stock analysis

from flask import Flask, jsonify, request, Response, stream_with_context, send_from_directory
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json
import math
import time
import os
import numpy as np
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv
from database import Database

# Load environment variables from .env file
load_dotenv()
from data_fetcher import DataFetcher
from earnings_analyzer import EarningsAnalyzer
from lynch_criteria import LynchCriteria, ALGORITHM_METADATA
from tradingview_price_client import TradingViewPriceClient
from lynch_analyst import LynchAnalyst
from conversation_manager import ConversationManager
from wacc_calculator import calculate_wacc
from backtester import Backtester
from algorithm_validator import AlgorithmValidator
from correlation_analyzer import CorrelationAnalyzer
from algorithm_optimizer import AlgorithmOptimizer
from finnhub_news import FinnhubNewsClient
from stock_rescorer import StockRescorer
from sec_8k_client import SEC8KClient
from fly_machines import get_fly_manager

from algorithm_optimizer import AlgorithmOptimizer
import logging

# Feature flag for background job processing
USE_BACKGROUND_JOBS = os.environ.get('USE_BACKGROUND_JOBS', 'true').lower() == 'true'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress noisy third-party library logs
logging.getLogger('yfinance').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('peewee').setLevel(logging.WARNING)

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# PostgreSQL connection parameters
# Parse DATABASE_URL if available (Fly.io), otherwise use individual env vars
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Parse postgres://user:password@host:port/database
    from urllib.parse import urlparse
    parsed = urlparse(database_url)
    db_host = parsed.hostname
    db_port = parsed.port or 5432
    db_name = parsed.path.lstrip('/')
    db_user = parsed.username
    db_password = parsed.password
else:
    # Use individual environment variables for local development
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = int(os.environ.get('DB_PORT', '5432'))
    db_name = os.environ.get('DB_NAME', 'lynch_stocks')
    db_user = os.environ.get('DB_USER', 'lynch')
    db_password = os.environ.get('DB_PASSWORD', 'lynch_dev_password')

print(f"Connecting to PostgreSQL: {db_user}@{db_host}:{db_port}/{db_name}")
db = Database(
    host=db_host,
    port=db_port,
    database=db_name,
    user=db_user,
    password=db_password
)
fetcher = DataFetcher(db)
analyzer = EarningsAnalyzer(db)
criteria = LynchCriteria(db, analyzer)
# Historical price provider - using TradingView (replaces Schwab)
price_client = TradingViewPriceClient()
lynch_analyst = LynchAnalyst(db)
conversation_manager = ConversationManager(db)
backtester = Backtester(db)
validator = AlgorithmValidator(db)
analyzer_corr = CorrelationAnalyzer(db)
optimizer = AlgorithmOptimizer(db)

# Initialize Finnhub client for news
finnhub_api_key = os.environ.get('FINNHUB_API_KEY', 'd4nkaqpr01qk2nucd6q0d4nkaqpr01qk2nucd6qg')
finnhub_client = FinnhubNewsClient(finnhub_api_key)

# Initialize SEC 8-K client for material events
sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener info@lynchstocks.com')
sec_8k_client = SEC8KClient(sec_user_agent)

# Track running validation/optimization jobs
validation_jobs = {}
optimization_jobs = {}
rescoring_jobs = {}

# Global dict to track active screening threads
active_screenings = {}
screening_lock = threading.Lock()


def clean_nan_values(obj):
    """Recursively replace NaN values with None and convert numpy types for JSON serialization"""
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    elif isinstance(obj, np.ndarray):
        return clean_nan_values(obj.tolist())
    return obj


def resume_incomplete_sessions():
    """Resume any screening sessions that were interrupted by backend restart"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, algorithm, total_count, processed_count
            FROM screening_sessions
            WHERE status = 'running'
        """)
        incomplete_sessions = cursor.fetchall()
        db.return_connection(conn)
        
        for session_id, algorithm, total_count, processed_count in incomplete_sessions:
            print(f"[Startup] Found incomplete session {session_id}: {processed_count}/{total_count} stocks processed")
            
            # Get all symbols
            symbols = fetcher.get_nyse_nasdaq_symbols()
            if not symbols:
                print(f"[Startup] Could not fetch symbols for session {session_id}")
                continue
            
            # Resume from where we left off
            remaining_symbols = symbols[processed_count:]
            
            if remaining_symbols:
                print(f"[Startup] Resuming session {session_id} with {len(remaining_symbols)} remaining stocks")
                
                # Start background thread
                thread = threading.Thread(
                    target=run_screening_background,
                    args=(session_id, remaining_symbols, algorithm, False),
                    daemon=True
                )
                thread.start()
                
                # Track active screening
                with screening_lock:
                    active_screenings[session_id] = {
                        'thread': thread,
                        'started_at': datetime.now().isoformat(),
                        'resumed': True
                    }
            else:
                # No remaining symbols, mark as complete
                print(f"[Startup] Session {session_id} has no remaining symbols, marking complete")
                db.complete_session(session_id, processed_count, 0, 0, 0)
                
    except Exception as e:
        print(f"[Startup] Error resuming incomplete sessions: {e}")
        import traceback
        traceback.print_exc()


def run_screening_background(session_id: int, symbols: list, algorithm: str, force_refresh: bool):
    """
    Run stock screening in background thread.
    Updates progress in database as stocks are processed.
    """
    try:
        print(f"[Session {session_id}] ===== BACKGROUND THREAD STARTED =====")
        print(f"[Session {session_id}] Symbols to process: {len(symbols)}")
        print(f"[Session {session_id}] Algorithm: {algorithm}")
        print(f"[Session {session_id}] Force refresh: {force_refresh}")
        
        # Bulk prefetch market data from TradingView
        print(f"[Session {session_id}] Prefetching market data from TradingView...")
        from tradingview_fetcher import TradingViewFetcher
        tv_fetcher = TradingViewFetcher()
        # Fetch MAX stocks to ensure we get everything (limit=20000)
        market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000)

        # Bulk prefetch institutional ownership from Finviz
        print(f"[Session {session_id}] Prefetching institutional ownership from Finviz...")
        from finviz_fetcher import FinvizFetcher
        finviz_fetcher = FinvizFetcher()
        finviz_cache = finviz_fetcher.fetch_all_institutional_ownership(limit=20000)
        print(f"[Session {session_id}] ✅ Loaded {len(finviz_cache)} institutional ownership values from Finviz")
        
        # Use TradingView symbols as our source of truth
        tv_symbols = list(market_data_cache.keys())
        
        # Apply filters (Warrants, Preferreds, etc) to the TV list immediately
        filtered_tv_symbols = []
        for sym in tv_symbols:
            # Filter preferred/warrants/etc
            if any(char in sym for char in ['$', '-', '.']) and sym not in ['BRK.B', 'BF.B']:
                continue
            if len(sym) >= 5 and sym[-1] in ['W', 'R', 'U']:
                continue
            filtered_tv_symbols.append(sym)
            
        # Determine if we should use the full list or a subset (if user requested a limit)
        FULL_UNIVERSE_THRESHOLD = 5000
        
        if len(symbols) < FULL_UNIVERSE_THRESHOLD and len(symbols) < len(filtered_tv_symbols):
            # User likely requested a limit (e.g. "Screen top 100")
            print(f"[Session {session_id}] User requested limit detected ({len(symbols)} symbols). Using top {len(symbols)} from TradingView.")
            symbols = filtered_tv_symbols[:len(symbols)]
        else:
            # Full screen - use the entire TradingView universe
            print(f"[Session {session_id}] Using full TradingView universe ({len(filtered_tv_symbols)} symbols) as source.")
            symbols = filtered_tv_symbols
            
        # Update session total in DB since the count likely changed
        db.update_session_total_count(session_id, len(symbols))
        
        print(f"[Session {session_id}] ✅ Ready to screen {len(symbols)} stocks (100% market data cached)")
        print()
        
        # Worker function to process a single stock
        def process_stock(symbol):
            try:
                # Pass market data cache and finviz cache to avoid individual yfinance calls
                stock_data = fetcher.fetch_stock_data(symbol, force_refresh, market_data_cache=market_data_cache, finviz_cache=finviz_cache)
                if not stock_data:
                    return None

                evaluation = criteria.evaluate_stock(symbol, algorithm=algorithm)
                if not evaluation:
                    return None

                # Save result to session
                db.save_screening_result(session_id, evaluation)
                return evaluation
                
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                return None
        
        results = []
        processed_count = 0
        failed_symbols = []
        total = len(symbols)
        
        # Process stocks in batches using parallel workers
        # Increased parallelization since we're using local caches (TradingView + Finviz)
        BATCH_SIZE = 10  # Increased from 3
        MAX_WORKERS = 40  # Optimal for I/O-bound operations with cached data
        BATCH_DELAY = 0.5  # Reduced from 1.5s since most data is cached
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for batch_start in range(0, total, BATCH_SIZE):
                # Check if session was cancelled
                with screening_lock:
                    if session_id not in active_screenings:
                        print(f"[Session {session_id}] Cancelled by user, exiting...")
                        return
                
                batch_end = min(batch_start + BATCH_SIZE, total)
                batch = symbols[batch_start:batch_end]
                
                # Submit batch to thread pool
                future_to_symbol = {executor.submit(process_stock, symbol): symbol for symbol in batch}
                
                # Collect results as they complete
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    processed_count += 1
                    
                    try:
                        evaluation = future.result()
                        if evaluation:
                            results.append(evaluation)
                        else:
                            failed_symbols.append(symbol)
                        
                        # Update progress in database
                        db.update_session_progress(session_id, processed_count, symbol)
                        
                    except Exception as e:
                        print(f"Error getting result for {symbol}: {e}")
                        failed_symbols.append(symbol)
                        db.update_session_progress(session_id, processed_count, symbol)
                
                # Rate limiting delay between batches
                if batch_end < total:
                    time.sleep(BATCH_DELAY)
        
        # Automatic retry pass for failed stocks
        if failed_symbols:
            print(f"[Session {session_id}] Retrying {len(failed_symbols)} failed stocks")
            time.sleep(5)
            
            for symbol in failed_symbols:
                try:
                    evaluation = process_stock(symbol)
                    if evaluation:
                        results.append(evaluation)
                        # Do not increment processed_count on retry, as it was already counted in the main loop
                        db.update_session_progress(session_id, processed_count, symbol)
                    time.sleep(2)
                except Exception as e:
                    print(f"Retry error for {symbol}: {e}")
        
        # Calculate final counts
        results_by_status = {}
        if algorithm == 'classic':
            results_by_status = {
                'pass': [r for r in results if r['overall_status'] == 'PASS'],
                'close': [r for r in results if r['overall_status'] == 'CLOSE'],
                'fail': [r for r in results if r['overall_status'] == 'FAIL']
            }
        else:
            results_by_status = {
                'strong_buy': [r for r in results if r['overall_status'] == 'STRONG_BUY'],
                'buy': [r for r in results if r['overall_status'] == 'BUY'],
                'hold': [r for r in results if r['overall_status'] == 'HOLD'],
                'caution': [r for r in results if r['overall_status'] == 'CAUTION'],
                'avoid': [r for r in results if r['overall_status'] == 'AVOID']
            }
        
        total_analyzed = len(results)
        pass_count = len(results_by_status.get('pass', [])) + len(results_by_status.get('strong_buy', []))
        close_count = len(results_by_status.get('close', [])) + len(results_by_status.get('buy', []))
        fail_count = len(results_by_status.get('fail', [])) + len(results_by_status.get('avoid', []))
        
        # Mark session as complete
        db.complete_session(session_id, total_analyzed, pass_count, close_count, fail_count)
        
        print(f"[Session {session_id}] Screening complete: {total_analyzed} stocks analyzed")
        
    except Exception as e:
        print(f"[Session {session_id}] Fatal error in background screening: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Remove from active screenings
        with screening_lock:
            if session_id in active_screenings:
                del active_screenings[session_id]


# Resume incomplete sessions on startup
resume_incomplete_sessions()


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})


# ============================================================
# Background Job API Endpoints
# ============================================================

# API token for external job creation (GitHub Actions, etc.)
API_AUTH_TOKEN = os.environ.get('API_AUTH_TOKEN')


def check_api_auth():
    """Check bearer token authentication. Returns error response or None if authorized."""
    if not API_AUTH_TOKEN:
        # No token configured - allow all requests (local dev)
        return None

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Authorization header required'}), 401

    token = auth_header[7:]  # Remove 'Bearer ' prefix
    if token != API_AUTH_TOKEN:
        return jsonify({'error': 'Invalid token'}), 401

    return None


@app.route('/api/jobs', methods=['POST'])
def create_job():
    """Create a new background job (requires API token if configured)"""
    # Check auth for external requests (skip for internal calls from /api/screen/start)
    if request.headers.get('X-Internal-Request') != 'true':
        auth_error = check_api_auth()
        if auth_error:
            return auth_error

    try:
        data = request.get_json()

        if not data or 'type' not in data:
            return jsonify({'error': 'Job type is required'}), 400

        job_type = data['type']
        params = data.get('params', {})

        job_id = db.create_background_job(job_type, params)

        return jsonify({
            'job_id': job_id,
            'status': 'pending'
        })

    except Exception as e:
        print(f"Error creating job: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job(job_id):
    """Get background job status and details"""
    try:
        job = db.get_background_job(job_id)

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        return jsonify(job)

    except Exception as e:
        print(f"Error getting job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<int:job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """Cancel a background job"""
    try:
        job = db.get_background_job(job_id)

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        db.cancel_job(job_id)

        return jsonify({'status': 'cancelled'})

    except Exception as e:
        print(f"Error cancelling job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/algorithms', methods=['GET'])
def get_algorithms():
    """Return metadata for all available scoring algorithms."""
    return jsonify(ALGORITHM_METADATA)


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get all application settings."""
    try:
        settings = db.get_all_settings()
        return jsonify(settings)
    except Exception as e:
        print(f"Error getting settings: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update application settings."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        for key, item in data.items():
            value = item.get('value')
            description = item.get('description')
            
            # Update setting in DB
            db.set_setting(key, value, description)
            
        # Reload settings in criteria object
        criteria.reload_settings()
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error updating settings: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/stock/<symbol>', methods=['GET'])
def get_stock(symbol):
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    algorithm = request.args.get('algorithm', 'weighted')

    stock_data = fetcher.fetch_stock_data(symbol.upper(), force_refresh)
    if not stock_data:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    evaluation = criteria.evaluate_stock(symbol.upper(), algorithm=algorithm)

    return jsonify({
        'stock_data': clean_nan_values(stock_data),
        'evaluation': clean_nan_values(evaluation)
    })


@app.route('/api/screen/start', methods=['POST'])
def start_screening():
    """Start a new screening session via background job queue or thread"""
    data = request.get_json() or {}
    limit = data.get('limit')
    force_refresh = data.get('force_refresh', False)
    algorithm = data.get('algorithm', 'weighted')

    try:
        print(f"[START] Starting screening with limit={limit}, algorithm={algorithm}")
        print(f"[START] USE_BACKGROUND_JOBS={USE_BACKGROUND_JOBS}")

        # Create session first (needed for both approaches)
        session_id = db.create_session(algorithm=algorithm, total_count=0)
        print(f"[START] Created session {session_id}")

        if USE_BACKGROUND_JOBS:
            # Create background job and wake up worker
            job_id = db.create_background_job('full_screening', {
                'session_id': session_id,
                'algorithm': algorithm,
                'force_refresh': force_refresh,
                'limit': limit
            })
            print(f"[START] Created background job {job_id} for session {session_id}")

            # Start worker machine if configured
            fly_manager = get_fly_manager()
            worker_started = fly_manager.ensure_worker_running()
            print(f"[START] Worker start result: {worker_started}")

            return jsonify({
                'session_id': session_id,
                'job_id': job_id,
                'status': 'pending',
                'use_background_jobs': True
            })
        else:
            # Fall back to in-process threading (original behavior)
            symbols = fetcher.get_nyse_nasdaq_symbols()
            if not symbols:
                print("[START] ERROR: No symbols returned from fetcher")
                return jsonify({'error': 'Unable to fetch stock symbols'}), 500

            print(f"[START] Fetched {len(symbols)} symbols")

            if limit:
                symbols = symbols[:limit]

            total = len(symbols)
            print(f"[START] Will screen {total} symbols")

            # Update session with total count
            db.update_session_total_count(session_id, total)

            # Start background thread
            thread = threading.Thread(
                target=run_screening_background,
                args=(session_id, symbols, algorithm, force_refresh),
                daemon=True
            )

            # Track active screening BEFORE starting thread to avoid race condition
            with screening_lock:
                active_screenings[session_id] = {
                    'thread': thread,
                    'started_at': datetime.now().isoformat()
                }
            print(f"[START] Session {session_id} registered in active_screenings")

            # Now start the thread
            thread.start()
            print(f"[START] Started background thread for session {session_id}")

            return jsonify({
                'session_id': session_id,
                'total_count': total,
                'status': 'started',
                'use_background_jobs': False
            })

    except Exception as e:
        print(f"Error starting screening: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/progress/<int:session_id>', methods=['GET'])
def get_screening_progress(session_id):
    """Get current progress of a screening session"""
    try:
        progress = db.get_session_progress(session_id)
        if not progress:
            return jsonify({'error': 'Session not found'}), 404
        
        # Check if thread is still active
        with screening_lock:
            is_active = session_id in active_screenings
        
        progress['is_active'] = is_active
        return jsonify(progress)
        
    except Exception as e:
        print(f"Error getting progress: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/results/<int:session_id>', methods=['GET'])
def get_screening_results(session_id):
    """Get results for a screening session"""
    try:
        results = db.get_session_results(session_id)
        # Clean NaN values before returning
        clean_results = [clean_nan_values(result) for result in results]
        return jsonify({'results': clean_results})
    except Exception as e:
        print(f"Error getting results: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/stop/<int:session_id>', methods=['POST'])
def stop_screening(session_id):
    """Stop an active screening session"""
    try:
        # Check if session exists
        progress = db.get_session_progress(session_id)

        if not progress:
            # Session doesn't exist (likely database was reset)
            # Remove from active screenings anyway to clean up
            with screening_lock:
                if session_id in active_screenings:
                    del active_screenings[session_id]

            return jsonify({
                'status': 'not_found',
                'message': f'Session {session_id} not found (database may have been reset)',
                'progress': None
            }), 404

        # Mark session as cancelled
        db.cancel_session(session_id)

        # Remove from active screenings (thread will exit on next check)
        with screening_lock:
            if session_id in active_screenings:
                del active_screenings[session_id]

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


@app.route('/api/screen', methods=['GET'])
def screen_stocks():
    limit_param = request.args.get('limit')
    limit = int(limit_param) if limit_param else None
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    algorithm = request.args.get('algorithm', 'weighted')

    def generate():
        session_id = None
        try:
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Fetching stock list...'})}\n\n"

            symbols = fetcher.get_nyse_nasdaq_symbols()
            # symbols = ['AAPL', 'MSFT', 'GOOG', 'AMD', 'F', 'NVDA', 'ABNB', 'AMD']

            if not symbols:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Unable to fetch stock symbols'})}\n\n"
                return

            if limit:
                symbols = symbols[:limit]

            total = len(symbols)
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Found {total} stocks to screen...'})}\n\n"

            # Create a new screening session
            session_id = db.create_session(total_analyzed=0, pass_count=0, close_count=0, fail_count=0)

            # Worker function to process a single stock
            def process_stock(symbol):
                try:
                    stock_data = fetcher.fetch_stock_data(symbol, force_refresh)
                    if not stock_data:
                        print(f"No stock data returned for {symbol}")
                        return None

                    evaluation = criteria.evaluate_stock(symbol, algorithm=algorithm)
                    if not evaluation:
                        print(f"No evaluation returned for {symbol}")
                        return None

                    # Save result to session
                    db.save_screening_result(session_id, evaluation)
                    return evaluation
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")
                    import traceback
                    traceback.print_exc()
                    return None

            results = []
            processed_count = 0
            failed_symbols = []  # Track symbols that failed
            
            # Process stocks in batches using parallel workers
            # Increased parallelization since we're using local caches (TradingView + Finviz)
            BATCH_SIZE = 10  # Increased from 3
            MAX_WORKERS = 40  # Optimal for I/O-bound operations with cached data
            BATCH_DELAY = 0.5  # Reduced from 1.5s since most data is cached
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                for batch_start in range(0, total, BATCH_SIZE):
                    batch_end = min(batch_start + BATCH_SIZE, total)
                    batch = symbols[batch_start:batch_end]
                    
                    # Submit batch to thread pool
                    future_to_symbol = {executor.submit(process_stock, symbol): symbol for symbol in batch}
                    
                    # Collect results as they complete
                    for future in as_completed(future_to_symbol):
                        symbol = future_to_symbol[future]
                        processed_count += 1
                        
                        try:
                            evaluation = future.result()
                            if evaluation:
                                results.append(evaluation)
                                clean_eval = clean_nan_values(evaluation)
                                yield f"data: {json.dumps({'type': 'stock_result', 'stock': clean_eval})}\n\n"
                            else:
                                # Track failed stocks for retry
                                failed_symbols.append(symbol)
                            
                            # Send progress update
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'Analyzed {symbol} ({processed_count}/{total})...'})}\n\n"
                            
                            # Send keep-alive heartbeat every stock to prevent Fly.io auto-stop
                            yield f": keep-alive\n\n"
                            
                        except Exception as e:
                            print(f"Error getting result for {symbol}: {e}")
                            failed_symbols.append(symbol)
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'Error with {symbol} ({processed_count}/{total})'})}\n\n"
                    
                    # Rate limiting delay between batches with heartbeat
                    if batch_end < total:
                        time.sleep(BATCH_DELAY)
                        yield f": heartbeat-batch-delay\n\n"

            # Automatic retry pass for failed stocks
            if failed_symbols:
                retry_count = len(failed_symbols)
                yield f"data: {json.dumps({'type': 'progress', 'message': f'Retrying {retry_count} failed stocks with conservative settings...'})}\n\n"
                
                # Wait a bit for rate limits to reset
                time.sleep(5)
                
                # Retry failed stocks one at a time with longer delays
                for i, symbol in enumerate(failed_symbols, 1):
                    try:
                        yield f"data: {json.dumps({'type': 'progress', 'message': f'Retry {i}/{retry_count}: {symbol}...'})}\n\n"
                        
                        evaluation = process_stock(symbol)
                        if evaluation:
                            results.append(evaluation)
                            clean_eval = clean_nan_values(evaluation)
                            yield f"data: {json.dumps({'type': 'stock_result', 'stock': clean_eval})}\n\n"
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'✓ Retry succeeded for {symbol}'})}\n\n"
                        else:
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'✗ Retry failed for {symbol}'})}\n\n"
                        
                        # Keep-alive heartbeat during retry
                        yield f": keep-alive-retry\n\n"
                        
                        # Longer delay between retries to avoid rate limits
                        time.sleep(2)
                    except Exception as e:
                        print(f"Retry error for {symbol}: {e}")
                        yield f"data: {json.dumps({'type': 'progress', 'message': f'✗ Retry error for {symbol}'})}\n\n"
                        time.sleep(2)
                
                yield f"data: {json.dumps({'type': 'progress', 'message': f'Retry pass complete. Successfully recovered {len(results) - (total - retry_count)} stocks.'})}\n\n"


            # Group results by status - support both old and new status formats
            results_by_status = {}
            if algorithm == 'classic':
                results_by_status = {
                    'pass': [r for r in results if r['overall_status'] == 'PASS'],
                    'close': [r for r in results if r['overall_status'] == 'CLOSE'],
                    'fail': [r for r in results if r['overall_status'] == 'FAIL']
                }
            else:
                # New algorithms use different statuses
                results_by_status = {
                    'strong_buy': [r for r in results if r['overall_status'] == 'STRONG_BUY'],
                    'buy': [r for r in results if r['overall_status'] == 'BUY'],
                    'hold': [r for r in results if r['overall_status'] == 'HOLD'],
                    'caution': [r for r in results if r['overall_status'] == 'CAUTION'],
                    'avoid': [r for r in results if r['overall_status'] == 'AVOID']
                }

            # Update session with final counts
            conn = db.get_connection()
            cursor = conn.cursor()
            if algorithm == 'classic':
                cursor.execute("""
                    UPDATE screening_sessions
                    SET total_analyzed = %s, pass_count = %s, close_count = %s, fail_count = %s
                    WHERE id = %s
                """, (len(results), len(results_by_status['pass']), len(results_by_status['close']), len(results_by_status['fail']), session_id))
            else:
                # For new algorithms, map to old schema for backward compatibility
                pass_count = len(results_by_status.get('strong_buy', [])) + len(results_by_status.get('buy', []))
                close_count = len(results_by_status.get('hold', []))
                fail_count = len(results_by_status.get('caution', [])) + len(results_by_status.get('avoid', []))
                cursor.execute("""
                    UPDATE screening_sessions
                    SET total_analyzed = %s, pass_count = %s, close_count = %s, fail_count = %s
                    WHERE id = %s
                """, (len(results), pass_count, close_count, fail_count, session_id))
            conn.commit()
            db.return_connection(conn)

            # Cleanup old sessions, keeping only the 2 most recent
            db.cleanup_old_sessions(keep_count=2)

            # Build completion payload based on algorithm
            completion_payload = {
                'type': 'complete',
                'total_analyzed': len(results),
                'results': results_by_status,
                'algorithm': algorithm
            }
            if algorithm == 'classic':
                completion_payload.update({
                    'pass_count': len(results_by_status['pass']),
                    'close_count': len(results_by_status['close']),
                    'fail_count': len(results_by_status['fail'])
                })
            else:
                completion_payload.update({
                    'strong_buy_count': len(results_by_status.get('strong_buy', [])),
                    'buy_count': len(results_by_status.get('buy', [])),
                    'hold_count': len(results_by_status.get('hold', [])),
                    'caution_count': len(results_by_status.get('caution', [])),
                    'avoid_count': len(results_by_status.get('avoid', []))
                })

            yield f"data: {json.dumps(completion_payload)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(generate()), content_type='text/event-stream')


@app.route('/api/cached', methods=['GET'])
def get_cached_stocks():
    symbols = db.get_all_cached_stocks()

    results = []
    for symbol in symbols:
        evaluation = criteria.evaluate_stock(symbol)
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


@app.route('/api/sessions/latest', methods=['GET'])
def get_latest_session():
    """Get the most recent screening session with all results"""
    session_data = db.get_latest_session()

    if not session_data:
        return jsonify({'error': 'No screening sessions found'}), 404

    # Clean NaN values in results
    if 'results' in session_data:
        session_data['results'] = [clean_nan_values(result) for result in session_data['results']]

    return jsonify(session_data)


@app.route('/api/stock/<symbol>/history', methods=['GET'])
def get_stock_history(symbol):
    """Get historical earnings, revenue, price, and P/E ratio data for charting"""

    # Get period_type parameter (default to 'annual' for backward compatibility)
    period_type = request.args.get('period_type', 'annual').lower()
    if period_type not in ['annual', 'quarterly']:
        return jsonify({'error': f'Invalid period_type: {period_type}. Must be annual or quarterly'}), 400

    # Get earnings history from database (filtered by period_type)
    earnings_history = db.get_earnings_history(symbol.upper(), period_type)

    if not earnings_history:
        return jsonify({'error': f'No historical data found for {symbol}'}), 404

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
    dividend_yield_values = []
    operating_cash_flow_values = []
    capital_expenditures_values = []
    free_cash_flow_values = []

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
        dividend_yield = entry.get('dividend_yield')
        operating_cash_flow = entry.get('operating_cash_flow')
        capital_expenditures = entry.get('capital_expenditures')
        free_cash_flow = entry.get('free_cash_flow')
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
        dividend_yield_values.append(dividend_yield)
        operating_cash_flow_values.append(operating_cash_flow)
        capital_expenditures_values.append(capital_expenditures)
        free_cash_flow_values.append(free_cash_flow)

        price = None

        # Fetch historical price for this year's fiscal year-end
        if fiscal_end:
            # Try TradingView API first if available
            if price_client.is_available():
                try:
                    price = price_client.get_historical_price(symbol.upper(), fiscal_end)
                except Exception as e:
                    print(f"TradingView API error for {symbol} on {fiscal_end}: {e}")
                    price = None

            # Fall back to yfinance if Schwab failed or unavailable
            if price is None:
                try:
                    # Use fiscal year-end date for yfinance
                    # Fetch a few days before and after to handle weekends/holidays
                    from datetime import timedelta
                    fiscal_date = datetime.strptime(fiscal_end, '%Y-%m-%d')
                    start_date = (fiscal_date - timedelta(days=7)).strftime('%Y-%m-%d')
                    end_date = (fiscal_date + timedelta(days=3)).strftime('%Y-%m-%d')

                    hist = ticker.history(start=start_date, end=end_date)

                    if not hist.empty:
                        # Get closing price from the last available day
                        price = hist.iloc[-1]['Close']
                except Exception as e:
                    print(f"yfinance error for {symbol} on {fiscal_end}: {e}")
                    price = None
        else:
            # No fiscal_end date, fall back to December 31
            try:
                start_date = f"{year}-12-01"
                end_date = f"{year}-12-31"

                hist = ticker.history(start=start_date, end=end_date)

                if not hist.empty:
                    price = hist.iloc[-1]['Close']
            except Exception as e:
                print(f"Error fetching historical price for {symbol} year {year}: {e}")
                price = None
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
    stock_metrics = db.get_stock_metrics(symbol.upper())
    wacc_data = calculate_wacc(stock_metrics) if stock_metrics else None

    # Get weekly price history for granular chart display
    # Use the earliest year in earnings history as start year
    start_year = min(entry['year'] for entry in earnings_history) if earnings_history else None
    weekly_prices = {}
    weekly_pe_ratios = {}
    if price_client.is_available():
        try:
            weekly_prices = price_client.get_weekly_price_history(symbol.upper(), start_year)
            
            # Calculate weekly P/E ratios using EPS from earnings history
            # For each week, use the EPS from the corresponding fiscal year
            if weekly_prices.get('dates') and weekly_prices.get('prices'):
                # Build a mapping of year -> EPS from earnings history
                eps_by_year = {}
                for entry in earnings_history:
                    if entry.get('eps') and entry.get('eps') > 0:
                        eps_by_year[entry['year']] = entry['eps']
                
                # Calculate P/E for each week
                weekly_pe_dates = []
                weekly_pe_values = []
                for i, date_str in enumerate(weekly_prices['dates']):
                    year = int(date_str[:4])
                    price = weekly_prices['prices'][i]
                    
                    # Use EPS from the current year, or fall back to previous year
                    eps = eps_by_year.get(year) or eps_by_year.get(year - 1)
                    
                    if eps and eps > 0 and price:
                        pe = price / eps
                        weekly_pe_dates.append(date_str)
                        weekly_pe_values.append(round(pe, 2))
                
                weekly_pe_ratios = {
                    'dates': weekly_pe_dates,
                    'values': weekly_pe_values
                }
        except Exception as e:
            print(f"Error fetching weekly prices for {symbol}: {e}")

    response_data = {
        'labels': labels,
        'eps': eps_values,
        'revenue': revenue_values,
        'price': prices,
        'pe_ratio': pe_ratios,
        'debt_to_equity': debt_to_equity_values,
        'net_income': net_income_values,
        'dividend_amount': dividend_values,
        'dividend_yield': dividend_yield_values,
        'operating_cash_flow': operating_cash_flow_values,
        'capital_expenditures': capital_expenditures_values,
        'free_cash_flow': free_cash_flow_values,
        'history': earnings_history,
        'wacc': wacc_data,
        'weekly_prices': weekly_prices,
        'weekly_pe_ratios': weekly_pe_ratios
    }

    # Clean NaN values before returning
    response_data = clean_nan_values(response_data)
    return jsonify(response_data)


@app.route('/api/stock/<symbol>/filings', methods=['GET'])
def get_stock_filings(symbol):
    """Get recent SEC filings (10-K and 10-Q) for a stock"""
    symbol = symbol.upper()

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only fetch for US stocks
    country = stock_metrics.get('country', '')
    if country:
        country_upper = country.upper()
        if country_upper not in ('US', 'USA', 'UNITED STATES'):
            return jsonify({})

    # Check cache validity
    if db.is_filings_cache_valid(symbol):
        filings = db.get_sec_filings(symbol)
        if filings:
            return jsonify(filings)

    # Fetch fresh filings from EDGAR
    try:
        edgar_fetcher = fetcher.edgar_fetcher
        recent_filings = edgar_fetcher.fetch_recent_filings(symbol)

        if not recent_filings:
            return jsonify({})

        # Save to database
        for filing in recent_filings:
            db.save_sec_filing(
                symbol,
                filing['type'],
                filing['date'],
                filing['url'],
                filing['accession_number']
            )

        # Return the formatted result
        filings = db.get_sec_filings(symbol)
        return jsonify(filings if filings else {})

    except Exception as e:
        print(f"Error fetching filings for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch filings: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/sections', methods=['GET'])
def get_stock_sections(symbol):
    """
    Extract key sections from SEC filings (10-K and 10-Q)
    Returns: business, risk_factors, mda, market_risk
    """
    import sys
    symbol = symbol.upper()
    app.logger.info(f"[SECTIONS] Starting section extraction for {symbol}")
    print(f"[SECTIONS] Starting section extraction for {symbol}", file=sys.stderr, flush=True)

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only fetch for US stocks
    country = stock_metrics.get('country', '')
    app.logger.info(f"[SECTIONS] {symbol} country: {country}")
    print(f"[SECTIONS] {symbol} country: {country}", file=sys.stderr, flush=True)
    if country:
        country_upper = country.upper()
        if country_upper not in ('US', 'USA', 'UNITED STATES'):
            app.logger.info(f"[SECTIONS] Skipping non-US stock {symbol}")
            print(f"[SECTIONS] Skipping non-US stock {symbol}", file=sys.stderr, flush=True)
            return jsonify({'sections': {}, 'cached': False})

    # Check cache validity (30 days)
    if db.is_sections_cache_valid(symbol, max_age_days=30):
        app.logger.info(f"[SECTIONS] Cache is valid for {symbol}")
        print(f"[SECTIONS] Cache is valid for {symbol}", file=sys.stderr, flush=True)
        sections = db.get_filing_sections(symbol)
        if sections:
            return jsonify({'sections': sections, 'cached': True})
    else:
        app.logger.info(f"[SECTIONS] Cache is NOT valid for {symbol}")
        print(f"[SECTIONS] Cache is NOT valid for {symbol}", file=sys.stderr, flush=True)

    # Extract sections using edgartools (no need for filing URLs)
    edgar_fetcher = fetcher.edgar_fetcher
    all_sections = {}

    # Extract from most recent 10-K (Items 1, 1A, 7, 7A)
    try:
        app.logger.info(f"[SECTIONS] Extracting 10-K sections for {symbol}")
        print(f"[SECTIONS] Extracting 10-K sections for {symbol}", file=sys.stderr, flush=True)
        sections_10k = edgar_fetcher.extract_filing_sections(symbol, '10-K')

        # Save each section to database
        for section_name, section_data in sections_10k.items():
            db.save_filing_section(
                symbol,
                section_name,
                section_data['content'],
                section_data['filing_type'],
                section_data['filing_date']
            )
            all_sections[section_name] = section_data

        app.logger.info(f"[SECTIONS] Extracted {len(sections_10k)} sections from 10-K")
        print(f"[SECTIONS] Extracted {len(sections_10k)} sections from 10-K", file=sys.stderr, flush=True)

    except Exception as e:
        print(f"Error extracting 10-K sections for {symbol}: {e}")
        import traceback
        traceback.print_exc()

    # Extract from most recent 10-Q (Items 2, 3)
    try:
        app.logger.info(f"[SECTIONS] Extracting 10-Q sections for {symbol}")
        print(f"[SECTIONS] Extracting 10-Q sections for {symbol}", file=sys.stderr, flush=True)
        sections_10q = edgar_fetcher.extract_filing_sections(symbol, '10-Q')

        # Save and add 10-Q sections (may overwrite 10-K MD&A and Market Risk with more recent data)
        for section_name, section_data in sections_10q.items():
            db.save_filing_section(
                symbol,
                section_name,
                section_data['content'],
                section_data['filing_type'],
                section_data['filing_date']
            )
            all_sections[section_name] = section_data

        app.logger.info(f"[SECTIONS] Extracted {len(sections_10q)} sections from 10-Q")
        print(f"[SECTIONS] Extracted {len(sections_10q)} sections from 10-Q", file=sys.stderr, flush=True)

    except Exception as e:
        print(f"Error extracting 10-Q sections for {symbol}: {e}")
        import traceback
        traceback.print_exc()

    # Return all extracted sections
    return jsonify({'sections': all_sections, 'cached': False})


@app.route('/api/stock/<symbol>/news', methods=['GET'])
def get_stock_news(symbol):
    """
    Get news articles for a stock (from cache or fetch fresh)
    """
    symbol = symbol.upper()

    try:
        # Check cache status
        cache_status = db.get_news_cache_status(symbol)
        
        # If we have cache and it's recent (< 24 hours), return it
        if cache_status and cache_status['last_updated']:
            from datetime import timedelta
            last_updated = cache_status['last_updated']
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            
            if age_hours < 24:
                # Assuming 'logger' is defined elsewhere, e.g., from 'app.logger'
                # If not, replace with 'print' or define 'logger'
                # from flask import current_app as app
                # logger = app.logger
                print(f"Returning cached news for {symbol} ({cache_status['article_count']} articles)")
                articles = db.get_news_articles(symbol)
                return jsonify({
                    'articles': articles,
                    'cached': True,
                    'last_updated': cache_status['last_updated'].isoformat(),
                    'article_count': cache_status['article_count']
                })
        
        # Cache is stale or doesn't exist, fetch fresh news
        print(f"Fetching fresh news for {symbol} from Finnhub")
        raw_articles = finnhub_client.fetch_all_news(symbol)
        
        if not raw_articles:
            return jsonify({
                'articles': [],
                'cached': False,
                'last_updated': datetime.now().isoformat(),
                'article_count': 0
            })
        
        # Format and save articles to database
        for raw_article in raw_articles:
            formatted_article = finnhub_client.format_article(raw_article)
            db.save_news_article(symbol, formatted_article)
        
        # Wait for writes to complete
        db.flush()
        
        # Return fresh articles
        articles = db.get_news_articles(symbol)
        print(f"Fetched and cached {len(articles)} news articles for {symbol}")
        
        return jsonify({
            'articles': articles,
            'cached': False,
            'last_updated': datetime.now().isoformat(),
            'article_count': len(articles)
        })
        
    except Exception as e:
        print(f"Error fetching news for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to fetch news: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/news/refresh', methods=['POST'])
def refresh_stock_news(symbol):
    """
    Force refresh news articles for a stock from Finnhub API
    """
    symbol = symbol.upper()
    
    try:
        print(f"Force refreshing news for {symbol}")
        raw_articles = finnhub_client.fetch_all_news(symbol)
        
        if not raw_articles:
            return jsonify({
                'articles': [],
                'last_updated': datetime.now().isoformat(),
                'article_count': 0
            })
        
        # Format and save articles to database
        for raw_article in raw_articles:
            formatted_article = finnhub_client.format_article(raw_article)
            db.save_news_article(symbol, formatted_article)
        
        # Wait for writes to complete
        db.flush()
        
        # Return fresh articles
        articles = db.get_news_articles(symbol)
        print(f"Refreshed {len(articles)} news articles for {symbol}")
        
        return jsonify({
            'articles': articles,
            'last_updated': datetime.now().isoformat(),
            'article_count': len(articles)
        })
        
    except Exception as e:
        print(f"Error refreshing news for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to refresh news: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/material-events', methods=['GET'])
def get_material_events(symbol):
    """
    Get material events (8-K filings) for a stock (from cache or fetch fresh)
    """
    symbol = symbol.upper()

    try:
        # Check cache status
        cache_status = db.get_material_events_cache_status(symbol)

        # If we have cache and it's recent (< 24 hours), return it
        if cache_status and cache_status['last_updated']:
            from datetime import timedelta
            last_updated = cache_status['last_updated']
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600

            if age_hours < 24:
                print(f"Returning cached material events for {symbol} ({cache_status['event_count']} events)")
                events = db.get_material_events(symbol)
                return jsonify({
                    'events': events,
                    'cached': True,
                    'last_updated': cache_status['last_updated'].isoformat(),
                    'event_count': cache_status['event_count']
                })

        # Cache is stale or doesn't exist, fetch fresh events
        print(f"Fetching fresh material events (8-Ks) for {symbol} from SEC")
        raw_events = sec_8k_client.fetch_recent_8ks(symbol)

        if not raw_events:
            return jsonify({
                'events': [],
                'cached': False,
                'last_updated': datetime.now().isoformat(),
                'event_count': 0
            })

        # Save events to database
        for event in raw_events:
            db.save_material_event(symbol, event)

        # Wait for writes to complete
        db.flush()

        # Return fresh events
        events = db.get_material_events(symbol)
        print(f"Fetched and cached {len(events)} material events for {symbol}")

        return jsonify({
            'events': events,
            'cached': False,
            'last_updated': datetime.now().isoformat(),
            'event_count': len(events)
        })

    except Exception as e:
        print(f"Error fetching material events for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to fetch material events: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/material-events/refresh', methods=['POST'])
def refresh_material_events(symbol):
    """
    Force refresh material events (8-K filings) for a stock from SEC
    """
    symbol = symbol.upper()

    try:
        print(f"Force refreshing material events for {symbol}")
        raw_events = sec_8k_client.fetch_recent_8ks(symbol)

        if not raw_events:
            return jsonify({
                'events': [],
                'last_updated': datetime.now().isoformat(),
                'event_count': 0
            })

        # Save events to database
        for event in raw_events:
            db.save_material_event(symbol, event)

        # Wait for writes to complete
        db.flush()

        # Return fresh events
        events = db.get_material_events(symbol)
        print(f"Refreshed {len(events)} material events for {symbol}")

        return jsonify({
            'events': events,
            'last_updated': datetime.now().isoformat(),
            'event_count': len(events)
        })

    except Exception as e:
        print(f"Error refreshing material events for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to refresh material events: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/lynch-analysis', methods=['GET'])
def get_lynch_analysis(symbol):
    """
    Get Peter Lynch-style analysis for a stock.
    Returns cached analysis if available, otherwise generates a new one.
    """
    symbol = symbol.upper()

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = criteria.evaluate_stock(symbol)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio') if evaluation else None,
        'earnings_cagr': evaluation.get('earnings_cagr') if evaluation else None,
        'revenue_cagr': evaluation.get('revenue_cagr') if evaluation else None
    }

    # Get filing sections if available (for US stocks only)
    sections = None
    country = stock_metrics.get('country', '')
    if not country or country.upper() in ['USA', 'UNITED STATES']:
        sections = db.get_filing_sections(symbol)

    # Check if analysis exists in cache before generating
    cached_analysis = db.get_lynch_analysis(symbol)
    was_cached = cached_analysis is not None

    # If only_cached is requested, return what we have (or None)
    only_cached = request.args.get('only_cached', 'false').lower() == 'true'
    if only_cached:
        if was_cached:
            return jsonify({
                'analysis': cached_analysis['analysis_text'],
                'cached': True,
                'generated_at': cached_analysis['generated_at']
            })
        else:
            return jsonify({
                'analysis': None,
                'cached': False,
                'generated_at': None
            })

    # Get or generate analysis
    try:
        # Fetch material events and news articles for context
        material_events = db.get_material_events(symbol, limit=10)
        news_articles = db.get_news_articles(symbol, limit=20)

        analysis_text = lynch_analyst.get_or_generate_analysis(
            symbol,
            stock_data,
            history,
            sections=sections,
            news=news_articles,
            material_events=material_events,
            use_cache=True
        )

        # Get timestamp (fetch again if it was just generated)
        if not was_cached:
            cached_analysis = db.get_lynch_analysis(symbol)

        return jsonify({
            'analysis': analysis_text,
            'cached': was_cached,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error generating Lynch analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/lynch-analysis/refresh', methods=['POST'])
def refresh_lynch_analysis(symbol):
    """
    Force regeneration of Peter Lynch-style analysis for a stock,
    bypassing the cache.
    """
    symbol = symbol.upper()

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = criteria.evaluate_stock(symbol)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio') if evaluation else None,
        'earnings_cagr': evaluation.get('earnings_cagr') if evaluation else None,
        'revenue_cagr': evaluation.get('revenue_cagr') if evaluation else None
    }

    # Get filing sections if available (for US stocks only)
    sections = None
    country = stock_metrics.get('country', '')
    if not country or country.upper() in ['USA', 'UNITED STATES']:
        sections = db.get_filing_sections(symbol)

    # Force regeneration
    try:
        # Fetch material events and news articles for context
        material_events = db.get_material_events(symbol, limit=10)
        news_articles = db.get_news_articles(symbol, limit=20)

        analysis_text = lynch_analyst.get_or_generate_analysis(
            symbol,
            stock_data,
            history,
            sections=sections,
            news=news_articles,
            material_events=material_events,
            use_cache=False
        )

        cached_analysis = db.get_lynch_analysis(symbol)

        return jsonify({
            'analysis': analysis_text,
            'cached': False,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error refreshing Lynch analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/unified-chart-analysis', methods=['POST'])
def get_unified_chart_analysis(symbol):
    """
    Generate unified Peter Lynch-style analysis for all three chart sections.
    Returns all three sections with shared context and cohesive narrative.
    """
    symbol = symbol.upper()
    data = request.get_json() or {}
    
    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = criteria.evaluate_stock(symbol)
    stock_data = {
        **stock_metrics,
        'peg_ratio': evaluation.get('peg_ratio') if evaluation else None,
        'earnings_cagr': evaluation.get('earnings_cagr') if evaluation else None,
        'revenue_cagr': evaluation.get('revenue_cagr') if evaluation else None
    }

    # Check cache first
    force_refresh = data.get('force_refresh', False)
    only_cached = data.get('only_cached', False)
    
    # Check if all three sections are cached
    cached_growth = db.get_chart_analysis(symbol, 'growth')
    cached_cash = db.get_chart_analysis(symbol, 'cash')
    cached_valuation = db.get_chart_analysis(symbol, 'valuation')
    
    all_cached = cached_growth and cached_cash and cached_valuation
    
    if all_cached and not force_refresh:
        return jsonify({
            'sections': {
                'growth': cached_growth['analysis_text'],
                'cash': cached_cash['analysis_text'],
                'valuation': cached_valuation['analysis_text']
            },
            'cached': True,
            'generated_at': cached_growth['generated_at']
        })
    
    # If only_cached is True and not all sections are cached, return empty
    if only_cached:
        return jsonify({})

    try:
        # Get filing sections if available (for US stocks only)
        sections_data = None
        country = stock_metrics.get('country', '')
        if not country or country.upper() in ['US', 'USA', 'UNITED STATES']:
            sections_data = db.get_filing_sections(symbol)

        # Fetch material events and news articles for context
        material_events = db.get_material_events(symbol, limit=10)
        news_articles = db.get_news_articles(symbol, limit=20)

        # Generate unified analysis with full context
        sections = lynch_analyst.generate_unified_chart_analysis(
            stock_data,
            history,
            sections=sections_data,
            news=news_articles,
            material_events=material_events
        )

        # Save each section to cache
        for section_name, analysis_text in sections.items():
            db.set_chart_analysis(symbol, section_name, analysis_text, lynch_analyst.model_version)

        return jsonify({
            'sections': sections,
            'cached': False,
            'generated_at': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error generating unified chart analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/watchlist', methods=['GET'])
def get_watchlist():
    try:
        symbols = db.get_watchlist()
        return jsonify({'symbols': symbols})
    except Exception as e:
        print(f"Error getting watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/<symbol>', methods=['POST'])
def add_to_watchlist(symbol):
    try:
        db.add_to_watchlist(symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error adding {symbol} to watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/<symbol>', methods=['DELETE'])
def remove_from_watchlist(symbol):
    try:
        db.remove_from_watchlist(symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error removing {symbol} from watchlist: {e}")
        return jsonify({'error': str(e)}), 500


# Chat / RAG Endpoints

@app.route('/api/chat/<symbol>/conversations', methods=['GET'])
def list_conversations(symbol):
    """List all conversations for a stock"""
    try:
        conversations = conversation_manager.list_conversations(symbol.upper())
        return jsonify({'conversations': conversations})
    except Exception as e:
        print(f"Error listing conversations for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<symbol>/new', methods=['POST'])
def create_conversation(symbol):
    """Create a new conversation for a stock"""
    try:
        data = request.get_json() or {}
        title = data.get('title')

        conversation_id = conversation_manager.create_conversation(symbol.upper(), title)

        return jsonify({
            'conversation_id': conversation_id,
            'symbol': symbol.upper(),
            'title': title
        })
    except Exception as e:
        print(f"Error creating conversation for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/conversation/<int:conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id):
    """Get all messages in a conversation"""
    try:
        messages = conversation_manager.get_messages(conversation_id)
        conversation = conversation_manager.get_conversation(conversation_id)

        return jsonify({
            'conversation': conversation,
            'messages': messages
        })
    except Exception as e:
        print(f"Error getting messages for conversation {conversation_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<symbol>/message', methods=['POST'])
def send_message(symbol):
    """
    Send a message and get AI response.
    Creates a new conversation if none exists, or uses the most recent one.
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400

        user_message = data['message']
        conversation_id = data.get('conversation_id')

        # Get or create conversation
        if not conversation_id or conversation_id == 0 or conversation_id == '0':
            conversation_id = conversation_manager.get_or_create_conversation(symbol.upper())

        # Send message and get response
        result = conversation_manager.send_message(conversation_id, user_message)

        return jsonify({
            'conversation_id': conversation_id,
            'user_message': user_message,
            'assistant_message': result['message'],
            'sources': result['sources'],
            'message_id': result['message_id']
        })

    except Exception as e:
        print(f"Error sending message: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<symbol>/message/stream', methods=['POST'])
def send_message_stream(symbol):
    """
    Send a message and stream AI response using Server-Sent Events.
    Creates a new conversation if none exists, or uses the most recent one.
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400

        user_message = data['message']
        conversation_id = data.get('conversation_id')
        lynch_analysis = data.get('lynch_analysis')

        # Get or create conversation
        if not conversation_id or conversation_id == 0 or conversation_id == '0':
            conversation_id = conversation_manager.get_or_create_conversation(symbol.upper())

        def generate():
            """Generate Server-Sent Events"""
            # Send conversation ID first
            yield f"data: {json.dumps({'type': 'conversation_id', 'data': conversation_id})}\n\n"

            # Stream response from conversation manager
            for event in conversation_manager.send_message_stream(conversation_id, user_message, lynch_analysis):
                yield f"data: {json.dumps(event)}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        print(f"Error streaming message: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# Serve React static files
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react_app(path):
    """Serve React app for all non-API routes"""
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/backtest', methods=['POST'])
def run_backtest():
    """Run a backtest for a specific stock."""
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        years_back = int(data.get('years_back', 1))
        
        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400
            
        result = backtester.run_backtest(symbol.upper(), years_back)
        
        if 'error' in result:
            return jsonify(result), 400
            
        return jsonify(clean_nan_values(result))
        
    except Exception as e:
        print(f"Error running backtest: {e}")
        return jsonify({'error': str(e)}), 500




# ============================================================
# Algorithm Validation & Optimization Endpoints
# ============================================================

@app.route('/api/validate/run', methods=['POST'])
def start_validation():
    """Start a validation run for S&P 500 stocks"""
    try:
        data = request.get_json()
        years_back = int(data.get('years_back', 1))
        limit = data.get('limit')  # Optional limit for testing
        force = data.get('force', True)  # Default to True to ensure we test new settings
        config = data.get('config')  # Optional config overrides
        
        # Generate unique job ID
        import uuid
        job_id = str(uuid.uuid4())
        
        # Start validation in background thread
        def run_validation_background():
            try:
                validation_jobs[job_id] = {'status': 'running', 'progress': 0}
                
                summary = validator.run_sp500_backtests(
                    years_back=years_back,
                    max_workers=5,
                    limit=limit,
                    force_rerun=force,
                    overrides=config
                )
                
                # Run correlation analysis
                analysis = analyzer_corr.analyze_results(years_back=years_back)
                
                validation_jobs[job_id] = {
                    'status': 'complete',
                    'summary': summary,
                    'analysis': analysis
                }
            except Exception as e:
                validation_jobs[job_id] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        thread = threading.Thread(target=run_validation_background, daemon=True)
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'years_back': years_back
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/validate/progress/<job_id>', methods=['GET'])
def get_validation_progress(job_id):
    """Get progress of a validation job"""
    if job_id not in validation_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(clean_nan_values(validation_jobs[job_id]))

@app.route('/api/validate/results/<int:years_back>', methods=['GET'])
def get_validation_results(years_back):
    """Get validation results and analysis"""
    try:
        # Get correlation analysis
        analysis = analyzer_corr.analyze_results(years_back=years_back)
        
        if 'error' in analysis:
            return jsonify(analysis), 400
        
        return jsonify(clean_nan_values(analysis))
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/optimize/run', methods=['POST'])
def start_optimization():
    """Start auto-optimization to find best weights"""
    try:
        data = request.get_json()
        years_back = int(data.get('years_back', 1))
        method = data.get('method', 'gradient_descent')
        max_iterations = int(data.get('max_iterations', 50))
        limit = data.get('limit')  # Capture limit for use in background thread

        # Generate unique job ID
        import uuid
        job_id = str(uuid.uuid4())

        # Start optimization in background thread
        def run_optimization_background():
            try:
                optimization_jobs[job_id] = {'status': 'running', 'progress': 0, 'stage': 'optimizing'}

                # Get baseline analysis
                baseline_analysis = analyzer_corr.analyze_results(years_back=years_back)

                # Progress callback
                def on_progress(data):
                    optimization_jobs[job_id].update({
                        'progress': data['iteration'],
                        'best_score': data['best_score'],
                        'best_config': data['best_config']
                    })

                # Run optimization
                result = optimizer.optimize(
                    years_back=years_back,
                    method=method,
                    max_iterations=max_iterations,
                    progress_callback=on_progress
                )

                if 'error' in result:
                    optimization_jobs[job_id] = {
                        'status': 'complete',
                        'result': result,
                        'baseline_analysis': baseline_analysis
                    }
                    return

                # Delete old backtest results to prepare for revalidation with new config
                optimization_jobs[job_id]['stage'] = 'clearing_cache'
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM backtest_results WHERE years_back = %s', (years_back,))
                conn.commit()
                db.return_connection(conn)

                # Run validation with optimized config
                optimization_jobs[job_id]['stage'] = 'revalidating'
                summary = validator.run_sp500_backtests(
                    years_back=years_back,
                    max_workers=5,
                    limit=limit,  # Use same limit as original validation
                    force_rerun=True,
                    overrides=result['best_config']
                )

                # Get optimized analysis
                optimized_analysis = analyzer_corr.analyze_results(years_back=years_back)

                optimization_jobs[job_id] = {
                    'status': 'complete',
                    'result': result,
                    'baseline_analysis': baseline_analysis,
                    'optimized_analysis': optimized_analysis
                }
            except Exception as e:
                optimization_jobs[job_id] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        thread = threading.Thread(target=run_optimization_background, daemon=True)
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'years_back': years_back,
            'method': method
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/optimize/progress/<job_id>', methods=['GET'])
def get_optimization_progress(job_id):
    """Get progress of an optimization job"""
    if job_id not in optimization_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(clean_nan_values(optimization_jobs[job_id]))

@app.route('/api/rescore/run', methods=['POST'])
def start_rescoring():
    """Start rescoring all stocks from latest session with current algorithm settings"""
    try:
        import uuid
        job_id = str(uuid.uuid4())
        
        # Start rescoring in background thread
        def run_rescoring_background():
            try:
                rescoring_jobs[job_id] = {
                    'status': 'running',
                    'progress': 0,
                    'total': 0
                }
                
                # Progress callback
                def on_progress(current, total):
                    rescoring_jobs[job_id].update({
                        'progress': current,
                        'total': total
                    })
                
                # Run rescoring
                rescorer = StockRescorer(db, criteria)
                summary = rescorer.rescore_saved_stocks(
                    algorithm='weighted',
                    progress_callback=on_progress
                )
                
                rescoring_jobs[job_id] = {
                    'status': 'complete',
                    'summary': summary
                }
            except Exception as e:
                logger.error(f"Rescoring failed: {e}", exc_info=True)
                rescoring_jobs[job_id] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        thread = threading.Thread(target=run_rescoring_background, daemon=True)
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'status': 'started'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rescore/progress/<job_id>', methods=['GET'])
def get_rescoring_progress(job_id):
    """Get progress of a rescoring job"""
    if job_id not in rescoring_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(clean_nan_values(rescoring_jobs[job_id]))

@app.route('/api/algorithm/config', methods=['GET', 'POST'])
def algorithm_config():
    """Get or update algorithm configuration"""
    if request.method == 'GET':
        # Get current configuration from settings table (includes all thresholds)
        config = {
            # Weights
            'weight_peg': db.get_setting('weight_peg', 0.50),
            'weight_consistency': db.get_setting('weight_consistency', 0.25),
            'weight_debt': db.get_setting('weight_debt', 0.15),
            'weight_ownership': db.get_setting('weight_ownership', 0.10),
            
            # PEG Thresholds
            'peg_excellent': db.get_setting('peg_excellent', 1.0),
            'peg_good': db.get_setting('peg_good', 1.5),
            'peg_fair': db.get_setting('peg_fair', 2.0),
            
            # Debt Thresholds
            'debt_excellent': db.get_setting('debt_excellent', 0.5),
            'debt_good': db.get_setting('debt_good', 1.0),
            'debt_moderate': db.get_setting('debt_moderate', 2.0),
            
            # Institutional Ownership Thresholds
            'inst_own_min': db.get_setting('inst_own_min', 0.20),
            'inst_own_max': db.get_setting('inst_own_max', 0.60),
            
            # Revenue Growth Thresholds
            'revenue_growth_excellent': db.get_setting('revenue_growth_excellent', 15.0),
            'revenue_growth_good': db.get_setting('revenue_growth_good', 10.0),
            'revenue_growth_fair': db.get_setting('revenue_growth_fair', 5.0),
            
            # Income Growth Thresholds
            'income_growth_excellent': db.get_setting('income_growth_excellent', 15.0),
            'income_growth_good': db.get_setting('income_growth_good', 10.0),
            'income_growth_fair': db.get_setting('income_growth_fair', 5.0),
        }
        
        return jsonify({'current': config})
    
    elif request.method == 'POST':
        # Update configuration - save all provided parameters to settings table
        data = request.get_json()
        
        if 'config' in data:
            config = data['config']
            
            # Save all parameters that are provided
            for key, value in config.items():
                db.set_setting(key, value)

            # Reload settings in LynchCriteria to pick up new thresholds
            criteria.reload_settings()

            # Start async rescoring job
            import uuid
            job_id = str(uuid.uuid4())
            
            def run_rescoring_background():
                try:
                    rescoring_jobs[job_id] = {
                        'status': 'running',
                        'progress': 0,
                        'total': 0
                    }
                    
                    # Progress callback
                    def on_progress(current, total):
                        rescoring_jobs[job_id].update({
                            'progress': current,
                            'total': total
                        })
                    
                    # Run rescoring
                    rescorer = StockRescorer(db, criteria)
                    summary = rescorer.rescore_saved_stocks(
                        algorithm='weighted',
                        progress_callback=on_progress
                    )
                    
                    rescoring_jobs[job_id] = {
                        'status': 'complete',
                        'summary': summary
                    }
                except Exception as e:
                    logger.error(f"Rescoring failed: {e}", exc_info=True)
                    rescoring_jobs[job_id] = {
                        'status': 'error',
                        'error': str(e)
                    }
            
            thread = threading.Thread(target=run_rescoring_background, daemon=True)
            thread.start()

            return jsonify({
                'status': 'updated',
                'config': config,
                'rescore_job_id': job_id
            })
        else:
            return jsonify({'error': 'No config provided'}), 400


@app.route('/api/backtest/results', methods=['GET'])
def get_backtest_results():
    """Get all backtest results"""
    try:
        years_back = request.args.get('years_back', type=int)
        results = db.get_backtest_results(years_back=years_back)
        
        return jsonify(clean_nan_values(results))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
