"""
Production environment commands for bag CLI
"""
import typer
from rich.console import Console
from cli.utils.fly import run_fly_command, get_machines, filter_machines, select_machine_interactive, get_running_jobs_from_prod_db

console = Console()
app = typer.Typer(help="Production environment operations")


@app.command()
def deploy():
    """Deploy to Fly.io"""
    console.print("[bold blue]🚀 Deploying to Fly.io...[/bold blue]")
    run_fly_command(["deploy"])
    console.print("[bold green]✓ Deployment complete![/bold green]")


@app.command()
def machines():
    """List Fly.io machines"""
    run_fly_command(["machines", "list"])


@app.command()
def restart(
    web: bool = typer.Option(False, "--web", help="Restart web machine"),
    worker: bool = typer.Option(False, "--worker", help="Restart worker machine"),
    all: bool = typer.Option(False, "--all", help="Restart all machines"),
):
    """Restart Fly.io machines"""
    machines_list = get_machines()
    
    if not machines_list:
        console.print("[red]No machines found[/red]")
        raise typer.Exit(1)
    
    # Determine which machines to restart
    if all:
        targets = machines_list
    elif worker:
        targets = filter_machines(machines_list, "worker")
    elif web:
        targets = filter_machines(machines_list, "web")
    else:
        # Default: restart web machine
        targets = filter_machines(machines_list, "web")
    
    if not targets:
        console.print("[yellow]No matching machines found[/yellow]")
        raise typer.Exit(1)
    
    # Restart each target
    for machine in targets:
        machine_id = machine["id"]
        name = machine.get("name", "unknown")
        console.print(f"[blue]Restarting {name} ({machine_id[:12]}...)...[/blue]")
        run_fly_command(["machine", "restart", machine_id])
    
    console.print("[bold green]✓ Restart complete![/bold green]")


@app.command()
def logs(
    worker: bool = typer.Option(False, "--worker", "-w", help="Show logs from worker machine only"),
    web: bool = typer.Option(False, "--web", help="Show logs from web machine only"),
    hours: int = typer.Option(None, "--hours", "-h", help="Show logs from last N hours"),
):
    """View Fly.io logs (streams by default, optionally filter by machine type)"""
    # Build base command args
    cmd_args = ["logs"]
    
    # Add machine filter if specified
    if worker or web:
        machines_list = get_machines()
        if not machines_list:
            console.print("[red]No machines found[/red]")
            raise typer.Exit(1)
        
        machine_type = "worker" if worker else "web"
        targets = filter_machines(machines_list, machine_type)
        
        if not targets:
            console.print(f"[yellow]No {machine_type} machines found[/yellow]")
            raise typer.Exit(1)
        
        # If multiple machines of the type, let user select
        if len(targets) > 1:
            # Fetch running jobs for worker selection
            job_info = get_running_jobs_from_prod_db() if worker else None
            machine_id = select_machine_interactive(targets, job_info=job_info)
        else:
            machine_id = targets[0]["id"]
        
        if not machine_id:
            raise typer.Exit(1)
        
        machine_name = next((m.get("name", "unknown") for m in targets if m["id"] == machine_id), "unknown")
        console.print(f"[bold blue]📋 Streaming logs from {machine_name} ({machine_id[:12]}...)...[/bold blue]")
        cmd_args.extend(["--instance", machine_id])
    else:
        console.print("[bold blue]📋 Streaming logs (Ctrl+C to stop)...[/bold blue]")
    
    # Add hours filter if specified
    if hours is not None:
        cmd_args.extend(["--hours", str(hours)])
    
    # Run the logs command
    try:
        run_fly_command(cmd_args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped streaming logs[/yellow]")


@app.command()
def ssh(
    web: bool = typer.Option(False, "--web", help="SSH into web machine"),
    worker: bool = typer.Option(False, "--worker", help="SSH into worker machine"),
):
    """SSH into a Fly.io machine"""
    machines_list = get_machines()
    
    if not machines_list:
        console.print("[red]No machines found[/red]")
        raise typer.Exit(1)
    
    # Filter by type if specified
    if worker:
        targets = filter_machines(machines_list, "worker")
    elif web:
        targets = filter_machines(machines_list, "web")
    else:
        targets = machines_list
    
    if not targets:
        console.print("[yellow]No matching machines found[/yellow]")
        raise typer.Exit(1)
    
    # Select machine
    machine_id = select_machine_interactive(targets)
    if not machine_id:
        raise typer.Exit(1)
    
    console.print(f"[bold blue]🔐 Connecting to machine {machine_id[:12]}...[/bold blue]")
    run_fly_command(["ssh", "console", "-s", machine_id])


@app.command()
def db():
    """Connect to Postgres database"""
    console.print("[bold blue]🗄️  Connecting to database...[/bold blue]")
    run_fly_command(["postgres", "connect", "-a", "lynch-postgres"])


@app.command()
def secrets():
    """Manage secrets (use subcommands: list, set)"""
    # This is just a parent command - users will use `secrets list` or `secrets set`
    console.print("[yellow]Use 'bag prod secrets list' or 'bag prod secrets set'[/yellow]")


# Secrets subcommands
secrets_app = typer.Typer(help="Manage Fly.io secrets")
app.add_typer(secrets_app, name="secrets")


@secrets_app.command("list")
def secrets_list():
    """List all secrets"""
    run_fly_command(["secrets", "list"])


@secrets_app.command("set")
def secrets_set(
    key: str = typer.Argument(..., help="Secret key"),
    value: str = typer.Argument(..., help="Secret value"),
):
    """Set a secret value"""
    console.print(f"[bold blue]Setting secret {key}...[/bold blue]")
    run_fly_command(["secrets", "set", f"{key}={value}"])
    console.print("[bold green]✓ Secret set![/bold green]")
