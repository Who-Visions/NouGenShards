"""DECISION shard 30954: a tenant gets the full NouGen tool surface scoped to
its own root, not a shard-only subset. These tests pin:

1. every tool registered on the node is labelled TENANT_SCOPED or OWNER_ONLY;
2. a tenant's tools/list is rewritten to the scoped set, the owner's is not;
3. tools/call to an owner-only tool is refused before it reaches the server;
4. relay legs, secrets, destinies and message inboxes written by a tenant land
   under the tenant's own vault and never under the owner's home.
"""
import asyncio
import inspect
import json
import os
import tempfile
from pathlib import Path

import pytest

TEST_TOKEN = "test-tenant-surface-token"

_tmp = Path(tempfile.mkdtemp(prefix="ngs_tenant_surface_"))
OWNER_HOME = _tmp / "owner_home"
OWNER_HOME.mkdir()
os.environ["NGS_NODE_TOKEN"] = TEST_TOKEN
os.environ["NOUGEN_HOME"] = str(OWNER_HOME)
os.environ["NOUGEN_ROOT"] = str(OWNER_HOME)
os.environ["NOUGEN_VAULT_DIR"] = str(_tmp / ".vault")
os.environ["NOUGEN_SECRETS_VAULT"] = str(OWNER_HOME / "secrets")
os.environ["NOUGEN_TENANTS_FILE"] = str(_tmp / "tenants.json")
os.environ["NOUGEN_TENANT_VAULT_ROOT"] = str(_tmp / "tenants")

import app as node  # noqa: E402
import nougen_shards.core as core  # noqa: E402
from nougen_shards import destiny, keymaker, nougenmsg, tenant_policy, tenants  # noqa: E402

MCP_HEADERS = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
OWNER_AUTH = {"X-NGS-Token": TEST_TOKEN, **MCP_HEADERS}
TENANT_ID = "acme"


def _rpc(method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


@pytest.fixture(autouse=True)
def _tenant_env(monkeypatch):
    """conftest isolates the tenant registry and runtime root per test; point
    them back at this module's throwaway owner home and registry."""
    monkeypatch.setenv("NOUGEN_TENANTS_FILE", str(_tmp / "tenants.json"))
    monkeypatch.setenv("NOUGEN_TENANT_VAULT_ROOT", str(_tmp / "tenants"))
    monkeypatch.setenv("NOUGEN_ROOT", str(OWNER_HOME))


@pytest.fixture(scope="module")
def tenant_token():
    return tenants.mint_tenant(TENANT_ID, "Acme test tenant")


@pytest.fixture(scope="module")
def tenant_auth(tenant_token):
    return {"X-NGS-Token": tenant_token, **MCP_HEADERS}


@pytest.fixture(scope="module")
def client(shared_mcp_client):
    vault = _tmp / "owner_vault"
    vault.mkdir()
    saved = (core.GLOBAL_DIR, core.get_db_path, node.NODE_TOKEN)
    core.GLOBAL_DIR = vault
    core.get_db_path = lambda index: vault / f"mcp_{index}.db"
    node.NODE_TOKEN = TEST_TOKEN
    core.init_db(1)
    try:
        yield shared_mcp_client  # lifespan entered once per process (conftest)
    finally:
        core.GLOBAL_DIR, core.get_db_path, node.NODE_TOKEN = saved


def _registered_tool_names():
    listed = node.node_mcp.list_tools()
    if inspect.isawaitable(listed):
        listed = asyncio.run(listed)
    return {t.name for t in listed}


def _tenant_vault() -> Path:
    return tenants.vault_dir_for(TENANT_ID, core.GLOBAL_DIR)


# --- 1. policy completeness --------------------------------------------------

def test_every_registered_tool_is_labelled():
    report = tenant_policy.classify(_registered_tool_names())
    assert report["unclassified"] == [], (
        "label these in nougen_shards/tenant_policy.py before shipping: "
        f"{report['unclassified']} (policy file={tenant_policy.__file__}, "
        f"scoped={len(tenant_policy.TENANT_SCOPED)}, owner_only={len(tenant_policy.OWNER_ONLY)}, "
        f"xoah_in_owner_only={sorted(n for n in tenant_policy.OWNER_ONLY if 'xoah' in n)})")
    assert report["double_labelled"] == []
    # Owner-only labels may name tools that only exist where a plugin is
    # installed (the xoah canon tools register from the node's plugin dir, so
    # CI never sees them): a stale OWNER_ONLY label is harmless. A stale
    # TENANT_SCOPED label is a typo that silently grants nothing, so it fails.
    stale_scoped = sorted(set(report["stale_labels"]) & tenant_policy.TENANT_SCOPED)
    assert stale_scoped == [], f"TENANT_SCOPED names not registered on this node: {stale_scoped}"
    assert len(report["tenant"]) > 40, "the tenant surface regressed to a stub"


def test_env_can_widen_and_narrow_tenant_set_but_never_grant_owner_only(monkeypatch):
    monkeypatch.setenv("NOUGEN_TENANT_EXTRA_TOOLS", "ask_rhea,some_future_tool")
    monkeypatch.setenv("NOUGEN_TENANT_DENY_TOOLS", "search")
    assert not tenant_policy.tenant_allowed("ask_rhea"), "extras must not pierce the owner-only floor"
    assert tenant_policy.tenant_allowed("some_future_tool")
    assert not tenant_policy.tenant_allowed("search")
    monkeypatch.delenv("NOUGEN_TENANT_EXTRA_TOOLS")
    monkeypatch.delenv("NOUGEN_TENANT_DENY_TOOLS")
    assert not tenant_policy.tenant_allowed("some_future_tool")
    assert tenant_policy.allowed_for("owner", "ask_rhea")


def test_tenant_call_with_non_object_params_is_refused(client, tenant_auth):
    r = client.post("/mcp/", headers=tenant_auth, json=_rpc("tools/call", ["nougen_time_now"]))
    assert r.status_code == 403
    r = client.post("/mcp/", headers=tenant_auth, json=[
        _rpc("tools/call", {"name": "nougen_time_now", "arguments": {}}, id_=1),
        _rpc("tools/call", {"name": "fleet_send", "arguments": {}}, id_=2)])
    assert r.status_code == 403, "an owner-only call hidden in a batch must refuse the whole batch"


def test_tenant_env_overrides_do_not_redirect_to_owner_paths(monkeypatch):
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(OWNER_HOME / "cc_sessions.json"))
    monkeypatch.setenv("NOUGEN_CLAUDE_INBOX", str(OWNER_HOME / "claude_inbox"))
    monkeypatch.setenv("NOUGEN_CODEX_INBOX", str(OWNER_HOME / "codex_inbox"))
    tokens = core.bind_active_vault(_tenant_vault(), TENANT_ID)
    try:
        assert Path(nougenmsg.AgentPinger._cc_registry_path()).is_relative_to(_tenant_vault())
        assert Path(nougenmsg.AgentPinger._claude_inbox_dir()).is_relative_to(_tenant_vault())
        assert Path(nougenmsg._codex_inbox_dirs()[0]).is_relative_to(_tenant_vault())
        assert nougenmsg.fleet_hosts_path() == _tenant_vault() / "fleet_hosts.json"
    finally:
        core.reset_active_vault(tokens)
    assert nougenmsg.AgentPinger._cc_registry_path() == str(OWNER_HOME / "cc_sessions.json")


def test_listing_filter_flush_emits_withheld_start_and_keeps_crlf():
    sent = []

    async def sink(msg):
        sent.append(msg)

    f = node._TenantListingFilter(sink, TENANT_ID)

    async def run():
        await f({"type": "http.response.start", "status": 200, "headers": []})
        await f({"type": "http.response.body", "body": b"partial", "more_body": True})
        await f.flush()
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": [
            {"name": "search"}, {"name": "fleet_send"}]}})
        await f({"type": "http.response.start", "status": 200,
                 "headers": [(b"content-type", b"text/event-stream")]})
        await f({"type": "http.response.body", "body": ("data: " + payload + "\r\n\r\n").encode(),
                 "more_body": False})

    asyncio.run(run())
    assert sent[0]["status"] == 200 and sent[1]["body"] == b"partial"
    out = sent[3]["body"].decode()
    assert out.endswith("\r\n\r\n")
    assert "fleet_send" not in out and "search" in out


# --- 2. tools/list ----------------------------------------------------------------

def test_tenant_listing_is_the_scoped_set_and_owner_listing_is_not(client, tenant_auth):
    r = client.post("/mcp/", headers=tenant_auth, json=_rpc("tools/list"))
    assert r.status_code == 200, r.text
    tenant_names = {t["name"] for t in r.json()["result"]["tools"]}
    assert tenant_names == tenant_policy.tenant_allowed_names() & _registered_tool_names()
    assert "ask_rhea" not in tenant_names and "fleet_send" not in tenant_names
    assert {"relay_create_leg", "nougenmsg", "vault_put", "create_destiny"} <= tenant_names

    r = client.post("/mcp/", headers=OWNER_AUTH, json=_rpc("tools/list"))
    owner_names = {t["name"] for t in r.json()["result"]["tools"]}
    assert tenant_policy.OWNER_ONLY & owner_names, "owner listing lost owner-only tools"
    assert owner_names >= tenant_names


def test_listing_filter_rewrites_sse_bodies():
    sent = []

    async def sink(msg):
        sent.append(msg)

    f = node._TenantListingFilter(sink, TENANT_ID)
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [
        {"name": "search"}, {"name": "ask_rhea"}, {"name": "nougen_time_now"}]}}
    body = ("event: message\ndata: " + json.dumps(payload) + "\n\n").encode()

    async def run():
        await f({"type": "http.response.start", "status": 200,
                 "headers": [(b"content-type", b"text/event-stream"), (b"content-length", b"1")]})
        await f({"type": "http.response.body", "body": body[:20], "more_body": True})
        await f({"type": "http.response.body", "body": body[20:], "more_body": False})

    asyncio.run(run())
    assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]
    out = sent[1]["body"].decode()
    names = [t["name"] for t in json.loads(out.split("data: ", 1)[1].strip())["result"]["tools"]]
    assert names == ["search", "nougen_time_now"]
    headers = dict(sent[0]["headers"])
    assert headers[b"content-length"] == str(len(sent[1]["body"])).encode()


# --- 3. tools/call gate -------------------------------------------------------

def test_tenant_owner_only_call_is_refused_and_scoped_call_served(client, tenant_auth):
    r = client.post("/mcp/", headers=tenant_auth, json=_rpc(
        "tools/call", {"name": "ask_rhea", "arguments": {"question": "hi"}}))
    assert r.status_code == 403
    assert "not available to this identity" in r.text

    r = client.post("/mcp/", headers=tenant_auth, json=_rpc(
        "tools/call", {"name": "nougen_time_now", "arguments": {}}))
    assert r.status_code == 200, r.text
    assert not r.json()["result"].get("isError")


# --- 4. tenant state lands under the tenant root ----------------------------

def _text(result):
    return "".join(c.get("text", "") for c in result["content"])


def test_tenant_relay_leg_lands_in_tenant_vault_not_owner_home(client, tenant_auth):
    r = client.post("/mcp/", headers=tenant_auth, json=_rpc(
        "tools/call", {"name": "relay_create_leg",
                       "arguments": {"goal": "tenant leg", "body": "scoped"}}))
    assert r.status_code == 200, r.text
    created = json.loads(_text(r.json()["result"]))
    leg_id = created["leg_id"]
    tenant_legs = list((_tenant_vault() / "relay" / ".handoffs").glob("*.md"))
    assert [p for p in tenant_legs if p.stem == leg_id], "leg did not land under the tenant vault"
    assert not (OWNER_HOME / "relay").exists(), "tenant wrote into the owner's relay board"

    r = client.post("/mcp/", headers=tenant_auth, json=_rpc(
        "tools/call", {"name": "relay_open_legs", "arguments": {"limit": 5}}))
    assert leg_id in _text(r.json()["result"])


def test_tenant_vault_put_uses_tenant_secrets_db(client, tenant_auth, monkeypatch):
    import time
    started = time.time() - 1
    # This test pins WHICH secrets DB a tenant write lands in, not the cipher.
    # POSIX CI runners have no DPAPI and no `keyring` backend, where keymaker
    # fails closed; allow the plaintext path for this throwaway tmp vault only.
    monkeypatch.setenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", "1")
    r = client.post("/mcp/", headers=tenant_auth, json=_rpc(
        "tools/call", {"name": "vault_put",
                       "arguments": {"key": "ACME_KEY", "value": "s3cr3t-value"}}))
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError"), result
    text = _text(result)
    assert "s3cr3t-value" not in text
    tenant_db = _tenant_vault() / "secrets" / keymaker.DB_FILENAME
    assert tenant_db.exists()
    owner_db = keymaker.DB_PATH
    assert owner_db != tenant_db
    if owner_db.exists():  # another module may have imported app with a real keyring path
        assert owner_db.stat().st_mtime < started, "tenant secret reached the owner keyring"


def test_destiny_and_nougenmsg_resolve_inside_tenant_context():
    tokens = core.bind_active_vault(_tenant_vault(), TENANT_ID)
    try:
        assert core.is_tenant_context()
        assert core.active_home() == _tenant_vault()
        assert destiny.db_path() == _tenant_vault() / "destinies.db"
        os_env_override = os.environ.get("NOUGEN_DESTINY_DB")
        os.environ["NOUGEN_DESTINY_DB"] = str(OWNER_HOME / "owner_destinies.db")
        try:
            assert destiny.db_path() == _tenant_vault() / "destinies.db", \
                "operator env override must not point a tenant at the owner store"
        finally:
            if os_env_override is None:
                os.environ.pop("NOUGEN_DESTINY_DB", None)
            else:
                os.environ["NOUGEN_DESTINY_DB"] = os_env_override
        agy = nougenmsg._agy_inbox_dirs(archive=True)
        assert all(Path(d).is_relative_to(_tenant_vault()) for d in agy), agy
        assert nougenmsg._codex_inbox_dirs()[0] == str(_tenant_vault() / "inbox" / "codex")
        assert nougenmsg._live_pipe_names() == []
        assert keymaker.db_path() == _tenant_vault() / "secrets" / keymaker.DB_FILENAME
    finally:
        core.reset_active_vault(tokens)
    assert not core.is_tenant_context()
    assert core.active_home() == OWNER_HOME
    assert destiny.db_path() == Path(core.GLOBAL_DIR) / "destinies.db"
    assert keymaker.db_path() == keymaker.DB_PATH
    owner_codex = nougenmsg._codex_inbox_dirs()[0]
    assert owner_codex.endswith(os.path.join(".codex", "inbox"))
    assert not Path(owner_codex).is_relative_to(_tenant_vault())


def test_owner_home_prefers_env_and_logs_fallback(monkeypatch, caplog):
    monkeypatch.setenv("NOUGEN_ROOT", str(_tmp / "root_env"))
    monkeypatch.setenv("NOUGEN_HOME", str(_tmp / "code_home"))
    assert core.owner_home() == _tmp / "root_env"
    monkeypatch.delenv("NOUGEN_ROOT")
    assert core.owner_home() != _tmp / "code_home", "NOUGEN_HOME is the code tree, never runtime state"
    monkeypatch.setattr(core, "_OWNER_HOME_FALLBACK_LOGGED", False)
    with caplog.at_level("INFO", logger="nougen_shards.core"):
        assert core.owner_home() == Path.home() / ".nougen"
    assert any("falling back to ~/.nougen" in r.message for r in caplog.records)


def test_tenant_get_secret_reads_only_the_tenant_db(monkeypatch):
    monkeypatch.setenv("ACME_ONLY_KEY", "owner-process-env-value")
    monkeypatch.setenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", "1")
    tokens = core.bind_active_vault(_tenant_vault(), TENANT_ID)
    try:
        assert keymaker.get_secret("ACME_ONLY_KEY") is None, "tenant read fell through to the node env"
        keymaker.init_vault()
        keymaker.ingest_secret("ACME_ONLY_KEY", "tenant-value")
        assert keymaker.get_secret("ACME_ONLY_KEY") == "tenant-value"
    finally:
        core.reset_active_vault(tokens)
    assert keymaker.get_secret("ACME_ONLY_KEY") == "owner-process-env-value"


def test_tenant_messages_never_touch_host_sockets(monkeypatch, tmp_path):
    import socket as _socket

    class _NoSocket:
        def __init__(self, *a, **k):
            raise AssertionError("tenant message opened a host socket")

    monkeypatch.setattr(_socket, "socket", _NoSocket)
    monkeypatch.setattr(nougenmsg.AgentPinger, "_write_windows_named_pipe",
                        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("named pipe used"))))
    monkeypatch.setattr(nougenmsg.glob, "glob", lambda pattern: [str(tmp_path / "fake.sock")])
    tokens = core.bind_active_vault(_tenant_vault(), TENANT_ID)
    try:
        assert nougenmsg.AgentPinger._discover_claude_endpoints() == []
        out = nougenmsg.AgentPinger.ping_antigravity("hello tenant")
        assert out.get("pipe_delivered") is False
        out = nougenmsg.AgentPinger.ping_claude("hello tenant")
        assert out.get("tenant_scope") == "file-inbox-only"
        assert Path(out["file"]).is_relative_to(_tenant_vault())
    finally:
        core.reset_active_vault(tokens)
