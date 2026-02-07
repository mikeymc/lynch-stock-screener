# ABOUTME: Investment strategy CRUD and execution endpoints
# ABOUTME: Handles strategy creation, manual runs, previews, and template listing

from flask import Blueprint, jsonify, request
from app import deps
from auth import require_user_auth
import logging

logger = logging.getLogger(__name__)

strategies_bp = Blueprint('strategies', __name__)


@strategies_bp.route('/api/strategies', methods=['POST'])
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
            portfolio_id = deps.db.create_portfolio(user_id, name, initial_cash=100000.0)

        strategy_id = deps.db.create_strategy(
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


@strategies_bp.route('/api/strategies/<int:strategy_id>', methods=['PUT'])
@require_user_auth
def update_strategy(user_id, strategy_id):
    """Update an existing investment strategy."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Verify ownership
        strategy = deps.db.get_strategy(strategy_id)
        if not strategy:
            return jsonify({'error': 'Strategy not found'}), 404
        if strategy['user_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        success = deps.db.update_strategy(
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


@strategies_bp.route('/api/strategies', methods=['GET'])
@require_user_auth
def get_strategies(user_id):
    """Get all investment strategies for the current user."""
    try:
        strategies = deps.db.get_user_strategies(user_id)
        return jsonify(strategies)
    except Exception as e:
        logger.error(f"Error getting strategies: {e}")
        return jsonify({'error': str(e)}), 500


@strategies_bp.route('/api/strategies/<int:strategy_id>', methods=['GET'])
@require_user_auth
def get_strategy_detail(user_id, strategy_id):
    """Get detailed strategy info including performance and recent runs."""
    try:
        strategy = deps.db.get_strategy(strategy_id)
        if not strategy:
            return jsonify({'error': 'Strategy not found'}), 404

        if strategy['user_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Get performance series
        performance = deps.db.get_strategy_performance(strategy_id)

        # Get recent runs
        runs = deps.db.get_strategy_runs(strategy_id, limit=20)

        return jsonify({
            'strategy': strategy,
            'performance': performance,
            'runs': runs
        })
    except Exception as e:
        logger.error(f"Error getting strategy detail: {e}")
        return jsonify({'error': str(e)}), 500


@strategies_bp.route('/api/strategies/<int:strategy_id>/run', methods=['POST'])
@require_user_auth
def manual_run_strategy(user_id, strategy_id):
    """Manually trigger a strategy execution via background job."""
    try:
        # Verify ownership
        strategy = deps.db.get_strategy(strategy_id)
        if not strategy:
            return jsonify({'error': 'Strategy not found'}), 404

        if strategy['user_id'] != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Create background job for strategy execution (beefy tier)
        job_id = deps.db.create_background_job(
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


@strategies_bp.route('/api/strategies/preview', methods=['POST'])
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
        evaluator = ConditionEvaluator(deps.db)
        analyzer = EarningsAnalyzer(deps.db)
        lynch_criteria = LynchCriteria(deps.db, analyzer)

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
            vectors = StockVectors(deps.db)
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


@strategies_bp.route('/api/strategies/runs/<int:run_id>/decisions', methods=['GET'])
@require_user_auth
def get_run_decisions(user_id, run_id):
    """Get decisions for a specific strategy run."""
    try:
        # Verify ownership via strategy -> run -> decision chain
        # Use a join or two-step lookup. For now, simple lookup.
        run = deps.db.get_strategy_run(run_id)
        if not run:
            return jsonify({'error': 'Run not found'}), 404

        strategy = deps.db.get_strategy(run['strategy_id'])
        if not strategy or strategy['user_id'] != user_id:
             return jsonify({'error': 'Unauthorized'}), 403

        decisions = deps.db.get_run_decisions(run_id)
        return jsonify(decisions)
    except Exception as e:
        logger.error(f"Error getting run decisions: {e}")
        return jsonify({'error': str(e)}), 500


@strategies_bp.route('/api/strategy-templates', methods=['GET'])
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
