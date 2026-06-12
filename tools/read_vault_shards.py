"""
NouGenShards: Main Vault Inspector & Transcripter.
Reads all 33,130 shards from the main vault database, processes them,
writes a full text log to transcript.log, and prints progress via tqdm/rich.
"""
import os
import sqlite3
import sys
from pathlib import Path
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

# UTF-8 Console protection for Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except (AttributeError, ValueError):
        pass

import argparse

_watchtower_root = os.environ.get("WATCHTOWER_ROOT") or str(Path.home() / "Watchtower")
DEFAULT_DEV_DB = Path(_watchtower_root) / "vault" / "nougenai_memory_vault.db"
LOG_PATH = Path("transcript.log")

def get_user_vault_dir():
    _vault_dir = os.environ.get("NOUGEN_VAULT_DIR")
    if not _vault_dir:
        local_vault = Path(".vault")
        if local_vault.exists() and local_vault.is_dir():
            _vault_dir = str(local_vault)
        else:
            _vault_dir = str(Path.home() / ".nougen" / "shards")
    return Path(_vault_dir)

def get_cluster_db_path(vault_dir: Path, index: int) -> Path:
    local_name = f"shards_{index}.db" if index > 1 else "shards.db"
    local_path = Path(local_name)
    if local_path.exists():
        return local_path
    return vault_dir / f"nougen_shards_{index}.db"

def format_row(row_dict: dict) -> str:
    if "content" in row_dict:
        # 9-db cluster schema
        return (
            f"=== SHARD ID: {row_dict.get('id')} ===\n"
            f"Title: {row_dict.get('title')}\n"
            f"Event Type: {row_dict.get('event_type')}\n"
            f"Timestamp: {row_dict.get('timestamp')}\n"
            f"Utility Score: {row_dict.get('utility_score')}\n"
            f"Access Count: {row_dict.get('access_count')}\n"
            f"Tags: {row_dict.get('tags')}\n"
            f"File Hash: {row_dict.get('file_hash')}\n"
            f"Content: {row_dict.get('content')}\n"
            f"{'-'*80}\n"
        )
    else:
        # Personal vault schema
        return (
            f"=== SHARD ID: {row_dict.get('id')} ===\n"
            f"Category: {row_dict.get('category')}\n"
            f"Source: {row_dict.get('source')}\n"
            f"Timestamp: {row_dict.get('timestamp')}\n"
            f"Utility Score: {row_dict.get('utility_score')}\n"
            f"Access Count: {row_dict.get('access_count')}\n"
            f"Tags: {row_dict.get('tags')}\n"
            f"Finding: {row_dict.get('finding')}\n"
            f"Logic: {row_dict.get('logic')}\n"
            f"{'-'*80}\n"
        )

def main():
    parser = argparse.ArgumentParser(description="NouGenShards Vault Inspector & Transcripter.")
    parser.add_argument("--cluster", action="store_true", help="Force transcribing from the 9-DB cluster.")
    parser.add_argument("--db", type=Path, default=None, help="Direct path to a single SQLite database.")
    parser.add_argument("--vault-dir", type=Path, default=None, help="Override user vault directory.")
    args = parser.parse_args()

    console = Console()
    console.print("\n[bold cyan]🪩 NouGenShards Vault Inspector[/bold cyan]")

    # Auto-detection of cluster vs single database mode
    use_cluster = args.cluster
    vault_dir = args.vault_dir or get_user_vault_dir()
    db_path = args.db

    if not use_cluster and not db_path:
        # If the developer DB does not exist, or if we have DB files in the vault dir, auto-default to cluster mode
        has_vault_dbs = any(get_cluster_db_path(vault_dir, i).exists() for i in range(1, 10))
        if not DEFAULT_DEV_DB.exists() or has_vault_dbs:
            use_cluster = True
        else:
            db_path = DEFAULT_DEV_DB

    shards_list = []

    if use_cluster:
        console.print(f"Cluster Mode Active. Scanning vault directory: [yellow]{vault_dir}[/yellow]")
        for i in range(1, 10):
            p = get_cluster_db_path(vault_dir, i)
            if p.exists():
                console.print(f" -> Reading DB #{i}: [yellow]{p}[/yellow]")
                try:
                    conn = sqlite3.connect(str(p))
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM shards")
                    for row in cursor:
                        row_dict = dict(row)
                        row_dict["_db_index"] = i
                        shards_list.append(row_dict)
                    conn.close()
                except Exception as e:
                    console.print(f"[red]Error reading DB #{i}: {e}[/red]")
    else:
        console.print(f"Single DB Mode Active. Connecting to: [yellow]{db_path}[/yellow]")
        if not db_path.exists():
            console.print(f"[red]Error: Database not found at {db_path}[/red]")
            sys.exit(1)
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM shards")
            for row in cursor:
                shards_list.append(dict(row))
            conn.close()
        except Exception as e:
            console.print(f"[red]Error reading database: {e}[/red]")
            sys.exit(1)

    total_shards = len(shards_list)
    console.print(f"Total shards found: [green]{total_shards}[/green]")

    # Open log file
    console.print(f"Writing detailed log to: [yellow]{LOG_PATH.absolute()}[/yellow]")
    with open(LOG_PATH, "w", encoding="utf-8") as log_file:
        category_stats = {}
        total_score = 0.0

        # Iterate with tqdm
        with tqdm(total=total_shards, desc="Processing Shards", unit="shard") as pbar:
            for idx, row_dict in enumerate(shards_list):
                # Update statistics
                cat = row_dict.get("category") or row_dict.get("event_type") or "UNKNOWN"
                category_stats[cat] = category_stats.get(cat, 0) + 1
                total_score += row_dict.get("utility_score", 1.0)

                # Format detailed log entry
                log_entry = format_row(row_dict)
                log_file.write(log_entry)

                # Periodically print a sample to stdout using rich (every 1000 shards or first/last)
                if (idx + 1) % 1000 == 0 or idx == 0 or idx == total_shards - 1:
                    sample_text = Text()
                    shard_id = row_dict.get('id')
                    db_label = f" (DB #{row_dict['_db_index']})" if "_db_index" in row_dict else ""
                    sample_text.append(f"Sample Shard #{shard_id}{db_label}\n", style="bold green")
                    sample_text.append(f"Category: {cat} | Score: {row_dict.get('utility_score')}\n", style="cyan")
                    snippet_source = row_dict.get('finding') or row_dict.get('content') or ''
                    snippet = str(snippet_source)[:100]
                    sample_text.append(f"Details: {snippet}...", style="italic white")

                    panel = Panel(
                        sample_text,
                        title=f"Progress Sample ({idx + 1}/{total_shards})",
                        border_style="blue",
                        expand=False
                    )
                    console.print()
                    console.print(panel)

                pbar.update(1)

    console.print("\n[bold green]Processing complete![/bold green]")

    # Print rich summary table
    table = Table(title="Vault Substrate Summary")
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Count", style="magenta", justify="right")
    table.add_column("Percentage", style="yellow", justify="right")

    for cat, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_shards) * 100 if total_shards > 0 else 0
        table.add_row(cat, f"{count:,}", f"{pct:.2f}%")

    avg_score = total_score / total_shards if total_shards > 0 else 0
    table.add_row("---", "---", "---")
    table.add_row("[bold white]Total[/bold white]", f"[bold white]{total_shards:,}[/bold white]", "100.00%")
    table.add_row("[bold white]Avg Utility Score[/bold white]", f"[bold white]{avg_score:.4f}[/bold white]", "-")

    console.print(table)

if __name__ == "__main__":
    main()

