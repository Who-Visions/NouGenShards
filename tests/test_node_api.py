"""Functional tests for the Space node's REST API (app.py).

Boots the FastAPI app against a throwaway vault and exercises the full
auth + data surface: deny-by-default, capture->search round trip, JSON-clean
export, dedup-aware bulk ingest. Skipped when the node's web stack (fastapi/
gradio) isn't installed - CI installs the full package so it runs there.
"""
import os
import tempfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")

TEST_TOKEN = "test-node-token"

# app.py reads NGS_NODE_TOKEN and the vault location at import time, so the
# environment must be prepared before the module is first imported.
_tmp = tempfile.mkdtemp(prefix="ngs_node_api_")
os.environ["NGS_NODE_TOKEN"] = TEST_TOKEN
os.environ["NOUGEN_HOME"] = _tmp
os.environ["NOUGEN_VAULT_DIR"] = os.path.join(_tmp, ".vault")

from fastapi.testclient import TestClient  # noqa: E402

import app as node  # noqa: E402
import nougen_shards.core as core  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # Point the substrate at a fresh per-test vault.
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(core, "get_db_path",
                        lambda index: tmp_path / f"node_api_{index}.db")
    monkeypatch.setattr(node, "NODE_TOKEN", TEST_TOKEN)
    core.init_db(1)
    return TestClient(node.app)


AUTH = {"X-NGS-Token": TEST_TOKEN}


def test_health_is_open_and_reports_readiness(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ignited"
    assert body["node_token_configured"] is True
    assert "total_shards" not in body
    assert "substrate" not in body
    assert isinstance(body["warnings"], list)
    # HUD creds aren't set in tests -> not ready for a public flip.
    assert body["hud_auth_configured"] is False
    assert body["public_ready"] is False

    authed = client.get("/health", headers=AUTH).json()
    assert authed["tenant_id"] == "owner"
    assert isinstance(authed["total_shards"], int)
    assert isinstance(authed["substrate"], dict)


def test_data_endpoints_deny_without_token(client):
    assert client.post("/search", json={"query": "x"}).status_code == 401
    assert client.get("/sync/pull").status_code == 401
    assert client.post("/capture", json={"title": "t", "content": "c"}).status_code == 401
    assert client.post("/agent", json={"name": "Rhea", "prompt": "audit"}).status_code == 401
    assert client.post("/search", json={"query": "x"},
                       headers={"X-NGS-Token": "wrong"}).status_code == 401


def test_deny_by_default_when_unconfigured(client, monkeypatch, tmp_path):
    # Isolate the tenant registry: a live ~/.nougen/tenants.json makes
    # credentials count as configured, turning the expected 503 into a 401.
    monkeypatch.setenv("NOUGEN_TENANTS_FILE", str(tmp_path / "tenants.json"))
    monkeypatch.setattr(node, "NODE_TOKEN", None)
    assert client.post("/search", json={"query": "x"}, headers=AUTH).status_code == 503


def test_capture_search_roundtrip(client):
    r = client.post("/capture", json={
        "title": "Cloud automation shard",
        "content": "This shard proves the cloud capture endpoint works end to end.",
    }, headers=AUTH)
    assert r.status_code == 200 and r.json()["captured"] is True

    r = client.post("/search", json={"query": "automation", "limit": 5}, headers=AUTH)
    assert r.status_code == 200
    assert any(h.get("title") == "Cloud automation shard" for h in r.json())


def test_search_degrades_instead_of_500(client, monkeypatch):
    """A crash in the full retrieval stack must not 500 the endpoint - federated
    callers read any non-200 as 'node down' and drop the relay. It must fall back
    to keyword-only, and to [] if that fails too."""
    def boom(*a, **k):
        raise RuntimeError("vector lane exploded")

    # Full retrieve blows up; keyword fallback still answers -> 200, not 500.
    monkeypatch.setattr(core, "retrieve", boom)
    r = client.post("/search", json={"query": "anything", "limit": 3}, headers=AUTH)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # Both lanes blow up -> still 200 with an empty list, never an exception.
    monkeypatch.setattr(core, "_keyword_retrieve", boom)
    r = client.post("/search", json={"query": "anything", "limit": 3}, headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


def test_pull_and_dedup_aware_push(client):
    client.post("/capture", json={"title": "Seed", "content": "Seed content for pull."},
                headers=AUTH)

    r = client.get("/sync/pull", headers=AUTH)
    assert r.status_code == 200
    exported = r.json()
    assert len(exported) == 1  # and JSON-serializable end to end

    # Re-pushing the export dedups; a new shard ingests; junk is skipped.
    shards = exported + [
        {"title": "Second shard", "content": "Bulk pushed shard content.", "tags": '["a","b"]'},
        {"title": "", "content": "missing title -> skipped"},
    ]
    r = client.post("/sync/push", json={"shards": shards}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["count"] == 1
    assert body["skipped"] == 2

    r = client.get("/sync/hashes", headers=AUTH)
    assert r.status_code == 200
    manifest = r.json()
    assert manifest["count"] == 2
    assert len(manifest["hashes"]) == 2


def test_hash_manifest_requires_auth(client):
    assert client.get("/sync/hashes").status_code == 401


def test_sync_push_preserves_private_sensitivity(client, monkeypatch):
    import base64
    monkeypatch.setenv("NOUGEN_PRIVATE_KEY", base64.b64encode(b"X" * 32).decode("ascii"))
    from nougen_shards import private_vault

    captured = {}
    ciphertext = private_vault.encrypt_text("private replicated body")

    def fake_capture(event_type, title, content, **kwargs):
        captured.update(event_type=event_type, title=title, content=content, **kwargs)
        return True

    monkeypatch.setattr(core, "capture", fake_capture)
    r = client.post("/sync/push", json={"shards": [{
        "title": "Private replica",
        "content": ciphertext,
        "sensitivity": "private",
    }]}, headers=AUTH)

    assert r.status_code == 200
    assert captured["content"] == "private replicated body"
    assert captured["sensitivity"] == "private"


# --- era bounds on /search (relay leg 20260817T024250Z) ---------------------
#
# ask_griot gathers by calling this endpoint, so an unbounded /search made
# `since`/`until` decorative: a question bounded to 2025-Q1 came back with
# 2026-08 shards and undated vault rows, held_back=0. These pin every arm.


def _bounded(client, monkeypatch, federated_rows, query="highway", **bounds):
    """Run /search with the federated arm stubbed to a known, out-of-era set."""
    monkeypatch.setattr(node, "federated_retrieve",
                        lambda q, limit=5, **kw: list(federated_rows))
    r = client.post("/search", json={"query": query, "limit": 10, **bounds},
                    headers=AUTH)
    assert r.status_code == 200
    return r


def test_search_drops_out_of_era_federated_rows(client, monkeypatch):
    rows = [
        {"id": 1, "timestamp": "2026-08-17T05:00:00Z", "title": "today"},
        {"id": 2, "timestamp": "2025-02-11T09:00:00Z", "title": "in era"},
    ]
    r = _bounded(client, monkeypatch, rows, since="2025-01", until="2025-03")
    assert [row["title"] for row in r.json()] == ["in era"]
    assert r.headers["X-NouGen-Held-Back"] == "1"


def test_search_holds_back_undated_vault_rows(client, monkeypatch):
    # Vault lanes return rows with no timestamp ("era unknown" in the packet).
    # Undated is not provably in-era, so it must not be shown as evidence.
    rows = [
        {"id": "vault_2_abc", "source": "vault_sol_memory_vault", "title": "undated"},
        {"id": "vault_2_def", "source": "vault_sol_memory_vault",
         "timestamp": "", "title": "empty ts"},
    ]
    r = _bounded(client, monkeypatch, rows, since="2025-01", until="2025-03")
    assert r.json() == []
    assert r.headers["X-NouGen-Held-Back"] == "2"


def test_search_upper_bound_is_inclusive_to_month_end(client, monkeypatch):
    rows = [
        {"id": 1, "timestamp": "2025-03-31T23:59:59Z", "title": "last of march"},
        {"id": 2, "timestamp": "2025-04-01T00:00:00Z", "title": "april"},
    ]
    r = _bounded(client, monkeypatch, rows, since="2025-01", until="2025-03")
    assert [row["title"] for row in r.json()] == ["last of march"]


def test_search_unbounded_is_unchanged(client, monkeypatch):
    # No bounds -> no filtering, no held-back header: the ordinary recall path
    # must keep behaving exactly as it did before era bounds existed.
    rows = [{"id": 1, "timestamp": "2026-08-17T05:00:00Z", "title": "today"},
            {"id": 2, "title": "undated"}]
    r = _bounded(client, monkeypatch, rows)
    assert len(r.json()) == 2
    assert "X-NouGen-Held-Back" not in r.headers


def test_search_bounded_still_returns_sparse_era_shards(client, monkeypatch):
    # The SQL sweep is the reason a quiet era isn't lost to a relevance cut:
    # federated ranking returns nothing usable, the windowed sweep still does.
    captured = core.capture("KNOWLEDGE", "Quiet era shard", "highway work", tags=["t"])
    assert captured
    monkeypatch.setattr(node, "federated_retrieve", lambda q, limit=5, **kw: [])
    r = client.post("/search", json={"query": "highway", "limit": 10,
                                     "since": "2000-01"}, headers=AUTH)
    assert r.status_code == 200
    assert any(row["title"] == "Quiet era shard" for row in r.json())

def test_sync_push_preserves_original_timestamp(client):
    """Bulk ingest must stamp a shard at its true era, like /capture does.

    /sync/push forwarded event_type, tags, embedding, domain_key and
    density_score to capture() but not original_timestamp, so every bulk-pushed
    shard was re-dated to ingest time. The damage is permanent rather than
    cosmetic: capture() dedups on a content hash, so a corrected re-push is a
    silent no-op and the true era cannot be recovered. Verified against a live
    node before the fix -- a shard sent stamped 2020-01-01 came back stamped
    at push time.
    """
    r = client.post("/sync/push", json={"shards": [{
        "title": "Era-true bulk shard",
        "content": "Pushed in bulk, but it happened in 2020.",
        "original_timestamp": "2020-01-01T00:00:00Z",
    }]}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["count"] == 1

    row = client.get("/sync/pull", headers=AUTH).json()[0]
    assert row["timestamp"].startswith("2020-01-01"), (
        f"bulk push must not re-date the shard to ingest time, got {row['timestamp']}")


def test_sync_pull_push_round_trip_keeps_era(client):
    """pull -> push must not flatten history to the migration date.

    Exported rows carry their date under `timestamp`, not `original_timestamp`,
    so a round trip through the export format is the realistic migration path
    and the one most likely to silently re-date an entire vault.
    """
    client.post("/capture", json={
        "title": "Old memory", "content": "Captured long ago.",
        "original_timestamp": "2021-06-15T08:30:00Z",
    }, headers=AUTH)
    exported = client.get("/sync/pull", headers=AUTH).json()
    assert exported[0]["timestamp"].startswith("2021-06-15")

    # Same content dedups, so re-push a distinct body carrying the exported date.
    replay = dict(exported[0])
    replay["content"] = "Captured long ago, replayed to a sibling node."
    r = client.post("/sync/push", json={"shards": [replay]}, headers=AUTH)
    assert r.status_code == 200 and r.json()["count"] == 1

    dates = sorted(row["timestamp"] for row in
                   client.get("/sync/pull", headers=AUTH).json())
    assert all(d.startswith("2021-06-15") for d in dates), (
        f"round trip must preserve the era on both copies, got {dates}")


def test_federated_read_token_falls_back_to_env(monkeypatch, tmp_path):
    """A node with ephemeral storage must still authenticate its federated reads.

    keymaker reads only from its on-disk store. On an HF Space with no volume
    mounted, that store is empty after every restart -- but NGS_NODE_TOKEN is
    still in the environment, because it is what the node authenticates its own
    inbound requests with. Without the env fallback the node registers an
    upstream, sends every federated read unauthenticated, takes a 401, and
    returns an empty list that looks exactly like "the upstream has nothing".
    """
    from nougen_shards.connectors import cloud

    sent = {}

    # keymaker finds nothing — the wiped-store case.
    # keymaker finds nothing — the wiped-store case.
    import nougen_shards.keymaker as km
    monkeypatch.setattr(km, "get_secret", lambda key: None)
    monkeypatch.setenv("NGS_NODE_TOKEN", "env-token-value")
    monkeypatch.setattr(cloud, "_open_cloud", lambda req, url, timeout: (
        sent.__setitem__("token", req.get_header("X-ngs-token")) or b"[]"))

    cloud.query_cloud_shards(
        "anything", [{"name": "blade", "url": "https://blade.example.com"}], 3)

    assert sent.get("token") == "env-token-value", (
        "federated read must fall back to NGS_NODE_TOKEN from the environment "
        "when the keymaker store is empty")
