"""The ``nougentube`` tool is subtitle-first: a 30m01s video with subtitles
(field repro 3uoStyWxO5M, 2026-10-27) must transcribe through the subtitle
path and never hit the Whisper duration cap. Whisper is the fallback only
when no transcript exists, and its cap is NOUGEN_WHISPER_MAX_SECONDS."""
import asyncio
import json
import os
import sys
import tempfile
import types

import pytest

pytest.importorskip("gradio")
pytest.importorskip("mcp")

_tmp = tempfile.mkdtemp(prefix="ngs_tube_first_")
os.environ.setdefault("NGS_NODE_TOKEN", "test-token")
os.environ.setdefault("NOUGEN_HOME", _tmp)
os.environ.setdefault("NOUGEN_VAULT_DIR", os.path.join(_tmp, ".vault"))

import app as node  # noqa: E402

URL = "https://www.youtube.com/watch?v=3uoStyWxO5M"
LONG = 1801


def _fakes(monkeypatch, *, transcript, duration=LONG):
    calls = {"whisper": [], "sharded": []}

    class Tube:
        @staticmethod
        def extract_video_id(url):
            return url.rsplit("=", 1)[-1]

        @staticmethod
        def is_playlist(url):
            return False

        @staticmethod
        def fetch_transcript(video_id, url):
            return transcript, ("youtube-transcript-api" if transcript else None)

        @staticmethod
        def fetch_metadata(url, video_id):
            return {"title": "Long talk", "duration": duration, "channel": "C"}

        @staticmethod
        def process_video(url, dry_run=False, manifest_hint=None):
            calls["sharded"].append((url, dry_run))
            return "captured"

    class YDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            return {"duration": duration}

    class Transcriber:
        def __init__(self, output_dir=None, whisper_model="tiny"):
            pass

        def process_and_shard(self, url, language=None, auto_shard=False):
            calls["whisper"].append(url)
            return {"title": "W", "text": "whisper text", "language": "en",
                    "meta": {"duration": duration}, "sharded": False}

    monkeypatch.setattr(node, "_load_nougentube", lambda: Tube)
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL))
    import nougen_shards.transcriber as transcriber
    monkeypatch.setattr(transcriber, "NouGenTranscriber", Transcriber)
    return calls


def _wire(name, args):
    result = asyncio.run(node.node_mcp.call_tool(name, args))
    return result, "".join(getattr(c, "text", "") for c in result.content)


def test_long_video_with_subtitles_transcribes_without_whisper(monkeypatch):
    calls = _fakes(monkeypatch, transcript="[00:00] subtitles here")
    result, text = _wire("nougentube", {"url": URL})
    assert not result.is_error, text
    body = json.loads(text)
    assert body["transcript"].startswith("[00:00] subtitles")
    assert body["transcript_source"] == "youtube-transcript-api"
    assert body["fallback"] == "none" and body["duration_seconds"] == LONG
    assert calls["whisper"] == [], "subtitle path must not touch Whisper"
    assert body["sharded"] is False and calls["sharded"] == []


def test_auto_shard_captures_through_the_dedup_pipeline(monkeypatch):
    calls = _fakes(monkeypatch, transcript="[00:00] subtitles here")
    result, text = _wire("nougentube", {"url": URL, "auto_shard": True})
    assert not result.is_error, text
    body = json.loads(text)
    assert body["sharded"] is True and body["shard_status"] == "captured"
    assert calls["sharded"] == [(URL, False)]


def test_no_subtitles_falls_back_to_whisper_under_the_cap(monkeypatch):
    monkeypatch.setenv("NOUGEN_WHISPER_MAX_SECONDS", "100")
    calls = _fakes(monkeypatch, transcript="", duration=90)
    result, text = _wire("nougentube", {"url": URL})
    assert not result.is_error, text
    body = json.loads(text)
    assert body["transcript"] == "whisper text" and body["fallback"] == "whisper"
    assert calls["whisper"] == [URL]


def test_no_subtitles_over_the_env_cap_is_refused_with_the_cap_named(monkeypatch):
    monkeypatch.setenv("NOUGEN_WHISPER_MAX_SECONDS", "100")
    calls = _fakes(monkeypatch, transcript="", duration=LONG)
    # The MCP server raises on tool exceptions (the cause carries the message).
    with pytest.raises(Exception) as caught:
        _wire("nougentube", {"url": URL})
    chain = str(caught.value) + " " + str(getattr(caught.value, "__cause__", "") or "")
    assert "100 seconds" in chain and "NOUGEN_WHISPER_MAX_SECONDS" in chain
    assert calls["whisper"] == []


def test_media_transcribe_cap_comes_from_env(monkeypatch):
    monkeypatch.delenv("NOUGEN_WHISPER_MAX_SECONDS", raising=False)
    assert node._whisper_max_seconds() == node._WHISPER_MAX_SECONDS_FALLBACK == 1800
    monkeypatch.setenv("NOUGEN_WHISPER_MAX_SECONDS", "7200")
    assert node._whisper_max_seconds() == 7200
