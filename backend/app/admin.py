from flask import Blueprint, jsonify, request, session
from app import deps
from auth import require_user_auth
import logging
from datetime import datetime, timedelta
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


@admin_bp.route('/api/admin/job_stats', methods=['GET'])
@require_admin
def get_job_stats():
    """Get aggregated background job statistics and timeline data"""
    try:
        hours = int(request.args.get('hours', 24))
        job_type = request.args.get('job_type', 'all')
        
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            time_threshold = datetime.now() - timedelta(hours=hours)
            
            # 1. Get stats by job type
            cursor.execute("""
                SELECT 
                    job_type,
                    tier,
                    COUNT(*) as total_runs,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed_runs,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_runs,
                    COUNT(*) FILTER (WHERE status = 'running') as running_runs,
                    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) FILTER (
                        WHERE status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
                    ) as avg_duration_seconds,
                    MAX(created_at) as last_run
                FROM background_jobs
                WHERE created_at >= %s
                GROUP BY job_type, tier
                ORDER BY total_runs DESC
            """, (time_threshold,))
            stats = [dict(row) for row in cursor.fetchall()]
            
            # 2. Get recent jobs (all jobs in timeframe, but limited to last 1000 for safety)
            query = """
                SELECT * FROM background_jobs
                WHERE created_at >= %s
            """
            params = [time_threshold]
            
            if job_type != 'all':
                query += " AND job_type = %s"
                params.append(job_type)
                
            query += " ORDER BY created_at DESC LIMIT 1000"
            
            cursor.execute(query, params)
            jobs = [dict(row) for row in cursor.fetchall()]
            
            return jsonify({
                'stats': stats,
                'jobs': jobs,
                'time_range': hours
            })
        finally:
            deps.db.return_connection(conn)
    except Exception as e:
        logger.error(f"Error fetching job stats: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/user_actions', methods=['GET'])
@require_admin
def get_user_actions():
    """Get recent user actions/events and user stats"""
    try:
        conn = deps.db.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            
            # 1. Get recent events (existing logic)
            cursor.execute("""
                SELECT ue.*, u.email as user_email, u.name as user_name 
                FROM user_events ue
                LEFT JOIN users u ON ue.user_id = u.id
                ORDER BY ue.created_at DESC
                LIMIT 100
            """)
            events = [dict(row) for row in cursor.fetchall()]
            
            # 2. Get aggregate user stats
            cursor.execute("""
                SELECT 
                    u.id as user_id,
                    u.email,
                    u.name,
                    COUNT(ue.id) as total_hits,
                    MAX(ue.created_at) as last_activity
                FROM users u
                LEFT JOIN user_events ue ON u.id = ue.user_id
                GROUP BY u.id, u.email, u.name
                ORDER BY total_hits DESC
            """)
            stats = [dict(row) for row in cursor.fetchall()]
            
            return jsonify({
                'events': events,
                'stats': stats
            })
        finally:
            deps.db.return_connection(conn)
    except Exception as e:
        logger.error(f"Error fetching user events: {e}")
        return jsonify({'error': str(e)}), 500
