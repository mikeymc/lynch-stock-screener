# ABOUTME: Entry point for running the Flask dev server
# ABOUTME: Usage: uv run python -m app (from backend/)

import os

from app import app

# Start debugpy if ENABLE_DEBUGPY environment variable is set
if os.environ.get('ENABLE_DEBUGPY', 'false').lower() == 'true':
    import debugpy
    debugpy.listen(('0.0.0.0', 15679))
    print("⚠️  Debugpy listening on port 15679 - ready for debugger to attach", flush=True)

try:
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting Flask app on port {port}...", flush=True)
    app.run(debug=False, host='0.0.0.0', port=port)
except Exception as e:
    print(f"CRITICAL ERROR IN MAIN: {e}", flush=True)
    import time
    time.sleep(3600)
