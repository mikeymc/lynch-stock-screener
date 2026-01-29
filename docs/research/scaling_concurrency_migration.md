# Research: Scaling Backend Concurrency
**Problem**: The application currently relies on in-memory global dictionaries (`validation_jobs`, `optimization_jobs`, `rescoring_jobs`) to track the state of long-running background tasks.
**Impact**: This forces the API to run as a single-process (`workers=1`), single-threaded (`sync`) Gunicorn server. If we scale to multiple workers, a user's request to "check progress" might hit a worker that doesn't know about the job, resulting in 404 errors.
**Goal**: Migrate all job state to PostgreSQL to allow stateless application workers.

## 1. Targeted Global State
The following global variables in `backend/app.py` must be deprecated:
- `validation_jobs = {}` (Tracks S&P 500 backtests)
- `optimization_jobs = {}` (Tracks genetic/gradient descent optimization)
- `rescoring_jobs = {}` (Tracks mass-rescoring of stocks)
- `active_screenings = {}` (Legacy? Need to verify if `screening_lock` is still needed for DB ops)

## 2. Proposed Database Schema
We should introduce a unified `background_jobs` table to handle all async task tracking.

```sql
CREATE TABLE background_jobs (
    id UUID PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    job_type VARCHAR(50) NOT NULL, -- 'validation', 'optimization', 'rescoring'
    status VARCHAR(20) NOT NULL,   -- 'pending', 'running', 'complete', 'error', 'cancelled'
    progress JSONB DEFAULT '{}',   -- Stores {current, total, stage, etc.}
    result JSONB,                  -- Stores final output or error message
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_jobs_user ON background_jobs(user_id);
CREATE INDEX idx_jobs_status ON background_jobs(status);
```

## 3. Implementation Plan

### Phase 1: Database Migration
- Create the `background_jobs` table.
- Add `Database.create_job(type, user_id) -> job_id`
- Add `Database.update_job(job_id, status, progress=None, result=None)`
- Add `Database.get_job(job_id)`

### Phase 2: Refactor `app.py` Endpoints
**For each feature (Validation, Optimization, Rescoring):**
1.  **Start Endpoint** (`POST /run`):
    -   Instead of `jobs[id] = ...`, call `db.create_job()`.
    -   Pass the `job_id` to the background thread.
2.  **Background Thread**:
    -   Replace shared memory updates with `db.update_job()`.
    -   *Performance Note*: Throttle DB updates (e.g., once per second or every 1-5% progress) to avoid slamming the DB with write traffic during tight loops.
3.  **Progress Endpoint** (`GET /progress/<id>`):
    -   Replace dict lookup with `db.get_job(id)`.

### Phase 3: Infrastructure Update
- Once verified, update `gunicorn.conf.py` to allow multiple workers:
    ```python
    workers = 2  # or 4, depending on CPU cores
    worker_class = "gthread"  # Allow threads per worker for better I/O concurrency
    threads = 4
    ```
- This will significantly improve responsiveness (checking progress won't be blocked by a heavy optimization job).

## 4. Considerations
- **Locking**: The current code uses `active_screenings` in `screening_lock`. If we move to DB, we rely on Postgres's row-level locking or internal consistency. We might need `SELECT FOR UPDATE` if multiple threads try to update the same job (unlikely since one thread owns one job).
- **Cleanup**: In-memory dicts clear on restart. DB tables persist. We will need a cleanup job (cron or startup script) to mark "running" jobs as "failed" if the server restarts unexpectedly.
