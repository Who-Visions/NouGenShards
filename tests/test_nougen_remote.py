"""Tests for NouGenRemote Pro iPhone 14 Cockpit & Direct Antigravity Injection."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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


def test_google_id_token_post_verification_cache_and_header_only_policy(monkeypatch):
    """Google ID tokens are verified via POST to tokeninfo (iss, aud, exp, email_verified, allowlist),
    cached by SHA-256 up to min(TTL, exp) with expired-entry eviction, and accepted only in the
    Authorization header across both GET and POST routes."""
    import hashlib
    import importlib
    import io
    import sys
    import threading
    import time
    import urllib.error
    import urllib.parse
    import urllib.request
    from http.server import ThreadingHTTPServer
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    monkeypatch.setenv("NOUGEN_REMOTE_TOKEN", "test-token-123")
    monkeypatch.setenv("NOUGEN_GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("NOUGEN_GOOGLE_ALLOWED_EMAILS", "owner@example.com")
    nr = importlib.reload(importlib.import_module("nougen_remote"))

    real_urlopen = urllib.request.urlopen
    now = time.time()

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, *a, **kw):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url == "https://oauth2.googleapis.com/tokeninfo":
            assert req.get_method() == "POST"
            form = urllib.parse.parse_qs((req.data or b"").decode("utf-8"))
            tok = (form.get("id_token") or [""])[0]
            if tok == "good.token.here":
                body = {
                    "iss": "https://accounts.google.com",
                    "aud": "test-client-id.apps.googleusercontent.com",
                    "email": "owner@example.com",
                    "email_verified": "true",
                    "exp": str(int(now + 60)),
                }
                return _Resp(json.dumps(body).encode())
            if tok == "wrong.iss.token":
                body = {
                    "iss": "https://evil.example.com",
                    "aud": "test-client-id.apps.googleusercontent.com",
                    "email": "owner@example.com",
                    "email_verified": "true",
                    "exp": str(int(now + 60)),
                }
                return _Resp(json.dumps(body).encode())
            if tok == "expired.token.here":
                body = {
                    "iss": "accounts.google.com",
                    "aud": "test-client-id.apps.googleusercontent.com",
                    "email": "owner@example.com",
                    "email_verified": "true",
                    "exp": str(int(now - 5)),
                }
                return _Resp(json.dumps(body).encode())
            raise urllib.error.HTTPError(url, 400, "invalid", {}, None)
        return real_urlopen(req, *a, **kw)

    monkeypatch.setattr(nr.urllib.request, "urlopen", fake_urlopen)

    # Pre-seed an expired entry to verify eviction and sha256 keying
    nr._google_token_cache["stale_hash"] = now - 10
    assert nr._google_id_token_valid("wrong.iss.token") is False
    assert nr._google_id_token_valid("expired.token.here") is False
    assert "stale_hash" not in nr._google_token_cache

    assert nr._google_id_token_valid("good.token.here") is True
    good_hash = hashlib.sha256(b"good.token.here").hexdigest()
    assert good_hash in nr._google_token_cache
    assert "good.token.here" not in nr._google_token_cache
    assert nr._google_token_cache[good_hash] <= now + 60

    srv = ThreadingHTTPServer(("127.0.0.1", 0), nr.RemoteHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def req_status(path, headers=None, data=None, method="GET"):
        req = urllib.request.Request(base + path, data=data, headers=headers or {}, method=method)
        try:
            return real_urlopen(req, timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code

    try:
        # Query string Google token refused
        assert req_status("/api/v1/inbox?token=good.token.here") == 401
        # Query string + valid Authorization header fails closed when query token is not static TOKEN
        assert req_status("/api/v1/inbox?token=bad", {"Authorization": "Bearer good.token.here"}) == 401
        # Valid Google token in Authorization header succeeds on GET
        assert req_status("/api/v1/inbox", {"Authorization": "Bearer good.token.here"}) == 200
        # Valid Google token in Authorization header succeeds on POST (400 = authed, missing text)
        assert req_status(
            "/api/v1/inject_agy",
            {"Authorization": "Bearer good.token.here", "Content-Type": "application/json"},
            data=b"{}",
            method="POST",
        ) == 400
        # Google token in POST JSON body refused
        assert req_status(
            "/api/v1/inject_agy",
            {"Content-Type": "application/json"},
            data=b'{"token":"good.token.here"}',
            method="POST",
        ) == 401
    finally:
        srv.shutdown()

