"""Tests for NouGenRemote Pro iPhone 14 Cockpit & Direct Antigravity Injection."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_nougen_remote():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "tools" / "nougen_remote.py"
    spec = importlib.util.spec_from_file_location("nougen_remote", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_design_choices_100_catalog():
    mod = _load_nougen_remote()
    assert len(mod.DESIGN_CHOICES_100) == 100
    pillars = {item["pillar"] for item in mod.DESIGN_CHOICES_100}
    assert len(pillars) == 5
    assert mod.DESIGN_CHOICES_100[0]["id"] == 1
    assert mod.DESIGN_CHOICES_100[-1]["id"] == 100


def test_pwa_html_contains_smartkeys_and_wakelock():
    mod = _load_nougen_remote()
    html = mod.HTML_PWA
    assert "smartkeys-bar" in html
    assert "requestWakeLock" in html
    assert "visualViewport" in html
    assert "pollInboxStatus" in html


def test_get_inbox_status_structure():
    mod = _load_nougen_remote()
    status = mod.get_inbox_status(limit=3)
    assert status["ok"] is True
    assert "watermark" in status
    assert "seen_count" in status
    assert isinstance(status["recent"], list)


def test_inject_to_antigravity_fallback(monkeypatch, tmp_path):
    mod = _load_nougen_remote()
    monkeypatch.setenv("NOUGEN_REMOTE_DISABLE_CONSOLE_PULSE", "1")
    monkeypatch.setattr(mod.Path, "home", lambda: tmp_path)

    def _fail_urlopen(*args, **kwargs):
        raise ConnectionRefusedError("8766 offline in unit test")

    monkeypatch.setattr(mod.urllib.request, "urlopen", _fail_urlopen)
    res = mod.inject_to_antigravity("unit test ping from iPhone 14", sender="iPhone 14 Test")
    assert res["ok"] is True
    assert res["injected"] is True
    inbox_files = list((tmp_path / ".nougen" / "agy_inbox").glob("msg_*.json"))
    assert len(inbox_files) == 1
    doc = json.loads(inbox_files[0].read_text(encoding="utf-8"))
    assert doc["text"] == "unit test ping from iPhone 14"
    assert doc["body"] == "unit test ping from iPhone 14"
    assert doc["target"] == "antigravity"


def test_crd_host_status_and_gestures():
    mod = _load_nougen_remote()
    crd = mod.get_crd_host_status()
    assert crd["ok"] is True
    assert crd["service_name"] == "chromoting"
    assert "touch_mode" in crd["gestures"]
    assert "trackpad_mode" in crd["gestures"]


def test_dispatch_screen_input_simulated(monkeypatch):
    mod = _load_nougen_remote()
    monkeypatch.setenv("NOUGEN_REMOTE_DISABLE_CONSOLE_PULSE", "1")
    res_touch = mod.dispatch_screen_input({"mode": "touch", "action": "left_click", "norm_x": 0.5, "norm_y": 0.5})
    assert res_touch["ok"] is True
    res_pad = mod.dispatch_screen_input({"mode": "trackpad", "action": "right_click", "dx": 15, "dy": -10})
    assert res_pad["ok"] is True


def test_private_get_routes_require_token(monkeypatch):
    import importlib
    import sys
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    monkeypatch.setenv("NOUGEN_REMOTE_TOKEN", "test-token-123")
    nr = importlib.reload(importlib.import_module("nougen_remote"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), nr.RemoteHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def status(url):
            try:
                return urllib.request.urlopen(url, timeout=5).status
            except urllib.error.HTTPError as e:
                return e.code

        assert status(base + "/api/v1/inbox") == 401
        assert status(base + "/api/v1/inbox?token=wrong") == 401
        assert status(base + "/api/v1/inbox?token=test-token-123") == 200
        assert status(base + "/api/v1/health") == 200
    finally:
        srv.shutdown()


def _stub_google_verify(monkeypatch):
    """Stub google.oauth2.id_token.verify_oauth2_token with canned claims."""
    pytest.importorskip("google.oauth2.id_token")
    import google.oauth2.id_token as google_id_token

    def _fake_verify(token, request, audience):
        assert audience == "test-client-id.apps.googleusercontent.com"
        if token == "good.token.here":
            return {"email": "owner@example.com", "email_verified": True}
        if token == "unverified.token.here":
            return {"email": "owner@example.com", "email_verified": False}
        if token == "outsider.token.here":
            return {"email": "someone-else@example.com", "email_verified": True}
        raise ValueError("invalid token")

    monkeypatch.setattr(google_id_token, "verify_oauth2_token", _fake_verify)


def test_google_id_token_valid(monkeypatch):
    mod = _load_nougen_remote()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "owner@example.com")
    _stub_google_verify(monkeypatch)

    assert mod._google_id_token_valid("good.token.here") is True
    assert mod._google_id_token_valid("unverified.token.here") is False
    assert mod._google_id_token_valid("outsider.token.here") is False
    assert mod._google_id_token_valid("bad.token.here") is False
    assert mod._google_id_token_valid("not-a-jwt") is False
    assert mod._google_id_token_valid("") is False


def test_google_id_token_valid_fails_closed_without_config(monkeypatch):
    mod = _load_nougen_remote()
    _stub_google_verify(monkeypatch)

    # No client ID configured: even a token the stub would accept is refused.
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("NOUGEN_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "owner@example.com")
    assert mod._google_id_token_valid("good.token.here") is False

    # No allowlist configured: refused as well.
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "")
    assert mod._google_id_token_valid("good.token.here") is False


def test_post_accepts_valid_google_id_token(monkeypatch):
    import importlib
    import sys
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    monkeypatch.setenv("NOUGEN_REMOTE_TOKEN", "test-token-123")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "owner@example.com")
    _stub_google_verify(monkeypatch)
    nr = importlib.reload(importlib.import_module("nougen_remote"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), nr.RemoteHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def post_status(token):
            req = urllib.request.Request(
                base + "/api/v1/chat",
                data=b"{}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                return urllib.request.urlopen(req, timeout=5).status
            except urllib.error.HTTPError as e:
                return e.code

        # Valid Google token passes auth (400 = authed, missing text).
        assert post_status("good.token.here") == 400
        # Invalid Google token is refused before routing.
        assert post_status("bad.token.here") == 401
        # Static token still works.
        assert post_status("test-token-123") == 400
    finally:
        srv.shutdown()
