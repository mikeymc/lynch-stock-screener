# ABOUTME: Backtesting, validation, and optimization endpoints for algorithms
# ABOUTME: Handles backtest runs, validation jobs, and parameter optimization

from flask import Blueprint, jsonify, request
from app import deps
from app.helpers import clean_nan_values
from auth import require_user_auth
from characters import get_character
import uuid
import logging
import threading

logger = logging.getLogger(__name__)

backtesting_bp = Blueprint('backtesting', __name__)


@backtesting_bp.route('/api/backtest', methods=['POST'])
@require_user_auth
def run_backtest(user_id):
    """Run a backtest for a specific stock."""
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        years_back = int(data.get('years_back', 1))

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        # Get user's active character
        character_id = deps.db.get_user_character(user_id)

        # Load the saved configuration for this character
        configs = deps.db.get_algorithm_configs()
        character_config = None
        for config in configs:
            if config.get('character') == character_id:
                character_config = config
                logger.info(f"Using config ID {config.get('id')} for character {character_id}, correlation_5yr: {config.get('correlation_5yr')}")
                break

        if not character_config:
            logger.warning(f"No saved configuration found for character {character_id}, using defaults")

        # Convert config to overrides format (if found)
        overrides = character_config if character_config else None

        result = deps.backtester.run_backtest(symbol.upper(), years_back, overrides=overrides, character_id=character_id)

        if 'error' in result:
            return jsonify(result), 400

        return jsonify(clean_nan_values(result))

    except Exception as e:
        print(f"Error running backtest: {e}")
        return jsonify({'error': str(e)}), 500




# ============================================================
# Algorithm Validation & Optimization Endpoints
# ============================================================

@backtesting_bp.route('/api/validate/run', methods=['POST'])
def start_validation():
    """Start a validation run for S&P 500 stocks"""
    try:
        data = request.get_json()
        years_back = int(data.get('years_back', 1))
        limit = data.get('limit')  # Optional limit for testing
        force = data.get('force', True)  # Default to True to ensure we test new settings
        config = data.get('config')  # Optional config overrides

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Start validation in background thread
        def run_validation_background():
            try:
                deps.validation_jobs[job_id] = {'status': 'running', 'progress': 0, 'total': 0}

                # Progress callback to update validation_jobs
                def on_progress(data):
                    deps.validation_jobs[job_id].update({
                        'progress': data['progress'],
                        'total': data['total'],
                        'current_symbol': data.get('current_symbol')
                    })

                summary = deps.validator.run_sp500_backtests(
                    years_back=years_back,
                    max_workers=5,
                    limit=limit,
                    force_rerun=force,
                    overrides=config,
                    character_id=data.get('character_id', 'lynch'),  # Use character from request or default to lynch
                    progress_callback=on_progress
                )

                # Run correlation analysis
                analysis = deps.analyzer_corr.analyze_results(years_back=years_back)

                deps.validation_jobs[job_id] = {
                    'status': 'complete',
                    'summary': summary,
                    'analysis': analysis
                }
            except Exception as e:
                deps.validation_jobs[job_id] = {
                    'status': 'error',
                    'error': str(e)
                }

        thread = threading.Thread(target=run_validation_background, daemon=True)
        thread.start()

        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'years_back': years_back
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@backtesting_bp.route('/api/validate/progress/<job_id>', methods=['GET'])
def get_validation_progress(job_id):
    """Get progress of a validation job"""
    if job_id not in deps.validation_jobs:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify(clean_nan_values(deps.validation_jobs[job_id]))

@backtesting_bp.route('/api/validate/results/<int:years_back>', methods=['GET'])
def get_validation_results(years_back):
    """Get validation results and analysis"""
    try:
        # Get correlation analysis
        analysis = deps.analyzer_corr.analyze_results(years_back=years_back)

        if 'error' in analysis:
            return jsonify(analysis), 400

        return jsonify(clean_nan_values(analysis))

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@backtesting_bp.route('/api/optimize/run', methods=['POST'])
@require_user_auth
def start_optimization(user_id=None):
    """Start auto-optimization to find best weights"""
    try:
        data = request.get_json()
        years_back = int(data.get('years_back', 1))
        method = data.get('method', 'gradient_descent')
        max_iterations = int(data.get('max_iterations', 50))
        limit = data.get('limit')  # Capture limit for use in background thread
        character_id = data.get('character_id', 'lynch') # Default to Lynch if not specified

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Start optimization in background thread
        def run_optimization_background():
            try:
                deps.optimization_jobs[job_id] = {'status': 'running', 'progress': 0, 'total': max_iterations, 'stage': 'optimizing'}

                # Get baseline correlation from most recent saved config for this character
                latest_config = deps.db.get_user_algorithm_config(user_id, character_id)
                baseline_correlation = None
                if latest_config:
                    # Prefer correlation_10yr over correlation_5yr
                    baseline_correlation = latest_config.get('correlation_10yr') or latest_config.get('correlation_5yr')

                # Create a simple baseline_analysis object with the saved correlation
                baseline_analysis = {
                    'overall_correlation': {
                        'coefficient': baseline_correlation if baseline_correlation else 0.0
                    }
                }

                # Progress callback
                def on_progress(data):
                    deps.optimization_jobs[job_id].update({
                        'progress': data['iteration'],
                        'total': max_iterations,
                        'best_score': data.get('best_correlation', data.get('correlation', 0)),
                        'best_config': data.get('best_config', data['config']),
                        'current_config': data.get('config')
                    })

                # Run optimization
                result = deps.optimizer.optimize(
                    years_back=years_back,
                    character_id=character_id,
                    user_id=user_id,
                    method=method,
                    max_iterations=max_iterations,
                    progress_callback=on_progress
                )

                if 'error' in result:
                    deps.optimization_jobs[job_id] = {
                        'status': 'complete',
                        'result': result,
                        'baseline_analysis': baseline_analysis
                    }
                    return

                # Delete old backtest results to prepare for revalidation with new config
                deps.optimization_jobs[job_id]['stage'] = 'clearing_cache'
                conn = deps.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM backtest_results WHERE years_back = %s', (years_back,))
                conn.commit()
                deps.db.return_connection(conn)

                # Run validation with optimized config
                deps.optimization_jobs[job_id]['stage'] = 'revalidating'
                summary = deps.validator.run_sp500_backtests(
                    years_back=years_back,
                    max_workers=5,
                    limit=limit,  # Use same limit as original validation
                    force_rerun=True,
                    overrides=result['best_config'],
                    character_id=character_id
                )

                # Get optimized analysis
                optimized_analysis = deps.analyzer_corr.analyze_results(years_back=years_back)

                deps.optimization_jobs[job_id] = {
                    'status': 'complete',
                    'result': result,
                    'baseline_analysis': baseline_analysis,
                    'optimized_analysis': optimized_analysis
                }
            except Exception as e:
                deps.optimization_jobs[job_id] = {
                    'status': 'error',
                    'error': str(e)
                }

        thread = threading.Thread(target=run_optimization_background, daemon=True)
        thread.start()

        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'years_back': years_back,
            'method': method
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@backtesting_bp.route('/api/optimize/progress/<job_id>', methods=['GET'])
def get_optimization_progress(job_id):
    """Get progress of an optimization job"""
    try:
        if job_id not in deps.optimization_jobs:
            return jsonify({'error': 'Job not found'}), 404

        job_data = deps.optimization_jobs[job_id]
        if job_data is None:
            return jsonify({'error': 'Job data is None', 'status': 'error'}), 500

        return jsonify(clean_nan_values(job_data))
    except Exception as e:
        logger.error(f"Error getting optimization progress for job {job_id}: {e}")
        return jsonify({'error': str(e), 'status': 'error'}), 500



@backtesting_bp.route('/api/algorithm/config', methods=['GET', 'POST'])
@require_user_auth
def algorithm_config(user_id=None):
    """Get or update algorithm configuration for the user's active character.

    Source of truth: algorithm_configurations table (filtered by character and user)
    """
    if request.method == 'GET':
        # Check for character_id override in query params
        character_id = request.args.get('character_id')

        # If not provided, fallback to user's active character
        if not character_id:
            character_id = deps.db.get_user_character(user_id)

        # Get character object to determine defaults
        character = get_character(character_id)
        if not character:
            # Fallback to Lynch if unknown
            character = get_character('lynch')

        # Key translation map: backend metric name -> frontend key name
        # The frontend uses shortened keys for historical reasons
        METRIC_TO_FRONTEND_KEY = {
            'peg': 'peg',
            'debt_to_equity': 'debt',
            'earnings_consistency': 'consistency',
            'institutional_ownership': 'ownership',
            'roe': 'roe',
            'debt_to_earnings': 'debt_to_earnings',
            'gross_margin': 'gross_margin',
        }

        # Build dynamic defaults from character config
        default_values = {}

        # 1. Map scoring weights and their thresholds
        for sw in character.scoring_weights:
            # Translate metric name to frontend key
            frontend_key = METRIC_TO_FRONTEND_KEY.get(sw.metric, sw.metric)

            # Weight key: weight_{frontend_key}
            default_values[f"weight_{frontend_key}"] = sw.weight

            # Threshold keys: Use frontend key for consistency
            if sw.metric == 'institutional_ownership':
                # Special case: institutional ownership uses inst_own_min/max instead of excellent/good/fair
                if sw.threshold:
                    # Use the 'excellent' value as the ideal (min), 'good' as max
                    # This is a simplification - ideally we'd have separate min/max in the config
                    default_values['inst_own_min'] = 0.20  # Hardcoded for now
                    default_values['inst_own_max'] = 0.60  # Hardcoded for now
                continue

            # Standard threshold keys: {frontend_key}_{level}
            if sw.threshold:
                default_values[f"{frontend_key}_excellent"] = sw.threshold.excellent
                default_values[f"{frontend_key}_good"] = sw.threshold.good

                # Special case: debt uses 'moderate' instead of 'fair'
                if sw.metric == 'debt_to_equity':
                    default_values[f"{frontend_key}_moderate"] = sw.threshold.fair
                else:
                    default_values[f"{frontend_key}_fair"] = sw.threshold.fair

        # 2. Add common defaults (Revenue/Income growth) if not present
        # These are used by frontend for all characters but might not be in scoring weights
        common_defaults = {
            'revenue_growth_excellent': 15.0,
            'revenue_growth_good': 10.0,
            'revenue_growth_fair': 5.0,
            'income_growth_excellent': 15.0,
            'income_growth_good': 10.0,
            'income_growth_fair': 5.0,

            # Also ensure weights that might exist in other characters but not this one
            # are explicitly zeroed out to prevent carrying over values on frontend
            'weight_peg': 0.0,
            'weight_consistency': 0.0,
            'weight_debt': 0.0,
            'weight_ownership': 0.0,
            'weight_roe': 0.0,
            'weight_debt_to_earnings': 0.0,
            'weight_gross_margin': 0.0,
        }

        # Merge common defaults (only if not already set by character)
        for k, v in common_defaults.items():
            if k not in default_values:
                default_values[k] = v

        # Load config for user's character from DB
        latest_config = deps.db.get_user_algorithm_config(user_id, character_id)

        if latest_config:
            # Merge DB config with defaults (DB takes precedence)
            config = default_values.copy()

            # Update with values from DB
            # We iterate over keys we know about + keys in DB
            all_keys = set(config.keys()) | set(latest_config.keys())

            for key in all_keys:
                if key in latest_config:
                   config[key] = latest_config[key]

            # Ensure metadata fields are preserved/added
            config['id'] = latest_config.get('id')
            config['correlation_5yr'] = latest_config.get('correlation_5yr')
            config['correlation_10yr'] = latest_config.get('correlation_10yr')

        else:
            # No configs exist for this character - return pure defaults
            config = default_values

        return jsonify({'current': config})

    elif request.method == 'POST':
        data = request.get_json()
        if 'config' not in data:
            return jsonify({'error': 'No config provided'}), 400

        config = data['config']

        # Check for character_id in body
        character_id = data.get('character_id')
        if not character_id:
             # Fallback to active char if not provided/embedded
             character_id = config.get('character', deps.db.get_user_character(user_id))

        # Ensure character_id is in config for saving
        config['character'] = character_id

        deps.db.save_algorithm_config(config, character=character_id, user_id=user_id)

        # Reload cached settings so detail page uses updated config
        deps.criteria.reload_settings()

        return jsonify({
            'success': True,
            'character_id': character_id
        })


@backtesting_bp.route('/api/backtest/results', methods=['GET'])
def get_backtest_results():
    """Get all backtest results"""
    try:
        years_back = request.args.get('years_back', type=int)
        results = deps.db.get_backtest_results(years_back=years_back)

        return jsonify(clean_nan_values(results))
    except Exception as e:
        return jsonify({'error': str(e)}), 500
