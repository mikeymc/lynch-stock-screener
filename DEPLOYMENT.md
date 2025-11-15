# Deployment Guide - Fly.io

This guide will walk you through deploying the Lynch Stock Screener to Fly.io.

## Why Fly.io?

- **Free tier**: 3 shared-cpu VMs with 256MB RAM each
- **Persistent volumes**: SQLite database with automatic backups
- **Global network**: Fast performance worldwide
- **Simple deployment**: One command to deploy

## Prerequisites

1. **Fly.io Account**: Sign up at https://fly.io/app/sign-up
2. **Fly CLI**: Install flyctl
   ```bash
   # macOS
   brew install flyctl

   # Linux
   curl -L https://fly.io/install.sh | sh

   # Windows
   iwr https://fly.io/install.ps1 -useb | iex
   ```

3. **Login to Fly.io**:
   ```bash
   fly auth login
   ```

## Initial Setup

### 1. Create the Fly.io App

**IMPORTANT**: Before running the command below, open `fly.toml` and change the app name to something unique (e.g., `lynch-screener-yourname`).

```bash
# Launch the app (this will use your fly.toml configuration)
fly launch --no-deploy

# When prompted:
# - Choose your app name (or use the one in fly.toml)
# - Choose your region (e.g., iad for US East)
# - Do NOT deploy yet (we need to set up secrets first)
```

### 2. Create Persistent Volume

The app needs a persistent volume to store the SQLite database:

```bash
fly volumes create lynch_data --region iad --size 1
```

**Note**: Replace `iad` with your chosen region if different.

### 3. Set Required Secrets

The app requires a Google Gemini API key for AI-powered analysis:

```bash
# Required: Google Gemini API key
fly secrets set GEMINI_API_KEY=your_gemini_api_key_here
```

Get your Gemini API key at: https://aistudio.google.com/app/apikey

### 4. Set Optional Secrets (Charles Schwab API)

If you want to use Schwab's API for historical prices:

```bash
fly secrets set SCHWAB_API_KEY=your_schwab_key
fly secrets set SCHWAB_API_SECRET=your_schwab_secret
fly secrets set SCHWAB_REDIRECT_URI=your_redirect_uri
```

Get Schwab API credentials at: https://developer.schwab.com

## Deployment

### Deploy the Application

```bash
fly deploy
```

This will:
1. Build the Docker image (frontend + backend)
2. Push to Fly.io registry
3. Start your application
4. Health check and confirm deployment

First deployment takes ~3-5 minutes.

### Open Your App

```bash
fly open
```

This opens your deployed app in your browser!

## Monitoring & Management

### View Logs

```bash
# Real-time logs
fly logs

# Specific number of lines
fly logs -n 100
```

### Check Status

```bash
fly status
```

### SSH Into the VM

```bash
fly ssh console
```

### View Database

```bash
# SSH into the VM
fly ssh console

# Check database
ls -lh /data/stocks.db

# Exit
exit
```

## Updating the Application

When you make code changes:

```bash
# Commit your changes (optional but recommended)
git add .
git commit -m "Your changes"

# Deploy updated code
fly deploy
```

Fly.io will:
- Build new Docker image
- Perform rolling deployment (zero downtime)
- Keep your database intact

## Scaling

### Check Current Resources

```bash
fly scale show
```

### Increase Memory (if needed)

If you run into memory issues:

```bash
# Upgrade to 512MB (costs ~$3/month)
fly scale memory 512

# Or 1GB (costs ~$6/month)
fly scale memory 1024
```

### Scale to Multiple Instances

```bash
# Run 2 instances
fly scale count 2
```

**Note**: With SQLite, multiple instances will each have their own database copy (not ideal). Stick to 1 instance unless you migrate to PostgreSQL.

## Cost Estimation

### Free Tier (Likely Sufficient)
- **1x shared-cpu VM** (256MB RAM)
- **1GB persistent volume**
- **Cost**: $0/month

### If You Exceed Free Tier
- **512MB RAM**: ~$3/month
- **1GB RAM**: ~$6/month
- **3GB volume**: ~$0.30/month

**Your use case (personal + few friends)**: Should stay **FREE** or under **$5/month**

## Troubleshooting

### App Won't Start

Check logs:
```bash
fly logs
```

Common issues:
- Missing GEMINI_API_KEY secret
- Database permission issues
- Out of memory (upgrade to 512MB)

### Health Check Failing

The app has a health check at `/api/health`. Verify it works:

```bash
curl https://your-app-name.fly.dev/api/health
```

Should return: `{"status": "healthy"}`

### Database Not Persisting

Verify volume is mounted:
```bash
fly ssh console
ls -la /data
```

Should show `stocks.db` after first use.

### Out of Memory

Upgrade memory:
```bash
fly scale memory 512
```

## Environment Variables

All environment variables are set in `fly.toml` or via secrets:

### Set in fly.toml (non-secret)
- `PORT=8080`
- `FLASK_ENV=production`
- `DATABASE_PATH=/data/stocks.db`

### Set via Secrets (sensitive)
- `GEMINI_API_KEY` (required)
- `SCHWAB_API_KEY` (optional)
- `SCHWAB_API_SECRET` (optional)
- `SCHWAB_REDIRECT_URI` (optional)

View current secrets (values are hidden):
```bash
fly secrets list
```

## Backup & Restore

### Manual Backup

```bash
# Download database
fly ssh sftp get /data/stocks.db ./stocks-backup.db
```

### Restore from Backup

```bash
# Upload database
fly ssh sftp shell
put stocks-backup.db /data/stocks.db
exit
```

## Advanced: Auto-scaling

Enable auto-stop to save costs when idle:

```bash
# Already configured in fly.toml:
# auto_stop_machines = 'stop'
# auto_start_machines = true
# min_machines_running = 0
```

This means:
- App stops after idle period (saves $)
- Restarts automatically on first request
- ~1-2 second cold start delay

## Getting Help

- **Fly.io Docs**: https://fly.io/docs/
- **Community Forum**: https://community.fly.io/
- **Status Page**: https://status.flyio.net/

## Cleanup / Delete App

To completely remove the app:

```bash
# Delete the app (includes volume)
fly apps destroy lynch-stock-screener

# Confirm deletion when prompted
```

---

## Quick Reference

```bash
# Deploy
fly deploy

# View logs
fly logs

# Check status
fly status

# Open app
fly open

# SSH into VM
fly ssh console

# Scale memory
fly scale memory 512

# Set secret
fly secrets set KEY=value

# List secrets
fly secrets list
```

---

**Estimated deployment time**: 10 minutes
**Estimated monthly cost**: $0 (free tier)

Enjoy your cloud-deployed Lynch Stock Screener! 🚀
