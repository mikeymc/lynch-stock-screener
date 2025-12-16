#!/bin/bash
# Quick test script to run screening with only 10 stocks
# This tests the new data caching implementation
# Starts worker locally and creates a test job

echo "🧪 Starting test screening with 10 stocks..."
echo ""

# Kill any existing worker
pkill -f "uv run python worker.py" 2>/dev/null
pkill -f "python3 worker.py" 2>/dev/null

echo "🚀 Starting worker in foreground (you'll see all logs)..."
echo "   Press Ctrl+C to stop when done"
echo ""
echo "---"
echo ""

# Start worker in background but keep output visible
uv run python worker.py &
WORKER_PID=$!
sleep 3

echo ""
echo "📝 Creating screening job..."

# Insert screening job directly into database
JOB_ID=$(psql -h localhost -U lynch -d lynch_stocks -t -c "
INSERT INTO background_jobs (job_type, params, status, created_at)
VALUES (
  'full_screening',
  '{\"algorithm\": \"weighted\", \"force_refresh\": false, \"limit\": 10}'::jsonb,
  'pending',
  NOW()
)
RETURNING id;
" | tr -d ' ')

echo ""
echo "✅ Job created! (ID: $JOB_ID)"
echo ""
echo "---"
echo "📊 WORKER LOGS (watch for data caching):"
echo "---"
echo ""

# Wait for worker to finish (or user to Ctrl+C)
wait $WORKER_PID
