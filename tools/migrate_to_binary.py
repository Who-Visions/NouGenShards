#!/usr/bin/env python
"""
migrate_to_binary.py — Binary float32 Vector Substrate Migration Tool.
Scans all 9 database nodes for legacy text/JSON-serialized embeddings
and converts them in-place to normalized, high-performance binary float32 buffers.
"""
import os
import sys
import json
import sqlite3
from pathlib import Path
import numpy as np
from rich.console import Console

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
    console.print("\n[bold cyan]⚡ Vector Substrate Migrator — float32 Transition[/bold cyan]")
    console.print(f"Active Vault Directory: [yellow]{vault_dir}[/yellow]\n")
    
    total_migrated = 0
    total_scanned = 0
    
    for idx in range(1, 10):
        db_path = vault_dir / f"nougen_shards_{idx}.db"
        if not db_path.exists():
            continue
            
        console.print(f"Scanning DB Node #{idx}...")
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Select shards with embeddings
            cursor.execute("SELECT id, embedding FROM shards WHERE embedding IS NOT NULL")
            rows = cursor.fetchall()
            
            updates = []
            for r in rows:
                total_scanned += 1
                shard_id = r["id"]
                emb_data = r["embedding"]
                
                # Check if this is a legacy JSON embedding
                is_legacy = False
                embedding_list = None
                
                try:
                    # If it's a binary blob of floats, np.frombuffer should parse it without throwing a ValueError
                    # unless it starts with b'[' (meaning it was stored as JSON text/bytes)
                    if isinstance(emb_data, (bytes, bytearray)):
                        if emb_data.startswith(b'['):
                            is_legacy = True
                            embedding_list = json.loads(emb_data.decode("utf-8"))
                        else:
                            # Verify if it has the correct length (e.g. dimensions * 4 bytes)
                            # If it's not a valid numpy buffer, np.frombuffer might succeed but have strange size
                            # So let's double check if we can parse it
                            arr = np.frombuffer(emb_data, dtype=np.float32)
                            if len(arr) == 0:
                                is_legacy = True
                except Exception:
                    is_legacy = True
                    
                if is_legacy:
                    # Let's try to parse as JSON list
                    try:
                        if embedding_list is None:
                            if isinstance(emb_data, bytes):
                                emb_data = emb_data.decode("utf-8")
                            embedding_list = json.loads(emb_data)
                            
                        if isinstance(embedding_list, list) and len(embedding_list) > 0:
                            # Convert to binary float32
                            arr = np.array(embedding_list, dtype=np.float32)
                            norm = np.linalg.norm(arr)
                            if norm > 0:
                                arr = arr / norm
                            binary_blob = sqlite3.Binary(arr.tobytes())
                            updates.append((binary_blob, shard_id))
                    except Exception as e:
                        console.print(f"  [red]Failed to parse legacy embedding for Shard #{shard_id}: {e}[/red]")
                        
            if updates:
                console.print(f"  -> Migrating {len(updates)} legacy embeddings on Node #{idx}...")
                conn.executemany("UPDATE shards SET embedding = ? WHERE id = ?", updates)
                conn.commit()
                # VACUUM to reclaim space after changing storage format
                cursor.execute("VACUUM")
                conn.commit()
                total_migrated += len(updates)
                
            conn.close()
        except Exception as e:
            console.print(f"[red]Error during migration on Node #{idx}: {e}[/red]")
            
    console.print(f"\n[bold green]Migration complete![/bold green]")
    console.print(f"Total Shards Scanned:  {total_scanned}")
    console.print(f"Total Shards Migrated: {total_migrated}")

if __name__ == "__main__":
    main()
