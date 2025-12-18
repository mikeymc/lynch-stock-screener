# ABOUTME: Flask REST API for Lynch stock screener
# ABOUTME: Provides endpoints for screening stocks and retrieving stock analysis

from flask import Flask, jsonify, request, Response, stream_with_context, send_from_directory, session, redirect
from flask_cors import CORS
from flask_session import Session
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json
import math
import time
import os
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import Database

# Load environment variables from .env file
load_dotenv()
from data_fetcher import DataFetcher
from earnings_analyzer import EarningsAnalyzer
from lynch_criteria import LynchCriteria, ALGORITHM_METADATA
from yfinance_price_client import YFinancePriceClient
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
from auth import init_oauth_client, require_user_auth

from algorithm_optimizer import AlgorithmOptimizer
import logging

# Available AI models for analysis generation
AVAILABLE_AI_MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]
DEFAULT_AI_MODEL = "gemini-3-pro-preview"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress noisy third-party library logs
logging.getLogger('yfinance').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('peewee').setLevel(logging.WARNING)

app = Flask(__name__, static_folder='static', static_url_path='')

# Configure Flask sessions
app.config['SECRET_KEY'] = os.getenv('SESSION_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_TYPE'] = os.getenv('SESSION_TYPE', 'filesystem')
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Session cookie settings
# Only use secure cookies in production (HTTPS)
is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
app.config['SESSION_COOKIE_SECURE'] = is_production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize session
Session(app)

# Configure CORS with credentials support
frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
CORS(app,
     resources={r"/api/*": {"origins": [frontend_url]}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
)

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
price_client = YFinancePriceClient()
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



@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})


# ============================================================
# OAuth Authentication Endpoints
# ============================================================

@app.route('/api/auth/google/url', methods=['GET'])
def get_google_auth_url():
    """Get Google OAuth authorization URL"""
    try:
        flow = init_oauth_client()
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        # Store state in session for CSRF protection
        session['oauth_state'] = state
        return jsonify({'url': authorization_url})
    except Exception as e:
        logger.error(f"Error generating OAuth URL: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/google/callback', methods=['GET'])
def google_auth_callback():
    """Handle OAuth callback from Google"""
    try:
        # Get authorization code from query params
        code = request.args.get('code')
        if not code:
            return jsonify({'error': 'No authorization code provided'}), 400

        # Verify state for CSRF protection
        state = request.args.get('state')
        if state != session.get('oauth_state'):
            return jsonify({'error': 'Invalid state parameter'}), 400

        # Exchange code for tokens
        flow = init_oauth_client()
        flow.fetch_token(code=code)

        # Get user info from ID token
        credentials = flow.credentials
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            google_requests.Request(),
            os.getenv('GOOGLE_CLIENT_ID')
        )

        # Extract user information
        google_id = id_info.get('sub')
        email = id_info.get('email')
        name = id_info.get('name')
        picture = id_info.get('picture')

        # Create or update user in database
        user_id = db.create_user(google_id, email, name, picture)

        # Set session
        session['user_id'] = user_id
        session['user_email'] = email
        session['user_name'] = name
        session['user_picture'] = picture

        # Clear OAuth state
        session.pop('oauth_state', None)

        # Redirect to frontend
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
        return redirect(frontend_url)

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/user', methods=['GET'])
def get_current_user():
    """Get current logged-in user info"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    return jsonify({
        'id': session.get('user_id'),
        'email': session.get('user_email'),
        'name': session.get('user_name'),
        'picture': session.get('user_picture')
    })


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user and clear session"""
    session.clear()
    return jsonify({'message': 'Logged out successfully'})


@app.route('/api/auth/test-login', methods=['POST'])
def test_login():
    """Test-only login endpoint for e2e tests"""
    # Only allow in test mode
    if os.environ.get('ENABLE_TEST_AUTH') != 'true':
        return jsonify({'error': 'Test auth not enabled'}), 403

    # Create or get test user
    test_google_id = 'test_google_id_12345'
    test_email = 'test@example.com'
    test_name = 'Test User'
    test_picture = 'https://example.com/test.jpg'

    try:
        user_id = db.create_user(test_google_id, test_email, test_name, test_picture)

        # Set session
        session['user_id'] = user_id
        session['user_email'] = test_email
        session['user_name'] = test_name
        session['user_picture'] = test_picture

        return jsonify({
            'message': 'Test login successful',
            'user': {
                'id': user_id,
                'email': test_email,
                'name': test_name,
                'picture': test_picture
            }
        })
    except Exception as e:
        logger.error(f"Test login error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# Background Job API Endpoints
# ============================================================

# API token for external job creation (GitHub Actions, etc.)
API_AUTH_TOKEN = os.environ.get('API_AUTH_TOKEN')


def check_flexible_auth():
    """
    Check authentication - accepts EITHER OAuth session OR API token.
    Returns error response or None if authorized.
    
    This allows:
    - Frontend users to use OAuth (session-based)
    - GitHub Actions to use API token (Bearer header)
    - Local dev without auth (if API_AUTH_TOKEN not configured)
    """
    # Check if user is authenticated via OAuth session
    if 'user_id' in session:
        return None  # Authorized via OAuth
    
    # Check if request has valid API token
    if API_AUTH_TOKEN:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            if token == API_AUTH_TOKEN:
                return None  # Authorized via API token
        
        # Neither OAuth nor valid API token provided
        return jsonify({'error': 'Unauthorized', 'message': 'Please log in or provide API token'}), 401
    
    # No API_AUTH_TOKEN configured (local dev) - allow all requests
    return None


@app.route('/api/jobs', methods=['POST'])
def create_job():
    """Create a new background job (accepts OAuth session OR API token)"""
    # Check authentication (OAuth OR API token)
    auth_error = check_flexible_auth()
    if auth_error:
        return auth_error

    try:
        data = request.get_json()

        if not data or 'type' not in data:
            return jsonify({'error': 'Job type is required'}), 400

        job_type = data['type']
        params = data.get('params', {})

        # For screening jobs, create session if not provided
        session_id = params.get('session_id')  # Check if already provided
        if job_type == 'full_screening' and not session_id:
            algorithm = params.get('algorithm', 'weighted')
            session_id = db.create_session(algorithm=algorithm, total_count=0)
            params['session_id'] = session_id
            logger.info(f"Created screening session {session_id} for job")

        # Check connection pool health before creating job
        pool_stats = db.get_pool_stats()
        if pool_stats['usage_percent'] >= 95:
            logger.error(f"Connection pool near exhaustion: {pool_stats}")
            return jsonify({
                'error': 'Database connection pool exhausted',
                'pool_stats': pool_stats
            }), 503

        logger.info(f"Creating background job: type={job_type}, params={params}")
        job_id = db.create_background_job(job_type, params)
        logger.info(f"Created background job {job_id}")

        # Start worker machine if configured
        fly_manager = get_fly_manager()
        worker_started = fly_manager.ensure_worker_running()
        logger.info(f"Worker startup triggered: {worker_started}")

        response_data = {
            'job_id': job_id,
            'status': 'pending'
        }
        
        # Include session_id in response for screening jobs
        if job_type == 'full_screening' and session_id:
            response_data['session_id'] = session_id

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error creating job: type={data.get('type') if data else 'unknown'}, error={e}", exc_info=True)
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
    """Cancel a background job (accepts OAuth session OR API token)"""
    # Check authentication (OAuth OR API token)
    auth_error = check_flexible_auth()
    if auth_error:
        return auth_error
    
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


@app.route('/api/ai-models', methods=['GET'])
def get_available_models():
    """Return list of available AI models for analysis generation."""
    return jsonify({
        'models': AVAILABLE_AI_MODELS,
        'default': DEFAULT_AI_MODEL
    })


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

    # Backfill missing debt-to-equity data on-demand for annual data
    if period_type == 'annual':
        years_needing_de = [entry['year'] for entry in earnings_history if entry.get('debt_to_equity') is None]
        if years_needing_de:
            logger.info(f"[{symbol}] Backfilling D/E for {len(years_needing_de)} years on-demand")
            try:
                data_fetcher = DataFetcher(db)
                data_fetcher._backfill_debt_to_equity(symbol.upper(), years_needing_de)
                # Re-fetch earnings history to get the updated data
                earnings_history = db.get_earnings_history(symbol.upper(), period_type)
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

        # Fetch historical price for this year's fiscal year-end from DATABASE
        if fiscal_end:
            try:
                # Get price from cached price_history table
                price_data = db.get_price_history(symbol.upper(), start_date=fiscal_end, end_date=fiscal_end)
                if price_data and len(price_data) > 0:
                    price = price_data[0].get('close')
            except Exception as e:
                logger.debug(f"Error fetching cached price for {symbol} on {fiscal_end}: {e}")
        else:
            # No fiscal_end date, try to get price from December 31
            try:
                dec_31 = f"{year}-12-31"
                price_data = db.get_price_history(symbol.upper(), start_date=dec_31, end_date=dec_31)
                if price_data and len(price_data) > 0:
                    price = price_data[0].get('close')
            except Exception as e:
                logger.debug(f"Error fetching cached price for {symbol} on Dec 31: {e}")
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

    # Get weekly price history for granular chart display from DATABASE
    # Use the earliest year in earnings history as start year
    start_year = min(entry['year'] for entry in earnings_history) if earnings_history else None
    weekly_prices = {}
    weekly_pe_ratios = {}
    try:
        # Get weekly prices from cached weekly_prices table
        weekly_prices = db.get_weekly_prices(symbol.upper(), start_year)
        
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
        logger.debug(f"Error fetching weekly prices for {symbol}: {e}")

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
    """Get recent SEC filings (10-K and 10-Q) for a stock from DATABASE"""
    symbol = symbol.upper()

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only return for US stocks
    country = stock_metrics.get('country', '')
    if country:
        country_upper = country.upper()
        if country_upper not in ('US', 'USA', 'UNITED STATES'):
            return jsonify({})

    # Get filings from database (cached during screening)
    try:
        filings = db.get_sec_filings(symbol)
        return jsonify(filings if filings else {})
    except Exception as e:
        logger.error(f"Error fetching cached filings for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch filings: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/sections', methods=['GET'])
def get_stock_sections(symbol):
    """
    Get key sections from SEC filings (10-K and 10-Q) from DATABASE
    Returns: business, risk_factors, mda, market_risk
    """
    symbol = symbol.upper()
    logger.info(f"[SECTIONS] Fetching cached sections for {symbol}")

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only return for US stocks
    country = stock_metrics.get('country', '')
    if country:
        country_upper = country.upper()
        if country_upper not in ('US', 'USA', 'UNITED STATES'):
            logger.info(f"[SECTIONS] Skipping non-US stock {symbol}")
            return jsonify({'sections': {}, 'cached': True})

    # Get sections from database (cached during screening)
    try:
        sections = db.get_filing_sections(symbol)
        return jsonify({'sections': sections if sections else {}, 'cached': True})
    except Exception as e:
        logger.error(f"Error fetching cached sections for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch sections: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/news', methods=['GET'])
def get_stock_news(symbol):
    """
    Get news articles for a stock from DATABASE
    """
    symbol = symbol.upper()

    try:
        # Get news from database (cached during screening)
        articles = db.get_news_articles(symbol)
        cache_status = db.get_news_cache_status(symbol)
        
        return jsonify({
            'articles': articles if articles else [],
            'cached': True,
            'last_updated': cache_status['last_updated'].isoformat() if cache_status and cache_status.get('last_updated') else None,
            'article_count': len(articles) if articles else 0
        })
    except Exception as e:
        logger.error(f"Error fetching cached news for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch news: {str(e)}'}), 500





@app.route('/api/stock/<symbol>/material-events', methods=['GET'])
def get_material_events(symbol):
    """
    Get material events (8-K filings) for a stock from DATABASE
    """
    symbol = symbol.upper()

    try:
        # Get events from database (cached during screening)
        events = db.get_material_events(symbol)
        cache_status = db.get_material_events_cache_status(symbol)

        return jsonify({
            'events': events if events else [],
            'cached': True,
            'last_updated': cache_status['last_updated'].isoformat() if cache_status and cache_status.get('last_updated') else None,
            'event_count': len(events) if events else 0
        })
    except Exception as e:
        logger.error(f"Error fetching cached material events for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch material events: {str(e)}'}), 500





@app.route('/api/stock/<symbol>/lynch-analysis', methods=['GET'])
@require_user_auth
def get_lynch_analysis(symbol, user_id):
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

    # Check if analysis exists in cache for this user
    cached_analysis = db.get_lynch_analysis(user_id, symbol)
    was_cached = cached_analysis is not None

    # Get model from query parameter and validate
    model = request.args.get('model', DEFAULT_AI_MODEL)
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

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
            user_id,
            symbol,
            stock_data,
            history,
            sections=sections,
            news=news_articles,
            material_events=material_events,
            use_cache=True,
            model_version=model
        )

        # Get timestamp (fetch again if it was just generated)
        if not was_cached:
            cached_analysis = db.get_lynch_analysis(user_id, symbol)

        return jsonify({
            'analysis': analysis_text,
            'cached': was_cached,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error generating Lynch analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/lynch-analysis/refresh', methods=['POST'])
@require_user_auth
def refresh_lynch_analysis(symbol, user_id):
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

    # Get model from request body and validate
    data = request.get_json() or {}
    model = data.get('model', DEFAULT_AI_MODEL)
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Force regeneration
    try:
        # Fetch material events and news articles for context
        material_events = db.get_material_events(symbol, limit=10)
        news_articles = db.get_news_articles(symbol, limit=20)

        analysis_text = lynch_analyst.get_or_generate_analysis(
            user_id,
            symbol,
            stock_data,
            history,
            sections=sections,
            news=news_articles,
            material_events=material_events,
            use_cache=False,
            model_version=model
        )

        cached_analysis = db.get_lynch_analysis(user_id, symbol)

        return jsonify({
            'analysis': analysis_text,
            'cached': False,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error refreshing Lynch analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/unified-chart-analysis', methods=['POST'])
@require_user_auth
def get_unified_chart_analysis(symbol, user_id):
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

    # Get model from request body and validate
    model = data.get('model', DEFAULT_AI_MODEL)
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Check cache first
    force_refresh = data.get('force_refresh', False)
    only_cached = data.get('only_cached', False)

    # Check if all three sections are cached for this user
    cached_growth = db.get_chart_analysis(user_id, symbol, 'growth')
    cached_cash = db.get_chart_analysis(user_id, symbol, 'cash')
    cached_valuation = db.get_chart_analysis(user_id, symbol, 'valuation')

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
            material_events=material_events,
            model_version=model
        )

        # Save each section to cache for this user
        for section_name, analysis_text in sections.items():
            db.set_chart_analysis(user_id, symbol, section_name, analysis_text, model)

        return jsonify({
            'sections': sections,
            'cached': False,
            'generated_at': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error generating unified chart analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/watchlist', methods=['GET'])
@require_user_auth
def get_watchlist(user_id):
    try:
        symbols = db.get_watchlist(user_id)
        return jsonify({'symbols': symbols})
    except Exception as e:
        print(f"Error getting watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/<symbol>', methods=['POST'])
@require_user_auth
def add_to_watchlist(symbol, user_id):
    try:
        db.add_to_watchlist(user_id, symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error adding {symbol} to watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/<symbol>', methods=['DELETE'])
@require_user_auth
def remove_from_watchlist(symbol, user_id):
    try:
        db.remove_from_watchlist(user_id, symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error removing {symbol} from watchlist: {e}")
        return jsonify({'error': str(e)}), 500


# Chat / RAG Endpoints

@app.route('/api/chat/<symbol>/conversations', methods=['GET'])
@require_user_auth
def list_conversations(symbol, user_id):
    """List all conversations for a stock"""
    try:
        conversations = conversation_manager.list_conversations(user_id, symbol.upper())
        return jsonify({'conversations': conversations})
    except Exception as e:
        print(f"Error listing conversations for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<symbol>/new', methods=['POST'])
@require_user_auth
def create_conversation(symbol, user_id):
    """Create a new conversation for a stock"""
    try:
        data = request.get_json() or {}
        title = data.get('title')

        conversation_id = conversation_manager.create_conversation(user_id, symbol.upper(), title)

        return jsonify({
            'conversation_id': conversation_id,
            'symbol': symbol.upper(),
            'title': title
        })
    except Exception as e:
        print(f"Error creating conversation for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/conversation/<int:conversation_id>/messages', methods=['GET'])
@require_user_auth
def get_messages(conversation_id, user_id):
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
@require_user_auth
def send_message(symbol, user_id):
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
            conversation_id = conversation_manager.get_or_create_conversation(user_id, symbol.upper())

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
@require_user_auth
def send_message_stream(symbol, user_id):
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
            conversation_id = conversation_manager.get_or_create_conversation(user_id, symbol.upper())

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
                validation_jobs[job_id] = {'status': 'running', 'progress': 0, 'total': 0}

                # Progress callback to update validation_jobs
                def on_progress(data):
                    validation_jobs[job_id].update({
                        'progress': data['progress'],
                        'total': data['total'],
                        'current_symbol': data.get('current_symbol')
                    })

                summary = validator.run_sp500_backtests(
                    years_back=years_back,
                    max_workers=5,
                    limit=limit,
                    force_rerun=force,
                    overrides=config,
                    progress_callback=on_progress
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
    # Start debugpy if ENABLE_DEBUGPY environment variable is set
    if os.environ.get('ENABLE_DEBUGPY', 'false').lower() == 'true':
        import debugpy
        debugpy.listen(('0.0.0.0', 15679))
        print("⚠️  Debugpy listening on port 15679 - ready for debugger to attach", flush=True)

    try:
        # Always run the app, even when debugging
        port = int(os.environ.get('PORT', 8080))
        print(f"Starting Flask app on port {port}...", flush=True)
        app.run(debug=False, host='0.0.0.0', port=port)
    except Exception as e:
        print(f"CRITICAL ERROR IN MAIN: {e}", flush=True)
        import time
        time.sleep(3600)
