"""NouGenTube pipeline contracts (network-free — every fetch layer is mocked).

The load-bearing regressions, each traceable to a recorded defect in the
ancestor pipeline this tool recomposes:
  * --dry-run performs ZERO writes (the ancestor accepted dry_run and ignored
    it — a "dry run" that wrote for real).
  * The dedupe gate keys on the EXACT video id and short-circuits BEFORE any
    fetch (the ancestor's semantic gate could false-positive and block).
  * capture(original_timestamp=publish date) lands the video's TRUE era in the
    timestamp column, not ingestion time.
  * Oversized transcripts split into numbered parts sharing the tube:<id> tag.
"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as core

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "nougentube.py"
_spec = importlib.util.spec_from_file_location("nougentube", _TOOL)
tube = importlib.util.module_from_spec(_spec)
sys.modules["nougentube"] = tube
_spec.loader.exec_module(tube)

VID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={VID}"


@pytest.fixture(autouse=True)
def temp_vault(monkeypatch):
    """Isolated grid; embedding and node lookups disabled for hermetic runs."""
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(core, "GLOBAL_DIR", Path(td))
        monkeypatch.setattr(core, "_INITIALIZED_DBS", set())
        monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
        monkeypatch.delenv("NGS_NODE_URL", raising=False)
        monkeypatch.delenv("NGS_NODE_TOKEN", raising=False)
        yield Path(td)


def _meta(published="2024-05-01T00:00:00Z"):
    return {"title": "Test Video", "channel": "Test Channel",
            "published": published, "duration": 61, "chapters": []}


def _mock_pipeline(monkeypatch, transcript="[00:00] hello world transcript",
                   published="2024-05-01T00:00:00Z"):
    monkeypatch.setattr(tube, "fetch_metadata", lambda u, v: _meta(published))
    monkeypatch.setattr(tube, "fetch_transcript",
                        lambda v, u: (transcript, "mock-tier") if transcript
                        else (None, None))


def _all_rows():
    rows = []
    for idx in range(1, core.MAX_DB_COUNT + 1):
        path = core.get_db_path(idx)
        if not path.exists():
            continue
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            rows += conn.execute(
                "SELECT timestamp, title, content, tags FROM shards").fetchall()
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
    return rows


# ---------------------------------------------------------------- video ids

def test_video_id_extraction_across_url_shapes():
    for url in (URL,
                f"https://youtu.be/{VID}",
                f"https://www.youtube.com/shorts/{VID}",
                f"https://www.youtube.com/embed/{VID}",
                f"https://www.youtube.com/watch?feature=share&v={VID}"):
        assert tube.extract_video_id(url) == VID, url
    assert tube.extract_video_id("https://example.com/nope") is None
    assert tube.is_playlist("https://www.youtube.com/playlist?list=PLx")
    assert not tube.is_playlist(URL + "&list=PLx")  # video wins over list


# --------------------------------------------------------------- dedupe gate

def test_dedupe_gate_short_circuits_before_any_fetch(monkeypatch):
    monkeypatch.setattr(tube, "dedupe_check", lambda vid: True)

    def _boom(*a, **k):
        raise AssertionError("fetch ran despite dedupe hit")
    monkeypatch.setattr(tube, "fetch_metadata", _boom)
    monkeypatch.setattr(tube, "fetch_transcript", _boom)
    monkeypatch.setattr(tube, "grid_capture", _boom)
    assert tube.process_video(URL) == "skipped-duplicate"


def test_dedupe_gate_is_exact_id_via_local_tag_scan(monkeypatch):
    _mock_pipeline(monkeypatch)
    assert tube.process_video(URL) == "captured"
    assert tube.dedupe_check(VID) is True          # exact id -> hit
    assert tube.dedupe_check("AAAAAAAAAAA") is False  # different id -> miss


# ------------------------------------------------------------------ dry run

def test_dry_run_performs_zero_writes(monkeypatch, temp_vault):
    """The ancestor's recorded defect: dry_run accepted, never used."""
    _mock_pipeline(monkeypatch)

    def _forbidden(*a, **k):
        raise AssertionError("grid_capture ran under --dry-run")
    monkeypatch.setattr(tube, "grid_capture", _forbidden)
    assert tube.process_video(URL, dry_run=True) == "captured"
    assert _all_rows() == []  # no shard DB rows materialized


def test_dry_run_manifest_writes_no_state_file(monkeypatch, tmp_path):
    _mock_pipeline(monkeypatch)
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"sources": [{"url": URL}]}), encoding="utf-8")
    counts = tube.run_manifest(manifest, dry_run=True, limit=0)
    assert counts.get("captured") == 1
    leftovers = [p for p in tmp_path.iterdir() if p != manifest]
    assert leftovers == []  # no state file, no anything


# ------------------------------------------------------------------- the era

def test_publish_date_lands_in_timestamp_column(monkeypatch):
    _mock_pipeline(monkeypatch, published="2023-11-20T00:00:00Z")
    assert tube.process_video(URL) == "captured"
    rows = _all_rows()
    assert len(rows) == 1
    assert rows[0]["timestamp"].startswith("2023-11-20")
    assert f"tube:{VID}" in json.loads(rows[0]["tags"])


def test_missing_publish_date_captures_at_now_tagged_era_unknown(monkeypatch):
    _mock_pipeline(monkeypatch, published=None)
    assert tube.process_video(URL) == "captured"
    rows = _all_rows()
    assert len(rows) == 1
    tags = json.loads(rows[0]["tags"])
    assert "era-unknown" in tags
    assert not rows[0]["timestamp"].startswith("20 ")  # sanity: real ISO stamp
    assert rows[0]["timestamp"] > "2026-01-01"  # now, never an invented date


# ----------------------------------------------------------------- splitting

def test_oversized_transcript_splits_into_linked_parts(monkeypatch):
    monkeypatch.setattr(tube, "MAX_SHARD_CHARS", 3000)
    long_transcript = "\n\n".join(
        f"[{i:02d}:00] sentence number {i} with unique filler content"
        for i in range(200))
    _mock_pipeline(monkeypatch, transcript=long_transcript)
    captured = []
    monkeypatch.setattr(
        tube, "grid_capture",
        lambda title, content, tags, ts: captured.append(
            {"title": title, "content": content, "tags": tags, "ts": ts}) or True)
    assert tube.process_video(URL) == "captured"
    assert len(captured) > 1
    for i, p in enumerate(captured, start=1):
        assert f"(part {i}/{len(captured)})" in p["title"]
        assert len(p["content"]) <= 3000  # every part respects the cap
        assert f"tube:{VID}" in p["tags"]           # shared linking tag
        assert p["ts"] == "2024-05-01T00:00:00Z"    # every part keeps the era
        assert "Raw Capture (Verbatim)" in p["content"]
    assert "First-Pass Extract" in captured[0]["content"]


def test_single_shard_preserves_verbatim_tail(monkeypatch):
    _mock_pipeline(monkeypatch)
    assert tube.process_video(URL) == "captured"
    rows = _all_rows()
    assert len(rows) == 1
    assert "Raw Capture (Verbatim)" in rows[0]["content"]
    assert "[00:00] hello world transcript" in rows[0]["content"]
    tags = json.loads(rows[0]["tags"])
    assert {"youtube", "nougentube", "test-channel",
            "provenance:third_party"} <= set(tags)


# ------------------------------------------------------- no-transcript fork

def test_both_tiers_failing_yields_stub_not_abort(monkeypatch):
    _mock_pipeline(monkeypatch, transcript=None)
    assert tube.process_video(URL) == "captured-stub"
    rows = _all_rows()
    assert len(rows) == 1
    assert "no-transcript" in json.loads(rows[0]["tags"])
    assert "[no-transcript]" in rows[0]["title"]


# ------------------------------------------------------------ manifest mode

def test_manifest_resume_state_heals_and_advances(monkeypatch, tmp_path):
    _mock_pipeline(monkeypatch)
    vid2 = "abcdefghijk"
    url2 = f"https://www.youtube.com/watch?v={vid2}"
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps(
        {"sources": [{"url": URL}, {"url": url2}]}), encoding="utf-8")
    state_file = tmp_path / "sources.json.state.json"
    state_file.write_text(json.dumps(
        {"done": {VID: "2026-08-01T00:00:00Z"}}), encoding="utf-8")

    processed = []
    monkeypatch.setattr(
        tube, "process_video",
        lambda url, dry_run=False, manifest_hint=None:
            processed.append(url) or "captured")
    counts = tube.run_manifest(manifest, dry_run=False, limit=0)
    assert processed == [url2]                      # first entry resume-skipped
    assert counts == {"resume-skipped": 1, "captured": 1}
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert set(state["done"]) == {VID, vid2}        # state advanced


def test_vtt_parser_strips_tags_and_dedupes():
    vtt = ("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n"
           "<c>hello</c> there\n\n00:00:04.000 --> 00:00:06.000\n"
           "hello there\n\n00:01:05.000 --> 00:01:07.000\ngeneral &amp; kenobi\n")
    out = tube._parse_vtt(vtt)
    assert out.count("hello there") == 1            # rolling-caption dedupe
    assert "[01:05] general & kenobi" in out
    assert "<c>" not in out
