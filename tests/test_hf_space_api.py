import importlib
import threading
import time

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

H = {"X-NGS-Token": "t0ken"}


@pytest.fixture
def wal(tmp_path, monkeypatch):
    monkeypatch.setenv("WAL_DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setenv("WAL_MIRROR_PATH", str(tmp_path / "wal" / "wal.jsonl"))
    monkeypatch.setenv("WAL_BEARER_TOKEN", "t0ken")
    monkeypatch.delenv("WAL_NODE_URLS", raising=False)
    from nougen_shards import wal_api
    mod = importlib.reload(wal_api)
    app = FastAPI()
    app.include_router(mod.router)
    return mod, TestClient(app)


def test_capture_requires_token(wal):
    _, c = wal
    assert c.post("/v1/shards/capture", json={"title": "a", "content": "x"}).status_code == 401


def test_wal_token_header_also_accepted(wal):
    _, c = wal
    r = c.post("/v1/shards/capture", json={"title": "a", "content": "x"}, headers={"X-WAL-Token": "t0ken"})
    assert r.status_code == 200


def test_no_token_configured_fails_closed(wal):
    mod, c = wal
    mod.TOKEN = ""
    r = c.post("/v1/shards/capture", json={"title": "a", "content": "x"}, headers=H)
    assert r.status_code == 503


def test_capture_returns_stored_true_via_buffer(wal):
    _, c = wal
    body = c.post("/v1/shards/capture", json={"title": "a", "content": "hello"}, headers=H).json()
    assert body["stored"] is True and body["via"] == "hf-cloud-buffer"


def test_pending_ack_drain_roundtrip(wal):
    _, c = wal
    c.post("/v1/shards/capture", json={"title": "a", "content": "one"}, headers=H)
    p = c.get("/v1/shards/pending", params={"node": "blade"}, headers=H).json()
    assert len(p["shards"]) == 1
    shas = [s["content_sha256"] for s in p["shards"]]
    a = c.post("/v1/shards/ack", json={"node": "blade", "shas": shas}, headers=H).json()
    assert a["newly_acked"] == 1
    assert c.get("/v1/shards/pending", params={"node": "blade"}, headers=H).json()["shards"] == []


def test_empty_content_is_400(wal):
    _, c = wal
    assert c.post("/v1/shards/capture", json={"title": "a", "content": "  "}, headers=H).status_code == 400


def test_health_is_open_and_reports_commit_state(wal):
    _, c = wal
    body = c.get("/v1/shards/health").json()
    assert body["ok"] is True and body["dataset_commits"] is False


def test_fanout_runs_in_background_and_acks_on_success(wal, monkeypatch):
    mod, c = wal
    done = threading.Event()
    sent = []

    def fake_post(url, record):
        sent.append((url, record["content_sha256"]))
        done.set()
        return True

    monkeypatch.setattr(mod, "NODE_URLS", {"blade": "https://blade.example/ingest"})
    monkeypatch.setattr(mod, "_post_to_node", fake_post)
    assert c.post("/v1/shards/capture", json={"title": "fan", "content": "fanout body"}, headers=H).status_code == 200
    assert done.wait(5)
    assert sent[0][0] == "https://blade.example/ingest"
    for _ in range(50):
        if mod.buffer().pending_for("blade") == []:
            break
        time.sleep(0.05)
    assert mod.buffer().pending_for("blade") == []


def test_standalone_space_entry_mounts_the_router(wal):
    from hf_space import app as space_app  # noqa: F401
    assert "/v1/shards/capture" in space_app.app.openapi()["paths"]
