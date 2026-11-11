"""Tests for workers/join/deploy.py provisioning token selection."""
import importlib.util
from pathlib import Path


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
    assert "newest:CLOUDFLARE_JOIN_TOKEN_" in captured[0][1]

    captured.clear()
    monkeypatch.setenv("NOUGEN_JOIN_CF_TOKEN_NAME", "CLOUDFLARE_JOIN_TOKEN_CUSTOM")
    deploy.main()
    assert "mock:cloudflare_join_token_custom" in captured[0][1]
