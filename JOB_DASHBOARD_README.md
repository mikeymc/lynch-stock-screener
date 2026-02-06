# Background Jobs Dashboard

A comprehensive real-time monitoring dashboard for your production background jobs.

## Features

### 📊 Real-Time Statistics
- **Total Jobs**: Count of all jobs in the selected timeframe
- **Success Rate**: Percentage of successfully completed jobs
- **Average Duration**: Mean execution time for completed jobs
- **Currently Running**: Number of active jobs

### 📈 Job Performance Summary
View detailed metrics for each job type:
- Total runs
- Success rate
- Average duration
- Last run time
- Current status

### ⏱️ Job Timeline & Overlaps
Visual timeline showing:
- When each job runs
- How long each execution takes
- Which jobs overlap with each other
- Failed vs successful executions (color-coded)

### 📋 Recent Job Executions
Detailed table of the 20 most recent jobs with:
- Job ID
- Job type
- Status
- Created/Started/Completed timestamps
- Duration

## Quick Start

### Prerequisites
- Python 3.x
- Flask and flask-cors (already installed)
- PostgreSQL proxy running on port 15432

### Starting the Dashboard

1. **Ensure your database proxy is running** (port 15432)

2. **Start the dashboard server**:
   ```bash
   python3 job_dashboard_server.py
   ```

3. **Open the dashboard** in your browser:
   ```
   http://localhost:5555
   ```

## Dashboard Controls

### Time Range Filter
Select the time window for job data:
- Last 1 hour
- Last 6 hours
- Last 24 hours (default)
- Last 7 days
- Last 30 days

### Job Type Filter
Filter by specific job type or view all jobs:
- All Jobs (default)
- Individual job types (dynamically populated)

### Auto Refresh
Automatically refresh the dashboard:
- Off
- Every 30 seconds (default)
- Every 1 minute
- Every 5 minutes

### Manual Refresh
Click the "🔄 Refresh Now" button to manually update the data.

## Understanding the Timeline

The timeline visualization shows:

- **Purple bars**: Successfully completed jobs
- **Red bars**: Failed jobs
- **Blue pulsing bars**: Currently running jobs
- **Overlapping regions**: Multiple jobs running simultaneously

Hover over any bar to see detailed information:
- Job ID
- Start time
- End time
- Duration
- Status

## API Endpoints

The dashboard server provides several API endpoints:

### `POST /api/jobs`
Get job data for a specific time range and job type.

**Request body**:
```json
{
  "hours": 24,
  "jobType": "all"
}
```

### `POST /api/overlaps`
Detect overlapping jobs in the specified time range.

**Request body**:
```json
{
  "hours": 24
}
```

### `POST /api/stats`
Get aggregated statistics by job type.

**Request body**:
```json
{
  "hours": 24
}
```

### `GET /api/health`
Health check endpoint to verify database connectivity.

## Database Schema

The dashboard reads from the `background_jobs` table with the following key columns:

- `id`: Job identifier
- `job_type`: Type of background job
- `status`: Current status (pending, running, completed, failed)
- `created_at`: When the job was created
- `started_at`: When the job started executing
- `completed_at`: When the job finished
- `error_message`: Error details for failed jobs

## Monitoring Job Overlaps

The timeline view makes it easy to identify:

1. **Resource contention**: Multiple jobs running simultaneously
2. **Scheduling issues**: Jobs that consistently overlap
3. **Performance bottlenecks**: Long-running jobs blocking others

### Tips for Reducing Overlaps

- Stagger job schedules in your cron configuration
- Reduce parallelism for resource-intensive jobs
- Consider job dependencies and execution order

## Troubleshooting

### Dashboard won't load
- Verify the server is running: `ps aux | grep job_dashboard_server`
- Check the server logs for errors
- Ensure port 5555 is not blocked by firewall

### No data showing
- Verify database proxy is running on port 15432
- Check database credentials in `job_dashboard_server.py`
- Test database connection: `python3 -c "import psycopg2; conn = psycopg2.connect(host='localhost', port=15432, dbname='lynch_stock_screener', user='postgres'); print('Connected!')"`

### Port already in use
If port 5555 is already in use, edit `job_dashboard_server.py` and change the port number in the last line.

## Files

- `job_dashboard.html`: Frontend dashboard interface
- `job_dashboard_server.py`: Flask backend API server
- `JOB_DASHBOARD_README.md`: This documentation

## Performance Considerations

- The dashboard queries the database on each refresh
- For large datasets (>10,000 jobs), consider:
  - Using shorter time ranges
  - Reducing auto-refresh frequency
  - Adding database indexes on `created_at` and `job_type`

## Future Enhancements

Potential improvements:
- Export data to CSV
- Email alerts for job failures
- Job duration trend charts
- Predictive overlap detection
- Custom date range selection
- Job retry functionality
