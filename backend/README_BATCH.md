# Batch Process Quick Start

## TL;DR - Get Started in 2 Minutes

```bash
# 1. Navigate to backend directory
cd backend

# 2. Run the setup script
./setup_scheduler.sh

# 3. Choose option 1 (systemd) or 2 (cron)
```

That's it! The batch process will now run nightly at 2:00 AM to refresh all stock data.

## What Gets Refreshed?

The nightly batch process refreshes data for ~5,000 NYSE and NASDAQ stocks:

- ✓ Current stock prices
- ✓ P/E ratios and PEG ratios
- ✓ Market capitalization
- ✓ Debt-to-equity ratios
- ✓ Institutional ownership
- ✓ Dividend yields
- ✓ 5-20 years of earnings history
- ✓ Revenue data
- ✓ SEC filings (10-K, 10-Q)

## Quick Commands

### Test Before Scheduling

```bash
# Test with just 5 stocks (takes ~30 seconds)
python3 batch_refresh.py --dry-run --limit 5 --verbose
```

### Manual Run

```bash
# Run for all stocks now (takes 2-4 hours)
python3 batch_refresh.py --verbose
```

### Monitor Progress

**If using systemd:**
```bash
# View live logs
journalctl --user -u stock-refresh.service -f

# Check next run time
systemctl --user list-timers stock-refresh.timer
```

**If using cron:**
```bash
# View logs
tail -f logs/batch_refresh.log
```

### View Results

```bash
# View latest summary report
ls -t reports/batch_summary_*.json | head -1 | xargs cat | jq .

# Count successful vs failed
grep "successful" logs/batch_refresh.log | tail -1
```

## File Structure

```
backend/
├── batch_refresh.py          # Main script
├── batch_config.json         # Configuration
├── setup_scheduler.sh        # Easy setup
├── test_batch_refresh.py     # Test suite (40+ tests)
├── test_config.json          # Test configuration
├── logs/                     # Logs (auto-rotated)
├── backups/                  # Database backups
├── reports/                  # Summary reports
├── BATCH_PROCESS.md         # Full documentation
└── TESTING.md               # Test documentation
```

## Configuration Highlights

Edit `batch_config.json` to customize:

```json
{
  "scheduling": {
    "run_time": "02:00"         // Change run time
  },
  "processing": {
    "batch_size": 100,          // Stocks per batch
    "force_refresh": true       // Bypass cache
  },
  "database": {
    "backup_before_run": true   // Auto backup
  }
}
```

## Running Tests

The batch process includes comprehensive tests (40+ test cases):

```bash
# Run all tests
pytest test_batch_refresh.py -v

# Run with coverage
pytest test_batch_refresh.py --cov=batch_refresh
```

See [TESTING.md](TESTING.md) for complete test documentation.

## Troubleshooting

**Problem: Script fails with import errors**
```bash
# Solution: Install dependencies
pip install -r requirements.txt
```

**Problem: Permission denied**
```bash
# Solution: Make executable
chmod +x batch_refresh.py setup_scheduler.sh
```

**Problem: Timer not running**
```bash
# Check status
systemctl --user status stock-refresh.timer

# Restart if needed
systemctl --user restart stock-refresh.timer
```

## Need More Help?

**Documentation:**
- [BATCH_PROCESS.md](BATCH_PROCESS.md) - Complete documentation including:
  - Advanced configuration
  - Performance tuning
  - Email notifications
  - Multiple schedules
  - Architecture details
- [TESTING.md](TESTING.md) - Test documentation:
  - Running tests
  - Writing new tests
  - Coverage reports
  - CI/CD integration
