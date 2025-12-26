"""
bag docs - Commands for managing research documentation
"""
import os
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()

# Gemini brain directory
BRAIN_DIR = Path.home() / ".gemini" / "antigravity" / "brain"

# Patterns to exclude (ephemeral docs)
EXCLUDE_PATTERNS = {"task.md", "implementation_plan.md", "walkthrough.md"}


def is_excluded(filename: str) -> bool:
    """Check if a file should be excluded from sync."""
    return filename in EXCLUDE_PATTERNS


def find_research_docs() -> list[tuple[Path, str]]:
    """Find all research docs in the Gemini brain directory."""
    docs = []
    if not BRAIN_DIR.exists():
        return docs
    
    for md_file in BRAIN_DIR.rglob("*.md"):
        # Skip files in .system_generated directories
        if ".system_generated" in str(md_file):
            continue
        if not is_excluded(md_file.name):
            # Get modification time
            mod_time = md_file.stat().st_mtime
            docs.append((md_file, mod_time))
    
    return sorted(docs, key=lambda x: x[1], reverse=True)


@app.command()
def sync():
    """Sync research documents from Gemini conversations to docs/research/."""
    project_root = Path(__file__).parent.parent.parent
    docs_dir = project_root / "docs" / "research"
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    research_docs = find_research_docs()
    
    if not research_docs:
        console.print("[yellow]No research documents found in Gemini brain.[/yellow]")
        return
    
    synced = 0
    skipped = 0
    
    for src_path, _ in research_docs:
        dest_path = docs_dir / src_path.name
        
        # Check if file is new or updated
        if not dest_path.exists() or src_path.stat().st_mtime > dest_path.stat().st_mtime:
            import shutil
            shutil.copy2(src_path, dest_path)
            console.print(f"  📄 [green]Synced:[/green] {src_path.name}")
            synced += 1
        else:
            skipped += 1
    
    console.print()
    console.print(f"[bold green]✅ Done![/bold green] {synced} synced, {skipped} unchanged")
    console.print(f"   Location: [dim]{docs_dir}[/dim]")


@app.command("list")
def list_docs():
    """List available research documents in Gemini brain."""
    from datetime import datetime
    
    research_docs = find_research_docs()
    
    if not research_docs:
        console.print("[yellow]No research documents found in Gemini brain.[/yellow]")
        return
    
    table = Table(title="📚 Research Documents")
    table.add_column("Date", style="dim")
    table.add_column("Document")
    table.add_column("Size", justify="right")
    
    for src_path, mod_time in research_docs:
        date_str = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d")
        size = src_path.stat().st_size
        size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
        table.add_row(date_str, src_path.name, size_str)
    
    console.print(table)
