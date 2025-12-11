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


def init_oauth_client():
    """Initialize Google OAuth client"""
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [OAUTH_REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=[
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ],
        redirect_uri=OAUTH_REDIRECT_URI
    )

    return flow


def require_user_auth(f):
    """
    Decorator to protect routes that require user authentication.
    Checks for user_id in session and injects it as a parameter to the route function.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized', 'message': 'Please log in'}), 401

        # Inject user_id into kwargs
        kwargs['user_id'] = session['user_id']
        return f(*args, **kwargs)

    return decorated_function
