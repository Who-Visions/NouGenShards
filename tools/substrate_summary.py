#!/usr/bin/env python
"""
substrate_summary.py — Multi-Database Substrate Diagnostic and Status HUD.
Provides a comprehensive overview of the 9-DB SQLite memory cluster,
measuring file size, record density, category distribution, and average utility.
"""
import os
import sys
import sqlite3
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

# UTF-8 Console protection for Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Resolve the package import path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import nougen_shards.core as core
except ImportError:
    # Fallback to local import if run outside the package tree
    sys.path.insert(0, str(REPO_ROOT))
    import src.nougen_shards.core as core

def get_vault_dir():
    _vault_dir = os.environ.get("NOUGEN_VAULT_DIR")
    if not _vault_dir:
        local_vault = REPO_ROOT / ".vault"
        if local_vault.exists() and local_vault.is_dir():
            _vault_dir = str(local_vault)
        else:
            _vault_dir = str(Path.home() / ".nougen" / "shards")
    return Path(_vault_dir)

def get_db_stats(db_path: Path):
    if not db_path.exists():
        return {"exists": False, "size_bytes": 0, "rows": 0, "avg_utility": 0.0}
    
    size_bytes = db_path.stat().st_size
    rows = 0
    avg_utility = 0.0
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check rows and average utility
        cursor.execute("SELECT COUNT(*), AVG(utility_score) FROM shards")
        row = cursor.fetchone()
        if row:
            rows = row[0] or 0
            avg_utility = row[1] or 0.0
        conn.close()
    except Exception as e:
        # DB might be locked or uninitialized
        pass
        
    return {
        "exists": True,
        "size_bytes": size_bytes,
        "rows": rows,
        "avg_utility": avg_utility
    }

def main():
    console = Console()
    vault_dir = get_vault_dir()
    
    console.print("\n[bold cyan]🏟️ Substrate Diagnostics HUD — NouGenShards[/bold cyan]")
    console.print(f"Active Memory Vault Directory: [yellow]{vault_dir.absolute()}[/yellow]\n")
    
    table = Table(title="9-DB Database Density & Allocation")
    table.add_column("DB Node", style="cyan", no_wrap=True)
    table.add_column("File Size", style="magenta", justify="right")
    table.add_column("Record Count", style="green", justify="right")
    table.add_column("Avg Utility", style="yellow", justify="right")
    table.add_column("Status", style="bold white")
    
    total_size = 0
    total_rows = 0
    weighted_utility_sum = 0.0
    active_nodes = 0
    
    for idx in range(1, 10):
        db_path = vault_dir / f"nougen_shards_{idx}.db"
        stats = get_db_stats(db_path)
        
        if stats["exists"]:
            active_nodes += 1
            total_size += stats["size_bytes"]
            total_rows += stats["rows"]
            weighted_utility_sum += stats["avg_utility"] * stats["rows"]
            
            size_mb = stats["size_bytes"] / (1024 * 1024)
            size_str = f"{size_mb:.2f} MB"
            rows_str = f"{stats['rows']:,}"
            util_str = f"{stats['avg_utility']:.4f}"
            
            # Check 1GB boundary
            if stats["size_bytes"] >= core.MAX_DB_SIZE:
                status = "[red]FULL (>=1GB)[/red]"
            else:
                status = "[green]ONLINE[/green]"
                
            table.add_row(f"Node #{idx}", size_str, rows_str, util_str, status)
        else:
            table.add_row(f"Node #{idx}", "[dim]0.00 MB[/dim]", "[dim]0[/dim]", "[dim]0.0000[/dim]", "[dim]UNINITIALIZED[/dim]")

    # Global summary calculations
    overall_avg_utility = weighted_utility_sum / total_rows if total_rows > 0 else 0.0
    total_size_mb = total_size / (1024 * 1024)
    
    table.add_row("---", "---", "---", "---", "---")
    table.add_row(
        "[bold cyan]TOTAL[/bold cyan]",
        f"[bold cyan]{total_size_mb:.2f} MB[/bold cyan]",
        f"[bold cyan]{total_rows:,}[/bold cyan]",
        f"[bold cyan]{overall_avg_utility:.4f}[/bold cyan]",
        f"[bold white]{active_nodes}/9 Active[/bold white]"
    )
    
    console.print(table)
    
    # 2. Category Density
    category_counts = {}
    for idx in range(1, 10):
        db_path = vault_dir / f"nougen_shards_{idx}.db"
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT event_type, COUNT(*) FROM shards GROUP BY event_type")
            for row in cursor:
                cat = row[0] or "UNKNOWN"
                count = row[1] or 0
                category_counts[cat] = category_counts.get(cat, 0) + count
            conn.close()
        except:
            pass
            
    if category_counts:
        cat_table = Table(title="Cognitive Type Distribution")
        cat_table.add_column("Event Type", style="cyan")
        cat_table.add_column("Count", style="magenta", justify="right")
        cat_table.add_column("Percentage", style="yellow", justify="right")
        
        for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_rows) * 100 if total_rows > 0 else 0.0
            cat_table.add_row(cat, f"{count:,}", f"{pct:.2f}%")
            
        console.print()
        console.print(cat_table)
        
    # Health Panel
    status_text = Text()
    status_text.append("Memory Fabric Status: ", style="bold white")
    if active_nodes > 0:
        status_text.append("HEALTHY (Ready)\n", style="bold green")
        status_text.append(f"The 9-DB partitioned substrate holds {total_rows:,} total memory shards across {total_size_mb:.2f} MB.")
    else:
        status_text.append("EMPTY / UNINITIALIZED\n", style="bold yellow")
        status_text.append("No active database files found. The memory vault is ready for ingestion.")
        
    console.print()
    console.print(Panel(status_text, title="Fabric Verdict", border_style="green" if active_nodes > 0 else "yellow", expand=False))

if __name__ == "__main__":
    main()
