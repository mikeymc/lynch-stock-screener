# ABOUTME: Flask application factory with middleware, session, and service initialization
# ABOUTME: Registers all route blueprints and re-exports app/db for backward compatibility

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import logging
from datetime import timedelta

from app import deps

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

# CRITICAL: Disable EDGAR caching BEFORE any other imports that use edgartools
from sec_rate_limiter import configure_edgartools_rate_limit
configure_edgartools_rate_limit()

# Initialize services and populate deps
from database import Database
from data_fetcher import DataFetcher
from earnings_analyzer import EarningsAnalyzer
from lynch_criteria import LynchCriteria
from yfinance_price_client import YFinancePriceClient
from stock_analyst import StockAnalyst
from backtester import Backtester
from algorithm_validator import AlgorithmValidator
from correlation_analyzer import CorrelationAnalyzer
from algorithm_optimizer import AlgorithmOptimizer
from finnhub_news import FinnhubNewsClient
from stock_vectors import StockVectors
from sec_8k_client import SEC8KClient
from material_event_summarizer import MaterialEventSummarizer

print(f"Connecting to PostgreSQL: {db_user}@{db_host}:{db_port}/{db_name}")
deps.db = Database(
    host=db_host,
    port=db_port,
    database=db_name,
    user=db_user,
    password=db_password
)
deps.fetcher = DataFetcher(deps.db)
deps.analyzer = EarningsAnalyzer(deps.db)
deps.criteria = LynchCriteria(deps.db, deps.analyzer)
# Historical price provider - using TradingView (replaces Schwab)
deps.price_client = YFinancePriceClient()
deps.stock_analyst = StockAnalyst(deps.db)
deps.backtester = Backtester(deps.db)
deps.validator = AlgorithmValidator(deps.db)
deps.analyzer_corr = CorrelationAnalyzer(deps.db)
deps.optimizer = AlgorithmOptimizer(deps.db)
deps.event_summarizer = MaterialEventSummarizer()
deps.stock_vectors = StockVectors(deps.db)

# Initialize Finnhub client for news
finnhub_api_key = os.environ.get('FINNHUB_API_KEY')
if not finnhub_api_key:
    logger.warning("FINNHUB_API_KEY not set - news features will be unavailable")
deps.finnhub_client = FinnhubNewsClient(finnhub_api_key) if finnhub_api_key else None

# Initialize SEC 8-K client for material events
sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener info@lynchstocks.com')
deps.sec_8k_client = SEC8KClient(sec_user_agent)

# API token for external job creation (GitHub Actions, etc.)
deps.API_AUTH_TOKEN = os.environ.get('API_AUTH_TOKEN')

# Track running validation/optimization jobs
deps.validation_jobs = {}
deps.optimization_jobs = {}

# Backward compat: export db at module level for tests that monkeypatch app.db
db = deps.db

# Health check route (stays in __init__)
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

# Register blueprints
from app.auth import auth_bp
from app.jobs import jobs_bp
from app.strategies import strategies_bp
from app.settings import settings_bp
from app.stocks import stocks_bp
from app.analysis import analysis_bp
from app.screening import screening_bp
from app.filings import filings_bp
from app.portfolios import portfolios_bp
from app.agent import agent_bp
from app.backtesting import backtesting_bp
from app.dashboard import dashboard_bp

app.register_blueprint(auth_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(strategies_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(stocks_bp)
app.register_blueprint(analysis_bp)
app.register_blueprint(screening_bp)
app.register_blueprint(filings_bp)
app.register_blueprint(portfolios_bp)
app.register_blueprint(agent_bp)
app.register_blueprint(backtesting_bp)
app.register_blueprint(dashboard_bp)

