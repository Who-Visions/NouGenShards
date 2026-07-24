"""NouGenTube — pull a YouTube channel's recent transcripts and shard them into the vault.

Flow: resolve channel (from a seed video or channel URL) -> enumerate uploads in the
lookback window via yt-dlp (newest-first, full metadata, breaks at the window edge)
-> fetch transcripts via youtube-transcript-api -> write markdown to disk -> shard
into the vault via nougen_shards.core.capture (hash-dedup, secret-guard, provenance).

Dry-run by default (fetch + markdown only); pass --confirm to write shards.
Markdown files on disk double as the refetch cache: an existing file is skipped.

Config (env -> arg -> fallback, per Dynamic State Doctrine):
  NOUGEN_YT_SEED      seed video or channel URL
  NOUGEN_YT_DAYS      lookback window in days (default 30)
  NOUGEN_YT_OUT       transcript output dir (default <repo>/transcripts/youtube)
  NOUGEN_YT_MAX       hard cap on videos per run (default 200)

Run with: PYTHONPATH=src python tools/nougentube.py --seed <url> [--confirm]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

DEFAULT_OUT = Path(os.environ.get("NOUGEN_YT_OUT", str(_REPO_ROOT / "transcripts" / "youtube")))
DEFAULT_DAYS = int(os.environ.get("NOUGEN_YT_DAYS", "30"))
DEFAULT_MAX = int(os.environ.get("NOUGEN_YT_MAX", "200"))
FETCH_SLEEP = float(os.environ.get("NOUGEN_YT_SLEEP", "8"))  # seconds between transcript fetches (429 guard)
EVENT_TYPE = os.environ.get("NOUGEN_YT_EVENT_TYPE", "YOUTUBE_TRANSCRIPT")


def _run_ytdlp(args: list[str], timeout: int = 1800) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "yt_dlp", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
    # --break-on-reject exits non-zero when it stops at the window edge; stdout is still valid.
    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(f"yt-dlp failed ({proc.returncode}): {proc.stderr.strip()[:400]}")
    return proc.stdout


def resolve_channel(seed_url: str) -> dict:
    out = _run_ytdlp(["--dump-single-json", "--playlist-items", "0", "--no-warnings", seed_url],
                     timeout=120)
    info = json.loads(out)
    channel_id = info.get("channel_id") or info.get("uploader_id")
    if not channel_id:
        raise RuntimeError(f"could not resolve channel from seed: {seed_url}")
    return {
        "channel_id": channel_id,
        "channel_url": info.get("channel_url") or f"https://www.youtube.com/channel/{channel_id}",
        "channel_name": info.get("channel") or info.get("uploader") or channel_id,
    }


def list_recent_videos(channel_url: str, days: int, cap: int) -> list[dict]:
    """Enumerate uploads in the window. Full metadata per video (flat listings carry no
    dates); newest-first with --break-on-reject stops at the first video older than the
    cutoff instead of walking the whole channel."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    out = _run_ytdlp([
        "--skip-download", "--dump-json", "--no-warnings", "--lazy-playlist",
        "--dateafter", cutoff, "--break-on-reject",
        "--playlist-items", f"1:{cap}",
        f"{channel_url.rstrip('/')}/videos",
    ])
    videos = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("id"):
            videos.append({
                "id": entry["id"],
                "title": entry.get("title") or entry["id"],
                "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry['id']}",
                "upload_date": entry.get("upload_date") or "",
            })
    return videos


def _parse_vtt(text: str) -> str:
    """Flatten a VTT/SRT caption file to plain text, dropping cue metadata and
    the rolling-window duplicates auto-subs produce."""
    lines, seen = [], None
    for raw in text.splitlines():
        line = re.sub(r"<[^>]+>", "", raw).strip()
        if (not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or "-->" in line or line.isdigit()):
            continue
        if line != seen:
            lines.append(line)
            seen = line
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _fetch_via_ytdlp_subs(video_id: str) -> str:
    """Fallback lane: yt-dlp auto-captions (different endpoints than the transcript API)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _run_ytdlp([
                "--skip-download", "--write-auto-subs", "--write-subs",
                "--sleep-requests", "3", "--retries", "3", "--retry-sleep", "30",
                "--sub-langs", "en.*,-live_chat", "--sub-format", "vtt/srt",
                "-o", str(Path(tmp) / "%(id)s"),
                f"https://www.youtube.com/watch?v={video_id}",
            ], timeout=300)
        except Exception as exc:  # noqa: BLE001
            print(f"  yt-dlp subs miss for {video_id}: {str(exc)[:120]}")
            return ""
        for sub in sorted(Path(tmp).glob(f"{video_id}*")):
            parsed = _parse_vtt(sub.read_text(encoding="utf-8", errors="replace"))
            if parsed:
                return parsed
    return ""


def fetch_transcript(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:
            fetched = YouTubeTranscriptApi().fetch(video_id)  # >=1.0 API
            snippets = getattr(fetched, "snippets", fetched)
            parts = [getattr(s, "text", None) or s.get("text", "") for s in snippets]
        except AttributeError:
            data = YouTubeTranscriptApi.get_transcript(video_id)  # legacy API
            parts = [d.get("text", "") for d in data]
        text = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
        if text:
            return text
    except Exception as exc:  # noqa: BLE001 — fall through to the yt-dlp lane
        print(f"  transcript-api miss for {video_id}: {type(exc).__name__}, trying yt-dlp subs")
    return _fetch_via_ytdlp_subs(video_id)


def markdown_path(out_dir: Path, video: dict) -> Path:
    safe_title = re.sub(r"[^\w\- ]+", "", video["title"])[:80].strip().replace(" ", "_")
    return out_dir / f"{video.get('upload_date') or 'undated'}_{video['id']}_{safe_title}.md"


def write_markdown(path: Path, channel_name: str, video: dict, transcript: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {video['title']}\n\n"
        f"- **Channel**: {channel_name}\n"
        f"- **URL**: {video['url']}\n"
        f"- **Uploaded**: {video.get('upload_date') or 'undated'}\n"
        f"- **Fetched**: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"## Transcript\n\n{transcript}\n",
        encoding="utf-8",
    )


def shard(channel_name: str, video: dict, transcript: str, extra_tags: list[str]) -> bool:
    from nougen_shards import core
    title = f"[{channel_name}] {video['title']} ({video.get('upload_date') or 'undated'})"
    content = f"Source: {video['url']}\n\n{transcript}"
    tags = ["youtube", "transcript", "nougentube",
            re.sub(r"[^\w\- ]+", "", channel_name).strip().lower().replace(" ", "-"),
            *extra_tags]
    return core.capture(EVENT_TYPE, title, content, tags=tags)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):  # Windows cp1252 console chokes on exotic channel names
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default=os.environ.get("NOUGEN_YT_SEED"))
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--max", type=int, default=DEFAULT_MAX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--confirm", action="store_true", help="Actually write shards to the vault.")
    parser.add_argument("--tags", default=os.environ.get("NOUGEN_YT_EXTRA_TAGS", ""),
                        help="Comma-separated extra tags stamped on every shard (e.g. genre:ai-news,category:tutorials)")
    args = parser.parse_args()
    extra_tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    if not args.seed:
        parser.error("no seed: pass --seed or set NOUGEN_YT_SEED")

    channel = resolve_channel(args.seed)
    print(f"channel: {channel['channel_name']} ({channel['channel_id']})")
    videos = list_recent_videos(channel["channel_url"], args.days, args.max)
    print(f"{len(videos)} videos in last {args.days} days (cap {args.max})")

    stats = {"sharded": 0, "dedup_skipped": 0, "cached": 0, "no_transcript": 0, "dry_run": 0}
    for i, video in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] {video['upload_date']} {video['title'][:70]}")
        path = markdown_path(args.out, video)
        if path.exists():
            transcript = ""
            stats["cached"] += 1
        else:
            import time
            time.sleep(FETCH_SLEEP)
            transcript = fetch_transcript(video["id"])
            if not transcript:
                stats["no_transcript"] += 1
                continue
            write_markdown(path, channel["channel_name"], video, transcript)
        if not args.confirm:
            stats["dry_run"] += 1
            continue
        if not transcript:  # cached file — reload for sharding, capture() dedups
            body = path.read_text(encoding="utf-8")
            transcript = body.split("## Transcript", 1)[-1].strip()
        if shard(channel["channel_name"], video, transcript, extra_tags):
            stats["sharded"] += 1
        else:
            stats["dedup_skipped"] += 1

    mode = "WRITE" if args.confirm else "DRY-RUN"
    print(f"\n{mode} complete: {json.dumps(stats)}")
    print(f"transcripts dir: {args.out}")


if __name__ == "__main__":
    main()
