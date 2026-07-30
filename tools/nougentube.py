"""NouGenTube — pull a YouTube channel's recent transcripts and shard them into the vault.

Flow: resolve channel (from a seed video or channel URL) -> enumerate uploads in the
lookback window via yt-dlp (newest-first, full metadata, breaks at the window edge)
-> fetch transcripts via youtube-transcript-api -> write markdown to disk -> shard
into the vault via nougen_shards.core.capture (hash-dedup, secret-guard, provenance).

Dry-run by default (fetch + markdown only); pass --confirm to write shards.
Markdown files on disk double as the refetch cache: an existing file is skipped.

Single-video fast path: --video <url> skips channel resolution entirely — one
authenticated yt-dlp session fetches metadata + subtitles together (browser-cookie
lane survives networks where youtube-transcript-api is IP-blocked), with the
transcript API as fallback. Markdown cache and vault sharding are shared with
channel mode.

Config (env -> arg -> fallback, per Dynamic State Doctrine):
  NOUGEN_YT_SEED            seed video or channel URL
  NOUGEN_YT_VIDEO           single video URL (same as --video)
  NOUGEN_YT_DAYS            lookback window in days (default 30)
  NOUGEN_YT_OUT             transcript output dir (default <repo>/transcripts/youtube)
  NOUGEN_YT_MAX             hard cap on videos per run (default 200)
  NOUGEN_YT_COOKIE_BROWSER  browser whose cookies authenticate yt-dlp (default chrome, "" disables)
  NOUGEN_YT_COOKIES_FILE    Netscape cookies.txt export; preferred over browser extraction
  NOUGEN_YT_JS_RUNTIME      JS runtime for PO tokens (default: probe PATH for deno, then node)
  NOUGEN_YT_SUB_LANGS       yt-dlp subtitle language selector (default en.*,-live_chat)

Run with: PYTHONPATH=src python tools/nougentube.py --seed <url> [--confirm]
      or: PYTHONPATH=src python tools/nougentube.py --video <url> [--confirm]
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
COOKIE_BROWSER = os.environ.get("NOUGEN_YT_COOKIE_BROWSER", "chrome")  # "" disables the cookie lane
COOKIES_FILE = os.environ.get("NOUGEN_YT_COOKIES_FILE", "")  # Netscape cookies.txt export; beats browser extraction
SUB_LANGS = os.environ.get("NOUGEN_YT_SUB_LANGS", "en.*,-live_chat")

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([\w-]{11})")


def _js_runtime_args() -> list[str]:
    """YouTube 429s caption URLs from clients that can't mint PO tokens; a JS runtime
    fixes that. Probe PATH per Dynamic State Doctrine (env override -> deno -> node)."""
    import shutil
    runtime = os.environ.get("NOUGEN_YT_JS_RUNTIME", "")
    if not runtime:
        runtime = next((r for r in ("deno", "node") if shutil.which(r)), "")
    return ["--js-runtimes", runtime] if runtime else []


def _cookie_args() -> list[str]:
    """Best available auth lane: an exported cookies.txt always wins (browser DB
    extraction is dead on modern Windows Chrome/Edge — app-bound encryption)."""
    if COOKIES_FILE and Path(COOKIES_FILE).exists():
        return ["--cookies", COOKIES_FILE]
    return ["--cookies-from-browser", COOKIE_BROWSER] if COOKIE_BROWSER else []


def _video_id_from_url(url: str) -> str:
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else ""


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
                *_cookie_args(), *_js_runtime_args(),
                "--skip-download", "--write-auto-subs", "--write-subs",
                "--sleep-requests", "3", "--retries", "3", "--retry-sleep", "30",
                "--sub-langs", SUB_LANGS, "--sub-format", "vtt/srt",
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


def _fetch_via_transcript_api(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:
            fetched = YouTubeTranscriptApi().fetch(video_id)  # >=1.0 API
            snippets = getattr(fetched, "snippets", fetched)
            parts = [getattr(s, "text", None) or s.get("text", "") for s in snippets]
        except AttributeError:
            data = YouTubeTranscriptApi.get_transcript(video_id)  # legacy API
            parts = [d.get("text", "") for d in data]
        return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
    except Exception as exc:  # noqa: BLE001 — caller decides the next lane
        print(f"  transcript-api miss for {video_id}: {type(exc).__name__}")
        return ""


def fetch_transcript(video_id: str) -> str:
    text = _fetch_via_transcript_api(video_id)
    return text or _fetch_via_ytdlp_subs(video_id)


def fetch_single_video(url: str) -> tuple[dict, str, str]:
    """--video fast path: one yt-dlp session pulls metadata + subtitles together,
    authenticated via browser cookies when available (that lane survives networks
    where the transcript API is IP-blocked). Returns (video, channel_name, transcript);
    transcript falls back to youtube-transcript-api, inverting the channel-sweep order."""
    import tempfile
    lanes = [("auth", _cookie_args()), ("anonymous", [])]
    if not _cookie_args():
        lanes = lanes[1:]
    info, transcript = None, ""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        base = [
            *_js_runtime_args(),
            "--skip-download", "--no-playlist", "--no-warnings",
            "--write-auto-subs", "--write-subs", "--write-info-json",
            "--ignore-no-formats-error", "--ignore-errors",
            "--sub-langs", SUB_LANGS, "--sub-format", "vtt/srt",
            "--retries", "2",
            "-o", str(tmp_path / "%(id)s"), url,
        ]
        # Success is judged by artifacts on disk, not exit codes — yt-dlp exits 0 on
        # some failures (cookie DB copy) and non-0 on some successes (window edge).
        for lane, lane_args in lanes:
            try:
                _run_ytdlp([*lane_args, *base], timeout=180)
            except Exception as exc:  # noqa: BLE001 — try the next lane
                print(f"  {lane} lane error: {str(exc)[:120]}")
            if info is None:
                infos = sorted(tmp_path.glob("*.info.json"))
                if infos:
                    info = json.loads(infos[0].read_text(encoding="utf-8", errors="replace"))
            if any(not p.name.endswith(".json") for p in tmp_path.iterdir()):
                break  # got subtitle files; stop burning lanes
            print(f"  {lane} lane: no subtitles")
        if info is None:
            raise RuntimeError(f"yt-dlp returned no metadata for {url}")
        video = {
            "id": info.get("id") or _video_id_from_url(url) or "unknown",
            "title": info.get("title") or info.get("id") or url,
            "url": info.get("webpage_url") or url,
            "upload_date": info.get("upload_date") or "",
        }
        channel_name = info.get("channel") or info.get("uploader") or "unknown-channel"
        for sub in sorted(tmp_path.glob(f"{video['id']}*")):
            if sub.name.endswith(".json"):
                continue
            transcript = _parse_vtt(sub.read_text(encoding="utf-8", errors="replace"))
            if transcript:
                break
    if not transcript:
        print("  no yt-dlp subs, falling back to youtube-transcript-api")
        transcript = _fetch_via_transcript_api(video["id"])
    return video, channel_name, transcript


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


def run_single(args: argparse.Namespace, extra_tags: list[str]) -> None:
    """URL -> transcript -> markdown -> shard, no channel enumeration. Cache-first:
    an existing markdown for this video id skips the network entirely."""
    vid = _video_id_from_url(args.video)
    cached = sorted(args.out.glob(f"*_{vid}_*.md")) if vid else []
    if cached:
        body = cached[0].read_text(encoding="utf-8")
        title_m = re.search(r"^# (.+)$", body, re.MULTILINE)
        chan_m = re.search(r"\*\*Channel\*\*: (.+)", body)
        date_m = re.search(r"\*\*Uploaded\*\*: (.+)", body)
        upload_date = (date_m.group(1).strip() if date_m else "")
        video = {
            "id": vid,
            "title": title_m.group(1).strip() if title_m else vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "upload_date": "" if upload_date == "undated" else upload_date,
        }
        channel_name = chan_m.group(1).strip() if chan_m else "unknown-channel"
        transcript = body.split("## Transcript", 1)[-1].strip()
        print(f"cache hit: {cached[0].name}")
    else:
        video, channel_name, transcript = fetch_single_video(args.video)
        if not transcript:
            print(f"no transcript available for {args.video}")
            sys.exit(2)
        path = markdown_path(args.out, video)
        write_markdown(path, channel_name, video, transcript)
        print(f"markdown: {path.name}")
    print(f"[{channel_name}] {video['title']} — {len(transcript)} chars")
    if not args.confirm:
        print("DRY-RUN complete: pass --confirm to write the shard")
        return
    if shard(channel_name, video, transcript, extra_tags):
        print("WRITE complete: shard captured")
    else:
        print("WRITE complete: dedup skip (shard already in vault)")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):  # Windows cp1252 console chokes on exotic channel names
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default=os.environ.get("NOUGEN_YT_SEED"))
    parser.add_argument("--video", default=os.environ.get("NOUGEN_YT_VIDEO"),
                        help="Single video URL: fast path straight to transcript + shard, no channel sweep.")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--max", type=int, default=DEFAULT_MAX)
    parser.add_argument("--max-new", type=int, default=int(os.environ.get("NOUGEN_YT_MAX_NEW", "0")),
                        help="Stop fetching after this many NEW transcripts this run (0 = unlimited). "
                             "Cached files and misses don't consume budget. Drip-backfill throttle.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--confirm", action="store_true", help="Actually write shards to the vault.")
    parser.add_argument("--tags", default=os.environ.get("NOUGEN_YT_EXTRA_TAGS", ""),
                        help="Comma-separated extra tags stamped on every shard (e.g. genre:ai-news,category:tutorials)")
    args = parser.parse_args()
    extra_tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    if args.video:
        run_single(args, extra_tags)
        return
    if not args.seed:
        parser.error("no target: pass --video/--seed or set NOUGEN_YT_VIDEO/NOUGEN_YT_SEED")

    channel = resolve_channel(args.seed)
    print(f"channel: {channel['channel_name']} ({channel['channel_id']})")
    videos = list_recent_videos(channel["channel_url"], args.days, args.max)
    print(f"{len(videos)} videos in last {args.days} days (cap {args.max})")

    stats = {"sharded": 0, "dedup_skipped": 0, "cached": 0, "no_transcript": 0, "dry_run": 0}
    breaker_limit = int(os.environ.get("NOUGEN_YT_BREAKER", "3"))  # consecutive misses -> stop digging (extends the IP flag)
    consecutive_misses = 0
    circuit_open = False
    new_fetches = 0
    for i, video in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] {video['upload_date']} {video['title'][:70]}")
        path = markdown_path(args.out, video)
        if path.exists():
            transcript = ""
            stats["cached"] += 1
        else:
            if args.max_new and new_fetches >= args.max_new:
                continue  # new-fetch budget spent; cached items above still shard, uncached wait for tomorrow's drip
            import time
            time.sleep(FETCH_SLEEP)
            transcript = fetch_transcript(video["id"])
            if transcript:
                consecutive_misses = 0
                new_fetches += 1
            else:
                consecutive_misses += 1
                if consecutive_misses >= breaker_limit:
                    circuit_open = True
                    print(f"circuit OPEN after {breaker_limit} consecutive misses — stopping sweep to protect the IP")
                    stats["no_transcript"] += 1
                    break
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
    print(f"NEW_FETCHES: {new_fetches}")  # machine-readable budget marker for batch drip accounting
    print(f"\n{mode} complete: {json.dumps(stats)}")
    print(f"transcripts dir: {args.out}")
    if circuit_open:
        sys.exit(3)  # signal callers: rate-limited, cool down before resuming


if __name__ == "__main__":
    main()
