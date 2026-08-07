"""NouGenTube pick — drain the targeted video queue (transcripts/pending_videos.txt), drip-capped.

Queue format: one video per line, `<video_id>\t<title>\t<note>` (tab-separated; only the id is
required). Lines starting with `#` are comments or processed entries (`#done`, `#skip-*`).
Runs BEFORE the channel drip in the daily task so GM-priority videos drain first.
Same safety envelope as nougentube.py: FETCH_SLEEP pacing, miss breaker -> exit 3.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "tools"))
import nougentube  # noqa: E402

DEFAULT_QUEUE = Path(os.environ.get("NOUGEN_YT_QUEUE",
                                    str(_REPO_ROOT / "transcripts" / "pending_videos.txt")))


def video_metadata(video_id: str) -> dict:
    out = nougentube._run_ytdlp(["--dump-single-json", "--no-warnings", "--skip-download",
                                 f"https://www.youtube.com/watch?v={video_id}"], timeout=120)
    info = json.loads(out)
    return {
        "id": video_id,
        "title": info.get("title") or video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "upload_date": info.get("upload_date"),
        "channel_name": info.get("channel") or info.get("uploader") or "Unknown",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--out", type=Path, default=nougentube.DEFAULT_OUT)
    parser.add_argument("--max-new", type=int, default=int(os.environ.get("NOUGEN_YT_MAX_NEW", "0")))
    parser.add_argument("--confirm", action="store_true", help="Actually write shards to the vault.")
    args = parser.parse_args()

    if not args.queue.exists():
        print(f"no queue at {args.queue} — nothing to do")
        print("NEW_FETCHES: 0")
        return

    lines = args.queue.read_text(encoding="utf-8").splitlines()
    breaker_limit = int(os.environ.get("NOUGEN_YT_BREAKER", "3"))
    misses = 0
    new_fetches = 0
    circuit_open = False

    for idx, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if args.max_new and new_fetches >= args.max_new:
            break
        if circuit_open:
            break
        video_id = line.split("\t")[0].split()[0].strip()
        print(f"queue: {video_id}")
        try:
            video = video_metadata(video_id)
        except Exception as exc:  # noqa: BLE001 — metadata miss counts toward the breaker too
            print(f"  metadata miss: {str(exc)[:120]}")
            misses += 1
            if misses >= breaker_limit:
                circuit_open = True
            continue
        path = nougentube.markdown_path(args.out, video)
        if path.exists():
            transcript = path.read_text(encoding="utf-8").split("## Transcript", 1)[-1].strip()
            print("  cached")
        else:
            time.sleep(nougentube.FETCH_SLEEP)
            transcript = nougentube.fetch_transcript(video_id)
            if not transcript:
                misses += 1
                lines[idx] = f"#skip-no-transcript {line}"
                if misses >= breaker_limit:
                    circuit_open = True
                    print(f"circuit OPEN after {breaker_limit} misses — stopping queue drain")
                continue
            misses = 0
            new_fetches += 1
            nougentube.write_markdown(path, video["channel_name"], video, transcript)
        if args.confirm:
            ok = nougentube.shard(video["channel_name"], video, transcript,
                                  ["gm-queue", "targeted-drip"])
            print(f"  sharded: {ok}")
        lines[idx] = f"#done {line}"

    args.queue.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"NEW_FETCHES: {new_fetches}")
    if circuit_open:
        sys.exit(3)


if __name__ == "__main__":
    main()
