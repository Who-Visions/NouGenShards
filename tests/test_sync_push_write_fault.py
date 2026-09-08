"""A write FAULT on the writer must reach the caller as that fault.

2026-09-08: blade's grid was lock-contended ("database is locked" across the
node log). capture() answered captured=False reason="error"; /sync/push
tallied that under skipped_malformed; snapshot_mode.forward_capture turned
the counter into "forward target REJECTED the row (missing title or content
on arrival)". Three lanes concluded their payloads were broken and re-sent
them. The payloads were fine; the writer was locked and the error was
relabeled twice on the way back.
"""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nougen_shards import core, snapshot_mode  # noqa: E402


def _fault():
    return core.CaptureResult(captured=False, reason="error",
                              error="database is locked")


def test_sync_push_reports_write_fault_as_errored_not_malformed(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("gradio")
    import app as node  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(node.core, "capture", lambda *a, **k: _fault())
    req = SimpleNamespace(shards=[{"title": "fine title", "content": "fine body"}])
    answer = node.sync_push(req, _tenant=None)

    assert answer["skipped_malformed"] == 0
    assert answer["errored"] == 1
    assert "database is locked" in answer["errors"][0]["error"]
    assert answer["results"][0]["reason"] == "error"
    assert "database is locked" in answer["results"][0]["error"]


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_forward_capture_surfaces_writer_fault(monkeypatch):
    monkeypatch.setenv("NOUGEN_CAPTURE_FORWARD_URL", "http://writer.test")
    wire = {"status": "ok", "count": 0, "skipped": 0, "skipped_duplicate": 0,
            "skipped_malformed": 0, "errored": 1,
            "errors": [{"title": "fine title", "error": "database is locked"}],
            "results": [{"reason": "error", "durable": False,
                         "error": "database is locked"}]}
    monkeypatch.setattr(snapshot_mode.urllib.request, "urlopen",
                        lambda req, timeout=None: _Resp(json.dumps(wire).encode()))

    out = snapshot_mode.forward_capture({"title": "fine title", "content": "fine body"})

    assert out["captured"] is False
    assert out["reason"] == "error"
    assert "database is locked" in out["error"]
    assert "missing title" not in out["error"]
