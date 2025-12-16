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

### Testing & Shipping
```bash
bag test                     # Run all tests
bag test --file PATH         # Test specific file
bag test --match PATTERN     # Test matching pattern
bag ship                     # Run tests → git push
```

### Background Jobs
```bash
# Setup (one-time) - token is already in .env file
# If needed, update .env with: fly ssh console -a lynch-stock-screener -C "printenv API_AUTH_TOKEN"

# Trigger jobs (API_AUTH_TOKEN loaded automatically from .env)
bag jobs screen              # Trigger stock screening
bag jobs sec-cache           # Trigger SEC cache refresh
bag jobs sec-cache --limit 100 --force  # With options
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

# Trigger background jobs
bag jobs screen
bag jobs sec-cache --limit 100
```

See [walkthrough.md](file:///Users/mikey/.gemini/antigravity/brain/f244e78b-be2b-4650-8efa-14599c3cc4bd/walkthrough.md) for complete documentation.
