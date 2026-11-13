"""The opt-in Go vector lane: _vector_retrieve uses the front's scores for the
DBs it answers and never builds the in-process vector cache for them."""
import json
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import nougen_shards.core as core  # noqa: E402
from nougen_shards import history  # noqa: E402

DIM = 4


@pytest.fixture
def vault(monkeypatch, tmp_path):
    path = tmp_path / "nougen_shards_1.db"
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT, title TEXT, content TEXT,
        utility_score REAL, embedding BLOB, tags TEXT, domain_key TEXT, event_type TEXT)""")
    for sid in (1, 2, 3):
        vec = np.zeros(DIM, dtype=np.float32)
        vec[0] = sid / 10
        conn.execute("INSERT INTO shards VALUES (?, '2026-01-01T00:00:00Z', ?, 'body', 1.0, ?, '', 'global', 'KNOWLEDGE')",
                     (sid, f"shard {sid}", vec.tobytes()))
    conn.commit()
    monkeypatch.setattr(core, "_VECTOR_CACHE", {})
    monkeypatch.setattr(core, "_VECTOR_DB_LOCKS", {})
    monkeypatch.setattr(core, "get_db_path", lambda i=1: path if i == 1 else tmp_path / f"absent_{i}.db")
    monkeypatch.setattr(core, "get_readonly_connection", lambda i: conn)
    monkeypatch.setattr(history, "log_events", lambda *a, **k: None)
    monkeypatch.setenv("NOUGEN_VECTOR_SIDECAR", "0")
    yield path
    conn.close()


def _q():
    return [1.0, 0.0, 0.0, 0.0]


def test_off_by_default(monkeypatch, vault):
    monkeypatch.delenv("NOUGEN_VECTOR_GO", raising=False)
    monkeypatch.setenv("NGS_GO_FRONT_URL", "http://127.0.0.1:1")
    assert core._go_vector_lane_url() is None
    assert [r["id"] for r in core._vector_retrieve(_q(), limit=2, domain_key="*")] == [3, 2]


def test_front_scores_are_used_and_no_cache_is_built(monkeypatch, vault):
    monkeypatch.setattr(core, "_go_vector_rows", lambda *a, **k: ({1: str(vault)}, {1: [(0.9, 1), (0.5, 3)]}))
    monkeypatch.setattr(core, "_vector_cache_entry",
                        lambda *a, **k: pytest.fail("the in-process cache must not be built for a delegated DB"))
    got = core._vector_retrieve(_q(), limit=5, domain_key="*")
    assert [(r["id"], r["final_score"]) for r in got] == [(1, 0.9), (3, 0.5)]
    assert got[0]["title"] == "shard 1" and got[0]["_db_index"] == 1


def test_another_vaults_answer_is_not_used(monkeypatch, vault):
    """Same DB index, different file (a tenant vault): score in-process."""
    monkeypatch.setattr(core, "_go_vector_rows", lambda *a, **k: ({1: "/some/other/vault/nougen_shards_1.db"}, {1: [(0.9, 1)]}))
    assert [r["id"] for r in core._vector_retrieve(_q(), limit=2, domain_key="*")] == [3, 2]


def test_a_db_the_front_hands_back_is_scored_here(monkeypatch, vault):
    monkeypatch.setattr(core, "_go_vector_rows", lambda *a, **k: ({}, {}))
    assert [r["id"] for r in core._vector_retrieve(_q(), limit=2, domain_key="*")] == [3, 2]


class _Front(BaseHTTPRequestHandler):
    reply: dict = {}
    seen: dict = {}

    def do_POST(self):  # noqa: N802
        _Front.seen = {"path": self.path, "token": self.headers.get("X-NGS-Token"),
                       "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))}
        raw = json.dumps(_Front.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


def test_wire_format(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Front)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("NOUGEN_VECTOR_GO", "1")
        monkeypatch.setenv("NGS_GO_FRONT_URL", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("NGS_NODE_TOKEN", "t0k")
        _Front.reply = {"rows": [{"db": 2, "id": 7, "final_score": 0.25}, {"db": 2, "id": 9, "final_score": 0.2}],
                        "dbs": [2], "fallback": [3], "skipped_dim_mismatch": [4],
                        "paths": {"2": "/v/db2", "3": "/v/db3", "4": "/v/db4"}}
        paths, rows = core._go_vector_rows(np.array([1, 0], dtype=np.float32), 5, None, frozenset({"B", "A"}))
        assert paths == {2: "/v/db2", 4: "/v/db4"}  # answered: scored and dim-skipped; never the handed-back DB
        assert rows == {2: [(0.25, 7), (0.2, 9)]}
        assert _Front.seen["path"] == "/v1/vector/retrieve" and _Front.seen["token"] == "t0k"
        assert _Front.seen["body"] == {"embedding": [1.0, 0.0], "limit": 5, "domain_key": "*", "excluded_types": ["A", "B"]}
    finally:
        server.shutdown()


def test_front_down_falls_back(monkeypatch, vault):
    monkeypatch.setenv("NOUGEN_VECTOR_GO", "1")
    monkeypatch.setenv("NGS_GO_FRONT_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(core, "_GO_LANE_WARNED", False)
    assert core._go_vector_rows(np.array([1, 0], dtype=np.float32), 5, "*", frozenset()) is None
    assert [r["id"] for r in core._vector_retrieve(_q(), limit=2, domain_key="*")] == [3, 2]
