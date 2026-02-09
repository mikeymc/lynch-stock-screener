# ABOUTME: Portfolio and watchlist management endpoints for paper trading
# ABOUTME: Handles portfolio CRUD, trade execution, and value history tracking

from flask import Blueprint, jsonify, request, session
from app import deps
from auth import require_user_auth
import logging

logger = logging.getLogger(__name__)

portfolios_bp = Blueprint('portfolios', __name__)


@portfolios_bp.route('/api/watchlist', methods=['GET'])
@require_user_auth
def get_watchlist(user_id):
    try:
        symbols = deps.db.get_watchlist(user_id)
        return jsonify({'symbols': symbols})
    except Exception as e:
        print(f"Error getting watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/watchlist/<symbol>', methods=['POST'])
@require_user_auth
def add_to_watchlist(symbol, user_id):
    try:
        deps.db.add_to_watchlist(user_id, symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error adding {symbol} to watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/watchlist/<symbol>', methods=['DELETE'])
@require_user_auth
def remove_from_watchlist(symbol, user_id):
    try:
        deps.db.remove_from_watchlist(user_id, symbol.upper())
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error removing {symbol} from watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/portfolios', methods=['GET'])
@require_user_auth
def list_portfolios(user_id):
    """List all portfolios for the authenticated user with computed values."""
    try:
        portfolios = deps.db.get_user_portfolios(user_id)

        # Gather all symbols across all portfolios for a single batch fetch
        all_symbols = set()
        for p in portfolios:
            try:
                holdings = deps.db.get_portfolio_holdings(p['id'])
                for symbol in holdings.keys():
                    all_symbols.add(symbol)
            except Exception:
                pass

        # Batch fetch prices from stock_metrics (cached prices, very fast)
        prices_map = {}
        if all_symbols:
            prices_map = deps.db.get_prices_batch(list(all_symbols))

        # Enrich each portfolio with computed summary data
        enriched_portfolios = []
        for i, portfolio in enumerate(portfolios):
            summary = deps.db.get_portfolio_summary(portfolio['id'], use_live_prices=True, prices_map=prices_map)

            if summary:
                enriched_portfolios.append(summary)
            else:
                # Fallback to basic portfolio data if summary fails
                enriched_portfolios.append(portfolio)

        return jsonify({'portfolios': enriched_portfolios})
    except Exception as e:
        logger.error(f"Error listing portfolios: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/portfolios', methods=['POST'])
@require_user_auth
def create_portfolio(user_id):
    """Create a new portfolio."""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Name is required'}), 400

        name = data['name']
        initial_cash = data.get('initial_cash', 100000.0)

        portfolio_id = deps.db.create_portfolio(user_id, name, initial_cash)
        portfolio = deps.db.get_portfolio(portfolio_id)

        return jsonify(portfolio), 201
    except Exception as e:
        logger.error(f"Error creating portfolio: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/portfolios/<int:portfolio_id>', methods=['GET'])
@require_user_auth
def get_portfolio(portfolio_id, user_id):
    """Get portfolio details with computed values."""
    try:
        portfolio = deps.db.get_portfolio(portfolio_id)
        is_admin = session.get('user_type') == 'admin'
        if not portfolio or (portfolio['user_id'] != user_id and not is_admin):
            return jsonify({'error': 'Portfolio not found'}), 404

        # Pre-fetch prices for all holdings from cached prices
        holdings = deps.db.get_portfolio_holdings(portfolio_id)
        prices_map = {}
        if holdings:
            prices_map = deps.db.get_prices_batch(list(holdings.keys()))

        summary = deps.db.get_portfolio_summary(portfolio_id, use_live_prices=True, prices_map=prices_map)
        return jsonify(summary)
    except Exception as e:
        logger.error(f"Error getting portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/portfolios/<int:portfolio_id>', methods=['PUT'])
@require_user_auth
def update_portfolio(portfolio_id, user_id):
    """Update portfolio (currently only name)."""
    try:
        portfolio = deps.db.get_portfolio(portfolio_id)
        is_admin = session.get('user_type') == 'admin'
        if not portfolio or (portfolio['user_id'] != user_id and not is_admin):
            return jsonify({'error': 'Portfolio not found'}), 404

        data = request.get_json()
        if data and 'name' in data:
            deps.db.rename_portfolio(portfolio_id, data['name'])

        updated = deps.db.get_portfolio(portfolio_id)
        return jsonify(updated)
    except Exception as e:
        logger.error(f"Error updating portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/portfolios/<int:portfolio_id>', methods=['DELETE'])
@require_user_auth
def delete_portfolio(portfolio_id, user_id):
    """Delete a portfolio and all its transactions."""
    try:
        portfolio = deps.db.get_portfolio(portfolio_id)
        if not portfolio:
            return jsonify({'error': 'Portfolio not found'}), 404

        is_admin = session.get('user_type') == 'admin'
        if portfolio['user_id'] != user_id and not is_admin:
            return jsonify({'error': 'Unauthorized'}), 403

        deleted = deps.db.delete_portfolio(portfolio_id, portfolio['user_id'])
        if not deleted:
            return jsonify({'error': 'Delete failed'}), 500

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/portfolios/<int:portfolio_id>/transactions', methods=['GET'])
@require_user_auth
def get_portfolio_transactions(portfolio_id, user_id):
    """Get transaction history for a portfolio."""
    try:
        portfolio = deps.db.get_portfolio(portfolio_id)
        is_admin = session.get('user_type') == 'admin'
        if not portfolio or (portfolio['user_id'] != user_id and not is_admin):
            return jsonify({'error': 'Portfolio not found'}), 404

        transactions = deps.db.get_portfolio_transactions(portfolio_id)
        return jsonify({'transactions': transactions})
    except Exception as e:
        logger.error(f"Error getting transactions for portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500


@portfolios_bp.route('/api/portfolios/<int:portfolio_id>/trade', methods=['POST'])
@require_user_auth
def execute_portfolio_trade(portfolio_id, user_id):
    """Execute a buy or sell trade."""
    try:
        portfolio = deps.db.get_portfolio(portfolio_id)
        is_admin = session.get('user_type') == 'admin'
        if not portfolio or (portfolio['user_id'] != user_id and not is_admin):
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
            db=deps.db,
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


@portfolios_bp.route('/api/portfolios/<int:portfolio_id>/value-history', methods=['GET'])
@require_user_auth
def get_portfolio_value_history(portfolio_id, user_id):
    """Get portfolio value history for charts."""
    try:
        portfolio = deps.db.get_portfolio(portfolio_id)
        is_admin = session.get('user_type') == 'admin'
        if not portfolio or (portfolio['user_id'] != user_id and not is_admin):
            return jsonify({'error': 'Portfolio not found'}), 404

        snapshots = deps.db.get_portfolio_snapshots(portfolio_id)
        return jsonify({'snapshots': snapshots})
    except Exception as e:
        logger.error(f"Error getting value history for portfolio {portfolio_id}: {e}")
        return jsonify({'error': str(e)}), 500
