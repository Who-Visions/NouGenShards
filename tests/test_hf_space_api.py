import importlib.util
import threading
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "hf_space" / "app.py"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WAL_DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setenv("WAL_MIRROR_PATH", str(tmp_path / "wal.jsonl"))
    monkeypatch.setenv("WAL_BEARER_TOKEN", "t0ken")
    spec = importlib.util.spec_from_file_location("hf_space_app_t", APP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hf_space_app_t"] = mod
    spec.loader.exec_module(mod)
    return TestClient(mod.app)


H = {"Authorization": "Bearer t0ken"}


def test_capture_requires_bearer(client):
    r = client.post("/v1/shards/capture", json={"title": "a", "content": "x"})
    assert r.status_code == 401


def test_no_token_configured_fails_closed(client, monkeypatch):
    monkeypatch.setenv("WAL_BEARER_TOKEN", "")
    import hf_space_app_t as mod
    mod.TOKEN = ""
    r = client.post("/v1/shards/capture", json={"title": "a", "content": "x"}, headers=H)
    assert r.status_code == 503


def test_capture_returns_stored_true_via_buffer(client):
    r = client.post("/v1/shards/capture", json={"title": "a", "content": "hello"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["stored"] is True and body["via"] == "hf-cloud-buffer"


def test_pending_ack_drain_roundtrip(client):
    client.post("/v1/shards/capture", json={"title": "a", "content": "one"}, headers=H)
    p = client.get("/v1/shards/pending", params={"node": "blade"}, headers=H).json()
    assert len(p["shards"]) == 1
    shas = [s["content_sha256"] for s in p["shards"]]
    a = client.post("/v1/shards/ack", json={"node": "blade", "shas": shas}, headers=H).json()
    assert a["newly_acked"] == 1
    assert client.get("/v1/shards/pending", params={"node": "blade"}, headers=H).json()["shards"] == []


def test_empty_content_is_400(client):
    r = client.post("/v1/shards/capture", json={"title": "a", "content": "  "}, headers=H)
    assert r.status_code == 400


def test_fanout_runs_in_background_and_acks_on_success(client, monkeypatch, tmp_path):
    import hf_space_app_t as mod
    done = threading.Event()
    sent = []

    def fake_post(url, record):
        sent.append((url, record["content_sha256"]))
        done.set()
        return True

    monkeypatch.setattr(mod, "NODE_URLS", {"blade": "https://blade.example/ingest"})
    monkeypatch.setattr(mod, "_post_to_node", fake_post)
    r = client.post("/v1/shards/capture", json={"title": "fan", "content": "fanout body"}, headers=H)
    assert r.status_code == 200
    assert done.wait(5)
    assert sent and sent[0][0] == "https://blade.example/ingest"
    # the blade ack is recorded, so blade has nothing pending
    import time
    for _ in range(50):
        if mod.buffer().pending_for("blade") == []:
            break
        time.sleep(0.05)
    assert mod.buffer().pending_for("blade") == []
