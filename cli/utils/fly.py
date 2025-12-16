"""
Fly.io utility functions for bag CLI
"""
import json
import subprocess
import typer
from typing import List, Dict, Optional
from rich.console import Console
from rich.prompt import Prompt

console = Console()


def run_fly_command(args: List[str], capture_output: bool = False) -> Optional[str]:
    """Run a fly command with the given arguments."""
    cmd = ["fly"] + args
    
    if capture_output:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Error running fly command:[/red] {result.stderr}")
            raise typer.Exit(1)
        return result.stdout
    else:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise typer.Exit(1)
        return None


def get_machines() -> List[Dict]:
    """Get list of machines from fly machines list -j"""
    try:
        output = run_fly_command(["machines", "list", "-j"], capture_output=True)
        machines = json.loads(output)
        return machines
    except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
        console.print(f"[red]Failed to get machines:[/red] {e}")
        return []


def filter_machines(machines: List[Dict], machine_type: str) -> List[Dict]:
    """Filter machines by type (web/worker)"""
    if machine_type == "web":
        return [m for m in machines if "worker" not in m.get("name", "").lower()]
    elif machine_type == "worker":
        return [m for m in machines if "worker" in m.get("name", "").lower()]
    return machines


def select_machine_interactive(machines: List[Dict]) -> Optional[str]:
    """Interactive machine selection"""
    if not machines:
        console.print("[yellow]No machines found[/yellow]")
        return None
    
    if len(machines) == 1:
        return machines[0]["id"]
    
    console.print("\n[bold]Available machines:[/bold]")
    for idx, machine in enumerate(machines, 1):
        name = machine.get("name", "unknown")
        machine_id = machine["id"]
        state = machine.get("state", "unknown")
        console.print(f"  {idx}. {name} ({machine_id[:12]}...) - {state}")
    
    choice = Prompt.ask(
        "\nSelect machine",
        choices=[str(i) for i in range(1, len(machines) + 1)],
        default="1"
    )
    
    return machines[int(choice) - 1]["id"]
