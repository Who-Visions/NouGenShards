"""transcribe_media / nougentube / nougen_media_transcribe must never put a raw coroutine on the wire.

Repro ids from the field: s7KhLuc3Mck, 4J0bYyag09Q, 6Te4hpYoJt4. The heavy parts (yt-dlp, Whisper)
are faked; the real @node_mcp.tool() -> _offloaded -> run_in_threadpool path is what is exercised.
"""
import asyncio
import json
import os
import sys
import tempfile
import types

import pytest

pytest.importorskip("gradio")
pytest.importorskip("mcp")

_tmp = tempfile.mkdtemp(prefix="ngs_transcribe_")
os.environ.setdefault("NGS_NODE_TOKEN", "test-token")
os.environ.setdefault("NOUGEN_HOME", _tmp)
os.environ.setdefault("NOUGEN_VAULT_DIR", os.path.join(_tmp, ".vault"))

import app as node  # noqa: E402

IDS = ["s7KhLuc3Mck", "4J0bYyag09Q", "6Te4hpYoJt4"]
TOOLS = [("transcribe_media", "url"), ("transcribe_media", "source"), ("nougentube", "url"), ("nougen_media_transcribe", "url")]


@pytest.fixture
def faked(monkeypatch):
    seen = []

    class Tube:
        @staticmethod
        def extract_video_id(url):
            return url.rsplit("=", 1)[-1]

        @staticmethod
        def is_playlist(url):
            return False

    class YDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            return {"duration": 60}

    class Transcriber:
        def __init__(self, output_dir=None, whisper_model="tiny"):
            pass

        def process_and_shard(self, url, language=None, auto_shard=False):
            seen.append(url)
            return {"title": "T", "text": "hello world", "language": "en", "meta": {"duration": 60}, "sharded": False}

    monkeypatch.setattr(node, "_load_nougentube", lambda: Tube)
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL))
    import nougen_shards.transcriber as transcriber
    monkeypatch.setattr(transcriber, "NouGenTranscriber", Transcriber)
    return seen


def _wire(name, args):
    result = asyncio.run(node.node_mcp.call_tool(name, args))
    return result, "".join(getattr(c, "text", "") for c in result.content)


@pytest.mark.parametrize("vid", IDS)
@pytest.mark.parametrize("name,field", TOOLS)
def test_registered_path_returns_a_transcript_not_a_coroutine(faked, name, field, vid):
    url = f"https://www.youtube.com/watch?v={vid}"
    result, text = _wire(name, {field: url})
    assert "<coroutine object" not in text and "coroutine" not in text.lower()
    assert not result.is_error
    body = json.loads(text)
    assert body["transcript"] == "hello world" and body["source"] == url
    assert faked[-1] == url, "implementation must be reached with the requested URL"


def test_direct_fn_path_stays_synchronous(faked):
    import inspect
    out = node.transcribe_media.fn(url=f"https://youtu.be/{IDS[0]}")
    assert not inspect.iscoroutine(out) and out["transcript"] == "hello world"


def test_validation_failure_surfaces_as_a_tool_error_not_a_leak(faked):
    with pytest.raises(Exception) as caught:
        _wire("transcribe_media", {"url": "https://example.com/not-youtube"})
    assert "coroutine" not in str(caught.value).lower()
    assert not faked, "implementation must not be reached for a rejected URL"
