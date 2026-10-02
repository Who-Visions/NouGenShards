#!/usr/bin/env python3
"""Batch recursive README compiler and shard persistence runner for November 2025 repos."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add project root and src to sys.path
root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from tools.readme_compiler import (
    _draft_sources,
    _resolve_persona,
    draft_manifest,
    compile_readme,
    _atomic_write,
)

TARGET_REPOS = [
    "Sd-3js",
    "Void-runner",
    "Mirrorverse",
    "Shadow-board",
    "Nyx-Playground",
    "Dav1d",
    "Kaedra",
    "WhoSite",
]

def process_repo(repo_name: str, model: str = "Yukiai:e2b") -> dict:
    repo_path = (root_dir.parent / repo_name).resolve()
    print(f"\n==================================================")
    print(f"[*] Processing: {repo_name} at {repo_path}")
    print(f"==================================================")

    if not repo_path.is_dir():
        print(f"[-] Directory not found: {repo_path}")
        return {"repo": repo_name, "status": "skipped", "reason": "not found"}

    t0 = time.time()
    sources = _draft_sources(repo_path, [])
    print(f"[+] Gathered {len(sources)} source files: {[s['path'] for s in sources]}")

    persona_info = _resolve_persona(sources, repo_path)
    if persona_info:
        print(f"[+] Persona Resolved: {persona_info['audience']} in '{persona_info['market']}' "
              f"[{persona_info['fingerprint']}] (Register: {persona_info['register']})")
    else:
        print("[!] No persona resolved, falling back to default.")

    host = "http://127.0.0.1:11434"
    print(f"[+] Requesting draft manifest from {model} at {host}...")
    manifest = draft_manifest(repo_path, sources, model, host, timeout=120.0)

    draft_path = repo_path / "README.nougen.draft.json"
    rendered_json = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write(draft_path, rendered_json)
    print(f"[+] Wrote draft manifest: {draft_path}")

    # Compile Markdown
    readme_md = compile_readme(manifest, repo_path)
    readme_path = repo_path / "README.md"
    _atomic_write(readme_path, readme_md.encode("utf-8"))
    duration = time.time() - t0
    print(f"[+] Compiled {readme_path} in {duration:.1f}s")

    return {
        "repo": repo_name,
        "status": "success",
        "duration": round(duration, 1),
        "audience": persona_info["audience"] if persona_info else "general",
        "market": persona_info["market"] if persona_info else "general",
        "fingerprint": persona_info["fingerprint"] if persona_info else "none",
        "sections": len(manifest.get("sections", [])),
        "readme_lines": len(readme_md.splitlines()),
    }

def shard_milestone(results: list[dict]):
    print("\n[*] Sharding milestone to NouGen memory substrate...")
    summary_lines = [
        "# Milestone: Batch Recursive README & Persona Sharding Complete",
        f"Processed {len(results)} November 2025 Fleet Repositories with Dynamic Deterministic Persona Resolution.",
        "",
        "| Repository | Audience | Market | Fingerprint | Sections | Lines | Duration |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in results:
        if r.get("status") == "success":
            summary_lines.append(
                f"| **{r['repo']}** | `{r['audience']}` | `{r['market']}` | `{r['fingerprint']}` | {r['sections']} | {r['readme_lines']} | {r['duration']}s |"
            )
        else:
            summary_lines.append(f"| **{r['repo']}** | Skipped | - | - | - | - | - |")

    summary_text = "\n".join(summary_lines)

    # Shard via CLI
    cmd = [
        sys.executable,
        "-m",
        "nougen_shards.cli",
        "add",
        "--tags",
        "nov2025,readme,persona,automation,milestone",
        summary_text,
    ]
    try:
        proc = subprocess.run(cmd, cwd=str(root_dir), capture_output=True, text=True, check=True)
        print(f"[+] Milestone sharded successfully:\n{proc.stdout}")
    except subprocess.CalledProcessError as exc:
        print(f"[-] Shard CLI error: {exc.stderr}")

def main():
    results = []
    for repo in TARGET_REPOS:
        try:
            res = process_repo(repo)
            results.append(res)
        except Exception as exc:
            print(f"[-] Error processing {repo}: {exc}")
            results.append({"repo": repo, "status": "error", "error": str(exc)})

    shard_milestone(results)
    print("\n[+] All repositories processed and milestone sharded.")

if __name__ == "__main__":
    main()
