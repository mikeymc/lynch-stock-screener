# ABOUTME: Application settings, algorithm config, and user preference endpoints
# ABOUTME: Manages characters, themes, expertise levels, and country selections

from flask import Blueprint, jsonify, request
from app import deps
from auth import require_user_auth
from characters import get_character, list_characters
import logging

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)

# Available AI models for analysis generation
AVAILABLE_AI_MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3-pro-preview"]
DEFAULT_AI_MODEL = "gemini-3-pro-preview"



@settings_bp.route('/api/ai-models', methods=['GET'])
def get_available_models():
    """Return list of available AI models for analysis generation."""
    return jsonify({
        'models': AVAILABLE_AI_MODELS,
        'default': DEFAULT_AI_MODEL
    })


@settings_bp.route('/api/settings', methods=['GET'])
def get_settings():
    """Get all application settings."""
    try:
        settings = deps.db.get_all_settings()
        return jsonify(settings)
    except Exception as e:
        print(f"Error getting settings: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings', methods=['POST'])
def update_settings():
    """Update application settings."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        for key, item in data.items():
            value = item.get('value')
            description = item.get('description')

            # Update setting in DB
            deps.db.set_setting(key, value, description)

        # Reload settings in criteria object
        deps.criteria.reload_settings()

        return jsonify({'success': True})
    except Exception as e:
        print(f"Error updating settings: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/countries', methods=['GET'])
def get_countries():
    """Get list of countries with stock counts for filtering."""
    try:
        conn = deps.db.get_connection()
        cursor = conn.cursor()

        # Get country counts
        cursor.execute("""
            SELECT country, COUNT(*) as count
            FROM stocks
            WHERE country IS NOT NULL
            GROUP BY country
            ORDER BY count DESC
        """)

        rows = cursor.fetchall()
        deps.db.return_connection(conn)

        countries = [{'code': row[0], 'count': row[1]} for row in rows]

        return jsonify({'countries': countries})
    except Exception as e:
        logger.error(f"Error getting countries: {e}")
        return jsonify({'error': str(e)}), 500

def get_characters():
    """Get list of available investment characters."""
    try:
        characters = list_characters()
        return jsonify({
            'characters': [
                {
                    'id': c.id,
                    'name': c.name,
                    'description': c.short_description,
                    'primary_metrics': c.primary_metrics,
                }
                for c in characters
            ]
        })
    except Exception as e:
        logger.error(f"Error getting characters: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings/character', methods=['GET'])
@require_user_auth
def get_active_character(user_id):
    """Get the currently active investment character for the logged-in user."""
    try:
        character_id = deps.db.get_user_character(user_id)

        character = get_character(character_id)
        if not character:
            character = get_character('lynch')
            character_id = 'lynch'

        return jsonify({
            'active_character': character_id,
            'character': {
                'id': character.id,
                'name': character.name,
                'description': character.short_description,
                'primary_metrics': character.primary_metrics,
                'hidden_metrics': character.hidden_metrics,
            }
        })
    except Exception as e:
        logger.error(f"Error getting active character: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings/character', methods=['PUT'])
@require_user_auth
def set_active_character(user_id):
    """Set the active investment character for the logged-in user."""
    try:
        data = request.get_json()
        if not data or 'character_id' not in data:
            return jsonify({'error': 'character_id is required'}), 400

        character_id = data['character_id']

        # Validate character exists
        character = get_character(character_id)
        if not character:
            return jsonify({'error': f'Unknown character: {character_id}'}), 400

        # Save to user's settings
        deps.db.set_user_character(user_id, character_id)
        deps.db.flush()  # Ensure write is committed

        return jsonify({
            'success': True,
            'active_character': character_id,
            'character': {
                'id': character.id,
                'name': character.name,
                'description': character.short_description,
            }
        })
    except Exception as e:
        logger.error(f"Error setting active character: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings/expertise-level', methods=['GET'])
@require_user_auth
def get_expertise_level(user_id):
    """Get the user's expertise level."""
    try:
        expertise_level = deps.db.get_user_expertise_level(user_id)
        return jsonify({
            'expertise_level': expertise_level
        })
    except Exception as e:
        logger.error(f"Error getting expertise level: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings/expertise-level', methods=['PUT'])
@require_user_auth
def set_expertise_level(user_id):
    """Set the user's expertise level."""
    try:
        data = request.get_json()
        if not data or 'expertise_level' not in data:
            return jsonify({'error': 'expertise_level is required'}), 400

        expertise_level = data['expertise_level']

        # Validate expertise level
        valid_levels = ['learning', 'practicing', 'expert']
        if expertise_level not in valid_levels:
            return jsonify({'error': f'Invalid expertise_level. Must be one of: {", ".join(valid_levels)}'}), 400

        # Save to user's settings
        deps.db.set_user_expertise_level(user_id, expertise_level)
        deps.db.flush()  # Ensure write is committed

        return jsonify({
            'success': True,
            'expertise_level': expertise_level
        })
    except Exception as e:
        logger.error(f"Error setting expertise level: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings/theme', methods=['GET'])
@require_user_auth
def get_user_theme_endpoint(user_id):
    """Get the user's active theme."""
    try:
        theme = deps.db.get_user_theme(user_id)
        return jsonify({'theme': theme})
    except Exception as e:
        logger.error(f"Error getting user theme: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings/theme', methods=['PUT'])
@require_user_auth
def set_user_theme_endpoint(user_id):
    """Set the user's active theme."""
    try:
        data = request.get_json()
        if not data or 'theme' not in data:
            return jsonify({'error': 'theme is required'}), 400

        theme = data['theme']

        # Validate theme value
        if theme not in ['light', 'dark', 'system']:
            return jsonify({'error': f'Invalid theme: {theme}. Must be light, dark, or system'}), 400

        deps.db.set_user_theme(user_id, theme)
        deps.db.flush()  # Ensure write is committed

        return jsonify({'success': True, 'theme': theme})
    except Exception as e:
        logger.error(f"Error setting user theme: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/algorithm/config', methods=['GET', 'POST'])
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
