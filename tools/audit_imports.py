"""
Comprehensive AST Import and Module Resolution Scanner for NouGen & Fleet repos.
"""

import ast
import os
import sys
import importlib
import importlib.util
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

relay_root = Path.home() / "Outpost" / "NouGenRelay"
if relay_root.exists():
    sys.path.insert(0, str(relay_root / "src"))

print("=" * 80)
print("AUDITING PYTHON IMPORTS & SYNTAX ACROSS NOUGEN & NOUGENRELAY")
print("=" * 80)

scan_dirs = [
    repo_root / "src",
    repo_root / "tools",
    repo_root / "tests",
    relay_root / "src" if relay_root.exists() else None,
    relay_root / "tests" if relay_root.exists() else None,
]
scan_dirs = [d for d in scan_dirs if d and d.is_dir()]

syntax_errors = []
import_errors = []
total_files = 0

for d in scan_dirs:
    for py_file in d.rglob("*.py"):
        total_files += 1
        # 1. Check syntax compilation
        try:
            with open(py_file, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
            tree = ast.parse(code, filename=str(py_file))
        except SyntaxError as e:
            syntax_errors.append((py_file, str(e)))
            continue

        # 2. Extract top-level imports and try resolving them if internal
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in ("nougen_shards", "nougen_relay"):
                        try:
                            importlib.import_module(alias.name)
                        except Exception as e:
                            import_errors.append((py_file, alias.name, str(e)))
            elif isinstance(node, ast.ImportFrom):
                if node.module and any(node.module.startswith(pkg) for pkg in ("nougen_shards", "nougen_relay")):
                    try:
                        mod = importlib.import_module(node.module)
                        for alias in node.names:
                            if alias.name != "*" and not hasattr(mod, alias.name):
                                import_errors.append((py_file, f"{node.module}.{alias.name}", f"attribute '{alias.name}' missing from '{node.module}'"))
                    except Exception as e:
                        import_errors.append((py_file, node.module, str(e)))

print(f"\nTotal Python files scanned: {total_files}")
print(f"Syntax Errors: {len(syntax_errors)}")
for f, err in syntax_errors:
    print(f"  ❌ Syntax Error in {f.name}: {err}")

print(f"Internal Import / Attribute Errors: {len(import_errors)}")
# Deduplicate
seen = set()
for f, mod, err in import_errors:
    key = (f.name, mod, err)
    if key not in seen:
        seen.add(key)
        print(f"  ⚠️ Import Error in {f.relative_to(repo_root.parent) if repo_root.parent in f.parents else f.name}: `{mod}` -> {err}")

print("\n" + "=" * 80)
if not syntax_errors and not import_errors:
    print("✅ 100% CLEAN: ZERO SYNTAX OR INTERNAL IMPORT ERRORS DETECTED")
else:
    print(f"🚨 FOUND {len(syntax_errors)} SYNTAX ERRORS AND {len(seen)} IMPORT DISCREPANCIES")
print("=" * 80)
