from flask import Blueprint, jsonify, request, session
from app import deps
from auth import require_user_auth
import logging
from datetime import datetime
import psycopg.rows

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)

def require_admin(f):
    """Decorator to require admin user_type"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        user = deps.db.get_user_by_id(session['user_id'])
        if not user or user.get('user_type') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
            
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/api/admin/background_jobs', methods=['GET'])
@require_admin
def get_background_jobs():
    """Get recent background jobs for admin dashboard"""
    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            job_type = request.args.get('job_type')
            
            query = """
                SELECT * FROM background_jobs 
                WHERE 1=1
            """
            params = []
            
            if job_type:
                query += " AND job_type = %s"
                params.append(job_type)
                
            query += " ORDER BY created_at DESC LIMIT 50"
            
            cursor.execute(query, params)
            jobs = [dict(row) for row in cursor.fetchall()]
            return jsonify({'jobs': jobs})
        finally:
            deps.db.return_connection(conn)
    except Exception as e:
        logger.error(f"Error fetching background jobs: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/conversations', methods=['GET'])
@require_admin
def get_conversations():
    """Get all conversations for admin review"""
    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            # Join with users to get user details
            # agent_conversations replaces conversations
            cursor.execute("""
                SELECT c.*, u.email as user_email, u.name as user_name 
                FROM agent_conversations c
                JOIN users u ON c.user_id = u.id
                ORDER BY c.last_message_at DESC
                LIMIT 100
            """)
            conversations = [dict(row) for row in cursor.fetchall()]
            return jsonify({'conversations': conversations})
        finally:
            deps.db.return_connection(conn)
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/conversations/<conversation_id>/messages', methods=['GET'])
@require_admin
def get_conversation_messages(conversation_id):
    """Get messages for a specific conversation (read-only)"""
    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT * FROM agent_messages 
                WHERE conversation_id = %s 
                ORDER BY created_at ASC
            """, (conversation_id,))
            messages = [dict(row) for row in cursor.fetchall()]
            return jsonify({'messages': messages})
        finally:
            deps.db.return_connection(conn)
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/strategies', methods=['GET'])
@require_admin
def get_all_strategies():
    """Get all strategies across all users"""
    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT s.*, u.email as user_email, p.name as portfolio_name
                FROM investment_strategies s
                JOIN users u ON s.user_id = u.id
                LEFT JOIN portfolios p ON s.portfolio_id = p.id
                ORDER BY s.created_at DESC
            """)
            strategies = [dict(row) for row in cursor.fetchall()]
            return jsonify({'strategies': strategies})
        finally:
            deps.db.return_connection(conn)
    except Exception as e:
        logger.error(f"Error fetching strategies: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/portfolios', methods=['GET'])
@require_admin
def get_all_portfolios():
    """Get all portfolios across all users"""
    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT p.*, u.email as user_email 
                FROM portfolios p
                JOIN users u ON p.user_id = u.id
                ORDER BY p.initial_cash DESC
            """)
            portfolios = [dict(row) for row in cursor.fetchall()]
            return jsonify({'portfolios': portfolios})
        finally:
            deps.db.return_connection(conn)
    except Exception as e:
        logger.error(f"Error fetching portfolios: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/user_actions', methods=['GET'])
@require_admin
def get_user_actions():
    """Get recent user actions/events"""
    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT ue.*, u.email as user_email, u.name as user_name 
                FROM user_events ue
                LEFT JOIN users u ON ue.user_id = u.id
                ORDER BY ue.created_at DESC
                LIMIT 100
            """)
            events = [dict(row) for row in cursor.fetchall()]
            return jsonify({'events': events})
        finally:
            deps.db.return_connection(conn)
    except Exception as e:
        logger.error(f"Error fetching user events: {e}")
        return jsonify({'error': str(e)}), 500
