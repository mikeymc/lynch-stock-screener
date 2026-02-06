#!/usr/bin/env python3
"""
Background Jobs Dashboard Server
Provides API endpoints for the job monitoring dashboard
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 15432,
    'database': 'lynch_stock_screener',
    'user': 'postgres'
}

def get_db_connection():
    """Create a database connection"""
    return psycopg2.connect(**DB_CONFIG)

@app.route('/')
def index():
    """Serve the dashboard HTML"""
    return send_file('job_dashboard.html')

@app.route('/api/jobs', methods=['POST'])
def get_jobs():
    """Get job data for the specified time range and job type"""
    try:
        data = request.get_json()
        hours = data.get('hours', 24)
        job_type = data.get('jobType', 'all')
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Calculate time threshold
        time_threshold = datetime.now() - timedelta(hours=hours)
        
        # Build query
        if job_type == 'all':
            query = """
                SELECT 
                    id,
                    job_type,
                    status,
                    claimed_by,
                    claimed_at,
                    claim_expires_at,
                    params,
                    progress_pct,
                    progress_message,
                    processed_count,
                    total_count,
                    result,
                    error_message,
                    created_at,
                    started_at,
                    completed_at
                FROM background_jobs
                WHERE created_at >= %s
                ORDER BY created_at DESC
            """
            cur.execute(query, (time_threshold,))
        else:
            query = """
                SELECT 
                    id,
                    job_type,
                    status,
                    claimed_by,
                    claimed_at,
                    claim_expires_at,
                    params,
                    progress_pct,
                    progress_message,
                    processed_count,
                    total_count,
                    result,
                    error_message,
                    created_at,
                    started_at,
                    completed_at
                FROM background_jobs
                WHERE created_at >= %s AND job_type = %s
                ORDER BY created_at DESC
            """
            cur.execute(query, (time_threshold, job_type))
        
        jobs = cur.fetchall()
        
        # Convert datetime objects to ISO format strings
        for job in jobs:
            for key in ['claimed_at', 'claim_expires_at', 'created_at', 'started_at', 'completed_at']:
                if job[key]:
                    job[key] = job[key].isoformat()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'jobs': jobs,
            'count': len(jobs),
            'timeRange': hours
        })
        
    except Exception as e:
        print(f"Error fetching jobs: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/overlaps', methods=['POST'])
def get_overlaps():
    """Detect overlapping jobs"""
    try:
        data = request.get_json()
        hours = data.get('hours', 24)
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        time_threshold = datetime.now() - timedelta(hours=hours)
        
        # Find overlapping jobs
        query = """
            WITH job_times AS (
                SELECT 
                    id,
                    job_type,
                    started_at,
                    COALESCE(completed_at, NOW()) as ended_at
                FROM background_jobs
                WHERE created_at >= %s 
                  AND started_at IS NOT NULL
            )
            SELECT 
                j1.id as job1_id,
                j1.job_type as job1_type,
                j1.started_at as job1_start,
                j1.ended_at as job1_end,
                j2.id as job2_id,
                j2.job_type as job2_type,
                j2.started_at as job2_start,
                j2.ended_at as job2_end
            FROM job_times j1
            JOIN job_times j2 ON j1.id < j2.id
            WHERE j1.started_at < j2.ended_at 
              AND j2.started_at < j1.ended_at
            ORDER BY j1.started_at DESC
        """
        
        cur.execute(query, (time_threshold,))
        overlaps = cur.fetchall()
        
        # Convert datetime objects to ISO format strings
        for overlap in overlaps:
            for key in ['job1_start', 'job1_end', 'job2_start', 'job2_end']:
                if overlap[key]:
                    overlap[key] = overlap[key].isoformat()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'overlaps': overlaps,
            'count': len(overlaps)
        })
        
    except Exception as e:
        print(f"Error fetching overlaps: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['POST'])
def get_stats():
    """Get aggregated statistics"""
    try:
        data = request.get_json()
        hours = data.get('hours', 24)
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        time_threshold = datetime.now() - timedelta(hours=hours)
        
        # Get statistics by job type
        query = """
            SELECT 
                job_type,
                COUNT(*) as total_runs,
                COUNT(*) FILTER (WHERE status = 'completed') as completed_runs,
                COUNT(*) FILTER (WHERE status = 'failed') as failed_runs,
                COUNT(*) FILTER (WHERE status = 'running') as running_runs,
                AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) FILTER (
                    WHERE status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
                ) as avg_duration_seconds,
                MIN(EXTRACT(EPOCH FROM (completed_at - started_at))) FILTER (
                    WHERE status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
                ) as min_duration_seconds,
                MAX(EXTRACT(EPOCH FROM (completed_at - started_at))) FILTER (
                    WHERE status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
                ) as max_duration_seconds,
                MAX(created_at) as last_run
            FROM background_jobs
            WHERE created_at >= %s
            GROUP BY job_type
            ORDER BY total_runs DESC
        """
        
        cur.execute(query, (time_threshold,))
        stats = cur.fetchall()
        
        # Convert datetime objects to ISO format strings
        for stat in stats:
            if stat['last_run']:
                stat['last_run'] = stat['last_run'].isoformat()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'stats': stats,
            'count': len(stats)
        })
        
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Starting Background Jobs Dashboard Server...")
    print("📊 Dashboard available at: http://localhost:5555")
    print("🔌 Database connection: localhost:15432/lynch_stock_screener")
    print("\nPress Ctrl+C to stop the server\n")
    
    app.run(host='0.0.0.0', port=5555, debug=True)
