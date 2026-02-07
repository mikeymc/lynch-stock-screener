# ABOUTME: Flask REST API for Lynch stock screener
# ABOUTME: Provides endpoints for screening stocks and retrieving stock analysis

from flask import Flask, jsonify, request, Response, stream_with_context, send_from_directory, session, redirect
from flask_cors import CORS
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json
import math
import time
import os
import secrets
import string
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone, date
from dotenv import load_dotenv
import psycopg.rows
from database import Database
from email_service import send_verification_email

# Load environment variables from .env file
load_dotenv()

# CRITICAL: Disable EDGAR caching BEFORE any other imports that use edgartools
from sec_rate_limiter import configure_edgartools_rate_limit
configure_edgartools_rate_limit()
from data_fetcher import DataFetcher
from earnings_analyzer import EarningsAnalyzer
from lynch_criteria import LynchCriteria, ALGORITHM_METADATA
from yfinance_price_client import YFinancePriceClient
from stock_analyst import StockAnalyst
from wacc_calculator import calculate_wacc
from backtester import Backtester
from algorithm_validator import AlgorithmValidator
from correlation_analyzer import CorrelationAnalyzer
from algorithm_optimizer import AlgorithmOptimizer
from finnhub_news import FinnhubNewsClient
from stock_rescorer import StockRescorer
from stock_vectors import StockVectors, DEFAULT_ALGORITHM_CONFIG
from sec_8k_client import SEC8KClient
from material_event_summarizer import MaterialEventSummarizer, SUMMARIZABLE_ITEM_CODES
from fly_machines import get_fly_manager
from auth import init_oauth_client, require_user_auth, DEV_AUTH_BYPASS
from characters import get_character, list_characters
from fred_service import get_fred_service, SUPPORTED_SERIES, CATEGORIES

from algorithm_optimizer import AlgorithmOptimizer
from google import genai
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

app = Flask(__name__, static_folder='static')

# Configure ProxyFix for Fly.io reverse proxy
# This tells Flask to trust X-Forwarded-* headers from Fly's proxy
# so it recognizes the custom domain instead of the internal .fly.dev address
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,      # Trust X-Forwarded-For (client IP)
    x_proto=1,    # Trust X-Forwarded-Proto (http/https)
    x_host=1,     # Trust X-Forwarded-Host (custom domain)
    x_prefix=1    # Trust X-Forwarded-Prefix (URL prefix)
)

# Configure Flask sessions with SQLAlchemy for persistence across deployments
app.config['SECRET_KEY'] = os.getenv('SESSION_SECRET_KEY', 'dev-secret-key-change-in-production')

# Database URL for SQLAlchemy session storage
# Use existing DATABASE_URL or construct from individual env vars
database_url_for_sessions = os.environ.get('DATABASE_URL')
if not database_url_for_sessions:
    _db_host = os.environ.get('DB_HOST', 'localhost')
    _db_port = os.environ.get('DB_PORT', '5432')
    _db_name = os.environ.get('DB_NAME', 'lynch_stocks')
    _db_user = os.environ.get('DB_USER', 'lynch')
    _db_password = os.environ.get('DB_PASSWORD', 'lynch_dev_password')
    database_url_for_sessions = f"postgresql+psycopg://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}"
else:
    # Fix deprecated postgres:// scheme (Fly.io uses postgres://, SQLAlchemy requires postgresql://)
    # Also switch to psycopg3 driver (postgresql+psycopg://)
    if database_url_for_sessions.startswith('postgres://'):
        database_url_for_sessions = database_url_for_sessions.replace('postgres://', 'postgresql+psycopg://', 1)
    elif database_url_for_sessions.startswith('postgresql://'):
        database_url_for_sessions = database_url_for_sessions.replace('postgresql://', 'postgresql+psycopg://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url_for_sessions
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Add pool health checks to prevent stale connection errors in Flask-Session
# pool_pre_ping: Test connections before use (detects closed connections)
# pool_recycle: Recycle connections after 5 minutes (before Fly.io Postgres times them out)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_size': 5,
    'max_overflow': 10,
}

# Use SQLAlchemy-backed sessions (persists across deployments)
session_db = SQLAlchemy(app)

app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SESSION_SQLALCHEMY'] = session_db
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Session cookie settings
# Only use secure cookies in production (HTTPS)
is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
app.config['SESSION_COOKIE_SECURE'] = is_production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize session (creates sessions table if not exists)
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
stock_analyst = StockAnalyst(db)
backtester = Backtester(db)
validator = AlgorithmValidator(db)
analyzer_corr = CorrelationAnalyzer(db)
optimizer = AlgorithmOptimizer(db)
event_summarizer = MaterialEventSummarizer()
stock_vectors = StockVectors(db)

# Initialize Finnhub client for news
finnhub_api_key = os.environ.get('FINNHUB_API_KEY')
if not finnhub_api_key:
    logger.warning("FINNHUB_API_KEY not set - news features will be unavailable")
finnhub_client = FinnhubNewsClient(finnhub_api_key) if finnhub_api_key else None

# Initialize SEC 8-K client for material events
sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener info@lynchstocks.com')
sec_8k_client = SEC8KClient(sec_user_agent)

# Track running validation/optimization jobs
validation_jobs = {}
optimization_jobs = {}





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


def generate_conversation_title(message: str) -> str:
    """Generate a concise title for a conversation using Gemini Flash."""
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"""Generate a very concise title (3-4 words) for a conversation that starts with this message.
Return ONLY the title, no quotes, no explanation.

Message: {message[:500]}

Title:"""
        )
        title = response.text.strip()
        # Remove any quotes that might be in the response
        title = title.strip('"\'')
        # Limit to 60 chars max
        if len(title) > 60:
            title = title[:57] + "..."
        return title
    except Exception as e:
        logger.warning(f"Failed to generate title with LLM: {e}")
        # Fallback to truncation
        return message[:50] if len(message) <= 50 else message[:47] + "..."


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
        # Construct dynamic redirect URI based on current host
        # e.g. http://localhost:5001/api/auth/google/callback
        redirect_uri = f"{request.host_url}api/auth/google/callback"
        
        flow = init_oauth_client(redirect_uri=redirect_uri)
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

        # Construct dynamic redirect URI
        redirect_uri = f"{request.host_url}api/auth/google/callback"

        # Exchange code for tokens
        flow = init_oauth_client(redirect_uri=redirect_uri)
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

    user = db.get_user_by_id(session.get('user_id'))
    if not user:
        session.clear()
        return jsonify({'error': 'User not found'}), 401

    return jsonify({
        'id': user['id'],
        'email': user['email'],
        'name': user['name'],
        'picture': user['picture'],
        'has_completed_onboarding': user.get('has_completed_onboarding', False)
    })


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user and clear session"""
    session.clear()
    return jsonify({'message': 'Logged out successfully'})


@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user with email and password"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        email = data.get('email')
        password = data.get('password')
        name = data.get('name')

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        # Check if user already exists
        existing_user = db.get_user_by_email(email)
        if existing_user:
            return jsonify({'error': 'Email already registered'}), 400

        # Create new user
        password_hash = generate_password_hash(password)
        if not name:
            name = email.split('@')[0]
            
        # Generate 6-digit numeric verification code
        verification_code = ''.join(secrets.choice(string.digits) for _ in range(6))
        code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        user_id = db.create_user_with_password(email, password_hash, name, verification_code, code_expires_at)

        # Send Verification Email
        email_sent = send_verification_email(email, verification_code)
        if email_sent:
            logger.info(f"Verification email sent to {email}")
        else:
            logger.error(f"Failed to send verification email to {email}")
            # Fallback log for dev
            logger.info(f"EMAILS FAILED - VERIFICATION CODE FOR {email}: {verification_code}")

        # Do NOT set session - require verification first
        # session['user_id'] = user_id ...

        return jsonify({
            'message': 'Registration successful. Please check your email for the verification code.',
            'user': {
                'id': user_id,
                'email': email,
                'name': name,
                'has_completed_onboarding': False
            }
        })

    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login with email and password"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        # Get user
        user = db.get_user_by_email(email)
        if not user:
            return jsonify({'error': 'Invalid email or password'}), 401
            
        # Verify password
        # Users registered via Google might not have a password hash
        if not user['password_hash']:
             return jsonify({'error': 'Please sign in with Google'}), 401
             
        if not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid email or password'}), 401

        # Check verification status (safely handle missing column for old instances or google users)
        if user.get('is_verified') is False:
             return jsonify({'error': 'Email not verified. Please check your inbox.'}), 403

        # Update last login
        db.update_last_login(user['id'])

        # Set session
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        session['user_name'] = user['name']
        session['user_picture'] = user['picture']

        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user['id'],
                'email': user['email'],
                'name': user['name'],
                'picture': user['picture'],
                'has_completed_onboarding': user.get('has_completed_onboarding', False)
            }
        })

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500


        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/verify', methods=['POST'])
def verify_email():
    """Verify user email with OTP code"""
    try:
        data = request.get_json()
        email = data.get('email')
        code = data.get('code')
        
        if not email or not code:
            return jsonify({'error': 'Email and code are required'}), 400
            
        success = db.verify_user_otp(email, code)
        
        if not success:
             return jsonify({'error': 'Invalid, expired, or incorrect code'}), 400
             
        return jsonify({'message': 'Email verified successfully'})

    except Exception as e:
        logger.error(f"Verification error: {e}")
        return jsonify({'error': str(e)}), 500
        return jsonify({'message': 'Email verified successfully'})


@app.route('/api/user/complete_onboarding', methods=['POST'])
def complete_onboarding():
    """Mark the current user's onboarding as complete"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
        
    try:
        db.mark_onboarding_complete(session['user_id'])
        return jsonify({'message': 'Onboarding completed'})
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        return jsonify({'error': str(e)}), 500

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


def check_for_api_token():
    """
    Check authentication - accepts EITHER OAuth session OR API token.
    Returns error response or None if authorized.
    
    This allows:
    - Frontend users to use OAuth (session-based)
    - GitHub Actions/CLI to use API token (Bearer header)
    """
    # Check if user is authenticated via OAuth session
    if 'user_id' in session:
        return None  # Authorized via OAuth
    
    # Check if dev bypass is enabled
    if DEV_AUTH_BYPASS:
        logger.info("[APP] Bypassing API token check (DEV_AUTH_BYPASS=True)")
        return None
        
    # Check if request has valid API token
    if API_AUTH_TOKEN:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            if token == API_AUTH_TOKEN:
                return None  # Authorized via API token
        
    # Neither OAuth nor valid API token provided
    return jsonify({'error': 'Unauthorized', 'message': 'Please log in or provide API token'}), 401


@app.route('/api/jobs', methods=['POST'])
def create_job():
    """Create a new background job (accepts OAuth session OR API token)"""
    # Check authentication (OAuth OR API token)
    auth_error = check_for_api_token()
    if auth_error:
        return auth_error

    try:
        data = request.get_json()

        if not data or 'type' not in data:
            return jsonify({'error': 'Job type is required'}), 400

        job_type = data['type']
        params = data.get('params', {})
        tier = data.get('tier', 'light')  # Default to light if not specified

        # AUTO-ASSIGN BEEFY TIER for known heavy jobs
        heavy_jobs = {
            'historical_fundamentals_cache', 
            'transcript_cache', 
            'quarterly_fundamentals_cache',
            'strategy_execution',
            'outlook_cache'
        }
        if job_type in heavy_jobs:
            tier = 'beefy'

        # Check connection pool health before creating job
        pool_stats = db.get_pool_stats()
        if pool_stats['usage_percent'] >= 95:
            logger.error(f"Connection pool near exhaustion: {pool_stats}")
            return jsonify({
                'error': 'Database connection pool exhausted',
                'pool_stats': pool_stats
            }), 503

        logger.info(f"Creating background job: type={job_type}, params={params}, tier={tier}")
        job_id = db.create_background_job(job_type, params, tier=tier)
        logger.info(f"Created background job {job_id}")

        # Start worker machine if configured (spawns new worker up to max for parallel jobs)
        fly_manager = get_fly_manager()
        worker_id = fly_manager.start_worker_for_job(tier=tier, max_workers=4)
        logger.info(f"Worker startup triggered: {worker_id}")

        response_data = {
            'job_id': job_id,
            'status': 'pending'
        }

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
    auth_error = check_for_api_token()
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


@app.route('/api/strategies', methods=['POST'])
@require_user_auth
def create_strategy(user_id):
    """Create a new investment strategy."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
            
        # Handle Portfolio creation if needed
        portfolio_id = data.get('portfolio_id')
        if portfolio_id == 'new':
            # Create new portfolio with same name
            # Defaulting to 100k cash as per standard practice
            portfolio_id = db.create_portfolio(user_id, name, initial_cash=100000.0)
        
        strategy_id = db.create_strategy(
            user_id=user_id,
            portfolio_id=portfolio_id,
            name=name,
            description=data.get('description'),
            conditions=data.get('conditions', {}),
            consensus_mode=data.get('consensus_mode', 'both_agree'),
            consensus_threshold=float(data.get('consensus_threshold', 70.0)),
            position_sizing=data.get('position_sizing'),
            exit_conditions=data.get('exit_conditions'),
            schedule_cron=data.get('schedule_cron', '0 9 * * 1-5')
        )
        
        return jsonify({
            'id': strategy_id, 
            'message': 'Strategy created successfully', 
            'portfolio_id': portfolio_id
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating strategy: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategies/<int:strategy_id>', methods=['PUT'])
@require_user_auth
def update_strategy(user_id, strategy_id):
    """Update an existing investment strategy."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        # Verify ownership
        strategy = db.get_strategy(strategy_id)
        if not strategy:
            return jsonify({'error': 'Strategy not found'}), 404
        if strategy['user_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
            
        success = db.update_strategy(
            user_id=user_id,
            strategy_id=strategy_id,
            name=data.get('name'),
            description=data.get('description'),
            conditions=data.get('conditions'),
            consensus_mode=data.get('consensus_mode'),
            consensus_threshold=float(data.get('consensus_threshold')) if data.get('consensus_threshold') else None,
            position_sizing=data.get('position_sizing'),
            exit_conditions=data.get('exit_conditions'),
            schedule_cron=data.get('schedule_cron'),
            portfolio_id=data.get('portfolio_id'),
            enabled=data.get('enabled')
        )
        
        if success:
            return jsonify({'message': 'Strategy updated successfully'})
        else:
            return jsonify({'error': 'No changes made or update failed'}), 400
            
    except Exception as e:
        logger.error(f"Error updating strategy: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategies', methods=['GET'])
@require_user_auth
def get_strategies(user_id):
    """Get all investment strategies for the current user."""
    try:
        strategies = db.get_user_strategies(user_id)
        return jsonify(strategies)
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategies/<int:strategy_id>', methods=['GET'])
@require_user_auth
def get_strategy_detail(user_id, strategy_id):
    """Get detailed strategy info including performance and recent runs."""
    try:
        strategy = db.get_strategy(strategy_id)
        if not strategy:
            return jsonify({'error': 'Strategy not found'}), 404
            
        if strategy['user_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Get performance series
        performance = db.get_strategy_performance(strategy_id)
        
        # Get recent runs
        runs = db.get_strategy_runs(strategy_id, limit=20)
        
        return jsonify({
            'strategy': strategy,
            'performance': performance,
            'runs': runs
        })
    except Exception as e:
        logger.error(f"Error getting strategy detail: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategies/<int:strategy_id>/run', methods=['POST'])
@require_user_auth
def manual_run_strategy(user_id, strategy_id):
    """Manually trigger a strategy execution via background job."""
    try:
        # Verify ownership
        strategy = db.get_strategy(strategy_id)
        if not strategy:
            return jsonify({'error': 'Strategy not found'}), 404

        if strategy['user_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Create background job for strategy execution (beefy tier)
        job_id = db.create_background_job(
            job_type='strategy_execution',
            params={'strategy_id': strategy_id},
            tier='beefy'
        )

        logger.info(f"Manual strategy run queued: strategy_id={strategy_id}, job_id={job_id}")

        return jsonify({
            'message': 'Strategy run queued',
            'job_id': job_id,
            'strategy_id': strategy_id
        })
    except Exception as e:
        logger.error(f"Error queueing manual strategy run: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategies/preview', methods=['POST'])
@require_user_auth
def preview_strategy(user_id):
    """Preview stocks that match strategy criteria without executing trades."""
    try:
        data = request.get_json()
        conditions = data.get('conditions', {})

        # Import here to avoid circular dependencies
        from strategy_executor import ConditionEvaluator
        from lynch_criteria import LynchCriteria
        from earnings_analyzer import EarningsAnalyzer

        # Initialize evaluator and scorer
        evaluator = ConditionEvaluator(db)
        analyzer = EarningsAnalyzer(db)
        lynch_criteria = LynchCriteria(db, analyzer)

        # Filter universe
        candidates = evaluator.evaluate_universe(conditions)

        if not candidates:
            return jsonify({'candidates': []})

        # Get min scores for filtering
        scoring_requirements = conditions.get('scoring_requirements', [])
        lynch_min = next((r['min_score'] for r in scoring_requirements if r['character'] == 'lynch'), 0)
        buffett_min = next((r['min_score'] for r in scoring_requirements if r['character'] == 'buffett'), 0)

        # Use vectorized scoring (same as strategy executor) for consistency
        try:
            from stock_vectors import StockVectors, DEFAULT_ALGORITHM_CONFIG
            from characters.buffett import BUFFETT

            # Load stock data with vectorized approach
            vectors = StockVectors(db)
            df_all = vectors.load_vectors(country_filter='US')

            if df_all is None or df_all.empty:
                return jsonify({'candidates': []})

            # Filter to just our candidates
            df = df_all[df_all['symbol'].isin(candidates)].copy()

            if df.empty:
                return jsonify({'candidates': []})

            logger.info(f"[PREVIEW DEBUG] df columns: {df.columns.tolist()}")
            logger.info(f"[PREVIEW DEBUG] df sample: {df[['symbol', 'company_name']].head(3).to_dict() if 'company_name' in df.columns else 'NO COMPANY_NAME'}")

            # Score with Lynch using default config
            df_lynch = lynch_criteria.evaluate_batch(df, DEFAULT_ALGORITHM_CONFIG)
            logger.info(f"[PREVIEW DEBUG] df_lynch columns: {df_lynch.columns.tolist()}")
            logger.info(f"[PREVIEW DEBUG] df_lynch sample: {df_lynch[['symbol', 'company_name']].head(3).to_dict() if 'company_name' in df_lynch.columns else 'NO COMPANY_NAME'}")

            # Score with Buffett - construct config from scoring weights
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

            df_buffett = lynch_criteria.evaluate_batch(df, buffett_config)

            # Merge scores - include company_name from df_lynch
            df_merged = df_lynch[['symbol', 'company_name', 'overall_score']].rename(
                columns={'overall_score': 'lynch_score'}
            )
            df_buffett_scores = df_buffett[['symbol', 'overall_score']].rename(
                columns={'overall_score': 'buffett_score'}
            )
            df_merged = df_merged.merge(df_buffett_scores, on='symbol', how='inner')
            logger.info(f"[PREVIEW DEBUG] df_merged columns: {df_merged.columns.tolist()}")
            logger.info(f"[PREVIEW DEBUG] df_merged sample: {df_merged[['symbol', 'company_name']].head(3).to_dict() if 'company_name' in df_merged.columns else 'NO COMPANY_NAME'}")

            # Filter by minimum thresholds
            df_filtered = df_merged[
                (df_merged['lynch_score'] >= lynch_min) &
                (df_merged['buffett_score'] >= buffett_min)
            ].copy()

            # Create results
            results = []
            for _, row in df_filtered.iterrows():
                results.append({
                    'symbol': row['symbol'],
                    'company_name': row.get('company_name', row['symbol']),
                    'lynch_score': float(row['lynch_score']),
                    'buffett_score': float(row['buffett_score'])
                })

            # Sort by average score descending
            results.sort(key=lambda x: (x['lynch_score'] + x['buffett_score']) / 2, reverse=True)

            logger.info(f"[PREVIEW DEBUG] Final results count: {len(results)}")
            if results:
                logger.info(f"[PREVIEW DEBUG] First result: {results[0]}")

        except Exception as e:
            logger.error(f"Error in vectorized scoring for preview: {e}")
            return jsonify({'error': f'Scoring failed: {str(e)}'}), 500

        return jsonify({'candidates': results})

    except Exception as e:
        logger.error(f"Error previewing strategy: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategies/runs/<int:run_id>/decisions', methods=['GET'])
@require_user_auth
def get_run_decisions(user_id, run_id):
    """Get decisions for a specific strategy run."""
    try:
        # Verify ownership via strategy -> run -> decision chain
        # Use a join or two-step lookup. For now, simple lookup.
        run = db.get_strategy_run(run_id)
        if not run:
            return jsonify({'error': 'Run not found'}), 404
            
        strategy = db.get_strategy(run['strategy_id'])
        if not strategy or strategy['user_id'] != user_id:
             return jsonify({'error': 'Unauthorized'}), 403

        decisions = db.get_run_decisions(run_id)
        return jsonify(decisions)
    except Exception as e:
        logger.error(f"Error getting run decisions: {e}")
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


@app.route('/api/countries', methods=['GET'])
def get_countries():
    """Get list of countries with stock counts for filtering."""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Get country counts
        cursor.execute("""
            SELECT country, COUNT(*) as count
            FROM stocks
            WHERE country IS NOT NULL
            GROUP BY country
            ORDER BY count DESC
        """)
        
        rows = cursor.fetchall()
        db.return_connection(conn)
        
        countries = [{'code': row[0], 'count': row[1]} for row in rows]
        
        return jsonify({'countries': countries})
    except Exception as e:
        logger.error(f"Error getting countries: {e}")
        return jsonify({'error': str(e)}), 500

def get_characters():
    """Get list of available investment characters."""
    try:
        characters = list_characters()
        return jsonify({
            'characters': [
                {
                    'id': c.id,
                    'name': c.name,
                    'description': c.short_description,
                    'primary_metrics': c.primary_metrics,
                }
                for c in characters
            ]
        })
    except Exception as e:
        logger.error(f"Error getting characters: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/character', methods=['GET'])
@require_user_auth
def get_active_character(user_id):
    """Get the currently active investment character for the logged-in user."""
    try:
        character_id = db.get_user_character(user_id)

        character = get_character(character_id)
        if not character:
            character = get_character('lynch')
            character_id = 'lynch'

        return jsonify({
            'active_character': character_id,
            'character': {
                'id': character.id,
                'name': character.name,
                'description': character.short_description,
                'primary_metrics': character.primary_metrics,
                'hidden_metrics': character.hidden_metrics,
            }
        })
    except Exception as e:
        logger.error(f"Error getting active character: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/character', methods=['PUT'])
@require_user_auth
def set_active_character(user_id):
    """Set the active investment character for the logged-in user."""
    try:
        data = request.get_json()
        if not data or 'character_id' not in data:
            return jsonify({'error': 'character_id is required'}), 400

        character_id = data['character_id']

        # Validate character exists
        character = get_character(character_id)
        if not character:
            return jsonify({'error': f'Unknown character: {character_id}'}), 400

        # Save to user's settings
        db.set_user_character(user_id, character_id)
        db.flush()  # Ensure write is committed

        return jsonify({
            'success': True,
            'active_character': character_id,
            'character': {
                'id': character.id,
                'name': character.name,
                'description': character.short_description,
            }
        })
    except Exception as e:
        logger.error(f"Error setting active character: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/expertise-level', methods=['GET'])
@require_user_auth
def get_expertise_level(user_id):
    """Get the user's expertise level."""
    try:
        expertise_level = db.get_user_expertise_level(user_id)
        return jsonify({
            'expertise_level': expertise_level
        })
    except Exception as e:
        logger.error(f"Error getting expertise level: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/expertise-level', methods=['PUT'])
@require_user_auth
def set_expertise_level(user_id):
    """Set the user's expertise level."""
    try:
        data = request.get_json()
        if not data or 'expertise_level' not in data:
            return jsonify({'error': 'expertise_level is required'}), 400

        expertise_level = data['expertise_level']

        # Validate expertise level
        valid_levels = ['learning', 'practicing', 'expert']
        if expertise_level not in valid_levels:
            return jsonify({'error': f'Invalid expertise_level. Must be one of: {", ".join(valid_levels)}'}), 400

        # Save to user's settings
        db.set_user_expertise_level(user_id, expertise_level)
        db.flush()  # Ensure write is committed

        return jsonify({
            'success': True,
            'expertise_level': expertise_level
        })
    except Exception as e:
        logger.error(f"Error setting expertise level: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/theme', methods=['GET'])
@require_user_auth
def get_user_theme_endpoint(user_id):
    """Get the user's active theme."""
    try:
        theme = db.get_user_theme(user_id)
        return jsonify({'theme': theme})
    except Exception as e:
        logger.error(f"Error getting user theme: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/theme', methods=['PUT'])
@require_user_auth
def set_user_theme_endpoint(user_id):
    """Set the user's active theme."""
    try:
        data = request.get_json()
        if not data or 'theme' not in data:
            return jsonify({'error': 'theme is required'}), 400

        theme = data['theme']

        # Validate theme value
        if theme not in ['light', 'dark', 'system']:
            return jsonify({'error': f'Invalid theme: {theme}. Must be light, dark, or system'}), 400

        db.set_user_theme(user_id, theme)
        db.flush()  # Ensure write is committed

        return jsonify({'success': True, 'theme': theme})
    except Exception as e:
        logger.error(f"Error setting user theme: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/stock/<symbol>', methods=['GET'])
def get_stock(symbol):
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    algorithm = request.args.get('algorithm', 'weighted')

    stock_data = fetcher.fetch_stock_data(symbol.upper(), force_refresh)
    if not stock_data:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get active character: prefer query param, then fallback to setting, then default
    active_character = request.args.get('character') or db.get_setting('active_character') or 'lynch'

    # Load fresh character-specific config using robust helper
    # Use session.get('user_id') if available, otherwise None for system defaults
    user_id = session.get('user_id')
    
    # helper method already handles fallback to system default if user-specific config not found
    db_config = db.get_user_algorithm_config(user_id, active_character)

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

    evaluation = criteria.evaluate_stock(symbol.upper(), algorithm=algorithm, overrides=overrides, character_id=active_character)

    return jsonify({
        'stock_data': clean_nan_values(stock_data),
        'evaluation': clean_nan_values(evaluation)
    })


@app.route('/api/stocks/batch', methods=['POST'])
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
                stock_data = fetcher.fetch_stock_data(symbol.upper(), force_refresh=False)
                if not stock_data:
                    return None
                    
                evaluation = criteria.evaluate_stock(symbol.upper(), algorithm=algorithm)
                
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
@app.route('/api/stock/<symbol>/insider', methods=['GET'])
@require_user_auth
def get_stock_insider_trades(symbol, user_id):
    """
    Get insider trades for a dedicated page.
    """
    symbol = symbol.upper()
    
    # Get all trades
    trades = db.get_insider_trades(symbol)
    
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


@app.route('/api/stock/<symbol>/outlook', methods=['GET'])
def get_stock_outlook(symbol):
    """
    Get data for the 'Future Outlook' tab:
    1. Forward Metrics (PEG, PE, EPS)
    2. Insider Buying/Selling Activity
    3. Inventory vs Sales Growth
    4. Gross Margin Stability
    """
    symbol = symbol.upper()
    
    # 1. Get Metrics (DB)
    metrics = db.get_stock_metrics(symbol)
    if not metrics:
        return jsonify({'error': 'Stock not found (please analyze first)'}), 404
    
    # 2. Get Insider Trades (DB) - filter to last 365 days
    all_trades = db.get_insider_trades(symbol)
    one_year_ago = datetime.now() - timedelta(days=365)
    trades = [
        t for t in all_trades 
        if datetime.strptime(t['transaction_date'], '%Y-%m-%d') >= one_year_ago
    ]
    
    # 3. Calculate Trends (Live from yfinance cache via helper)
    # We do this live because we don't store Inventory/GrossProfit yet
    # Use fetcher's protected methods to assume caching policies apply
    inventory_data = []
    margin_data = []
    
    try:
        # Fetch Financials & Balance Sheet
        financials = fetcher._get_yf_financials(symbol)
        balance_sheet = fetcher._get_yf_balance_sheet(symbol)
        
        if financials is not None and not financials.empty and balance_sheet is not None and not balance_sheet.empty:
            # Common years
            years = sorted([c for c in financials.columns if hasattr(c, 'year')], key=lambda x: x)
            # Filter for last 5 years
            years = years[-5:]
            
            for date in years:
                year_node = {'year': date.year}
                
                # --- Gross Margin ---
                # Gross Profit / Total Revenue
                rev = None
                gross_profit = None
                
                if 'Total Revenue' in financials.index:
                    rev = financials.loc['Total Revenue', date]
                if 'Gross Profit' in financials.index:
                    gross_profit = financials.loc['Gross Profit', date]
                
                if rev and gross_profit and rev != 0:
                    margin = (gross_profit / rev) * 100
                    margin_data.append({'year': date.year, 'value': margin})
                    
                # --- Inventory vs Sales ---
                # Inventory (Balance Sheet) / Revenue (Financials)
                # Compare Growth Rates
                inventory = None
                if 'Inventory' in balance_sheet.index:
                    if date in balance_sheet.columns:
                        inventory = balance_sheet.loc['Inventory', date]
                elif 'Inventories' in balance_sheet.index: # Alternative key
                     if date in balance_sheet.columns:
                        inventory = balance_sheet.loc['Inventories', date]
                
                if inventory is not None and rev is not None and pd.notna(inventory) and pd.notna(rev):
                    year_node['revenue'] = rev
                    year_node['inventory'] = inventory
                    inventory_data.append(year_node)
            
            # Calculate Growth Rates for Inventory Chart
            # Return absolute values (in billions) for cleaner display
            inventory_chart = []
            for item in inventory_data:
                inventory_chart.append({
                    'year': item['year'],
                    'revenue': item['revenue'] / 1e9 if item['revenue'] else 0,  # Convert to billions
                    'inventory': item['inventory'] / 1e9 if item['inventory'] else 0  # Convert to billions
                })

    except Exception as e:
        logger.warning(f"[{symbol}] Failed to calculate outlook trends: {e}")

    # Filter out records with None/NaN values before returning
    margin_data_clean = [m for m in margin_data if m.get('value') is not None and not (isinstance(m.get('value'), float) and math.isnan(m.get('value')))]
    inventory_chart_clean = [i for i in inventory_chart if i.get('revenue') is not None and i.get('inventory') is not None]

    # 4. Get new forward metrics tables
    analyst_estimates = db.get_analyst_estimates(symbol)
    eps_trends = db.get_eps_trends(symbol)
    eps_revisions = db.get_eps_revisions(symbol)
    growth_estimates = db.get_growth_estimates(symbol)
    recommendation_history = db.get_analyst_recommendations(symbol)

    # Calculate current fiscal quarter info
    fiscal_calendar = None
    if analyst_estimates:
        reporting_q = analyst_estimates.get('0q', {})
        next_q = analyst_estimates.get('+1q', {})

        # Determine which quarter we're actually IN right now
        # If 0q has already ended, we're in +1q. Otherwise we're in 0q.
        current_q = reporting_q
        if reporting_q.get('period_end_date'):
            period_end = datetime.strptime(reporting_q['period_end_date'], '%Y-%m-%d')
            today = datetime.now()

            # If the reporting quarter has already ended, we're in the next quarter
            if period_end < today:
                current_q = next_q

        if current_q.get('fiscal_quarter') and current_q.get('fiscal_year'):
            fiscal_calendar = {
                'current_quarter': current_q.get('fiscal_quarter'),
                'current_fiscal_year': current_q.get('fiscal_year'),
                'reporting_quarter': reporting_q.get('fiscal_quarter'),
                'reporting_fiscal_year': reporting_q.get('fiscal_year'),
                'next_earnings_date': metrics.get('next_earnings_date')
            }

    return jsonify({
        'symbol': symbol,
        'metrics': {
            'forward_pe': metrics.get('forward_pe'),
            'forward_peg_ratio': metrics.get('forward_peg_ratio'),
            'forward_eps': metrics.get('forward_eps'),
            'insider_net_buying_6m': metrics.get('insider_net_buying_6m'),
            'next_earnings_date': metrics.get('next_earnings_date'),
            # New fields
            'earnings_growth': metrics.get('earnings_growth'),
            'earnings_quarterly_growth': metrics.get('earnings_quarterly_growth'),
            'revenue_growth': metrics.get('revenue_growth'),
            'recommendation_key': metrics.get('recommendation_key'),
        },
        'analyst_consensus': {
            'rating': metrics.get('analyst_rating'),  # e.g., "buy", "hold", "sell"
            'rating_score': metrics.get('analyst_rating_score'),  # 1.0 (Strong Buy) to 5.0 (Sell)
            'analyst_count': metrics.get('analyst_count'),
            'price_target_high': metrics.get('price_target_high'),
            'price_target_low': metrics.get('price_target_low'),
            'price_target_mean': metrics.get('price_target_mean'),
            'price_target_median': metrics.get('price_target_median'),
        },
        'short_interest': {
            'short_ratio': metrics.get('short_ratio'),  # Days to cover
            'short_percent_float': metrics.get('short_percent_float')
        },
        'current_price': metrics.get('price'),
        'insider_trades': trades,
        'inventory_vs_revenue': clean_nan_values(inventory_chart_clean),
        'gross_margin_history': clean_nan_values(margin_data_clean),
        # New forward metrics sections
        'analyst_estimates': analyst_estimates,  # EPS/Revenue by period
        'eps_trends': eps_trends,  # How estimates changed over time
        'eps_revisions': eps_revisions,  # Up/down revision counts
        'growth_estimates': growth_estimates,  # Stock vs index trend
        'recommendation_history': recommendation_history,  # Monthly buy/hold/sell
        'fiscal_calendar': fiscal_calendar,  # Current quarter and earnings date info
    })


@app.route('/api/stock/<symbol>/transcript', methods=['GET'])
def get_stock_transcript(symbol):
    """
    Get the latest earnings call transcript.
    """
    transcript = db.get_latest_earnings_transcript(symbol)
    
    if not transcript:
        return jsonify({'error': 'No transcript found'}), 404
        
    return jsonify(clean_nan_values(transcript))


@app.route('/api/stock/<symbol>/transcript/summary', methods=['POST'])
def generate_transcript_summary(symbol):
    """
    Generate or retrieve AI summary for the latest earnings transcript.
    Returns cached summary if available, otherwise generates and caches new one.
    """
    try:
        # Get the transcript
        transcript = db.get_latest_earnings_transcript(symbol)
        
        if not transcript:
            return jsonify({'error': 'No transcript found'}), 404
        
        # Check if we already have a cached summary
        if transcript.get('summary'):
            return jsonify({
                'summary': transcript['summary'],
                'cached': True,
                'quarter': transcript['quarter'],
                'fiscal_year': transcript['fiscal_year']
            })
        
        # Generate new summary
        stock = db.get_stock_metrics(symbol)
        company_name = stock.get('company_name', symbol) if stock else symbol
        
        summary = stock_analyst.generate_transcript_summary(
            transcript_text=transcript['transcript_text'],
            company_name=company_name,
            quarter=transcript['quarter'],
            fiscal_year=transcript['fiscal_year']
        )
        
        # Save to database
        db.save_transcript_summary(
            symbol=symbol,
            quarter=transcript['quarter'],
            fiscal_year=transcript['fiscal_year'],
            summary=summary
        )
        db.flush()
        
        return jsonify({
            'summary': summary,
            'cached': False,
            'quarter': transcript['quarter'],
            'fiscal_year': transcript['fiscal_year']
        })
        
    except Exception as e:
        logger.error(f"Error generating transcript summary for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/progress/<int:session_id>', methods=['GET'])
def get_screening_progress(session_id):
    """Get current progress of a screening session"""
    try:
        progress = db.get_session_progress(session_id)
        if not progress:
            return jsonify({'error': 'Session not found'}), 404
        
        return jsonify(progress)
        
    except Exception as e:
        print(f"Error getting progress: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/results/<int:session_id>', methods=['GET'])
def get_screening_results(session_id):
    """Get results for a screening session"""
    try:
        results = db.get_session_results(session_id)
        
        # Enrich results with on-the-fly computed metrics
        for result in results:
            symbol = result.get('symbol')
            
            # Compute P/E range position from cached weekly prices
            pe_range = criteria._calculate_pe_52_week_range(symbol, result.get('pe_ratio'))
            result['pe_52_week_min'] = pe_range.get('pe_52_week_min')
            result['pe_52_week_max'] = pe_range.get('pe_52_week_max')
            result['pe_52_week_position'] = pe_range.get('pe_52_week_position')
            
            # Compute consistency scores from earnings history
            growth_data = analyzer.calculate_earnings_growth(symbol)
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


@app.route('/api/screen/stop/<int:session_id>', methods=['POST'])
def stop_screening(session_id):
    """Stop an active screening session"""
    try:
        # Check if session exists
        progress = db.get_session_progress(session_id)

        if not progress:
            # Session doesn't exist (likely database was reset)


            return jsonify({
                'status': 'not_found',
                'message': f'Session {session_id} not found (database may have been reset)',
                'progress': None
            }), 404

        # Mark session as cancelled
        db.cancel_session(session_id)



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


@app.route('/api/screen/v2', methods=['GET'])
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
    import time
    start_time = time.time()
    
    # Parse query params
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 100, type=int)
    sort_by = request.args.get('sort_by', 'overall_score')
    sort_dir = request.args.get('sort_dir', 'desc')
    search = request.args.get('search', None)
    
    # Check if US-only filter is enabled
    us_stocks_only = db.get_setting('us_stocks_only', True)
    country_filter = 'US' if us_stocks_only else None
    
    # Get active character to load appropriate config
    active_character = db.get_setting('active_character') or 'lynch'

    # Get user's algorithm config filtered by character
    configs = db.get_algorithm_configs()
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
        df = stock_vectors.load_vectors(country_filter=country_filter)
        load_time = time.time() - start_time
        
        # Score all stocks using vectorized method
        score_start = time.time()
        scored_df = criteria.evaluate_batch(df, config)
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


@app.route('/api/screen', methods=['GET'])
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

            symbols = fetcher.get_nyse_nasdaq_symbols()
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
                    stock_data = fetcher.fetch_stock_data(symbol, force_refresh)
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


@app.route('/api/stocks/search', methods=['GET'])
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
            
        results = db.search_stocks(query, limit)
        return jsonify({'results': results})
    except Exception as e:
        logger.error(f"Search endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sessions/latest', methods=['GET'])
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
    character_id = request.args.get('character', None) or db.get_user_character(user_id)
    character = get_character(character_id)

    # Check if US-only filter is enabled (default: True for production)
    us_stocks_only = db.get_setting('us_stocks_only', True)
    country_filter = 'US' if us_stocks_only else None

    # HYBRID APPROACH: Use vectorized for Lynch, database for other characters
    if character_id in ['lynch', 'buffett']:
        # --- VECTORIZED PATH (for performance) ---
        # Get user's algorithm config
        configs = db.get_algorithm_configs()
        
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
            df = stock_vectors.load_vectors(country_filter)
            scored_df = criteria.evaluate_batch(df, config)

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
        session_data = db.get_latest_session(
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
                pe_range = criteria.metric_calculator.calculate_pe_52_week_range(symbol, result)
                result['pe_52_week_min'] = pe_range.get('pe_52_week_min')
                result['pe_52_week_max'] = pe_range.get('pe_52_week_max')
                result['pe_52_week_position'] = pe_range.get('pe_52_week_position')

                # Compute consistency scores from earnings history
                growth_data = analyzer.calculate_earnings_growth(symbol)
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
            weekly_data = db.get_weekly_prices(symbol.upper())
            
            if weekly_data and weekly_data.get('dates') and weekly_data.get('prices'):
                # Find the closest week to target_date
                import pandas as pd
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
                import pandas as pd
                from datetime import datetime, timedelta
                
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
                        db.save_weekly_prices(symbol.upper(), {
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
    stock_metrics = db.get_stock_metrics(symbol.upper())
    wacc_data = calculate_wacc(stock_metrics) if stock_metrics else None

    # Get weekly price history for granular chart display from DATABASE
    # Use the earliest year in earnings history as start year
    start_year = min(entry['year'] for entry in earnings_history) if earnings_history else None
    weekly_prices = {}
    weekly_pe_ratios = {}
    weekly_dividend_yields = {}
    try:
        # Get weekly prices from cached weekly_prices table
        weekly_prices = db.get_weekly_prices(symbol.upper(), start_year)
        
        # Calculate weekly P/E ratios using TTM EPS (Trailing Twelve Months)
        # TTM EPS = Rolling sum of last 4 quarters of net income / shares outstanding
        # This ensures the P/E chart matches the current P/E shown on the stock list
        if weekly_prices.get('dates') and weekly_prices.get('prices'):
            # Get quarterly net income data for TTM calculation
            quarterly_history = db.get_earnings_history(symbol.upper(), period_type='quarterly')
            
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
                    from datetime import datetime
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
        estimates = db.get_analyst_estimates(symbol.upper())
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
        quarterly_history = db.get_earnings_history(symbol.upper(), period_type='quarterly')
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
        
        # Also get any cached summaries
        summaries = db.get_filing_section_summaries(symbol)
        
        # Merge summaries into sections response
        if sections and summaries:
            for section_name, summary_data in summaries.items():
                if section_name in sections:
                    sections[section_name]['summary'] = summary_data['summary']
        
        return jsonify({'sections': sections if sections else {}, 'cached': True})
    except Exception as e:
        logger.error(f"Error fetching cached sections for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch sections: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/section-summaries', methods=['GET'])
def get_section_summaries(symbol):
    """
    Get AI-generated summaries for SEC filing sections.
    Generates summaries on-demand if not cached.
    """
    symbol = symbol.upper()
    logger.info(f"[SECTION-SUMMARIES] Fetching/generating summaries for {symbol}")

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Only return for US stocks
    country = stock_metrics.get('country', '')
    if country:
        country_upper = country.upper()
        if country_upper not in ('US', 'USA', 'UNITED STATES'):
            return jsonify({'summaries': {}, 'cached': True})

    company_name = stock_metrics.get('company_name', symbol)

    try:
        # Get raw sections from database
        sections = db.get_filing_sections(symbol)
        if not sections:
            return jsonify({'summaries': {}, 'message': 'No filing sections available'})

        # Get any existing cached summaries
        cached_summaries = db.get_filing_section_summaries(symbol) or {}
        
        # Check which sections need summaries generated
        summaries = {}
        sections_to_generate = []
        
        for section_name, section_data in sections.items():
            if section_name in cached_summaries:
                # Use cached summary
                summaries[section_name] = {
                    'summary': cached_summaries[section_name]['summary'],
                    'filing_type': section_data.get('filing_type'),
                    'filing_date': section_data.get('filing_date'),
                    'cached': True
                }
            else:
                # Need to generate
                sections_to_generate.append((section_name, section_data))
        
        # Generate missing summaries
        for section_name, section_data in sections_to_generate:
            try:
                content = section_data.get('content', '')
                filing_type = section_data.get('filing_type', '10-K')
                filing_date = section_data.get('filing_date', '')
                
                if not content:
                    continue
                
                # Generate summary using AI
                summary = stock_analyst.generate_filing_section_summary(
                    section_name=section_name,
                    section_content=content,
                    company_name=company_name,
                    filing_type=filing_type
                )
                
                # Cache the summary
                db.save_filing_section_summary(
                    symbol=symbol,
                    section_name=section_name,
                    summary=summary,
                    filing_type=filing_type,
                    filing_date=filing_date
                )
                
                summaries[section_name] = {
                    'summary': summary,
                    'filing_type': filing_type,
                    'filing_date': filing_date,
                    'cached': False
                }
                
                logger.info(f"[SECTION-SUMMARIES] Generated summary for {symbol}/{section_name}")
                
            except Exception as e:
                logger.error(f"Error generating summary for {symbol}/{section_name}: {e}")
                # Continue with other sections even if one fails
                continue
        
        return jsonify({
            'summaries': summaries,
            'generated_count': len(sections_to_generate),
            'cached_count': len(cached_summaries)
        })
        
    except Exception as e:
        logger.error(f"Error fetching section summaries for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to fetch summaries: {str(e)}'}), 500


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


@app.route('/api/stock/<symbol>/reddit', methods=['GET'])
def get_stock_reddit(symbol):
    """
    Get Reddit sentiment data for a stock.
    
    First tries to get cached data from database.
    If no cached data exists, fetches live from Reddit (rate limited).
    Includes top conversations (comments + replies) for top 3 posts.
    """
    symbol = symbol.upper()
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    
    try:
        # Clear cache if refresh requested
        if force_refresh:
            conn = db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM social_sentiment WHERE symbol = %s", (symbol,))
                conn.commit()
                logger.info(f"Cleared {cursor.rowcount} cached Reddit posts for {symbol}")
            finally:
                db.return_connection(conn)
        
        # Try cached data first (unless we just cleared it)
        if not force_refresh:
            posts = db.get_social_sentiment(symbol, limit=20, min_score=10)
            
            if posts:
                return jsonify({
                    'posts': posts,
                    'cached': True,
                    'source': 'database'
                })
        
        # No cached data - fetch live (using Google Search Grounding)
        from reddit_client import RedditClient
        
        # Get company name for disambiguation (important for short symbols like TW)
        company_name = None
        metrics = db.get_stock_metrics(symbol)
        if metrics and metrics.get('company_name'):
            company_name = metrics.get('company_name')

        client = RedditClient()
        raw_posts = client.find_stock_mentions_with_conversations(
            symbol=symbol,
            time_filter='month',
            max_results=10,
            company_name=company_name
        )
        
        # Cache for future requests
        if raw_posts:
            db.save_social_sentiment(raw_posts)
        
        return jsonify({
            'posts': raw_posts,
            'cached': False,
            'source': 'reddit_live'
        })
        
    except Exception as e:
        logger.error(f"Error fetching Reddit data for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch Reddit data: {str(e)}'}), 500





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


@app.route('/api/stock/<symbol>/material-event-summaries', methods=['POST'])
def get_material_event_summaries(symbol):
    """
    Get or generate AI summaries for summarizable material events.
    
    Summarizable item types: 2.02 (earnings), 2.01 (M&A), 1.01 (agreements),
    1.05 (cybersecurity), 2.06 (impairments), 4.02 (accounting issues).
    
    Request body (optional):
        event_ids: List of specific event IDs to summarize
        model: AI model to use (default: gemini-2.5-flash)
    
    Returns:
        summaries: Dict mapping event_id to {summary, cached} objects
        generated_count: Number of newly generated summaries
        cached_count: Number of cached summaries returned
    """
    symbol = symbol.upper()
    data = request.get_json() or {}
    
    try:
        # Get stock info for company name
        stock_metrics = db.get_stock_metrics(symbol)
        if not stock_metrics:
            return jsonify({'error': f'Stock {symbol} not found'}), 404
        
        company_name = stock_metrics.get('company_name', symbol)
        
        # Get all material events for the symbol
        all_events = db.get_material_events(symbol)
        if not all_events:
            return jsonify({
                'summaries': {},
                'generated_count': 0,
                'cached_count': 0,
                'message': 'No material events found'
            })
        
        # Filter to summarizable events
        requested_ids = data.get('event_ids')
        model = data.get('model', 'gemini-2.5-flash')
        
        summarizable_events = []
        for event in all_events:
            item_codes = event.get('sec_item_codes', [])
            if event_summarizer.should_summarize(item_codes):
                # If specific IDs requested, filter to those
                if requested_ids is None or event['id'] in requested_ids:
                    summarizable_events.append(event)
        
        if not summarizable_events:
            return jsonify({
                'summaries': {},
                'generated_count': 0,
                'cached_count': 0,
                'message': 'No summarizable events found'
            })
        
        # Get cached summaries
        event_ids = [e['id'] for e in summarizable_events]
        cached_summaries = db.get_material_event_summaries_batch(event_ids)
        
        # Build response, generating missing summaries
        summaries = {}
        generated_count = 0
        cached_count = 0
        
        for event in summarizable_events:
            event_id = event['id']
            
            if event_id in cached_summaries:
                # Use cached summary
                summaries[event_id] = {
                    'summary': cached_summaries[event_id],
                    'cached': True
                }
                cached_count += 1
            else:
                # Generate new summary
                try:
                    # Check if event has content to summarize
                    if not event.get('content_text'):
                        logger.warning(f"Event {event_id} has no content_text, skipping")
                        continue
                    
                    summary = event_summarizer.generate_summary(
                        event_data=event,
                        company_name=company_name,
                        model_version=model
                    )
                    
                    # Cache the summary
                    db.save_material_event_summary(event_id, summary, model)
                    db.flush()  # Ensure it's written immediately
                    
                    summaries[event_id] = {
                        'summary': summary,
                        'cached': False
                    }
                    generated_count += 1
                    
                    logger.info(f"Generated summary for event {event_id} ({symbol})")
                    
                except Exception as e:
                    logger.error(f"Error generating summary for event {event_id}: {e}")
                    # Continue with other events
                    continue
        
        return jsonify({
            'summaries': summaries,
            'generated_count': generated_count,
            'cached_count': cached_count
        })
        
    except Exception as e:
        logger.error(f"Error generating material event summaries for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to generate summaries: {str(e)}'}), 500



@app.route('/api/stock/<symbol>/thesis', methods=['GET'])
@require_user_auth
def get_stock_thesis(symbol, user_id):
    """
    Get character-specific analysis (thesis) for a stock.
    Supports Lynch vs Buffett based on 'character' query param.
    """
    symbol = symbol.upper()
    character_id = request.args.get('character')
    
    # Check if stock exists
    t0 = time.time()
    stock_metrics = db.get_stock_metrics(symbol)
    t_metrics = (time.time() - t0) * 1000
    if not stock_metrics:
        logger.warning(f"[Thesis][{symbol}] Stock not found (metrics fetch took {t_metrics:.2f}ms)")
        return jsonify({'error': f'Stock {symbol} not found'}), 404
    logger.info(f"[Thesis][{symbol}] Fetched stock metrics in {t_metrics:.2f}ms")

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
        t0 = time.time()
        sections = db.get_filing_sections(symbol)
        t_sections = (time.time() - t0) * 1000
        section_size_mb = 0
        if sections:
            # Rough estimation of size
            section_size_mb = sum(len(s.get('content', '')) for s in sections.values()) / 1024 / 1024
        logger.info(f"[Thesis][{symbol}] Fetched SEC sections in {t_sections:.2f}ms (Size: {section_size_mb:.2f} MB)")

    # Check cache
    cached_analysis = db.get_lynch_analysis(user_id, symbol, character_id=character_id)
    was_cached = cached_analysis is not None
    
    # Get model from query parameter and validate
    model = request.args.get('model', DEFAULT_AI_MODEL)
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Handle 'only_cached' request
    only_cached = request.args.get('only_cached', 'false').lower() == 'true'
    should_stream = request.args.get('stream', 'false').lower() == 'true'

    if only_cached:
        if was_cached:
            return jsonify({
                'analysis': cached_analysis['analysis_text'],
                'cached': True,
                'generated_at': cached_analysis['generated_at'],
                'character_id': cached_analysis.get('character_id', 'lynch')
            })
        else:
            return jsonify({
                'analysis': None,
                'cached': False,
                'generated_at': None
            })

    # Get or generate analysis
    try:
        t_start = time.time()
        logger.info(f"[Thesis][{symbol}] Starting thesis generation request")
        
        # Fetch material events and news articles for context
        t0 = time.time()
        material_events = db.get_material_events(symbol, limit=10)
        t_events = (time.time() - t0) * 1000
        logger.info(f"[Thesis][{symbol}] Fetched material events in {t_events:.2f}ms")
        
        t0 = time.time()
        news_articles = db.get_news_articles(symbol, limit=20)
        t_news = (time.time() - t0) * 1000
        logger.info(f"[Thesis][{symbol}] Fetched news articles in {t_news:.2f}ms")

        if should_stream:
            def generate():
                try:
                    # Send metadata first
                    gen_at = cached_analysis['generated_at'] if was_cached else datetime.now().isoformat()
                    if hasattr(gen_at, 'isoformat'):
                        gen_at = gen_at.isoformat()
                    
                    yield f"data: {json.dumps({'type': 'metadata', 'cached': was_cached, 'generated_at': gen_at})}\n\n"

                    # Get iterator
                    iterator = stock_analyst.get_or_generate_analysis(
                        user_id, symbol, stock_data, history,
                        sections=sections, news=news_articles, material_events=material_events,
                        use_cache=True, model_version=model, character_id=character_id
                    )
                    
                    for chunk in iterator:
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                    
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                except Exception as e:
                    logger.error(f"Streaming error for {symbol}: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return Response(stream_with_context(generate()), mimetype='text/event-stream')

        # Normal synchronous response
        analysis_generator = stock_analyst.get_or_generate_analysis(
            user_id,
            symbol,
            stock_data,
            history,
            sections=sections,
            news=news_articles,
            material_events=material_events,
            use_cache=True,
            model_version=model,
            character_id=character_id
        )
        analysis_text = "".join(analysis_generator)

        # Get timestamp (fetch again if it was just generated)
        if not was_cached:
            cached_analysis = db.get_lynch_analysis(user_id, symbol, character_id=character_id)

        return jsonify({
            'analysis': analysis_text,
            'cached': was_cached,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat(),
            'character_id': character_id
        })
    except Exception as e:
        print(f"Error generating thesis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/thesis/refresh', methods=['POST'])
@require_user_auth
def refresh_stock_thesis(symbol, user_id):
    """
    Force regeneration of character-specific analysis for a stock,
    bypassing the cache.
    """
    symbol = symbol.upper()
    data = request.get_json() or {}
    character_id = data.get('character') or request.args.get('character')

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
    model = data.get('model', DEFAULT_AI_MODEL)
    should_stream = data.get('stream', False)
    
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Force regeneration
    try:
        # Fetch material events and news articles for context
        material_events = db.get_material_events(symbol, limit=10)
        news_articles = db.get_news_articles(symbol, limit=20)

        if should_stream:
            def generate():
                try:
                    # Send metadata first (cached=False since we are forcing refresh)
                    yield f"data: {json.dumps({'type': 'metadata', 'cached': False, 'generated_at': datetime.now().isoformat()})}\n\n"

                    # Get iterator
                    iterator = stock_analyst.get_or_generate_analysis(
                        user_id, symbol, stock_data, history,
                        sections=sections, news=news_articles, material_events=material_events,
                        use_cache=False, model_version=model, character_id=character_id
                    )
                    
                    for chunk in iterator:
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                    
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                except Exception as e:
                    logger.error(f"Streaming refresh error for {symbol}: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return Response(stream_with_context(generate()), mimetype='text/event-stream')

        analysis_generator = stock_analyst.get_or_generate_analysis(
            user_id,
            symbol,
            stock_data,
            history,
            sections=sections,
            news=news_articles,
            material_events=material_events,
            use_cache=False,
            model_version=model,
            character_id=character_id
        )
        analysis_text = "".join(analysis_generator)

        cached_analysis = db.get_lynch_analysis(user_id, symbol, character_id=character_id)

        return jsonify({
            'analysis': analysis_text,
            'cached': False,
            'generated_at': cached_analysis['generated_at'] if cached_analysis else datetime.now().isoformat(),
            'character_id': character_id
        })
    except Exception as e:
        print(f"Error refreshing thesis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/unified-chart-analysis', methods=['POST'])
@require_user_auth
def get_unified_chart_analysis(symbol, user_id):
    """
    Generate unified character-specific analysis for all three chart sections.
    Returns all three sections with shared context and cohesive narrative.
    """
    symbol = symbol.upper()
    data = request.get_json() or {}
    # Check for 'character' (consistent name) or 'character_id' (legacy/specific name)
    character_id = data.get('character') or data.get('character_id')

    # Check if stock exists
    stock_metrics = db.get_stock_metrics(symbol)
    if not stock_metrics:
        return jsonify({'error': f'Stock {symbol} not found'}), 404

    # Get historical data
    history = db.get_earnings_history(symbol)
    if not history:
        return jsonify({'error': f'No historical data for {symbol}'}), 404

    # Prepare stock data for analysis
    evaluation = criteria.evaluate_stock(symbol, character_id=character_id)
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

    # Check for cached unified narrative first (new format)
    cached_narrative = db.get_chart_analysis(user_id, symbol, 'narrative', character_id=character_id)
    
    if cached_narrative and not force_refresh:
        return jsonify({
            'narrative': cached_narrative['analysis_text'],
            'cached': True,
            'generated_at': cached_narrative['generated_at'],
            'character_id': character_id
        })
    
    # Fallback: check for legacy 3-section format
    # Legacy sections are also character-specific now
    cached_growth = db.get_chart_analysis(user_id, symbol, 'growth', character_id=character_id)
    cached_cash = db.get_chart_analysis(user_id, symbol, 'cash', character_id=character_id)
    cached_valuation = db.get_chart_analysis(user_id, symbol, 'valuation', character_id=character_id)
    
    all_legacy_cached = cached_growth and cached_cash and cached_valuation
    
    if all_legacy_cached and not force_refresh:
        # Return legacy sections format for backward compatibility
        return jsonify({
            'sections': {
                'growth': cached_growth['analysis_text'],
                'cash': cached_cash['analysis_text'],
                'valuation': cached_valuation['analysis_text']
            },
            'cached': True,
            'generated_at': cached_growth['generated_at'],
            'character_id': character_id
        })

    # If only_cached is True and nothing is cached, return empty
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
        
        # Fetch earnings transcripts (last 2 quarters)
        transcripts = db.get_earnings_transcripts(symbol, limit=2)
        
        # Fetch summary/thesis brief if it exists
        lynch_brief = db.get_lynch_analysis(user_id, symbol, character_id=character_id)
        lynch_brief_text = lynch_brief['analysis_text'] if lynch_brief else None

        # Generate unified analysis with full context
        result = stock_analyst.generate_unified_chart_analysis(
            stock_data,
            history,
            sections=sections_data,
            news=news_articles,
            material_events=material_events,
            transcripts=transcripts,
            lynch_brief=lynch_brief_text,
            model_version=model,
            user_id=user_id,
            character_id=character_id
        )

        # Save unified narrative to cache (using 'narrative' as section name)
        narrative = result.get('narrative', '')
        db.set_chart_analysis(user_id, symbol, 'narrative', narrative, model, character_id=character_id)

        return jsonify({
            'narrative': narrative,
            'cached': False,
            'generated_at': datetime.now().isoformat(),
            'character_id': character_id
        })
    except Exception as e:
        print(f"Error generating unified chart analysis for {symbol}: {e}")
        return jsonify({'error': f'Failed to generate analysis: {str(e)}'}), 500


@app.route('/api/stock/<symbol>/dcf-recommendations', methods=['POST'])
@require_user_auth
def get_dcf_recommendations(symbol, user_id):
    """
    Generate AI-powered DCF model recommendations.
    Returns three scenarios (conservative, base, optimistic) with reasoning.
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

    # Get model from request body (default to gemini-2.5-flash for DCF)
    model = data.get('model', 'gemini-2.5-flash')
    if model not in AVAILABLE_AI_MODELS:
        return jsonify({'error': f'Invalid model: {model}. Must be one of {AVAILABLE_AI_MODELS}'}), 400

    # Check cache first
    force_refresh = data.get('force_refresh', False)
    only_cached = data.get('only_cached', False)

    cached_recommendations = db.get_dcf_recommendations(user_id, symbol)

    if cached_recommendations and not force_refresh:
        return jsonify({
            'scenarios': cached_recommendations['scenarios'],
            'reasoning': cached_recommendations['reasoning'],
            'cached': True,
            'generated_at': cached_recommendations['generated_at']
        })

    # If only_cached is True and no cache, return empty
    if only_cached:
        return jsonify({})

    try:
        # Get WACC data
        wacc_data = calculate_wacc(stock_metrics) if stock_metrics else None

        # Get filing sections if available (for US stocks only)
        sections_data = None
        country = stock_metrics.get('country', '')
        if not country or country.upper() in ['US', 'USA', 'UNITED STATES']:
            sections_data = db.get_filing_sections(symbol)

        # Fetch material events and news articles for context
        material_events = db.get_material_events(symbol, limit=10)
        news_articles = db.get_news_articles(symbol, limit=20)

        # Generate DCF recommendations
        result = stock_analyst.generate_dcf_recommendations(
            stock_data,
            history,
            wacc_data=wacc_data,
            sections=sections_data,
            news=news_articles,
            material_events=material_events,
            model_version=model
        )

        # Save to cache for this user
        db.set_dcf_recommendations(user_id, symbol, result, model)

        return jsonify({
            'scenarios': result['scenarios'],
            'reasoning': result.get('reasoning', ''),
            'cached': False,
            'generated_at': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error generating DCF recommendations for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to generate recommendations: {str(e)}'}), 500


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


# =============================================================================
# Paper Trading Portfolio Endpoints
# =============================================================================

@app.route('/api/portfolios', methods=['GET'])
@require_user_auth
def list_portfolios(user_id):
    """List all portfolios for the authenticated user with computed values."""
    try:
        portfolios = db.get_user_portfolios(user_id)
        
        # Gather all symbols across all portfolios for a single batch fetch
        all_symbols = set()
        for p in portfolios:
            try:
                holdings = db.get_portfolio_holdings(p['id'])
                for symbol in holdings.keys():
                    all_symbols.add(symbol)
            except Exception:
                pass
        
        # Perform single batch fetch for all portfolio symbols
        prices_map = {}
        if all_symbols:
            from portfolio_service import fetch_current_prices_batch
            prices_map = fetch_current_prices_batch(list(all_symbols), db=db)
        
        # Enrich each portfolio with computed summary data
        enriched_portfolios = []
        for portfolio in portfolios:
            summary = db.get_portfolio_summary(portfolio['id'], use_live_prices=True, prices_map=prices_map)
            if summary:
                enriched_portfolios.append(summary)
            else:
                # Fallback to basic portfolio data if summary fails
                enriched_portfolios.append(portfolio)
        
        return jsonify({'portfolios': enriched_portfolios})
    except Exception as e:
        logger.error(f"Error listing portfolios: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolios', methods=['POST'])
@require_user_auth
def create_portfolio(user_id):
    """Create a new portfolio."""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Name is required'}), 400

        name = data['name']
        initial_cash = data.get('initial_cash', 100000.0)

        portfolio_id = db.create_portfolio(user_id, name, initial_cash)
        portfolio = db.get_portfolio(portfolio_id)

        return jsonify(portfolio), 201
    except Exception as e:
        logger.error(f"Error creating portfolio: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolios/<int:portfolio_id>', methods=['GET'])
@require_user_auth
def get_portfolio(portfolio_id, user_id):
    """Get portfolio details with computed values."""
    try:
        portfolio = db.get_portfolio(portfolio_id)
        if not portfolio or portfolio['user_id'] != user_id:
            return jsonify({'error': 'Portfolio not found'}), 404

        summary = db.get_portfolio_summary(portfolio_id)
        return jsonify(summary)
    except Exception as e:
        logger.error(f"Error getting portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolios/<int:portfolio_id>', methods=['PUT'])
@require_user_auth
def update_portfolio(portfolio_id, user_id):
    """Update portfolio (currently only name)."""
    try:
        portfolio = db.get_portfolio(portfolio_id)
        if not portfolio or portfolio['user_id'] != user_id:
            return jsonify({'error': 'Portfolio not found'}), 404

        data = request.get_json()
        if data and 'name' in data:
            db.rename_portfolio(portfolio_id, data['name'])

        updated = db.get_portfolio(portfolio_id)
        return jsonify(updated)
    except Exception as e:
        logger.error(f"Error updating portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolios/<int:portfolio_id>', methods=['DELETE'])
@require_user_auth
def delete_portfolio(portfolio_id, user_id):
    """Delete a portfolio and all its transactions."""
    try:
        deleted = db.delete_portfolio(portfolio_id, user_id)
        if not deleted:
            return jsonify({'error': 'Portfolio not found'}), 404

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolios/<int:portfolio_id>/transactions', methods=['GET'])
@require_user_auth
def get_portfolio_transactions(portfolio_id, user_id):
    """Get transaction history for a portfolio."""
    try:
        portfolio = db.get_portfolio(portfolio_id)
        if not portfolio or portfolio['user_id'] != user_id:
            return jsonify({'error': 'Portfolio not found'}), 404

        transactions = db.get_portfolio_transactions(portfolio_id)
        return jsonify({'transactions': transactions})
    except Exception as e:
        logger.error(f"Error getting transactions for portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolios/<int:portfolio_id>/trade', methods=['POST'])
@require_user_auth
def execute_portfolio_trade(portfolio_id, user_id):
    """Execute a buy or sell trade."""
    try:
        portfolio = db.get_portfolio(portfolio_id)
        if not portfolio or portfolio['user_id'] != user_id:
            return jsonify({'error': 'Portfolio not found'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        required_fields = ['symbol', 'transaction_type', 'quantity']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        from portfolio_service import execute_trade

        result = execute_trade(
            db=db,
            portfolio_id=portfolio_id,
            symbol=data['symbol'].upper(),
            transaction_type=data['transaction_type'].upper(),
            quantity=int(data['quantity']),
            note=data.get('note')
        )

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        logger.error(f"Error executing trade for portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/portfolios/<int:portfolio_id>/value-history', methods=['GET'])
@require_user_auth
def get_portfolio_value_history(portfolio_id, user_id):
    """Get portfolio value history for charts."""
    try:
        portfolio = db.get_portfolio(portfolio_id)
        if not portfolio or portfolio['user_id'] != user_id:
            return jsonify({'error': 'Portfolio not found'}), 404

        snapshots = db.get_portfolio_snapshots(portfolio_id)
        return jsonify({'snapshots': snapshots})
    except Exception as e:
        logger.error(f"Error getting value history for portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Smart Chat Agent Endpoint (ReAct-based agentic chat)
# =============================================================================

# Lazy-initialize the Smart Chat Agent
_smart_chat_agent = None

def get_smart_chat_agent():
    """Get or create the Smart Chat Agent singleton."""
    global _smart_chat_agent
    if _smart_chat_agent is None:
        from smart_chat_agent import SmartChatAgent
        _smart_chat_agent = SmartChatAgent(db)
    return _smart_chat_agent


@app.route('/api/chat/<symbol>/agent', methods=['POST'])
@require_user_auth
def agent_chat(symbol, user_id):
    """
    Smart Chat Agent endpoint using ReAct pattern.
    
    The agent can:
    - Reason about what data it needs
    - Call tools to fetch financial data
    - Synthesize a comprehensive answer
    
    Streams response via Server-Sent Events.
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400

        user_message = data['message']
        conversation_history = data.get('history', [])
        character_id = data.get('character')

        agent = get_smart_chat_agent()

        def generate():
            """Generate Server-Sent Events for agent response."""
            try:
                for event in agent.chat_stream(symbol.upper(), user_message, conversation_history, user_id, character_id):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                logger.error(f"Agent chat stream error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )

    except Exception as e:
        logger.error(f"Error in agent chat for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<symbol>/agent/sync', methods=['POST'])
@require_user_auth
def agent_chat_sync(symbol, user_id):
    """
    Synchronous Smart Chat Agent endpoint (non-streaming).
    
    Useful for testing or clients that don't support SSE.
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400

        user_message = data['message']
        conversation_history = data.get('history', [])
        character_id = data.get('character')

        agent = get_smart_chat_agent()
        result = agent.chat(symbol.upper(), user_message, conversation_history, user_id, character_id)

        return jsonify(clean_nan_values(result))

    except Exception as e:
        logger.error(f"Error in sync agent chat for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Agent Conversation Persistence Endpoints
# =============================================================================

@app.route('/api/agent/conversations', methods=['GET'])
@require_user_auth
def get_agent_conversations_list(user_id):
    """Get user's agent conversation list."""
    try:
        conversations = db.get_agent_conversations(user_id, limit=10)
        return jsonify({'conversations': conversations})
    except Exception as e:
        logger.error(f"Error getting agent conversations: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/conversations', methods=['POST'])
@require_user_auth
def create_agent_conversation_endpoint(user_id):
    """Create a new agent conversation."""
    try:
        conversation_id = db.create_agent_conversation(user_id)
        return jsonify({'conversation_id': conversation_id})
    except Exception as e:
        logger.error(f"Error creating agent conversation: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/conversation/<int:conversation_id>/messages', methods=['GET'])
@require_user_auth
def get_agent_conversation_messages(conversation_id, user_id):
    """Get messages for an agent conversation."""
    try:
        messages = db.get_agent_messages(conversation_id)
        return jsonify({'messages': messages})
    except Exception as e:
        logger.error(f"Error getting agent messages: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/conversation/<int:conversation_id>/messages', methods=['POST'])
@require_user_auth
def save_agent_conversation_message(conversation_id, user_id):
    """Save a message to an agent conversation."""
    try:
        data = request.get_json()
        if not data or 'role' not in data or 'content' not in data:
            return jsonify({'error': 'role and content required'}), 400
        
        db.save_agent_message(
            conversation_id,
            data['role'],
            data['content'],
            data.get('tool_calls')
        )

        # Auto-generate title from first user message using LLM
        title = None
        if data['role'] == 'user':
            messages = db.get_agent_messages(conversation_id)
            if len(messages) == 1:  # This is the first message
                title = generate_conversation_title(data['content'])
                db.update_conversation_title(conversation_id, title)

        return jsonify({'success': True, 'title': title})
    except Exception as e:
        logger.error(f"Error saving agent message: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/conversation/<int:conversation_id>', methods=['DELETE'])
@require_user_auth
def delete_agent_conversation(conversation_id, user_id):
    """Delete an agent conversation (verifies ownership)."""
    try:
        deleted = db.delete_agent_conversation(conversation_id, user_id)
        if deleted:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Conversation not found or not owned by user'}), 404
    except Exception as e:
        logger.error(f"Error deleting agent conversation: {e}")
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
@require_user_auth
def run_backtest(user_id):
    """Run a backtest for a specific stock."""
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        years_back = int(data.get('years_back', 1))

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        # Get user's active character
        character_id = db.get_user_character(user_id)
        
        # Load the saved configuration for this character
        configs = db.get_algorithm_configs()
        character_config = None
        for config in configs:
            if config.get('character') == character_id:
                character_config = config
                logger.info(f"Using config ID {config.get('id')} for character {character_id}, correlation_5yr: {config.get('correlation_5yr')}")
                break
        
        if not character_config:
            logger.warning(f"No saved configuration found for character {character_id}, using defaults")
        
        # Convert config to overrides format (if found)
        overrides = character_config if character_config else None
        
        result = backtester.run_backtest(symbol.upper(), years_back, overrides=overrides, character_id=character_id)
        
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
                    character_id=data.get('character_id', 'lynch'),  # Use character from request or default to lynch
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
@require_user_auth
def start_optimization(user_id=None):
    """Start auto-optimization to find best weights"""
    try:
        data = request.get_json()
        years_back = int(data.get('years_back', 1))
        method = data.get('method', 'gradient_descent')
        max_iterations = int(data.get('max_iterations', 50))
        limit = data.get('limit')  # Capture limit for use in background thread
        character_id = data.get('character_id', 'lynch') # Default to Lynch if not specified

        # Generate unique job ID
        import uuid
        job_id = str(uuid.uuid4())

        # Start optimization in background thread
        def run_optimization_background():
            try:
                optimization_jobs[job_id] = {'status': 'running', 'progress': 0, 'total': max_iterations, 'stage': 'optimizing'}

                # Get baseline correlation from most recent saved config for this character
                latest_config = db.get_user_algorithm_config(user_id, character_id)
                baseline_correlation = None
                if latest_config:
                    # Prefer correlation_10yr over correlation_5yr
                    baseline_correlation = latest_config.get('correlation_10yr') or latest_config.get('correlation_5yr')
                
                # Create a simple baseline_analysis object with the saved correlation
                baseline_analysis = {
                    'overall_correlation': {
                        'coefficient': baseline_correlation if baseline_correlation else 0.0
                    }
                }

                # Progress callback
                def on_progress(data):
                    optimization_jobs[job_id].update({
                        'progress': data['iteration'],
                        'total': max_iterations,
                        'best_score': data.get('best_correlation', data.get('correlation', 0)),
                        'best_config': data.get('best_config', data['config']),
                        'current_config': data.get('config')
                    })

                # Run optimization
                result = optimizer.optimize(
                    years_back=years_back,
                    character_id=character_id,
                    user_id=user_id,
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
                    overrides=result['best_config'],
                    character_id=character_id
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
    try:
        if job_id not in optimization_jobs:
            return jsonify({'error': 'Job not found'}), 404
        
        job_data = optimization_jobs[job_id]
        if job_data is None:
            return jsonify({'error': 'Job data is None', 'status': 'error'}), 500
        
        return jsonify(clean_nan_values(job_data))
    except Exception as e:
        logger.error(f"Error getting optimization progress for job {job_id}: {e}")
        return jsonify({'error': str(e), 'status': 'error'}), 500



@app.route('/api/algorithm/config', methods=['GET', 'POST'])
@require_user_auth
def algorithm_config(user_id=None):
    """Get or update algorithm configuration for the user's active character.
    
    Source of truth: algorithm_configurations table (filtered by character and user)
    """
    if request.method == 'GET':
        # Check for character_id override in query params
        character_id = request.args.get('character_id')
        
        # If not provided, fallback to user's active character
        if not character_id:
            character_id = db.get_user_character(user_id)
            
        # Get character object to determine defaults
        character = get_character(character_id)
        if not character:
            # Fallback to Lynch if unknown
            character = get_character('lynch')
            
        # Key translation map: backend metric name -> frontend key name
        # The frontend uses shortened keys for historical reasons
        METRIC_TO_FRONTEND_KEY = {
            'peg': 'peg',
            'debt_to_equity': 'debt',
            'earnings_consistency': 'consistency', 
            'institutional_ownership': 'ownership',
            'roe': 'roe',
            'debt_to_earnings': 'debt_to_earnings',
            'gross_margin': 'gross_margin',
        }
        
        # Build dynamic defaults from character config
        default_values = {}
        
        # 1. Map scoring weights and their thresholds
        for sw in character.scoring_weights:
            # Translate metric name to frontend key
            frontend_key = METRIC_TO_FRONTEND_KEY.get(sw.metric, sw.metric)
            
            # Weight key: weight_{frontend_key}
            default_values[f"weight_{frontend_key}"] = sw.weight
            
            # Threshold keys: Use frontend key for consistency
            if sw.metric == 'institutional_ownership':
                # Special case: institutional ownership uses inst_own_min/max instead of excellent/good/fair
                if sw.threshold:
                    # Use the 'excellent' value as the ideal (min), 'good' as max
                    # This is a simplification - ideally we'd have separate min/max in the config
                    default_values['inst_own_min'] = 0.20  # Hardcoded for now
                    default_values['inst_own_max'] = 0.60  # Hardcoded for now
                continue
            
            # Standard threshold keys: {frontend_key}_{level}
            if sw.threshold:
                default_values[f"{frontend_key}_excellent"] = sw.threshold.excellent
                default_values[f"{frontend_key}_good"] = sw.threshold.good
                
                # Special case: debt uses 'moderate' instead of 'fair'
                if sw.metric == 'debt_to_equity':
                    default_values[f"{frontend_key}_moderate"] = sw.threshold.fair
                else:
                    default_values[f"{frontend_key}_fair"] = sw.threshold.fair
        
        # 2. Add common defaults (Revenue/Income growth) if not present
        # These are used by frontend for all characters but might not be in scoring weights
        common_defaults = {
            'revenue_growth_excellent': 15.0,
            'revenue_growth_good': 10.0,
            'revenue_growth_fair': 5.0,
            'income_growth_excellent': 15.0,
            'income_growth_good': 10.0,
            'income_growth_fair': 5.0,
            
            # Also ensure weights that might exist in other characters but not this one
            # are explicitly zeroed out to prevent carrying over values on frontend
            'weight_peg': 0.0,
            'weight_consistency': 0.0,
            'weight_debt': 0.0,
            'weight_ownership': 0.0,
            'weight_roe': 0.0,
            'weight_debt_to_earnings': 0.0,
            'weight_gross_margin': 0.0,
        }
        
        # Merge common defaults (only if not already set by character)
        for k, v in common_defaults.items():
            if k not in default_values:
                default_values[k] = v

        # Load config for user's character from DB
        latest_config = db.get_user_algorithm_config(user_id, character_id)

        if latest_config:
            # Merge DB config with defaults (DB takes precedence)
            config = default_values.copy()
            
            # Update with values from DB
            # We iterate over keys we know about + keys in DB
            all_keys = set(config.keys()) | set(latest_config.keys())
            
            for key in all_keys:
                if key in latest_config:
                   config[key] = latest_config[key]
                   
            # Ensure metadata fields are preserved/added
            config['id'] = latest_config.get('id')
            config['correlation_5yr'] = latest_config.get('correlation_5yr')
            config['correlation_10yr'] = latest_config.get('correlation_10yr')
            
        else:
            # No configs exist for this character - return pure defaults
            config = default_values
            
        return jsonify({'current': config})

    elif request.method == 'POST':
        data = request.get_json()
        if 'config' not in data:
            return jsonify({'error': 'No config provided'}), 400
            
        config = data['config']
        
        # Check for character_id in body
        character_id = data.get('character_id')
        if not character_id:
             # Fallback to active char if not provided/embedded
             character_id = config.get('character', db.get_user_character(user_id))
        
        # Ensure character_id is in config for saving
        config['character'] = character_id
        
        db.save_algorithm_config(config, character=character_id, user_id=user_id)

        # Reload cached settings so detail page uses updated config
        criteria.reload_settings()

        return jsonify({
            'success': True,
            'character_id': character_id
        })


@app.route('/api/backtest/results', methods=['GET'])
def get_backtest_results():
    """Get all backtest results"""
    try:
        years_back = request.args.get('years_back', type=int)
        results = db.get_backtest_results(years_back=years_back)
        
        return jsonify(clean_nan_values(results))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# FRED Macroeconomic Data Endpoints
# ============================================================

@app.route('/api/fred/series/<series_id>', methods=['GET'])
def get_fred_series(series_id):
    """Get observations for a FRED series."""
    fred_enabled = db.get_setting('feature_fred_enabled', False)
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


@app.route('/api/fred/series/<series_id>/info', methods=['GET'])
def get_fred_series_info(series_id):
    """Get metadata for a FRED series."""
    fred_enabled = db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    fred = get_fred_service()
    if not fred.is_available():
        return jsonify({'error': 'FRED API key not configured'}), 503

    result = fred.get_series_info(series_id)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@app.route('/api/fred/dashboard', methods=['GET'])
def get_fred_dashboard():
    """Get all dashboard indicators with recent history."""
    fred_enabled = db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    fred = get_fred_service()
    if not fred.is_available():
        return jsonify({'error': 'FRED API key not configured'}), 503

    result = fred.get_dashboard_data()

    if 'error' in result:
        return jsonify(result), 500

    return jsonify(result)


@app.route('/api/fred/summary', methods=['GET'])
def get_fred_summary():
    """Get current values of all economic indicators."""
    fred_enabled = db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    fred = get_fred_service()
    if not fred.is_available():
        return jsonify({'error': 'FRED API key not configured'}), 503

    result = fred.get_economic_summary()

    if 'error' in result:
        return jsonify(result), 500

    return jsonify(result)


@app.route('/api/fred/indicators', methods=['GET'])
def get_fred_indicators():
    """Get list of supported FRED indicators."""
    fred_enabled = db.get_setting('feature_fred_enabled', False)
    if not fred_enabled:
        return jsonify({'error': 'FRED features are not enabled'}), 403

    return jsonify({
        'indicators': SUPPORTED_SERIES,
        'categories': CATEGORIES
    })


# ============================================================
# Catch-all Route for SPA Client-Side Routing
# ============================================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """
    Catch-all route to serve the React frontend app.
    If the path exists as a static file, serve it.
    Otherwise, serve index.html and let React Router handle the route.
    """
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


# ============================================================
# Alerts API Endpoints
# ============================================================

@app.route('/api/alerts', methods=['GET'])
@require_user_auth
def get_alerts(user_id):
    """Get all alerts for the current user."""
    try:
        alerts = db.get_alerts(user_id)
        
        # Check for sync since timestamp for real-time price updates
        since = request.args.get('since')
        updates = []
        if since:
            try:
                updates = db.get_recently_updated_stocks(since)
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


@app.route('/api/alerts', methods=['POST'])
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
            
        alert_id = db.create_alert(user_id, symbol, condition_type, condition_params, frequency)
        
        return jsonify({
            'success': True,
            'alert_id': alert_id,
            'message': 'Alert created successfully'
        })
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@require_user_auth
def delete_alert(alert_id, user_id):
    """Delete an alert."""
    try:
        success = db.delete_alert(alert_id, user_id)
        if success:
            return jsonify({'success': True, 'message': 'Alert deleted'})
        else:
            return jsonify({'error': 'Alert not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting alert: {e}")
        return jsonify({'error': str(e)}), 500



@app.route('/api/feedback', methods=['POST'])
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
            user = db.get_user_by_id(user_id)
            email = user['email'] if user else None
        else:
            email = data.get('email')

        feedback_id = db.create_feedback(
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


@app.route('/api/strategy-templates', methods=['GET'])
def get_strategy_templates():
    """Get available strategy templates for wizard and chat."""
    from strategy_templates import FILTER_TEMPLATES
    return jsonify({
        'templates': {
            k: {
                'name': v['name'],
                'description': v['description'],
                'filters': v['filters']
            }
            for k, v in FILTER_TEMPLATES.items()
        }
    })


# ============================================================
# Dashboard & Market Data Endpoints
# ============================================================

SUPPORTED_INDICES = {
    '^GSPC': 'S&P 500',
    '^IXIC': 'Nasdaq Composite',
    '^DJI': 'Dow Jones Industrial Average'
}


@app.route('/api/market/index/<symbols>', methods=['GET'])
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
            hist_data = yf.download(symbol_list, period=period, interval=interval, group_by='ticker', progress=False)
        else:
            # Single symbol - keep behavior consistent
            ticker = yf.Ticker(symbol_list[0])
            hist_data = ticker.history(period=period, interval=interval)

        results = {}
        for symbol in symbol_list:
            if len(symbol_list) > 1:
                hist = hist_data[symbol]
            else:
                hist = hist_data

            if hist.empty:
                results[symbol] = {'error': 'No data available'}
                continue

            # Format data for chart
            data_points = []
            for idx, row in hist.iterrows():
                if pd.isna(row['Close']):
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

        # If only one symbol was requested, return it directly for backward compatibility
        if len(symbol_list) == 1:
            return jsonify(results[symbol_list[0]])
        
        return jsonify(results)

    except Exception as e:
        logger.error(f"Error fetching indices {symbols}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/market/movers', methods=['GET'])
def get_market_movers():
    """Get top gainers and losers from screened stocks.

    Query params:
      - period: 1d, 1w, 1m, ytd (default: 1d)
      - limit: number of stocks per category (default: 5)
    """
    period = request.args.get('period', '1d')
    limit = min(int(request.args.get('limit', 5)), 20)

    try:
        conn = db.get_connection()
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
                    WITH price_change AS (
                        SELECT
                            wp.symbol,
                            s.company_name,
                            sm.price,
                            (sm.price - wp.price) / wp.price * 100 as change_pct
                        FROM weekly_prices wp
                        JOIN stocks s ON wp.symbol = s.symbol
                        JOIN stock_metrics sm ON wp.symbol = sm.symbol
                        WHERE wp.week_ending = (
                            SELECT MAX(week_ending)
                            FROM weekly_prices
                            WHERE week_ending <= CURRENT_DATE - INTERVAL '%s days'
                        )
                        AND sm.price IS NOT NULL
                        AND s.country = 'US'
                    )
                    SELECT * FROM price_change
                    WHERE change_pct IS NOT NULL
                    ORDER BY change_pct DESC
                    LIMIT %s
                """, (days_back, limit))
                gainers = cursor.fetchall()

                cursor.execute("""
                    WITH price_change AS (
                        SELECT
                            wp.symbol,
                            s.company_name,
                            sm.price,
                            (sm.price - wp.price) / wp.price * 100 as change_pct
                        FROM weekly_prices wp
                        JOIN stocks s ON wp.symbol = s.symbol
                        JOIN stock_metrics sm ON wp.symbol = sm.symbol
                        WHERE wp.week_ending = (
                            SELECT MAX(week_ending)
                            FROM weekly_prices
                            WHERE week_ending <= CURRENT_DATE - INTERVAL '%s days'
                        )
                        AND sm.price IS NOT NULL
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
            db.return_connection(conn)

    except Exception as e:
        logger.error(f"Error getting market movers: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/dashboard', methods=['GET'])
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
        conn = db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)

            # 1. Portfolio summaries (batched price retrieval)
            portfolios = db.get_user_portfolios(user_id)
            
            # Gather all symbols across all portfolios for a single batch fetch
            all_portfolio_symbols = set()
            portfolio_holdings_map = {}
            for p in portfolios:
                try:
                    holdings = db.get_portfolio_holdings(p['id'])
                    portfolio_holdings_map[p['id']] = holdings
                    for symbol in holdings.keys():
                        all_portfolio_symbols.add(symbol)
                except Exception:
                    pass
            
            # Perform single batch fetch for all portfolio symbols
            portfolio_prices = {}
            if all_portfolio_symbols:
                from portfolio_service import fetch_current_prices_batch
                portfolio_prices = fetch_current_prices_batch(list(all_portfolio_symbols), db=db)
            
            portfolio_summaries = []
            for p in portfolios:
                try:
                    summary = db.get_portfolio_summary(p['id'], prices_map=portfolio_prices)
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
            watchlist_symbols = db.get_watchlist(user_id)
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

            # 3. Alerts (recent triggered + pending)
            alerts = db.get_alerts(user_id)
            alert_summary = {
                'triggered': [a for a in alerts if a.get('status') == 'triggered'][:5],
                'pending': [a for a in alerts if a.get('status') == 'pending'][:5]
            }

            # 4. Active strategies
            strategies = db.get_user_strategies(user_id)
            strategy_summaries = [
                {
                    'id': s['id'],
                    'name': s['name'],
                    'enabled': s.get('enabled', True),
                    'last_run': s.get('last_run_at'),
                    'last_status': s.get('last_run_status')
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
                news_articles = db.get_news_articles_multi(list(all_symbols), limit=10)

            return jsonify({
                'portfolios': portfolio_summaries,
                'watchlist': watchlist_data,
                'alerts': alert_summary,
                'strategies': strategy_summaries,
                'upcoming_earnings': upcoming_earnings,
                'news': news_articles
            })

        finally:
            db.return_connection(conn)

    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
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
