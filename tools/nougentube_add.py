"""NouGenTube roster add — append new channels to the harvest roster from any YouTube URL.

Usage: python tools/nougentube_add.py <url> [<url> ...] [--sweep] [--genre g --category c]

For each URL (video, channel, or @handle): resolve the channel via yt-dlp, dedup
against transcripts/channels.csv, classify genre/category on the local ollama lane
(falls back to 'tbd' if no model answers), and append the row. --sweep runs an
immediate 30-day sweep of the newly added channels; otherwise the daily scheduled
harvest picks them up next run.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from nougentube import resolve_channel  # noqa: E402

ROSTER = Path(os.environ.get("NOUGEN_YT_ROSTER", str(_REPO_ROOT / "transcripts" / "channels.csv")))
sys.path.insert(0, str(_REPO_ROOT / "src"))
from nougen_shards.ollama_host import resolve_ollama_url  # noqa: E402

OLLAMA = resolve_ollama_url()
GENRES = ["ai-news", "ai-tools", "business", "entertainment", "science", "tech", "finance", "education", "other"]


def _classify(channel_name: str, seed_url: str) -> tuple[str, str]:
    """Ask the local fleet lane for genre/category; 'tbd' when no lane answers."""
    model = os.environ.get("NOUGEN_CLASSIFY_MODEL")
    try:
        if not model:  # probe live model list instead of trusting config (Rule 0.2)
            with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
                names = [m["name"] for m in json.load(r).get("models", [])]
            model = next((n for n in names if "gemma" in n.lower()), names[0] if names else None)
        if not model:
            return "tbd", "tbd"
        prompt = (
            f"YouTube channel: \"{channel_name}\" ({seed_url}). "
            f"Reply with ONLY JSON like {{\"genre\": \"...\", \"category\": \"...\"}}. "
            f"genre must be one of {GENRES}; category is a short kebab-case descriptor "
            f"(e.g. model-coverage, tutorials, interview-podcast, story-recaps)."
        )
        req = urllib.request.Request(
            f"{OLLAMA}/api/generate",
            data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                             "format": "json", "options": {"temperature": 0}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = json.load(r).get("response", "{}")
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        out = json.loads(raw)
        genre = str(out.get("genre", "tbd")).strip().lower()
        category = str(out.get("category", "tbd")).strip().lower().replace(" ", "-")
        return (genre if genre in GENRES else "tbd"), (category or "tbd")
    except Exception as exc:  # noqa: BLE001 — classification is best-effort
        print(f"  classify miss ({type(exc).__name__}) — marking tbd")
        return "tbd", "tbd"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--genre", default="", help="Override auto-classification")
    parser.add_argument("--category", default="", help="Override auto-classification")
    parser.add_argument("--sweep", action="store_true", help="Run an immediate 30-day sweep of the new channels")
    args = parser.parse_args()

    rows = list(csv.DictReader(ROSTER.open(encoding="utf-8"))) if ROSTER.exists() else []
    known_ids = {r.get("channel_id", "") for r in rows if r.get("channel_id")}
    known_handles = {r.get("handle", "").lower() for r in rows}
    known_seeds = {r.get("seed_url", "").rstrip("/").lower() for r in rows}
    fields = ["seed_url", "handle", "genre", "category", "notes", "channel_id"]

    added = []
    for url in args.urls:
        m = re.search(r"@([\w.-]+)", url)
        if url.rstrip("/").lower() in known_seeds or (m and m.group(1).lower() in known_handles):
            print(f"DUP  {url} — already on roster")
            continue
        try:
            ch = resolve_channel(url)
        except Exception as exc:  # noqa: BLE001
            print(f"SKIP {url}: could not resolve ({str(exc)[:120]})")
            continue
        handle = (m.group(1) if m else ch["channel_url"].rsplit("/", 1)[-1].lstrip("@")) or ch["channel_id"]
        if ch["channel_id"] in known_ids or handle.lower() in known_handles:
            print(f"DUP  {ch['channel_name']} — already on roster")
            continue
        genre = args.genre or None
        category = args.category or None
        if not (genre and category):
            g, c = _classify(ch["channel_name"], url)
            genre, category = genre or g, category or c
        row = {"seed_url": ch["channel_url"], "handle": handle, "genre": genre,
               "category": category, "notes": f"added via nougentube_add ({ch['channel_name']})",
               "channel_id": ch["channel_id"]}
        rows.append(row)
        known_ids.add(ch["channel_id"]); known_handles.add(handle.lower())
        added.append(row)
        print(f"ADD  {ch['channel_name']} -> genre:{genre}, category:{category}")

    if added:
        with ROSTER.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fields})
        print(f"roster now {len(rows)} seeds ({len(added)} new)")
    else:
        print("nothing added")

    if added and args.sweep:
        only = ",".join(r["handle"] for r in added)
        subprocess.run([sys.executable, str(_REPO_ROOT / "tools" / "nougentube_batch.py"),
                        "--days", "30", "--confirm", "--only", only],
                       env={**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")})


if __name__ == "__main__":
    main()
