"""WebVTT caption parsing with rolling-caption dedupe, for shard capture.

Why this is in the tree
-----------------------
Captured video transcripts were entering the vault through a naive VTT parse.
YouTube's auto-captions ROLL: each cue repeats most of the previous cue and
adds a few words, so a straight parse stores the same sentence four or five
times. Measured on a 15.3-minute video, 2026-09-08:

    cues parsed          826
    cues after dedupe    207
    naive characters  47,216
    deduped chars     15,755      -> 66.6% of the text was duplication

Two thirds of every naively captured transcript was duplicate text. That is
vault bloat, and worse, it is recall dilution: a repeated phrase outranks a
phrase said once, so the parts of a talk that were emphasised by repetition in
the *captions* beat the parts that were actually distinctive.

Attribution
-----------
``parse_vtt`` and ``dedupe_cues`` are ported from ``devinilabs/claude-watch``
(MIT, Copyright (c) 2026 claude-watch contributors), file
``scripts/transcribe.py``. The four-pattern rolling-overlap analysis is theirs
and is the load-bearing idea here; the port keeps their structure so upstream
fixes remain easy to follow. Adopted under the fleet's SHANG TSUNG rule — take
the peer's instrument, run it on your own artifact, and publish what you find
in it. What we found is recorded in ``tests/test_transcript.py``.

This module deliberately has **no network dependency**. Fetching the VTT is the
caller's problem (``yt-dlp`` covers it, and a captions-only path needs neither
``ffmpeg`` nor any paid transcription API — phoebus has no ffmpeg and captures
transcripts fine). Keeping the fetch out means the parsing is testable offline
and the module cannot become a reason the vault needs a network stack.
"""

from __future__ import annotations

import re

__all__ = ["parse_vtt", "dedupe_cues", "transcript_text", "duplication_ratio"]

_TS_RX = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?\s*-->\s*"
    r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"
)

# Characters of suffix/prefix overlap below which two cues are treated as
# unrelated rather than as one rolling caption. Ten is upstream's value; it is
# long enough that ordinary repeated words ("and then the", "you know") do not
# trigger a merge and short enough to catch a genuine rolling window.
_ROLLING_OVERLAP_MIN = 10


def _ts_to_s(h: str | None, m: str, s: str, ms: str | None) -> float:
    return ((int(h) if h else 0) * 3600 + int(m) * 60 + int(s)
            + (int(ms) / 1000.0 if ms else 0.0))


def parse_vtt(text: str) -> list[dict]:
    """Parse WebVTT into ``{t_start, t_end, text}`` cues.

    Inline formatting tags (``<c.colorE5E5E5>`` and friends, which YouTube
    emits heavily) are stripped, because they are styling and they wreck any
    text comparison the dedupe below tries to make.
    """
    cues: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _TS_RX.search(lines[i])
        if not match:
            i += 1
            continue
        t_start = _ts_to_s(*match.group(1, 2, 3, 4))
        t_end = _ts_to_s(*match.group(5, 6, 7, 8))
        i += 1
        body: list[str] = []
        while i < len(lines) and lines[i].strip():
            body.append(re.sub(r"<[^>]+>", "", lines[i]).strip())
            i += 1
        joined = " ".join(part for part in body if part).strip()
        if joined:
            cues.append({"t_start": t_start, "t_end": t_end, "text": joined})
    return cues


def dedupe_cues(cues: list[dict]) -> list[dict]:
    """Collapse rolling and duplicate cues.

    Four patterns, in order. They are not interchangeable: 2 must precede 3, or
    a rolling extension gets read as a contained tail and the new words are
    thrown away instead of kept.

    1. Identical text -> extend the previous cue's end time.
    2. This cue starts with the previous one and is longer (a rolling
       extension) -> replace the previous text with this longer one.
    3. The previous cue already ends with this one (a tail already shown) ->
       extend the end time and drop this cue.
    4. A suffix of the previous cue matches a prefix of this one by at least
       ``_ROLLING_OVERLAP_MIN`` characters -> keep only the new tail.

    Anything else is a genuinely new cue and both are kept.
    """
    out: list[dict] = []
    for cue in cues:
        if not out:
            out.append(dict(cue))
            continue
        prev = out[-1]

        if prev["text"] == cue["text"]:
            prev["t_end"] = max(prev["t_end"], cue["t_end"])
            continue

        if len(cue["text"]) > len(prev["text"]) and cue["text"].startswith(prev["text"]):
            prev["t_end"] = cue["t_end"]
            prev["text"] = cue["text"]
            continue

        if prev["text"].endswith(cue["text"]):
            prev["t_end"] = max(prev["t_end"], cue["t_end"])
            continue

        overlap = 0
        for size in range(min(len(prev["text"]), len(cue["text"])),
                          _ROLLING_OVERLAP_MIN - 1, -1):
            if prev["text"][-size:] == cue["text"][:size]:
                overlap = size
                break
        if overlap:
            tail = cue["text"][overlap:].lstrip()
            if tail:
                out.append({"t_start": cue["t_start"], "t_end": cue["t_end"],
                            "text": tail})
            else:
                prev["t_end"] = max(prev["t_end"], cue["t_end"])
            continue

        out.append(dict(cue))
    return out


def transcript_text(vtt: str) -> str:
    """VTT in, deduplicated prose out. The one call most captures want."""
    return " ".join(cue["text"] for cue in dedupe_cues(parse_vtt(vtt)))


def duplication_ratio(vtt: str) -> float:
    """Fraction of the naive parse that was duplication, in ``[0, 1]``.

    Worth recording alongside a captured transcript. A ratio near zero means
    the source had real subtitles; a ratio near two thirds means auto-captions,
    and that the naive text you might have stored instead was mostly repeats.
    """
    cues = parse_vtt(vtt)
    naive = len(" ".join(cue["text"] for cue in cues))
    if not naive:
        return 0.0
    clean = len(" ".join(cue["text"] for cue in dedupe_cues(cues)))
    return 1.0 - (clean / naive)
