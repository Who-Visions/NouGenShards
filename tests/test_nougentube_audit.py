"""Regression tests for the 2026-11-02 NouGenTube audit, run on both copies."""
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

VID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={VID}"


@pytest.fixture(params=["nougentube", "nougen_shards.tube"])
def tube(request):
    return importlib.import_module(request.param)


def _pipeline(tube, monkeypatch, parts=3):
    monkeypatch.setattr(tube, "dedupe_check", lambda v: False)
    monkeypatch.setattr(tube, "fetch_metadata", lambda u, v: {
        "title": "T", "channel": "C", "published": "2024-05-01T00:00:00Z",
        "duration": 1, "chapters": []})
    monkeypatch.setattr(tube, "fetch_transcript", lambda v, u: ("x", "test"))
    monkeypatch.setattr(tube, "distill", lambda m, u, t, r: [
        {"title": f"p{i}", "content": f"c{i}"} for i in range(1, parts + 1)])


def test_vtt_keeps_repeats_spoken_later_but_collapses_rolling_cues(tube):
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Right.

00:00:02.000 --> 00:00:03.000
Right.
Next line

00:00:03.000 --> 00:00:04.000
Next line
Third line

00:00:10.000 --> 00:00:11.000
Something else

00:00:20.000 --> 00:00:21.000
Right.
"""
    spoken = [line.split("] ", 1)[1] for line in tube._parse_vtt(vtt).split("\n\n")]
    assert spoken == ["Right.", "Next line", "Third line", "Something else", "Right."]


def test_vtt_collapses_two_line_cue_repeated_whole(tube):
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Alpha
Beta

00:00:02.000 --> 00:00:03.000
Alpha
Beta
"""
    assert tube._parse_vtt(vtt).count("Alpha") == 1


@pytest.mark.parametrize("text", [
    "intro\n\n" + "word " * 20000,
    "intro\n\n" + "x" * 50000,
    "a. " * 30000,
], ids=["space-wall", "unbroken", "sentences"])
def test_split_never_exceeds_cap(tube, text):
    chunks = tube.recursive_split(text, 3000, 200)
    assert len(chunks) > 1
    assert max(len(c) for c in chunks) <= 3000


def test_split_loses_no_words(tube):
    words = [f"w{i}" for i in range(5000)]
    joined = "intro\n\n" + " ".join(words)
    found = set(" ".join(tube.recursive_split(joined, 1000, 100)).split())
    assert set(words) <= found


def test_ytdlp_prefers_language_order_over_filename_order(tube, monkeypatch):
    order = ["en-US", "en"]
    monkeypatch.setattr(tube, "LANGS", order)

    class FakeDL:
        def __init__(self, opts):
            self.tmpl = opts["outtmpl"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def download(self, urls):
            for lang in ("en", "en-US"):
                Path(f"{self.tmpl}.{lang}.vtt").write_text(
                    f"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nfrom {lang}\n", encoding="utf-8")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeDL))
    assert "from en-US" in tube._fetch_via_ytdlp(URL)


def test_expand_playlist_drops_nested_playlist_ids(tube, monkeypatch):
    class FakeDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            return {"entries": [{"id": VID}, {"id": "UUabcdefghijklmnopqrstuv"}, None]}

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeDL))
    assert tube.expand_playlist("https://www.youtube.com/@x/videos?list=UU") == [URL]


def test_partial_capture_leaves_no_dedupe_marker_then_resumes(tube, monkeypatch):
    _pipeline(tube, monkeypatch)
    calls = []

    def fails_on_part_two(title, content, tags, ts):
        calls.append(tags)
        return len(calls) != 2

    monkeypatch.setattr(tube, "grid_capture", fails_on_part_two)
    assert tube.process_video(URL) == "failed"
    assert len(calls) == 2
    assert not any(f"tube:{VID}" in tags for tags in calls)

    calls.clear()
    monkeypatch.setattr(tube, "grid_capture",
                        lambda t, c, tags, ts: calls.append(tags) or True)
    assert tube.process_video(URL) == "captured"
    assert f"tube:{VID}" in calls[-1]
    assert [f"tube:{VID}" in tags for tags in calls] == [False, False, True]


def test_grid_capture_still_reports_rejection(tube, monkeypatch):
    import nougen_shards.core as core

    monkeypatch.setattr(core, "capture", lambda *a, **k: False)
    assert tube.grid_capture("t", "c", [], None) is False


def test_save_state_failure_keeps_old_file(tube, tmp_path, monkeypatch):
    path = tmp_path / "m.state.json"
    tube.save_state(path, {"done": {"a": "1"}})

    def boom(src, dst):
        raise OSError("killed")

    monkeypatch.setattr(tube.os, "replace", boom)
    with pytest.raises(OSError):
        tube.save_state(path, {"done": {"b": "2"}})
    assert json.loads(path.read_text(encoding="utf-8")) == {"done": {"a": "1"}}
