#!/usr/bin/env python
"""
metameric_deep_sweep.py — Cognitive Substrate Compactor and Index Sweeper.
Performs global deduplication checks, rebuilds FTS5 trigram indexes,
executes SQLite vacuum/optimization, and runs integrity diagnostics on all 9 nodes.
"""
import os
import sys
import sqlite3
from pathlib import Path
from rich.console import Console
from rich.table import Table

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

def main():
    console = Console()
    vault_dir = get_vault_dir()
    os.environ["NOUGEN_VAULT_DIR"] = str(vault_dir)
    
    console.print("\n[bold cyan]🧹 Metameric Deep Sweep — NouGenShards[/bold cyan]")
    console.print(f"Sweeping database nodes in: [yellow]{vault_dir}[/yellow]\n")
    
    table = Table(title="Substrate Sweep Diagnostic")
    table.add_column("Node", style="cyan")
    table.add_column("Deduplication", style="magenta")
    table.add_column("FTS5 Index Status", style="green")
    table.add_column("Integrity", style="yellow")
    table.add_column("Compacted Size", style="blue", justify="right")
    
    # 1. Deduplication pass: find duplicates across the entire cluster
    # Let's map file_hash -> list of (db_index, shard_id, utility_score, timestamp)
    global_hashes = {}
    duplicates_found = 0
    duplicates_resolved = 0
    
    console.print("[yellow]Phase 1: Scanning for global duplicate hashes...[/yellow]")
    for i in range(1, 10):
        db_path = vault_dir / f"nougen_shards_{i}.db"
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, file_hash, utility_score, timestamp FROM shards")
            for row in cursor:
                fhash = row["file_hash"]
                if fhash not in global_hashes:
                    global_hashes[fhash] = []
                global_hashes[fhash].append((i, row["id"], row["utility_score"], row["timestamp"]))
            conn.close()
        except Exception as e:
            console.print(f"[red]Error scanning Node #{i}: {e}[/red]")
            
    # Resolve duplicates: keep the one with the highest utility score
    for fhash, occurrences in global_hashes.items():
        if len(occurrences) > 1:
            duplicates_found += 1
            # Sort: highest utility first, then latest timestamp
            occurrences.sort(key=lambda x: (x[2], x[3] or ""), reverse=True)
            # The first one is the winner
            winner = occurrences[0]
            # Delete the losers
            for loser in occurrences[1:]:
                db_index, shard_id, _, _ = loser
                try:
                    conn = sqlite3.connect(str(vault_dir / f"nougen_shards_{db_index}.db"))
                    conn.execute("DELETE FROM shards WHERE id = ?", (shard_id,))
                    conn.commit()
                    conn.close()
                    duplicates_resolved += 1
                except Exception as e:
                    console.print(f"[red]Failed to delete duplicate shard {shard_id} from Node #{db_index}: {e}[/red]")
                    
    if duplicates_found > 0:
        console.print(f"[green]Duplicates Resolved: Removed {duplicates_resolved} redundant shards across {duplicates_found} conflicts.[/green]\n")
    else:
        console.print("[green]Deduplication: No redundant shards detected (100% clean).[/green]\n")

    # Rebuild dedup index hashes table if needed
    try:
        dconn = core._get_dedup_connection()
        dconn.execute("DELETE FROM hashes")
        dconn.commit()
        core._ensure_dedup_index(dconn)
        dconn.close()
    except Exception as e:
        console.print(f"[dim yellow]Notice: Dedup index regeneration bypassed: {e}[/dim yellow]")

    # 2. Main node optimization, rebuild, and check loop
    console.print("[yellow]Phase 2: Sweeping node substrates...[/yellow]")
    for i in range(1, 10):
        db_path = vault_dir / f"nougen_shards_{i}.db"
        if not db_path.exists():
            table.add_row(f"Node #{i}", "-", "-", "-", "[dim]0.00 MB[/dim]")
            continue
            
        dedup_status = "OK"
        fts_status = "FAILED"
        integrity_status = "FAILED"
        size_str = "0.00 MB"
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Rebuild FTS5 Virtual Table Index
            try:
                cursor.execute("INSERT INTO shards_fts(shards_fts) VALUES('rebuild')")
                conn.commit()
                fts_status = "REBUILT"
            except sqlite3.OperationalError:
                # Trigram virtual table might not exist or failed
                fts_status = "BYPASSED"
                
            # SQLite Optimization & Compact
            cursor.execute("PRAGMA optimize")
            cursor.execute("VACUUM")
            conn.commit()
            
            # Integrity check
            cursor.execute("PRAGMA integrity_check")
            check_res = cursor.fetchone()
            if check_res and check_res[0] == "ok":
                integrity_status = "PASS"
            else:
                integrity_status = f"FAIL: {check_res[0]}"
                
            conn.close()
            
            # Calculate compacted size
            size_mb = db_path.stat().st_size / (1024 * 1024)
            size_str = f"{size_mb:.2f} MB"
            
        except Exception as e:
            dedup_status = f"ERROR: {e}"
            
        table.add_row(f"Node #{i}", dedup_status, fts_status, integrity_status, size_str)
        
    console.print(table)
    console.print("\n[bold green]Metameric deep sweep completed successfully![/bold green]")

if __name__ == "__main__":
    main()
