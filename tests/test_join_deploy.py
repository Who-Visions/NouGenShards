"""Tests for workers/join/deploy.py provisioning token selection."""
import importlib.util
from pathlib import Path


# A well-formed KV namespace id (32 hex characters) that is plainly not a
# secret. Built from a repeated pair so a secret scanner does not read the
# literal as a key; a namespace id is an identifier, not a credential.
FAKE_KV_ID = "ab" * 16


def _load_deploy():
    path = Path(__file__).resolve().parents[1] / "workers" / "join" / "deploy.py"
    spec = importlib.util.spec_from_file_location("join_deploy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_deploy_defaults_to_newest_join_token_and_respects_override(monkeypatch):
    deploy = _load_deploy()
    captured = []

    class FakeCF:
        account_id = "acct-1"

        def call(self, *args, **kwargs):
            captured.append(("call", args, kwargs))
            return {}

    monkeypatch.setattr(deploy, "client", lambda: FakeCF())
    monkeypatch.setattr(deploy.t, "_zone_for", lambda c, host: "zone-1")
    monkeypatch.setattr(deploy.t, "_find_namespace", lambda c: "ns-1")
    monkeypatch.setattr(deploy.t, "_resolve_cf_token", lambda: "op-val")
    monkeypatch.setattr(deploy, "newest", lambda prefix: f"newest:{prefix}")
    monkeypatch.setattr(deploy.keymaker, "get_secret", lambda name: f"mock:{name.lower()}")

    def fake_urlopen(req, timeout=60):
        captured.append(("upload", req.data.decode("latin1")))

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b'{"success": true}'

        return Resp()

    monkeypatch.setattr(deploy.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("NOUGEN_JOIN_CF_TOKEN_NAME", raising=False)
    deploy.main()
    assert "newest:CLOUDFLARE_JOIN_TOKEN_" in next(x for x in captured if x[0] == "upload")[1]

    captured.clear()
    monkeypatch.setenv("NOUGEN_JOIN_CF_TOKEN_NAME", "CLOUDFLARE_JOIN_TOKEN_CUSTOM")
    deploy.main()
    assert "mock:cloudflare_join_token_custom" in next(x for x in captured if x[0] == "upload")[1]


def test_newest_reads_secret_key_column_and_falls_back_when_scan_empty(monkeypatch, tmp_path):
    deploy = _load_deploy()
    db = tmp_path / "secrets.db"
    import sqlite3
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE secrets (id INTEGER PRIMARY KEY, secret_key TEXT UNIQUE, secret_value TEXT, last_rotated TEXT)")
    con.execute("INSERT INTO secrets (secret_key, secret_value, last_rotated) VALUES ('CLOUDFLARE_JOIN_TOKEN_20261111_1800', 'ignored', 'now')")
    con.commit()
    con.close()

    monkeypatch.setattr(deploy.keymaker, "db_path", lambda: db)
    monkeypatch.setattr(deploy.keymaker, "list_providers", lambda: [])
    monkeypatch.setattr(deploy.keymaker, "resolve_secrets_store", lambda: {"active": db, "live": []})
    monkeypatch.setattr(deploy.keymaker, "get_secret", lambda name: f"resolved:{name}")
    assert deploy.newest("CLOUDFLARE_JOIN_TOKEN_") == "resolved:CLOUDFLARE_JOIN_TOKEN_20261111_1800"

    empty_db = tmp_path / "empty.db"
    monkeypatch.setattr(deploy.keymaker, "db_path", lambda: empty_db)
    monkeypatch.setattr(deploy.keymaker, "resolve_secrets_store", lambda: {"active": empty_db, "live": []})
    monkeypatch.setattr(deploy.keymaker, "get_secret", lambda name: "fallback-found" if name == deploy.DEFAULT_JOIN_TOKEN_NAME else None)
    assert deploy.newest("CLOUDFLARE_JOIN_TOKEN_") == "fallback-found"


def test_relay_bindings_are_off_unless_both_values_are_given():
    deploy = _load_deploy()
    assert deploy.relay_bindings({}) == []
    assert deploy.relay_bindings({"NOUGEN_JOIN_RELAY_URL": "  ", "NOUGEN_JOIN_RELAY_AUTH_KV_ID": ""}) == []
    got = deploy.relay_bindings({"NOUGEN_JOIN_RELAY_URL": "wss://relay.example.test/_relay/connect",
                                 "NOUGEN_JOIN_RELAY_AUTH_KV_ID": FAKE_KV_ID})
    assert got == [
        {"type": "kv_namespace", "name": "RELAY_AUTH", "namespace_id": FAKE_KV_ID},
        {"type": "plain_text", "name": "RELAY_URL", "text": "wss://relay.example.test/_relay/connect"},
    ]


def test_a_half_or_badly_configured_relay_stops_the_deploy():
    import pytest
    deploy = _load_deploy()
    good_url, good_id = "wss://relay.example.test/_relay/connect", FAKE_KV_ID
    for env in (
        {"NOUGEN_JOIN_RELAY_URL": good_url},
        {"NOUGEN_JOIN_RELAY_AUTH_KV_ID": good_id},
        {"NOUGEN_JOIN_RELAY_URL": "ws://relay.example.test/x", "NOUGEN_JOIN_RELAY_AUTH_KV_ID": good_id},
        {"NOUGEN_JOIN_RELAY_URL": "http://relay.example.test/x", "NOUGEN_JOIN_RELAY_AUTH_KV_ID": good_id},
        {"NOUGEN_JOIN_RELAY_URL": "wss://relay.example.test/a b", "NOUGEN_JOIN_RELAY_AUTH_KV_ID": good_id},
        {"NOUGEN_JOIN_RELAY_URL": good_url, "NOUGEN_JOIN_RELAY_AUTH_KV_ID": "not-an-id"},
        {"NOUGEN_JOIN_RELAY_URL": good_url, "NOUGEN_JOIN_RELAY_AUTH_KV_ID": good_id.upper()},
    ):
        with pytest.raises(SystemExit, match="nothing deployed"):
            deploy.relay_bindings(env)
