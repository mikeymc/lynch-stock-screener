# ABOUTME: Background job API endpoints for creating and monitoring async tasks
# ABOUTME: Supports both OAuth and API token authentication for CLI/CI access

from flask import Blueprint, jsonify, request, session
from app import deps
from auth import DEV_AUTH_BYPASS
from fly_machines import get_fly_manager
import os
import logging

logger = logging.getLogger(__name__)

jobs_bp = Blueprint('jobs', __name__)


def check_for_api_token():
    """
    Check authentication - accepts EITHER OAuth session OR API token.
    Returns error response or None if authorized.

    This allows:
    - Frontend users to use OAuth (session-based)
    - GitHub Actions/CLI to use API token (Bearer header)
    """
    # Check if user is authenticated via OAuth session
    if 'user_id' in session:
        return None  # Authorized via OAuth

    # Check if dev bypass is enabled
    if DEV_AUTH_BYPASS:
        logger.info("[APP] Bypassing API token check (DEV_AUTH_BYPASS=True)")
        return None

    # If no API token configured, allow access (local dev)
    if not deps.API_AUTH_TOKEN:
        return None

    # Check if request has valid API token
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        if token == deps.API_AUTH_TOKEN:
            return None  # Authorized via API token

    # Neither OAuth nor valid API token provided
    return jsonify({'error': 'Unauthorized', 'message': 'Please log in or provide API token'}), 401


@jobs_bp.route('/api/jobs', methods=['POST'])
def create_job():
    """Create a new background job (accepts OAuth session OR API token)"""
    # Check authentication (OAuth OR API token)
    auth_error = check_for_api_token()
    if auth_error:
        return auth_error

    try:
        data = request.get_json()

        if not data or 'type' not in data:
            return jsonify({'error': 'Job type is required'}), 400

        job_type = data['type']
        params = data.get('params', {})
        tier = data.get('tier', 'light')  # Default to light if not specified

        # AUTO-ASSIGN BEEFY TIER for known heavy jobs
        heavy_jobs = {
            'historical_fundamentals_cache',
            'transcript_cache',
            'quarterly_fundamentals_cache',
            'strategy_execution',
            'thesis_refresher',
            'outlook_cache'
        }
        if job_type in heavy_jobs:
            tier = 'beefy'

        # Check connection pool health before creating job
        pool_stats = deps.db.get_pool_stats()
        if pool_stats['usage_percent'] >= 95:
            logger.error(f"Connection pool near exhaustion: {pool_stats}")
            return jsonify({
                'error': 'Database connection pool exhausted',
                'pool_stats': pool_stats
            }), 503

        logger.info(f"Creating background job: type={job_type}, params={params}, tier={tier}")
        job_id = deps.db.create_background_job(job_type, params, tier=tier)
        logger.info(f"Created background job {job_id}")

        # Start worker machine if configured (spawns new worker up to max for parallel jobs)
        fly_manager = get_fly_manager()
        worker_id = fly_manager.start_worker_for_job(tier=tier, max_workers=4)
        logger.info(f"Worker startup triggered: {worker_id}")

        response_data = {
            'job_id': job_id,
            'status': 'pending'
        }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error creating job: type={data.get('type') if data else 'unknown'}, error={e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@jobs_bp.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job(job_id):
    """Get background job status and details"""
    try:
        job = deps.db.get_background_job(job_id)

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        return jsonify(job)

    except Exception as e:
        print(f"Error getting job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@jobs_bp.route('/api/jobs/<int:job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """Cancel a background job (accepts OAuth session OR API token)"""
    # Check authentication (OAuth OR API token)
    auth_error = check_for_api_token()
    if auth_error:
        return auth_error

    try:
        job = deps.db.get_background_job(job_id)

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        deps.db.cancel_job(job_id)

        return jsonify({'status': 'cancelled'})

    except Exception as e:
        print(f"Error cancelling job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500
