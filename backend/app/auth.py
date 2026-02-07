# ABOUTME: Authentication routes for OAuth, email/password login, and session management
# ABOUTME: Handles Google OAuth flow, user registration, and onboarding

from flask import Blueprint, jsonify, request, session, redirect
from app import deps
from auth import init_oauth_client, require_user_auth, DEV_AUTH_BYPASS
from werkzeug.security import generate_password_hash, check_password_hash
from email_service import send_verification_email
import os
import secrets
import string
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/google/url', methods=['GET'])
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


@auth_bp.route('/api/auth/google/callback', methods=['GET'])
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
        user_id = deps.db.create_user(google_id, email, name, picture)

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


@auth_bp.route('/api/auth/user', methods=['GET'])
def get_current_user():
    """Get current logged-in user info"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user = deps.db.get_user_by_id(session.get('user_id'))
    if not user:
        session.clear()
        return jsonify({'error': 'User not found'}), 401

    return jsonify({
        'id': user['id'],
        'email': user['email'],
        'name': user['name'],
        'picture': user['picture'],
        'feature_flags': user.get('feature_flags') or {},
        'has_completed_onboarding': user.get('has_completed_onboarding', False)
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user and clear session"""
    session.clear()
    return jsonify({'message': 'Logged out successfully'})


@auth_bp.route('/api/auth/register', methods=['POST'])
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
        existing_user = deps.db.get_user_by_email(email)
        if existing_user:
            return jsonify({'error': 'Email already registered'}), 400

        # Create new user
        password_hash = generate_password_hash(password)
        if not name:
            name = email.split('@')[0]

        # Generate 6-digit numeric verification code
        verification_code = ''.join(secrets.choice(string.digits) for _ in range(6))
        code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        user_id = deps.db.create_user_with_password(email, password_hash, name, verification_code, code_expires_at)

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


@auth_bp.route('/api/auth/login', methods=['POST'])
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
        user = deps.db.get_user_by_email(email)
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
        deps.db.update_last_login(user['id'])

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


@auth_bp.route('/api/auth/verify', methods=['POST'])
def verify_email():
    """Verify user email with OTP code"""
    try:
        data = request.get_json()
        email = data.get('email')
        code = data.get('code')

        if not email or not code:
            return jsonify({'error': 'Email and code are required'}), 400

        success = deps.db.verify_user_otp(email, code)

        if not success:
             return jsonify({'error': 'Invalid, expired, or incorrect code'}), 400

        return jsonify({'message': 'Email verified successfully'})

    except Exception as e:
        logger.error(f"Verification error: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/user/complete_onboarding', methods=['POST'])
def complete_onboarding():
    """Mark the current user's onboarding as complete"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        deps.db.mark_onboarding_complete(session['user_id'])
        return jsonify({'message': 'Onboarding completed'})
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/api/auth/test-login', methods=['POST'])
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
        user_id = deps.db.create_user(test_google_id, test_email, test_name, test_picture)

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

    # If no API token configured, allow access (local dev)
    if not deps.API_AUTH_TOKEN:
        return None

    # Check if request has valid API token
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        if token == deps.API_AUTH_TOKEN:
            return None  # Authorized via API token

    # Neither OAuth nor valid API token provided
    return jsonify({'error': 'Unauthorized', 'message': 'Please log in or provide API token'}), 401
