# ABOUTME: API endpoints for strategy run briefings
# ABOUTME: Serves briefings by portfolio and by individual briefing ID

from flask import Blueprint, jsonify, request
from app import deps
from auth import require_user_auth
import logging

logger = logging.getLogger(__name__)

briefings_bp = Blueprint('briefings', __name__)


@briefings_bp.route('/api/portfolios/<int:portfolio_id>/briefings', methods=['GET'])
@require_user_auth
def get_portfolio_briefings(user_id, portfolio_id):
    """Get all briefings for a portfolio."""
    limit = request.args.get('limit', 20, type=int)
    briefings = deps.db.get_briefings_for_portfolio(portfolio_id, limit=limit)

    # Convert datetime objects for JSON serialization
    result = []
    for b in briefings:
        item = dict(b)
        if item.get('generated_at'):
            item['generated_at'] = item['generated_at'].isoformat()
        result.append(item)

    return jsonify(result)


@briefings_bp.route('/api/briefings/<int:briefing_id>', methods=['GET'])
@require_user_auth
def get_briefing(user_id, briefing_id):
    """Get a single briefing by ID."""
    conn = deps.db.get_connection()
    try:
        import psycopg.rows
        cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
        cursor.execute("""
            SELECT id, run_id, strategy_id, portfolio_id, stocks_screened, stocks_scored,
                   theses_generated, trades_executed, portfolio_value, portfolio_return_pct,
                   spy_return_pct, alpha, buys_json, sells_json, holds_json, watchlist_json,
                   executive_summary, generated_at
            FROM strategy_briefings
            WHERE id = %s
        """, (briefing_id,))
        briefing = cursor.fetchone()
    finally:
        deps.db.return_connection(conn)

    if not briefing:
        return jsonify({'error': 'Briefing not found'}), 404

    result = dict(briefing)
    if result.get('generated_at'):
        result['generated_at'] = result['generated_at'].isoformat()

    return jsonify(result)
