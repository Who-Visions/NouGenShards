import os
import sys
import hashlib
import json
from pathlib import Path

# Ensure PYTHONPATH is set to include src so we can import nougen_shards
pull_clone_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pull_clone_root / "src"))

# Direct NOUGEN_VAULT_DIR to the active main memory of pull-clone
active_vault_dir = pull_clone_root / ".vault"
os.environ["NOUGEN_VAULT_DIR"] = str(active_vault_dir)

import nougen_shards.core as shards

# Target directories to scan
target_dirs = [
    Path(r"%USERPROFILE%\Watchtower\memory"),
    Path(r"%USERPROFILE%\Watchtower\Who-tester"),
    Path(r"%USERPROFILE%\Watchtower\Things the agent forget"),
    Path(r"%USERPROFILE%\Watchtower\gemini_cookbook"),
    Path(r"%USERPROFILE%\Watchtower\unk_trader_mobile"),
    Path(r"%USERPROFILE%\Watchtower\NouGen\NouGenAiAntigravityMonitor")
]

# Watchtower root path for calculating relative titles
watchtower_root = Path(r"%USERPROFILE%\Watchtower")

# Ignore lists (skip standard template/scaffold directories to keep memory core clean)
ignore_dirs = {
    ".git", ".venv", ".pytest_cache", "__pycache__", ".idea", ".vscode", 
    "node_modules", "build", "dist", ".dart_tool", ".next", "scratch",
    "android", "ios", "macos", "windows", "linux", "web"
}
binary_extensions = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".mp4", ".mp3", ".wav", ".avi", ".mov",
    ".db", ".sqlite", ".sqlite3"
}

print(f"Starting scanning and sharding into active memory vault at {active_vault_dir}...")
total_scanned = 0
total_imported = 0
total_skipped = 0
total_errors = 0

for target in target_dirs:
    if not target.exists():
        print(f"Directory {target} does not exist, skipping.")
        continue

    print(f"\nScanning directory: {target}")
    
    for root, dirs, files in os.walk(target):
        # In-place filtering of dirs to avoid walking ignored directories or saved _files assets
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.endswith("_files")]
        
        for file in files:
            file_path = Path(root) / file
            
            # Skip by extension
            ext = file_path.suffix.lower()
            if ext in binary_extensions:
                continue
                
            total_scanned += 1
            
            # Read content
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                total_errors += 1
                continue
                
            # Skip empty files
            if not content.strip():
                total_skipped += 1
                continue
                
            # Jupyter Notebooks cell parser: extract only text and code cells to avoid base64 bloat
            if ext == ".ipynb":
                try:
                    notebook = json.loads(content)
                    clean_lines = []
                    for cell in notebook.get("cells", []):
                        cell_type = cell.get("cell_type")
                        source = cell.get("source", [])
                        source_str = "".join(source) if isinstance(source, list) else str(source)
                        
                        if cell_type == "markdown":
                            clean_lines.append(source_str)
                        elif cell_type == "code":
                            # Wrap code cells in python Markdown blocks
                            clean_lines.append(f"\n```python\n{source_str.strip()}\n```\n")
                    content = "\n\n".join(clean_lines).strip()
                except Exception as e:
                    print(f"Warning: Failed to parse notebook {file_path}: {e}")
                    total_errors += 1
                    continue
                    
                # Skip if empty after cell extraction
                if not content.strip():
                    total_skipped += 1
                    continue
                    
            # Classify event type
            code_exts = {".py", ".sh", ".bat", ".ps1", ".json", ".toml", ".lock", ".yaml", ".yml", ".ts", ".tsx", ".js", ".jsx", ".css", ".dart"}
            event_type = "CODE" if ext in code_exts else "DOCUMENT"
            
            # Title is the path relative to %USERPROFILE%\Watchtower
            try:
                title = str(file_path.relative_to(watchtower_root)).replace("\\", "/")
            except ValueError:
                title = str(file_path.name)
                
            # Tags
            folder_name = target.name
            clean_ext = ext.lstrip(".") if ext else "no_ext"
            tags = ["imported", "watchtower", folder_name, clean_ext]
            
            # Ingest
            try:
                success = shards.capture(
                    event_type=event_type,
                    title=title,
                    content=content,
                    tags=tags
                )
                if success:
                    total_imported += 1
                else:
                    total_skipped += 1
            except Exception as e:
                print(f"Error capturing shard for {title}: {e}")
                total_errors += 1

print("\n=== SHARDING SUMMARY ===")
print(f"Total files scanned:    {total_scanned}")
print(f"Total shards imported:  {total_imported}")
print(f"Total shards skipped:   {total_skipped}")
print(f"Total errors:           {total_errors}")
