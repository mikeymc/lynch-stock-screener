# bag CLI Tool

🎒 Command-line interface for Lynch Stock Screener development tasks

## Quick Setup

```bash
# Install dependencies
uv pip install -r requirements.txt
uv pip install -e .

# Add alias to your ~/.zshrc (recommended)
echo 'alias bag="/Users/mikey/workspace/lynch-stock-screener/.venv/bin/bag"' >> ~/.zshrc
source ~/.zshrc

# Now you can use: bag --help
```

## Available Commands

### Production Operations
```bash
bag prod deploy              # Deploy to Fly.io
bag prod machines            # List machines
bag prod restart [options]   # Restart machines (--web, --worker, --all)
bag prod logs [options]      # View logs (--tail, --hours N)
bag prod ssh [options]       # SSH into machine (--web, --worker)
bag prod db                  # Connect to Postgres
bag prod secrets list        # List secrets
bag prod secrets set K V     # Set secret
```

### Stock Screening
```bash
# Local development (default)
bag screen start                    # Start local screening
bag screen start --algorithm weighted
bag screen start --limit 100
bag screen stop <session_id>        # Stop local session

# Production
bag screen start --prod             # Trigger prod screening
bag screen start --prod --algorithm weighted
bag screen stop --prod <job_id>     # Cancel prod job
```

### SEC Cache
```bash
# Production only (local not implemented yet)
bag sec-cache start --prod                      # Trigger SEC cache refresh
bag sec-cache start --prod --limit 100 --force  # With options
bag sec-cache stop --prod <job_id>              # Cancel job
```

### Testing & Shipping
```bash
bag test                     # Run all tests
bag test --file PATH         # Test specific file
bag test --match PATTERN     # Test matching pattern
bag ship                     # Run tests → git push
```

## Examples

```bash
# Deploy workflow
bag prod deploy
bag prod restart --all
bag prod logs --hours 2

# Development workflow
bag test --file tests/backend/test_app.py
bag ship

# Local screening
bag screen start --limit 100
bag screen stop 123

# Production screening and cache
bag screen start --prod --algorithm weighted
bag sec-cache start --prod --limit 100
```

See [walkthrough.md](file:///Users/mikey/.gemini/antigravity/brain/f244e78b-be2b-4650-8efa-14599c3cc4bd/walkthrough.md) for complete documentation.
