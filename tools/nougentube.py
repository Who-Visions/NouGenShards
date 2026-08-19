"""NouGenTube — YouTube URLs/playlists -> transcripts -> era-stamped shards.

Recomposition of a proven ingest pipeline (tiered transcript fetch, playlist
expansion, Recursive-512 splitting, verbatim preservation) with the grid as
the sink: each video becomes one or more shards captured at the video's TRUE
publish date via ``capture(original_timestamp=...)``, tagged ``tube:<id>`` so
the exact-id dedupe gate can short-circuit re-ingestion.

Usage:
  python tools/nougentube.py <video-or-playlist-url> [--dry-run] [--limit N]
  python tools/nougentube.py --manifest sources.json [--dry-run] [--limit N]

Manifest shape: {"sources": [{"url": "...", "title": "...", "channel": "..."}]}
Adding a channel/video is one manifest entry — config, not code. Manifest runs
keep a resume state file so a crashed run heals on restart.

Design commitments (recorded defects in the ancestor pipeline, fixed here):
  * ``--dry-run`` ACTUALLY gates every write: no shard capture, no state-file
    update, nothing persistent. A dry run that writes is a defect, not a mode.
  * The dedupe gate keys on the EXACT video id (``tube:<id>`` tag), never on
    semantic similarity — near-miss text must not silently block an ingest.
  * Playlists are first-class: a playlist URL expands and each entry runs the
    full per-video pipeline.
  * A failed transcript never aborts a batch: both fetch tiers failing yields
    a metadata-only stub shard tagged ``no-transcript``. An unobtainable
    publish date captures at now (no invented dates) tagged ``era-unknown``.

Environment (env -> default, every fallback logged via --print-config):
  NOUGEN_TUBE_MAX_SHARD_CHARS   max content chars per shard   (default 30000)
  NOUGEN_TUBE_SPLIT_OVERLAP     split overlap chars           (default 2000)
  NOUGEN_TUBE_EXTRACT_CHARS     first-pass extract size       (default 2000)
  NOUGEN_TUBE_EVENT_TYPE        shard event type              (default INGEST)
  NOUGEN_TUBE_LANGS             ';'-separated caption langs   (default en;en-US;en-GB)
  NOUGEN_TUBE_STATE             resume state path             (default <manifest>.state.json)
  NGS_NODE_URL / NGS_NODE_TOKEN optional node for the dedupe gate; without
                                them the gate scans the local grid directly.

Deps (optional extra ``[tube]``): youtube-transcript-api, yt-dlp. Both are
lazy-loaded so the missing-deps failure mode is a clear message, not a crash
at import time.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

logging.basicConfig(level=os.environ.get("NOUGEN_TUBE_LOG_LEVEL", "INFO"),
                    format="%(levelname)s %(message)s")
logger = logging.getLogger("nougentube")

_CONFIG_SOURCES: List[Tuple[str, Any, str]] = []


def _env(name: str, default, cast=str):
    """Env-first resolution with the fallback logged, never silent."""
    raw = os.environ.get(name)
    if raw is not None and str(raw).strip() != "":
        try:
            value, source = cast(raw), "env"
        except (TypeError, ValueError):
            logger.warning("%s=%r not a valid %s; using default %r",
                           name, raw, cast.__name__, default)
            value, source = default, "default(bad-env)"
    else:
        value, source = default, "default"
    _CONFIG_SOURCES.append((name, value, source))
    return value


MAX_SHARD_CHARS = _env("NOUGEN_TUBE_MAX_SHARD_CHARS", 30000, int)
SPLIT_OVERLAP = _env("NOUGEN_TUBE_SPLIT_OVERLAP", 2000, int)
EXTRACT_CHARS = _env("NOUGEN_TUBE_EXTRACT_CHARS", 2000, int)
EVENT_TYPE = _env("NOUGEN_TUBE_EVENT_TYPE", "INGEST")
LANGS = [l.strip() for l in
         _env("NOUGEN_TUBE_LANGS", "en;en-US;en-GB").split(";") if l.strip()]

_VIDEO_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|embed/|live/))"
    r"([A-Za-z0-9_-]{11})")


# ---------------------------------------------------------------- URL parsing

def extract_video_id(url: str) -> Optional[str]:
    m = _VIDEO_ID_RE.search(url or "")
    return m.group(1) if m else None


def is_playlist(url: str) -> bool:
    """A URL is a playlist job when it carries a list= and no single video id."""
    return "list=" in (url or "") and extract_video_id(url) is None


def expand_playlist(url: str) -> List[str]:
    """Playlist URL -> ordered list of video URLs (flat extraction, no media)."""
    import yt_dlp  # lazy: optional [tube] extra
    opts = {"extract_flat": "in_playlist", "quiet": True, "no_warnings": True,
            "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = (info or {}).get("entries") or []
    urls = []
    for e in entries:
        vid = e.get("id")
        if vid:
            urls.append(f"https://www.youtube.com/watch?v={vid}")
    return urls


# ------------------------------------------------------------------- fetching

def _fetch_via_transcript_api(video_id: str) -> Optional[str]:
    """Tier 1: youtube-transcript-api. Returns timestamped text or None."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # lazy
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=LANGS)
        lines = []
        for entry in fetched:
            start = getattr(entry, "start", None)
            text = (getattr(entry, "text", "") or "").replace("\n", " ").strip()
            if isinstance(entry, dict):  # older API shape
                start, text = entry.get("start", 0), (entry.get("text") or "").replace("\n", " ").strip()
            if text:
                stamp = f"[{int((start or 0) // 60):02d}:{int((start or 0) % 60):02d}]"
                lines.append(f"{stamp} {text}")
        return "\n\n".join(lines) or None
    except Exception as exc:  # noqa: BLE001 — any tier-1 failure falls to tier 2
        logger.info("tier-1 transcript-api failed for %s: %s", video_id, exc)
        return None


_VTT_TAG_RE = re.compile(r"<[^>]*>")
_VTT_TS_RE = re.compile(r"^(\d+):(\d\d):(\d\d)\.\d+\s+-->")


def _parse_vtt(text: str) -> str:
    """Minimal VTT -> timestamped transcript (no extra dependency)."""
    lines, seen = [], set()
    stamp = "[00:00]"
    for raw in text.splitlines():
        line = raw.strip()
        m = _VTT_TS_RE.match(line)
        if m:
            h, mnt, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            total = h * 3600 + mnt * 60 + s
            stamp = f"[{total // 60:02d}:{total % 60:02d}]"
            continue
        if not line or line in ("WEBVTT",) or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        clean = _VTT_TAG_RE.sub("", line)
        clean = clean.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<").strip()
        if clean and clean not in seen:
            lines.append(f"{stamp} {clean}")
            seen.add(clean)
    return "\n\n".join(lines)


def _fetch_via_ytdlp(url: str) -> Optional[str]:
    """Tier 2: yt-dlp auto/manual subs, parsed from VTT in a temp dir."""
    try:
        import yt_dlp  # lazy
        with tempfile.TemporaryDirectory(prefix="nougentube_") as tmp:
            opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": LANGS,
                "subtitlesformat": "vtt",
                "outtmpl": os.path.join(tmp, "sub"),
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    ydl.download([url])
                except Exception as exc:  # noqa: BLE001
                    logger.info("yt-dlp sub download issue for %s: %s", url, exc)
            for f in sorted(Path(tmp).glob("sub*.vtt")):
                parsed = _parse_vtt(f.read_text(encoding="utf-8", errors="replace"))
                if parsed:
                    return parsed
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("tier-2 yt-dlp failed for %s: %s", url, exc)
        return None


def fetch_transcript(video_id: str, url: str) -> Tuple[Optional[str], Optional[str]]:
    """Tiered fetch: transcript-api first, yt-dlp autosubs second.

    Returns (text, tier_name); (None, None) means both tiers failed and the
    caller should capture a metadata-only stub — never abort the batch.
    """
    text = _fetch_via_transcript_api(video_id)
    if text:
        return text, "youtube-transcript-api"
    text = _fetch_via_ytdlp(url)
    if text:
        return text, "yt-dlp-autosubs"
    return None, None


def fetch_metadata(url: str, video_id: str) -> Dict[str, Any]:
    """Title/channel via oEmbed; publish date, duration, chapters via yt-dlp.

    Every field is best-effort: a missing publish date is reported as None so
    the caller can apply the era-unknown fork instead of inventing a date.
    """
    meta: Dict[str, Any] = {"title": None, "channel": None, "published": None,
                            "duration": None, "chapters": []}
    try:
        q = urllib.parse.urlencode({"url": url, "format": "json"})
        with urllib.request.urlopen(
                f"https://www.youtube.com/oembed?{q}", timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        meta["title"] = data.get("title")
        meta["channel"] = data.get("author_name")
    except Exception as exc:  # noqa: BLE001
        logger.info("oEmbed lookup failed for %s: %s", video_id, exc)
    try:
        import yt_dlp  # lazy
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        upload = info.get("upload_date")  # YYYYMMDD
        if upload and len(str(upload)) == 8:
            u = str(upload)
            meta["published"] = f"{u[:4]}-{u[4:6]}-{u[6:8]}T00:00:00Z"
        meta["duration"] = info.get("duration")
        meta["chapters"] = info.get("chapters") or []
        meta["title"] = meta["title"] or info.get("title")
        meta["channel"] = meta["channel"] or info.get("channel") or info.get("uploader")
    except Exception as exc:  # noqa: BLE001
        logger.info("yt-dlp metadata failed for %s: %s", video_id, exc)
    return meta


# ---------------------------------------------------------------- dedupe gate

def dedupe_check(video_id: str) -> bool:
    """True when the grid already holds this EXACT video id (tag tube:<id>).

    Exact-id keying is deliberate: the ancestor pipeline's semantic gate could
    false-positive on near-miss text and silently block a legitimate ingest.
    Tries the node /search first (when NGS_NODE_URL/NGS_NODE_TOKEN are set),
    falls back to a direct tag scan of the local grid.
    """
    marker = f"tube:{video_id}"
    node = os.environ.get("NGS_NODE_URL")
    token = os.environ.get("NGS_NODE_TOKEN")
    if node and token:
        try:
            req = urllib.request.Request(
                f"{node.rstrip('/')}/search", method="POST",
                data=json.dumps({"query": marker, "limit": 5}).encode())
            req.add_header("Content-Type", "application/json")
            req.add_header("X-NGS-Token", token)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
            hits = data.get("results", data) if isinstance(data, dict) else data
            for hit in hits or []:
                blob = json.dumps(hit) if isinstance(hit, dict) else str(hit)
                if marker in blob:
                    return True
            return False
        except Exception as exc:  # noqa: BLE001
            logger.info("node dedupe probe failed (%s); scanning local grid", exc)
    try:
        import nougen_shards.core as core  # lazy: keeps --help dep-free
        for idx in range(1, core.MAX_DB_COUNT + 1):
            if not core.get_db_path(idx).exists():
                continue
            conn = core.get_connection(idx)
            try:
                row = conn.execute(
                    "SELECT 1 FROM shards WHERE tags LIKE ? LIMIT 1",
                    (f'%"{marker}"%',)).fetchone()
                if row:
                    return True
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("local dedupe scan failed (%s); treating as new", exc)
    return False


# ----------------------------------------------------------------- distilling

def _slug(text: Optional[str]) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "unknown-channel").lower()).strip("-")
    return s or "unknown-channel"


def _fmt_duration(seconds) -> str:
    try:
        s = int(seconds)
        return f"{s // 60}m{s % 60:02d}s"
    except (TypeError, ValueError):
        return "unknown"


def recursive_split(text: str, max_size: int, overlap: int) -> List[str]:
    """Recursive character splitting (the Recursive-512 shape): try paragraph,
    newline, sentence, then space boundaries; keep `overlap` chars of context
    between adjacent chunks so no thought is cut mid-air."""
    if len(text) <= max_size:
        return [text]
    separator = next((s for s in ("\n\n", "\n", ". ", " ") if s in text), "")
    splits = text.split(separator) if separator else list(text)
    chunks: List[str] = []
    current = ""
    for piece in splits:
        if len(current) + len(piece) + len(separator) > max_size:
            if current:
                chunks.append(current.strip())
            tail = current[max(0, len(current) - overlap):]
            current = tail + separator + piece
        else:
            current = current + separator + piece if current else piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _first_pass_extract(meta: Dict[str, Any], transcript: str) -> str:
    """Chapters when the video declares them; else the transcript lead."""
    chapters = meta.get("chapters") or []
    if chapters:
        lines = ["Declared chapters:"]
        for ch in chapters:
            start = ch.get("start_time")
            stamp = (f"[{int(start // 60):02d}:{int(start % 60):02d}] "
                     if isinstance(start, (int, float)) else "")
            lines.append(f"- {stamp}{ch.get('title', '(untitled)')}")
        return "\n".join(lines)
    lead = transcript[:EXTRACT_CHARS]
    return "Transcript lead (no declared chapters):\n" + lead


def _header(meta: Dict[str, Any], url: str, tier: Optional[str]) -> str:
    return "\n".join([
        f"# {meta.get('title') or '(title unknown)'}",
        f"Creator: {meta.get('channel') or '(channel unknown)'}",
        f"URL: {url}",
        f"Published: {meta.get('published') or 'unknown'}",
        f"Duration: {_fmt_duration(meta.get('duration'))}",
        f"Transcript source: {tier or 'none'}",
        "Provenance: third-party content (YouTube captions), verbatim preserved.",
    ])


def distill(meta: Dict[str, Any], url: str, transcript: Optional[str],
            tier: Optional[str]) -> List[Dict[str, str]]:
    """Video -> one or more shard payloads (title + content).

    No LLM in v1: structured header + first-pass extract + full verbatim tail.
    Oversized transcripts split Recursive-512-style into numbered parts; every
    part carries the header so each shard stands alone.
    """
    title = meta.get("title") or f"YouTube video {extract_video_id(url) or url}"
    head = _header(meta, url, tier)
    if not transcript:
        content = head + ("\n\n## First-Pass Extract\n"
                          "No transcript obtainable from any fetch tier; "
                          "metadata-only stub so the id is on record.")
        return [{"title": f"{title} — NouGenTube capture [no-transcript]",
                 "content": content}]
    extract = _first_pass_extract(meta, transcript)
    verbatim_intro = "## Raw Capture (Verbatim)\n"
    single = (head + "\n\n## First-Pass Extract\n" + extract
              + "\n\n" + verbatim_intro + transcript)
    if len(single) <= MAX_SHARD_CHARS:
        return [{"title": f"{title} — NouGenTube capture", "content": single}]
    # Part 1 also carries the extract, so the chunk budget must reserve room
    # for it — otherwise part 1 lands over the cap by exactly the extract size.
    # The extract itself is trimmed so header+extract never eat more than half
    # the cap, and the overlap is clamped to the budget so the cap holds at ANY
    # configured MAX_SHARD_CHARS, not just the default.
    extract = extract[:max(0, MAX_SHARD_CHARS // 2 - len(head))]
    budget = max(MAX_SHARD_CHARS - len(head) - len(verbatim_intro)
                 - len(extract) - 400, MAX_SHARD_CHARS // 4)
    parts = recursive_split(transcript, budget,
                            min(SPLIT_OVERLAP, budget // 4))
    payloads = []
    for i, chunk in enumerate(parts, start=1):
        body = [head, ""]
        if i == 1:
            body += ["## First-Pass Extract", extract, ""]
        body += [f"{verbatim_intro}(part {i}/{len(parts)})", chunk]
        payloads.append({
            "title": f"{title} — NouGenTube capture (part {i}/{len(parts)})",
            "content": "\n".join(body)})
    return payloads


# ------------------------------------------------------------------ capturing

def _local_density(content: str) -> float:
    """core's own gzip fallback computed locally: skips 4 model round-trips
    per shard (same heuristic, same score family; profiled in the arxiv lane)."""
    try:
        raw = content.encode("utf-8")
        ratio = len(zlib.compress(raw)) / max(1, len(raw))
        return float(min(1.0, max(0.1, ratio * 1.5)))
    except Exception:  # noqa: BLE001
        return 0.5


def grid_capture(title: str, content: str, tags: List[str],
                 original_timestamp: Optional[str]) -> bool:
    """Single write chokepoint — the only line in this tool that mutates the
    grid, so dry-run gating and tests both hang off one seam."""
    import nougen_shards.core as core  # lazy
    return core.capture(EVENT_TYPE, title, content, tags=tags,
                        density_score=_local_density(content),
                        original_timestamp=original_timestamp)


def process_video(url: str, dry_run: bool = False,
                  manifest_hint: Optional[Dict[str, Any]] = None) -> str:
    """Full per-video pipeline. Returns a status string:
    captured / captured-stub / skipped-duplicate / skipped-bad-url / failed."""
    video_id = extract_video_id(url)
    if not video_id:
        logger.warning("no video id in %s; skipping", url)
        return "skipped-bad-url"
    if dedupe_check(video_id):
        logger.info("SKIP tube:%s already in the grid (%s)", video_id, url)
        return "skipped-duplicate"

    meta = fetch_metadata(url, video_id)
    for key in ("title", "channel"):  # manifest may pre-supply metadata
        if not meta.get(key) and manifest_hint and manifest_hint.get(key):
            meta[key] = manifest_hint[key]
    transcript, tier = fetch_transcript(video_id, url)

    tags = ["youtube", "nougentube", _slug(meta.get("channel")),
            f"tube:{video_id}", "provenance:third_party"]
    published = meta.get("published")
    if not published:
        tags.append("era-unknown")  # capture at now; never invent a date
    if not transcript:
        tags.append("no-transcript")

    payloads = distill(meta, url, transcript, tier)
    if dry_run:
        for p in payloads:
            logger.info("DRY-RUN would capture: %r (%d chars, ts=%s, tags=%s)",
                        p["title"], len(p["content"]), published or "now", tags)
        return "captured-stub" if not transcript else "captured"

    ok_all = True
    for p in payloads:
        ok = grid_capture(p["title"], p["content"], list(tags), published)
        logger.info("%s %s", "captured:" if ok else "REJECTED:", p["title"])
        ok_all = ok_all and ok
    if not ok_all:
        return "failed"
    return "captured-stub" if not transcript else "captured"


# -------------------------------------------------------------- manifest mode

def _state_path(manifest: Path) -> Path:
    override = os.environ.get("NOUGEN_TUBE_STATE")
    return Path(override) if override else manifest.with_suffix(
        manifest.suffix + ".state.json")


def load_state(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("unreadable state file %s (%s); starting fresh", path, exc)
    return {"done": {}}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run_manifest(manifest_path: Path, dry_run: bool, limit: int) -> Dict[str, int]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = data.get("sources") or []
    state_file = _state_path(manifest_path)
    state = load_state(state_file)
    counts: Dict[str, int] = {}
    processed = 0
    for src in sources:
        if limit and processed >= limit:
            break
        url = src.get("url")
        if not url:
            continue
        jobs = expand_playlist(url) if is_playlist(url) else [url]
        for vurl in jobs:
            if limit and processed >= limit:
                break
            vid = extract_video_id(vurl)
            if vid and vid in state.get("done", {}):
                logger.info("resume-skip %s (already in state)", vid)
                counts["resume-skipped"] = counts.get("resume-skipped", 0) + 1
                continue
            status = process_video(vurl, dry_run=dry_run, manifest_hint=src)
            counts[status] = counts.get(status, 0) + 1
            processed += 1
            if not dry_run and vid and status.startswith(("captured", "skipped-dup")):
                state.setdefault("done", {})[vid] = datetime.now(
                    timezone.utc).isoformat()
                save_state(state_file, state)  # heal-on-crash: save per video
    return counts


# ------------------------------------------------------------------------ CLI

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="nougentube", description=__doc__.splitlines()[0])
    ap.add_argument("source", nargs="?",
                    help="video URL, playlist URL, or path to a manifest .json")
    ap.add_argument("--manifest", help="manifest json path (sources list)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be captured; performs ZERO writes")
    ap.add_argument("--limit", type=int,
                    default=_env("NOUGEN_TUBE_LIMIT", 0, int),
                    help="stop after N videos (0 = no limit)")
    ap.add_argument("--print-config", action="store_true",
                    help="show every resolved value and its source")
    args = ap.parse_args(argv)

    if args.print_config:
        for name, value, source in _CONFIG_SOURCES:
            print(f"{name} = {value!r}  [{source}]")
        return 0
    manifest = args.manifest or (
        args.source if args.source and args.source.lower().endswith(".json")
        else None)
    if manifest:
        counts = run_manifest(Path(manifest), args.dry_run, args.limit)
    elif args.source:
        if is_playlist(args.source):
            counts = {}
            for i, vurl in enumerate(expand_playlist(args.source)):
                if args.limit and i >= args.limit:
                    break
                status = process_video(vurl, dry_run=args.dry_run)
                counts[status] = counts.get(status, 0) + 1
        else:
            counts = {process_video(args.source, dry_run=args.dry_run): 1}
    else:
        ap.error("provide a URL/playlist/manifest.json or --manifest")
        return 2
    mode = "DRY-RUN (zero writes)" if args.dry_run else "execute"
    print(f"nougentube [{mode}]: " + json.dumps(counts))
    return 0 if not counts.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
