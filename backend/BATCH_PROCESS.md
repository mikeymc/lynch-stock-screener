# Nightly Batch Process - Stock Data Refresh

This document describes the nightly batch process that automatically refreshes stock data for all NYSE and NASDAQ stocks in the Lynch Stock Screener database.

## Overview

The batch process is designed to run during off-hours (default: 2:00 AM) to refresh stock data for approximately 5,000+ stocks from NYSE and NASDAQ exchanges. It uses the same data fetching mechanisms as the interactive API but runs automatically on a schedule.

### Key Features

- **Automatic Scheduling**: Runs nightly via systemd timer or cron
- **Comprehensive Logging**: Detailed logs with rotation to track progress and errors
- **Rate Limiting**: Respects API limits (EDGAR: 10 req/sec, yfinance: configurable)
- **Error Resilience**: Continues processing even if individual stocks fail
- **Database Backups**: Optional automatic backups before each run
- **Progress Tracking**: Batch processing with configurable delays
- **Summary Reports**: JSON reports for each run with statistics
- **Resource Limits**: CPU and memory limits to prevent runaway processes

## Quick Start

### 1. Automated Setup (Recommended)

Run the setup script to configure scheduling:

```bash
cd backend
./setup_scheduler.sh
```

This interactive script will:
- Create necessary directories
- Set up systemd timer (recommended) or cron job
- Test the batch process
- Display helpful commands

### 2. Manual Test Run

Before scheduling, test the batch process:

```bash
# Dry run to see what would be processed
python3 batch_refresh.py --dry-run --limit 10

# Test run with first 10 stocks
python3 batch_refresh.py --limit 10 --verbose

# Full run (will take several hours for all ~5000 stocks)
python3 batch_refresh.py --verbose
```

## Configuration

### Configuration File: `batch_config.json`

The batch process is controlled by a JSON configuration file with the following sections:

#### Scheduling
```json
"scheduling": {
  "run_time": "02:00",
  "timezone": "America/New_York",
  "comment": "Run at 2 AM ET when markets are closed"
}
```

#### Processing
```json
"processing": {
  "batch_size": 100,
  "delay_between_batches_seconds": 5,
  "max_workers": 1,
  "force_refresh": true
}
```

- **batch_size**: Number of stocks to process before pausing
- **delay_between_batches_seconds**: Delay between batches to avoid rate limits
- **force_refresh**: Bypass 24-hour cache to ensure fresh data

#### Rate Limiting
```json
"rate_limiting": {
  "edgar_requests_per_second": 9,
  "yfinance_delay_seconds": 0.5
}
```

Conservative limits to respect API rate limits and avoid getting blocked.

#### Logging
```json
"logging": {
  "log_directory": "logs",
  "log_file": "batch_refresh.log",
  "max_log_size_mb": 50,
  "backup_count": 10,
  "log_level": "INFO"
}
```

Logs rotate automatically when they reach `max_log_size_mb`.

#### Database
```json
"database": {
  "path": "stocks.db",
  "backup_before_run": true,
  "backup_directory": "backups"
}
```

#### Error Handling
```json
"error_handling": {
  "max_consecutive_failures": 50,
  "retry_failed_stocks": true,
  "max_retries_per_stock": 2,
  "continue_on_error": true
}
```

#### Reporting
```json
"reporting": {
  "generate_summary": true,
  "summary_directory": "reports",
  "keep_last_n_reports": 30
}
```

## Scheduling Methods

### Method 1: Systemd Timer (Recommended)

**Advantages:**
- Automatic logging to systemd journal
- Better resource management
- Easier monitoring and control
- Runs even if user not logged in

**Setup:**

1. Run the setup script:
   ```bash
   ./setup_scheduler.sh
   ```
   Choose option 1.

2. Or manually install:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp systemd/stock-refresh.service ~/.config/systemd/user/
   cp systemd/stock-refresh.timer ~/.config/systemd/user/

   # Update paths in the service file
   sed -i "s|/home/user|$HOME|g" ~/.config/systemd/user/stock-refresh.service

   systemctl --user daemon-reload
   systemctl --user enable stock-refresh.timer
   systemctl --user start stock-refresh.timer
   ```

**Useful Commands:**
```bash
# View timer status
systemctl --user status stock-refresh.timer

# View next scheduled run
systemctl --user list-timers stock-refresh.timer

# View service logs
journalctl --user -u stock-refresh.service -f

# Run manually now
systemctl --user start stock-refresh.service

# Stop timer
systemctl --user stop stock-refresh.timer

# Disable timer
systemctl --user disable stock-refresh.timer
```

### Method 2: Cron

**Advantages:**
- Simpler setup
- Available on all Unix-like systems
- Familiar to most system administrators

**Setup:**

1. Edit your crontab:
   ```bash
   crontab -e
   ```

2. Add this line (adjust paths as needed):
   ```cron
   0 2 * * * cd /home/user/lynch-stock-screener/backend && /usr/bin/python3 batch_refresh.py --config batch_config.json >> logs/cron.log 2>&1
   ```

**For Testing (runs every 5 minutes):**
```cron
*/5 * * * * cd /home/user/lynch-stock-screener/backend && /usr/bin/python3 batch_refresh.py --config batch_config.json --limit 10 >> logs/cron.log 2>&1
```

**Useful Commands:**
```bash
# View current crontab
crontab -l

# View cron logs
tail -f logs/cron.log

# Remove cron job
crontab -e  # then delete the line
```

## Command-Line Options

```bash
python3 batch_refresh.py [OPTIONS]

Options:
  --config CONFIG_FILE    Path to configuration file (default: batch_config.json)
  --dry-run              Show what would be processed without fetching data
  --limit N              Limit to first N stocks (for testing)
  --verbose              Enable verbose console output
  --help                 Show help message
```

### Examples

```bash
# Dry run to preview
python3 batch_refresh.py --dry-run

# Test with 10 stocks
python3 batch_refresh.py --limit 10 --verbose

# Test with 100 stocks using custom config
python3 batch_refresh.py --config test_config.json --limit 100

# Full production run
python3 batch_refresh.py
```

## Monitoring

### Logs

Logs are stored in the `logs/` directory:

```bash
# View latest log
tail -f logs/batch_refresh.log

# View specific date range
grep "2024-01-15" logs/batch_refresh.log

# Count errors
grep "ERROR" logs/batch_refresh.log | wc -l
```

### Summary Reports

After each run, a summary report is saved to `reports/`:

```bash
# View latest report
cat reports/batch_summary_*.json | tail -1 | jq .

# Example report structure:
{
  "start_time": "2024-01-15T02:00:00",
  "end_time": "2024-01-15T04:30:00",
  "duration_seconds": 9000,
  "total_stocks": 5234,
  "successful": 5180,
  "failed": 54,
  "skipped": 0,
  "success_rate": "98.97%",
  "failed_symbols": ["AAPL", "MSFT", ...],
  "error_types": {
    "HTTPError": 30,
    "Timeout": 15,
    "ValueError": 9
  }
}
```

### Systemd Journal (if using systemd)

```bash
# View all logs
journalctl --user -u stock-refresh.service

# Follow live logs
journalctl --user -u stock-refresh.service -f

# View logs from specific date
journalctl --user -u stock-refresh.service --since "2024-01-15"

# View only errors
journalctl --user -u stock-refresh.service -p err
```

## Performance

### Expected Runtime

For ~5,000 stocks with default settings:
- **Batch size**: 100 stocks
- **Delay between batches**: 5 seconds
- **Per-stock delay**: 0.5 seconds
- **Estimated total time**: 2-4 hours (depending on API response times)

### Resource Usage

- **CPU**: Limited to 50% of one core (configurable in systemd service)
- **Memory**: Limited to 2GB (configurable in systemd service)
- **Disk**: ~100-500MB for database, logs rotate at 50MB
- **Network**: Moderate (mostly API calls to EDGAR and yfinance)

## Troubleshooting

### Common Issues

#### 1. Permission Denied

```bash
# Make scripts executable
chmod +x batch_refresh.py setup_scheduler.sh
```

#### 2. Import Errors

```bash
# Ensure you're in the backend directory
cd backend
python3 batch_refresh.py
```

#### 3. Database Locked

This can happen if the Flask app is running:
- Solution: Run batch process when app is not running, or use `PRAGMA journal_mode=WAL` (Write-Ahead Logging) in SQLite

#### 4. API Rate Limits

If you hit rate limits:
- Increase `yfinance_delay_seconds` in config
- Decrease `batch_size`
- Increase `delay_between_batches_seconds`

#### 5. High Failure Rate

Check logs for common error types:
```bash
grep "ERROR" logs/batch_refresh.log | tail -20
```

Common causes:
- Network connectivity issues
- API service outages
- Invalid stock symbols
- Rate limiting

### Debug Mode

Run with verbose output to see detailed progress:

```bash
python3 batch_refresh.py --verbose --limit 10
```

## Maintenance

### Regular Tasks

#### Weekly
- Check summary reports for high failure rates
- Review error logs for patterns
- Verify disk space for logs and backups

#### Monthly
- Review and clean old backups
- Update stock symbol list if needed
- Check API quota usage

### Cleanup

```bash
# Remove old backups (keep last 7 days)
find backups/ -name "stocks_backup_*.db" -mtime +7 -delete

# Remove old reports (keep last 30)
ls -t reports/batch_summary_*.json | tail -n +31 | xargs rm -f

# Manually clean old logs (automatic rotation should handle this)
find logs/ -name "batch_refresh.log.*" -mtime +90 -delete
```

## Advanced Configuration

### Custom Schedule

To change the run time, edit the appropriate config:

**Systemd:**
Edit `~/.config/systemd/user/stock-refresh.timer`:
```ini
OnCalendar=*-*-* 03:00:00  # Run at 3 AM instead
```

**Cron:**
```cron
0 3 * * * ...  # Run at 3 AM instead
```

### Email Notifications (Future Enhancement)

The configuration supports email notifications, but this requires SMTP setup:

```json
"notifications": {
  "enabled": true,
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "from_address": "your-email@gmail.com",
    "to_addresses": ["admin@example.com"],
    "on_error_only": true
  }
}
```

Note: Email functionality not yet implemented in batch_refresh.py.

### Multiple Schedules

You can run different configurations at different times:

```bash
# Morning update (quick check)
0 8 * * * python3 batch_refresh.py --config morning_config.json --limit 500

# Nightly full refresh
0 2 * * * python3 batch_refresh.py --config batch_config.json
```

## Architecture

### Data Flow

```
1. Fetch stock symbols from GitHub
   ↓
2. Split into batches (default: 100 stocks)
   ↓
3. For each stock:
   - Call fetch_stock_data() from data_fetcher.py
   - Try EDGAR API first (historical fundamentals)
   - Fallback to yfinance (current + fallback data)
   - Save to SQLite database
   ↓
4. Generate summary report
   ↓
5. Rotate logs
```

### Database Tables Updated

- `stocks` - Basic company information
- `stock_metrics` - Current market metrics
- `earnings_history` - Historical earnings and financials
- `sec_filings` - 10-K and 10-Q filing metadata
- `filing_sections` - Extracted sections from filings

### Files and Directories

```
backend/
├── batch_refresh.py          # Main batch script
├── batch_config.json         # Configuration
├── setup_scheduler.sh        # Setup script
├── logs/                     # Log files
│   ├── batch_refresh.log
│   └── batch_refresh.log.1
├── backups/                  # Database backups
│   └── stocks_backup_YYYYMMDD_HHMMSS.db
├── reports/                  # Summary reports
│   └── batch_summary_YYYYMMDD_HHMMSS.json
├── systemd/                  # Systemd configs
│   ├── stock-refresh.service
│   └── stock-refresh.timer
└── cron/                     # Cron example
    └── stock-refresh.cron
```

## Security Considerations

- **API Keys**: If using Schwab API, store credentials securely
- **File Permissions**: Ensure logs and database are not world-readable
- **Resource Limits**: Systemd service limits CPU and memory usage
- **Network**: All API calls use HTTPS
- **No New Privileges**: Systemd service runs with `NoNewPrivileges=true`

## Support

For issues or questions:
1. Check logs in `logs/batch_refresh.log`
2. Review summary reports in `reports/`
3. Test with `--dry-run` and `--limit` flags
4. Check systemd status: `systemctl --user status stock-refresh.timer`

## Future Enhancements

Potential improvements:
- Email notifications on failures
- Slack/Discord webhook integration
- Prometheus metrics export
- Parallel processing (multi-threading)
- Delta updates (only refresh stale data)
- Incremental backups
- Web dashboard for monitoring
- Automatic retry of failed stocks
- Smart scheduling based on market hours
