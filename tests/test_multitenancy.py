"""Adversarial tests for the node's tenant/vault isolation boundary."""
import asyncio
import base64
import hashlib
import json
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")

from fastapi.testclient import TestClient  # noqa: E402

import app as node  # noqa: E402
from nougen_shards import cli, core, federation, mcp_oauth, private_vault, tenants  # noqa: E402


OWNER_TOKEN = "owner-compat-token"


@pytest.fixture()
def tenant_node(tmp_path, monkeypatch):
    owner = tmp_path / "owner-vault"
    tenant_root = tmp_path / "tenant-vaults"
    registry = tmp_path / "tenants.json"
    monkeypatch.setenv("NOUGEN_TENANTS_FILE", str(registry))
    monkeypatch.setenv("NOUGEN_TENANT_VAULT_ROOT", str(tenant_root))
    monkeypatch.setenv("NOUGEN_EMBED_MODEL", "")
    monkeypatch.setattr(node, "NODE_TOKEN", OWNER_TOKEN)
    monkeypatch.setattr(core, "GLOBAL_DIR", owner)
    core._INITIALIZED_DBS.clear()
    private_vault.reset_key_cache()

    token_a = tenants.mint_tenant("tenant-a", "Tenant A")
    token_b = tenants.mint_tenant("tenant-b", "Tenant B")
    yield {
        "client": TestClient(node.app),
        "owner": owner,
        "tenant_root": tenant_root,
        "registry": registry,
        "token_a": token_a,
        "token_b": token_b,
    }
    core._INITIALIZED_DBS.clear()
    private_vault.reset_key_cache()


def _auth(token):
    return {"X-NGS-Token": token}


def _titles_in_vault(vault: Path) -> set[str]:
    titles = set()
    for db in vault.glob("nougen_shards_*.db"):
        conn = sqlite3.connect(db)
        try:
            titles.update(row[0] for row in conn.execute("SELECT title FROM shards"))
        finally:
            conn.close()
    return titles


def test_tenant_capture_and_recall_are_isolated(tenant_node):
    client = tenant_node["client"]
    a = client.post("/capture", headers=_auth(tenant_node["token_a"]), json={
        "title": "Tenant A only",
        "content": "uniquely-visible-alpha-memory",
    })
    assert a.status_code == 200 and a.json()["captured"] is True

    b_search = client.post("/search", headers=_auth(tenant_node["token_b"]),
                           json={"query": "uniquely-visible-alpha-memory"})
    assert b_search.status_code == 200
    assert all(row.get("title") != "Tenant A only" for row in b_search.json())
    assert not (tenant_node["tenant_root"] / "tenant-b").exists(), \
        "a read of an empty tenant must not create its vault"

    a_search = client.post("/search", headers=_auth(tenant_node["token_a"]),
                           json={"query": "uniquely-visible-alpha-memory"})
    assert any(row.get("title") == "Tenant A only" for row in a_search.json())


def test_tenant_write_never_touches_owner_vault(tenant_node):
    owner = tenant_node["owner"]
    owner.mkdir(mode=0o700)
    marker = owner / "existing-owner-vault.marker"
    marker.write_text("untouched", encoding="utf-8")
    before = {p.relative_to(owner) for p in owner.rglob("*")}

    r = tenant_node["client"].post(
        "/capture", headers=_auth(tenant_node["token_b"]),
        json={"title": "Tenant B only", "content": "tenant-b-write-target"},
    )
    assert r.status_code == 200 and r.json()["captured"] is True
    after = {p.relative_to(owner) for p in owner.rglob("*")}

    assert after == before
    assert marker.read_text(encoding="utf-8") == "untouched"
    assert "Tenant B only" in _titles_in_vault(tenant_node["tenant_root"] / "tenant-b")
    assert "Tenant B only" not in _titles_in_vault(owner)


def test_unknown_and_missing_credentials_touch_no_vault(tenant_node, monkeypatch):
    calls = []
    original = core.get_db_path

    def observed(index):
        calls.append((core.active_tenant_id(), core.active_vault_dir()))
        return original(index)

    monkeypatch.setattr(core, "get_db_path", observed)
    client = tenant_node["client"]
    assert client.post("/search", json={"query": "x"}).status_code == 401
    assert client.post("/search", headers=_auth("unknown-token"),
                       json={"query": "x"}).status_code == 401
    assert client.post("/capture", json={"title": "x", "content": "y"}).status_code == 401
    assert calls == []
    assert not tenant_node["owner"].exists()


@pytest.mark.parametrize("tenant_id", ["..", "a/b", r"a\b"])
def test_registry_rejects_path_traversal_tenant_ids(tmp_path, tenant_id):
    path = tmp_path / "tenants.json"
    path.write_text(json.dumps({"tenants": [{
        "tenant_id": tenant_id,
        "label": "Unsafe",
        "token_sha256": "0" * 64,
    }]}), encoding="utf-8")
    with pytest.raises(tenants.TenantRegistryError):
        tenants.load_registry(path)


def test_interleaved_requests_keep_their_context_and_files(tenant_node, monkeypatch):
    seen = {}
    original_capture = core.capture

    def observed_capture(event_type, title, content, **kwargs):
        before = (core.active_tenant_id(), core.active_vault_dir())
        # Yield the worker thread while both requests are in flight. A mutable
        # module global would be overwritten here; ContextVars remain distinct.
        import time
        time.sleep(0.03)
        after = (core.active_tenant_id(), core.active_vault_dir())
        seen[title] = (before, after)
        return original_capture(event_type, title, content, **kwargs)

    monkeypatch.setattr(core, "capture", observed_capture)

    async def post(token, title):
        return await asyncio.to_thread(
            tenant_node["client"].post,
            "/capture",
            headers=_auth(token),
            json={"title": title, "content": f"content-for-{title}"},
        )

    async def run_both():
        return await asyncio.gather(
            post(tenant_node["token_a"], "Concurrent A"),
            post(tenant_node["token_b"], "Concurrent B"),
        )

    responses = asyncio.run(run_both())
    assert [response.status_code for response in responses] == [200, 200]
    for title, tenant_id in (("Concurrent A", "tenant-a"), ("Concurrent B", "tenant-b")):
        expected = tenant_node["tenant_root"] / tenant_id
        assert seen[title] == ((tenant_id, expected), (tenant_id, expected))
        assert title in _titles_in_vault(expected)
    assert "Concurrent A" not in _titles_in_vault(tenant_node["tenant_root"] / "tenant-b")
    assert "Concurrent B" not in _titles_in_vault(tenant_node["tenant_root"] / "tenant-a")


def test_owner_only_configuration_is_backwards_compatible(tmp_path, monkeypatch):
    owner = tmp_path / "legacy-owner"
    missing_registry = tmp_path / "does-not-exist.json"
    monkeypatch.setenv("NOUGEN_TENANTS_FILE", str(missing_registry))
    monkeypatch.setattr(node, "NODE_TOKEN", OWNER_TOKEN)
    monkeypatch.setattr(core, "GLOBAL_DIR", owner)
    core._INITIALIZED_DBS.clear()

    resolved = tenants.resolve_token(OWNER_TOKEN, OWNER_TOKEN, core.GLOBAL_DIR)
    assert resolved is not None
    assert resolved.tenant_id == "owner"
    assert resolved.vault_dir == owner

    client = TestClient(node.app)
    r = client.post("/capture", headers=_auth(OWNER_TOKEN),
                    json={"title": "Legacy owner", "content": "unchanged owner flow"})
    assert r.status_code == 200 and r.json()["captured"] is True
    assert "Legacy owner" in _titles_in_vault(owner)


def test_tenant_cli_prints_token_once_and_registry_has_only_hash(tmp_path, monkeypatch, capsys):
    registry = tmp_path / "tenants.json"
    monkeypatch.setenv("NOUGEN_TENANTS_FILE", str(registry))
    monkeypatch.setattr(sys, "argv", [
        "nougen", "tenant", "mint", "tester", "--label", "External Tester",
    ])
    cli.main()
    output = capsys.readouterr().out
    token = next(line.split(": ", 1)[1] for line in output.splitlines()
                 if line.startswith("Token: "))
    stored = registry.read_text(encoding="utf-8")
    assert token not in stored
    assert hashlib.sha256(token.encode()).hexdigest() in stored
    assert "token" not in json.loads(stored)["tenants"][0]


def test_oauth_access_token_carries_tenant_id(tenant_node):
    client = tenant_node["client"]
    redirect_uri = "https://client.example.test/callback"
    registered = client.post("/register", json={
        "redirect_uris": [redirect_uri],
        "client_name": "Tenant client",
    })
    client_id = registered.json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    authorized = client.post("/authorize", data={
        "node_token": tenant_node["token_a"],
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": "tenant-state",
        "code_challenge": challenge,
    }, follow_redirects=False)
    assert authorized.status_code == 303
    code = authorized.headers["location"].split("code=")[1].split("&")[0]
    exchanged = client.post("/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    })
    access_token = exchanged.json()["access_token"]
    assert mcp_oauth.issued_token_tenant(access_token) == "tenant-a"


def test_non_owner_federation_never_reads_owner_upstreams(tenant_node, monkeypatch):
    monkeypatch.setattr(federation.core, "retrieve", lambda *args, **kwargs: [{"id": 1}])

    def owner_leak():
        raise AssertionError("non-owner request touched owner federation config")

    monkeypatch.setattr(federation.keymaker, "list_external_dbs", owner_leak)
    monkeypatch.setattr(federation.keymaker, "list_cloud_nodes", owner_leak)
    tenant = tenants.resolve_token(
        tenant_node["token_b"], OWNER_TOKEN, tenant_node["owner"])
    tokens = core.bind_active_vault(tenant.vault_dir, tenant.tenant_id)
    try:
        assert federation.federated_retrieve("query")
    finally:
        core.reset_active_vault(tokens)


def test_sync_routes_are_tenant_scoped(tenant_node):
    client = tenant_node["client"]
    pushed = client.post("/sync/push", headers=_auth(tenant_node["token_a"]), json={
        "shards": [{"title": "A sync shard", "content": "a-sync-only-body"}],
    })
    assert pushed.status_code == 200 and pushed.json()["count"] == 1

    pull_a = client.get("/sync/pull", headers=_auth(tenant_node["token_a"])).json()
    pull_b = client.get("/sync/pull", headers=_auth(tenant_node["token_b"])).json()
    assert any(row["title"] == "A sync shard" for row in pull_a)
    assert all(row["title"] != "A sync shard" for row in pull_b)

    hashes_a = client.get("/sync/hashes", headers=_auth(tenant_node["token_a"])).json()
    hashes_b = client.get("/sync/hashes", headers=_auth(tenant_node["token_b"])).json()
    assert hashes_a["count"] == 1
    assert hashes_b["count"] == 0


def test_agent_route_receives_tenant_context(tenant_node, monkeypatch):
    observed = {}

    def fake_agent(*args, **kwargs):
        observed["tenant_id"] = core.active_tenant_id()
        observed["vault"] = core.active_vault_dir()
        return "ok"

    # /agent is Rhea-Noir's route (PR #103). It recalls from the grid, so it
    # must run against the CALLER's vault, not the owner's.
    monkeypatch.setattr(node.rhea_noir, "ask", fake_agent)
    r = tenant_node["client"].post(
        "/agent", headers=_auth(tenant_node["token_b"]),
        json={"prompt": "check isolation"},
    )
    assert r.status_code == 200
    assert observed == {
        "tenant_id": "tenant-b",
        "vault": tenant_node["tenant_root"] / "tenant-b",
    }


def test_mcp_gate_binds_tenant_context(tenant_node):
    async def inner(scope, receive, send):
        body = json.dumps({
            "tenant_id": core.active_tenant_id(),
            "vault": str(core.active_vault_dir()),
        }).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})

    gated = TestClient(node._TokenGatedMCP(inner))
    r = gated.post("/", headers=_auth(tenant_node["token_a"]), json={})
    assert r.status_code == 200
    assert r.json() == {
        "tenant_id": "tenant-a",
        "vault": str(tenant_node["tenant_root"] / "tenant-a"),
    }
    assert core.active_tenant_id() == "owner", "MCP context leaked after response"


def test_health_is_generic_until_authenticated(tenant_node, monkeypatch):
    calls = []
    original = core.get_db_path

    def observed(index):
        calls.append(core.active_tenant_id())
        return original(index)

    monkeypatch.setattr(core, "get_db_path", observed)
    generic = tenant_node["client"].get("/health")
    assert generic.status_code == 200
    assert "total_shards" not in generic.json()
    assert "substrate" not in generic.json()
    assert calls == []

    authed = tenant_node["client"].get(
        "/health", headers=_auth(tenant_node["token_a"]))
    assert authed.status_code == 200
    assert authed.json()["tenant_id"] == "tenant-a"
    assert set(calls) == {"tenant-a"}
