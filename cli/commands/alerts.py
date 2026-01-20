#!/usr/bin/env python3
"""
Alerts commands for bag CLI
"""
import os
import sys
import typer
import requests
from rich.console import Console
from datetime import datetime
from pathlib import Path

# Add parent directory to path for backend imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from database import Database

console = Console()
app = typer.Typer()


def get_db_url(prod: bool = False) -> tuple[str, dict]:
    """Get database connection parameters and API URL based on environment."""
    if prod:
        # Production environment
        api_url = os.environ.get('PROD_API_URL', 'https://lynchstocks.com')
        db_url = os.environ.get('DATABASE_URL')
        
        if not db_url:
            console.print("[red]ERROR: DATABASE_URL not set for production[/red]")
            raise typer.Exit(1)
        
        # Parse DATABASE_URL for production
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        db_params = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path.lstrip('/'),
            'user': parsed.username,
            'password': parsed.password
        }
    else:
        # Local development
        api_url = 'http://localhost:5001'
        db_params = {
            'host': os.environ.get('DB_HOST', 'localhost'),
            'port': int(os.environ.get('DB_PORT', 5432)),
            'database': os.environ.get('DB_NAME', 'lynch_stocks'),
            'user': os.environ.get('DB_USER', 'lynch'),
            'password': os.environ.get('DB_PASSWORD', 'lynch_dev_password')
        }
    
    return api_url, db_params


@app.command()
def check(
    prod: bool = typer.Option(False, "--prod", help="Run against production environment"),
    force: bool = typer.Option(False, "--force", help="Force scheduling even if recently scheduled (bypass 10-minute check)")
):
    """
    Manually trigger alert checking by creating a check_alerts background job.
    
    Examples:
        bag alerts check                  # Check alerts in local dev
        bag alerts check --prod           # Check alerts in production
        bag alerts check --force          # Force check, bypass 10-minute cooldown
        bag alerts check --prod --force   # Force check in production
    """
    env_name = "production" if prod else "local"
    console.print(f"\n[bold cyan]🔔 Creating check_alerts job ({env_name})[/bold cyan]")
    
    api_url, db_params = get_db_url(prod)
    
    # If --force is set, clear the last scheduled timestamp
    if force:
        console.print("[yellow]⚡ Force mode: bypassing 10-minute cooldown[/yellow]")
        try:
            db = Database(**db_params)
            db.set_setting('last_alert_check_scheduled', '', 'Cleared for force check')
            console.print("[green]✓ Cleared last schedule timestamp[/green]")
        except Exception as e:
            console.print(f"[red]ERROR clearing timestamp: {e}[/red]")
            raise typer.Exit(1)
    
    # Create the background job via API
    try:
        # Get token (always required, matching cache commands)
        api_token = os.environ.get('API_AUTH_TOKEN')
        if not api_token:
            console.print("[red]ERROR: API_AUTH_TOKEN not set[/red]")
            raise typer.Exit(1)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}"
        }
        
        response = requests.post(
            f"{api_url}/api/jobs",
            json={
                "type": "check_alerts",
                "params": {}
            },
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            job_id = data.get('job_id')
            console.print(f"[green]✓ Created check_alerts job: {job_id}[/green]")
            console.print(f"[dim]  Status: {data.get('status')}[/dim]")
            console.print(f"\n[cyan]Monitor job status:[/cyan]")
            console.print(f"  curl {api_url}/api/jobs/{job_id}")
        else:
            console.print(f"[red]ERROR: Failed to create job[/red]")
            console.print(f"[red]Status: {response.status_code}[/red]")
            console.print(f"[red]Response: {response.text}[/red]")
            raise typer.Exit(1)
            
    except requests.exceptions.RequestException as e:
        console.print(f"[red]ERROR: Failed to connect to API at {api_url}[/red]")
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
