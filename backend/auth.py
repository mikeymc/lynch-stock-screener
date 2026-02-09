# ABOUTME: Handles Google OAuth authentication and session management
# ABOUTME: Provides decorators for protecting routes and managing user sessions

import os
from functools import wraps
from flask import session, jsonify, request
from google.oauth2 import id_token
from google.auth.transport import requests
from google_auth_oauthlib.flow import Flow

# OAuth configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
OAUTH_REDIRECT_URI = os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:5000/api/auth/google/callback')

# Disable HTTPS requirement for local development
# In production, this should be removed (HTTPS required)
if 'localhost' in OAUTH_REDIRECT_URI or '127.0.0.1' in OAUTH_REDIRECT_URI:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# =============================================================================
# Dev Auth Bypass Configuration
# =============================================================================
# Only allow bypass if ALL conditions are true:
# 1. DEV_AUTH_BYPASS env var is explicitly "true"
# 2. FLASK_ENV is not "production"
# 3. Running on localhost (based on redirect URI)

_is_localhost = 'localhost' in OAUTH_REDIRECT_URI or '127.0.0.1' in OAUTH_REDIRECT_URI
_bypass_enabled = os.getenv('DEV_AUTH_BYPASS', 'false').lower() == 'true'
_not_production = os.getenv('FLASK_ENV', 'development') != 'production'

DEV_AUTH_BYPASS = _bypass_enabled and _not_production and _is_localhost

if DEV_AUTH_BYPASS:
    print("=" * 60)
    print("⚠️  DEV AUTH BYPASS IS ENABLED")
    print("   All routes will use 'dev-user-bypass' as user_id")
    print("   DO NOT USE IN PRODUCTION!")
    print("=" * 60)


def init_oauth_client(redirect_uri=None):
    """Initialize Google OAuth client"""
    # Use provided URI or fallback to env var
    uri = redirect_uri or OAUTH_REDIRECT_URI

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [uri],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=[
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ],
        redirect_uri=uri
    )

    return flow


def require_user_auth(f):
    """
    Decorator to protect routes that require user authentication.
    Checks for user_id in session and injects it as a parameter to the route function.

    If DEV_AUTH_BYPASS is enabled (local dev only), allows unauthenticated access
    with a dev user ID.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            # Normal authenticated user
            kwargs['user_id'] = session['user_id']
            
            # Ensure user_type is in session for admin checks downstream
            if 'user_type' not in session:
                try:
                    from app import deps
                    user = deps.db.get_user_by_id(session['user_id'])
                    if user:
                        session['user_type'] = user.get('user_type', 'regular')
                except Exception as e:
                    print(f"Error fetching user_type for session: {e}")
                    
        elif DEV_AUTH_BYPASS:
            # Dev bypass enabled - use mock user
            kwargs['user_id'] = 'dev-user-bypass'
        else:
            # No auth and no bypass - reject
            return jsonify({'error': 'Unauthorized', 'message': 'Please log in'}), 401

        return f(*args, **kwargs)

    return decorated_function




