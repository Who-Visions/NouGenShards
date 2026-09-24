#!/usr/bin/env python3
"""
Sync Engine for NouGenQ <-> NouGenQ-AIS
Keeps the Google AI Studio build and the canonical Who-Visions/NouGenQ repository in perfect two-way sync.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_OUTPOST = Path(r"c:\Users\super\Outpost")
AIS_REPO = ROOT_OUTPOST / "NouGenQ-AIS"
CANONICAL_REPO = ROOT_OUTPOST / "NouGenQ"

SYNC_PATHS = [
    ("src/engine", "src/engine"),
    ("src/services", "src/services"),
    ("src/types", "src/types"),
    ("src/components/TalentSurface.tsx", "src/components/TalentSurface.tsx"),
    ("src/components/OperatorSurface.tsx", "src/components/OperatorSurface.tsx"),
    ("src/components/ScriptCompilerView.tsx", "src/components/ScriptCompilerView.tsx"),
    ("src/components/DiagnosticsHUD.tsx", "src/components/DiagnosticsHUD.tsx"),
    ("src/components/MemoryVaultView.tsx", "src/components/MemoryVaultView.tsx"),
    ("src/components/OverlayMode.tsx", "src/components/OverlayMode.tsx"),
    ("src/components/QZeroScreen.tsx", "src/components/QZeroScreen.tsx"),
    ("src/components/TranscriptReplayHarness.tsx", "src/components/TranscriptReplayHarness.tsx"),
    ("docs/nougenq-master-specification.md", "docs/nougenq-master-specification.md"),
]


def run_cmd(cmd, cwd):
    print(f"[{cwd.name}] $ {cmd}")
    res = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    if res.returncode != 0 and "nothing to commit" not in res.stdout and "nothing to commit" not in res.stderr:
        print(f"  STDERR: {res.stderr.strip()}", file=sys.stderr)
    return res


def sync_files(src_repo: Path, dst_repo: Path):
    for src_rel, dst_rel in SYNC_PATHS:
        src_path = src_repo / src_rel
        dst_path = dst_repo / dst_rel

        if not src_path.exists():
            continue

        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
            for root, _, files in os.walk(src_path):
                for f in files:
                    s_file = Path(root) / f
                    rel = s_file.relative_to(src_path)
                    d_file = dst_path / rel
                    d_file.parent.mkdir(parents=True, exist_ok=True)
                    # Check if file changed
                    if not d_file.exists() or s_file.stat().st_mtime > d_file.stat().st_mtime:
                        shutil.copy2(s_file, d_file)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if not dst_path.exists() or src_path.stat().st_mtime > dst_path.stat().st_mtime:
                shutil.copy2(src_path, dst_path)


def main():
    print("🛰️ NouGenQ <-> NouGenQ-AIS Two-Way Sync Engine")
    print(f"  AIS Target:       {AIS_REPO}")
    print(f"  Canonical Target: {CANONICAL_REPO}")

    if not AIS_REPO.exists() or not CANONICAL_REPO.exists():
        print("❌ Error: One or both repositories do not exist on disk.", file=sys.stderr)
        sys.exit(1)

    # 1. Bidirectional file synchronization based on newer timestamp
    print("\n[1/4] Synchronizing modules (engine, services, components, types, docs)...")
    sync_files(AIS_REPO, CANONICAL_REPO)
    sync_files(CANONICAL_REPO, AIS_REPO)

    # 2. Verify AIS Build
    print("\n[2/4] Verifying AIS typecheck...")
    res_ais = run_cmd("npm run lint", cwd=AIS_REPO)
    if res_ais.returncode != 0:
        print(f"❌ AIS typecheck failed:\n{res_ais.stdout}\n{res_ais.stderr}")
        sys.exit(1)
    print("  ✅ AIS typecheck passed cleanly.")

    # 3. Verify Canonical Build
    print("\n[3/4] Verifying Canonical typecheck...")
    res_can = run_cmd("pnpm tsc --noEmit", cwd=CANONICAL_REPO)
    if res_can.returncode != 0:
        print(f"❌ Canonical typecheck failed:\n{res_can.stdout}\n{res_can.stderr}")
        sys.exit(1)
    print("  ✅ Canonical typecheck passed cleanly.")

    # 4. Git status & push if requested
    print("\n[4/4] Checking Git Status across both repos...")
    run_cmd("git status -s", cwd=AIS_REPO)
    run_cmd("git status -s", cwd=CANONICAL_REPO)

    print("\n🎯 Both repositories are 100% verified and synchronized.")


if __name__ == "__main__":
    main()
