# ABOUTME: Watchlist management endpoints for users
# ABOUTME: Handles fetching symbols, adding to watchlist, and removing from watchlist

from flask import Blueprint, jsonify, request
from app import deps
from auth import require_user_auth
import logging

logger = logging.getLogger(__name__)

watchlist_bp = Blueprint('watchlist', __name__)

@watchlist_bp.route('/api/watchlist', methods=['GET'])
@require_user_auth
def get_watchlist(user_id):
    try:
        symbols = deps.db.get_watchlist(user_id)
        return jsonify({'symbols': symbols})
    except Exception as e:
        logger.error(f"Error getting watchlist for user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500


@watchlist_bp.route('/api/watchlist/<symbol>', methods=['POST'])
@require_user_auth
def add_to_watchlist(symbol, user_id):
    try:
        deps.db.add_to_watchlist(user_id, symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error adding {symbol} to watchlist for user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500


@watchlist_bp.route('/api/watchlist/<symbol>', methods=['DELETE'])
@require_user_auth
def remove_from_watchlist(symbol, user_id):
    try:
        deps.db.remove_from_watchlist(user_id, symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error removing {symbol} from watchlist for user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500
