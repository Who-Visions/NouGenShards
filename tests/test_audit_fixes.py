"""Regression tests for the deep-dive audit fixes (branch: deep-dive-atom-audit).

Covers the secret-leak, validation, billing, context-timestamp and SSRF-guard
fixes. Each test pins behavior that was previously wrong, so a regression is
caught rather than silently reintroduced.
"""
import json

import pytest

from nougen_shards.brain_scan.redaction import redact_content
from nougen_shards import structured
from nougen_shards import nougen_context
from nougen_shards.connectors import cloud


# --- redaction (C5/C6) -------------------------------------------------------

@pytest.mark.parametrize("secret", [
    "sk-proj-abcDEF123456_ghJKL-mnopQRST7890uvwx",   # modern OpenAI project key
    "sk-svcacct-ABCdef1234567890ghijKLMNOP_qrst",     # service-account key
    "ASIAABCDEFGHIJKLMNOP",                            # AWS STS temp creds
    "postgres://user:s3cret@db.internal:5432",         # DB url with no path
    "redis://default:hunter2@cache:6379",              # broker url
    "postgresql+psycopg2://user:pass@host:5432/db",    # SQLAlchemy +driver form
    "mysql+pymysql://u:p@h/d",
])
def test_redaction_covers_modern_secret_forms(secret):
    out = redact_content(f"value = {secret}")
    assert "REDACTED" in out
    assert secret not in out


def test_nougen_token_redaction_keeps_json_valid():
    # The old pattern consumed the leading delimiter and broke surrounding JSON.
    out = redact_content('{"a":"nougen_fleet_token_AB12cd34","b":"x"}')
    assert "nougen_fleet_token" not in out
    json.loads(out)  # must still parse


def test_truncated_private_key_is_redacted():
    clipped = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAA...cut"
    assert "REDACTED" in redact_content(clipped)


# --- structured validation (bool-as-number) ---------------------------------

def test_bool_is_rejected_for_int_and_number():
    schema = {"properties": {"n": {"type": "integer"}, "x": {"type": "number"}}}
    valid, errors = structured.validate_against_schema({"n": True, "x": False}, schema)
    assert not valid
    assert len(errors) == 2


def test_real_numbers_still_validate():
    schema = {"properties": {"n": {"type": "integer"}, "x": {"type": "number"}}}
    valid, _ = structured.validate_against_schema({"n": 5, "x": 2.5}, schema)
    assert valid


# --- context timestamp (C7) --------------------------------------------------

def test_context_timestamp_is_valid_iso():
    ts = nougen_context._utc_now_iso()
    assert ts.endswith("Z") and "+00:00" not in ts
    # round-trips through fromisoformat
    from datetime import datetime
    datetime.fromisoformat(ts.replace("Z", "+00:00"))


def test_init_context_db_default_is_non_destructive():
    import inspect
    assert inspect.signature(nougen_context.init_context_db).parameters["clean_slate"].default is False


# --- SSRF guard (connectors) -------------------------------------------------

# --- models_client network timeouts + Gemini key (C4) ----------------------

def test_http_timeout_is_positive():
    from nougen_shards import models_client
    t = getattr(models_client, "_HTTP_TIMEOUT", getattr(models_client, "DEFAULT_TIMEOUT", None))
    assert isinstance(t, (int, float)) and t > 0


def test_no_timeout_less_urlopen_in_source():
    # Every request urlopen must carry a timeout; the Gemini key must not sit in
    # the URL query string. Guard at the source level so a regression is caught.
    import pathlib
    src = pathlib.Path("src/nougen_shards/models_client.py").read_text()
    assert "urlopen(req)" not in src, "found a urlopen without a timeout"
    assert "?key=" not in src, "Gemini API key is back in the URL query string"
    assert src.count("x-goog-api-key") == 3


# --- SSRF guard (connectors) -------------------------------------------------

@pytest.mark.parametrize("url,safe", [
    ("https://node.whovisions.com", True),
    ("http://127.0.0.1:4444", True),
    ("http://localhost:4444", True),
    ("http://evil.example.com", False),   # plaintext to remote leaks token
    ("file:///etc/passwd", False),
    ("gopher://internal:70/x", False),
    ("https://169.254.169.254/latest/meta-data/", False),  # cloud metadata SSRF
    ("https://224.0.0.1", False),         # multicast
    ("https://10.0.0.5", True),           # private LAN node allowed
    ("https://", False),
    ("not a url", False),
])
def test_cloud_url_guard(url, safe):
    assert cloud._is_safe_cloud_url(url) is safe


def test_cloud_url_guard_resolves_hostnames(monkeypatch):
    import socket
    # A hostname that resolves to the cloud-metadata IP must be rejected even
    # though it is not an IP literal (DNS-based SSRF bypass).
    def fake_getaddrinfo(host, port, *a, **k):
        ip = "169.254.169.254" if host == "metadata.evil" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert cloud._is_safe_cloud_url("https://metadata.evil/") is False
    assert cloud._is_safe_cloud_url("https://safe.example/") is True


def test_cloud_url_guard_rejects_loopback_dns_alias(monkeypatch):
    import socket
    # A non-local hostname that resolves to loopback is a DNS alias to a
    # loopback-only service — must be rejected (would leak X-NGS-Token).
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda h, p, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", p))])
    assert cloud._is_safe_cloud_url("http://evil.example:8080") is False
    # explicit loopback literal/name still allowed
    assert cloud._is_safe_cloud_url("http://127.0.0.1:4444") is True
    assert cloud._is_safe_cloud_url("http://localhost:4444") is True


@pytest.mark.parametrize("url", ["https://host:bad", "https://host:999999"])
def test_cloud_url_guard_rejects_malformed_port_without_raising(url):
    # parsed.port raises ValueError on a bad port; the guard must return False,
    # not crash the caller (it runs outside push/pull's network-error try).
    assert cloud._is_safe_cloud_url(url) is False


def test_find_best_model_skips_embedding_only():
    # find_best_edge_model feeds the default chat model; an embedding model must
    # not be chosen over an installed chat model.
    from nougen_shards.models_client import find_best_model_from_list
    cfg = find_best_model_from_list(["gemma4:12b", "nomic-embed-text:latest"])
    assert cfg.model_name == "gemma4:12b"


def test_search_context_fallback_keeps_fts_schema(tmp_path, monkeypatch):
    # An FTS-breaking query ('c++') must fall back to LIKE but return the SAME
    # keys as the FTS path (type/content, not event_type/description).
    monkeypatch.setattr(nougen_context, "SESSION_DB_PATH", str(tmp_path / "session.db"))
    nougen_context.init_context_db(clean_slate=True)
    nougen_context.log_event("EDIT", "working on c++ parser")
    rows = nougen_context.search_context("c++")
    assert rows
    assert {"id", "timestamp", "type", "content", "metadata"}.issubset(rows[0].keys())
    assert "event_type" not in rows[0] and "description" not in rows[0]


def test_detect_agent_prefers_claude_cli_over_stray_gemini_key(monkeypatch):
    from nougen_shards import handoff
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("NOUGEN_AGENT", raising=False)
    assert handoff.detect_current_agent() == "claude-cli"


def test_cloud_request_pins_validated_ip(monkeypatch):
    import socket
    # _pinned_ip_for returns the validated resolved IP for a hostname (to pin),
    # and _pin_dns forces getaddrinfo to that IP for the duration of the request.
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda h, p, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", p))])
    assert cloud._pinned_ip_for("https://node.example") == "93.184.216.34"
    assert cloud._pinned_ip_for("https://1.2.3.4") is None        # IP literal: no pin
    assert cloud._pinned_ip_for("http://localhost:4444") is None  # loopback name: no pin
    real = socket.getaddrinfo
    with cloud._pin_dns("node.example", "203.0.113.7"):
        assert [x[4][0] for x in socket.getaddrinfo("node.example", 443)] == ["203.0.113.7"]
    assert socket.getaddrinfo is real  # restored on exit


def test_open_cloud_refuses_hostname_when_pin_fails(monkeypatch):
    import socket, urllib.request, urllib.error
    # Hostname that resolves ONLY to metadata -> _pinned_ip_for returns None.
    # _open_cloud must refuse (raise) instead of re-resolving the hostname unpinned.
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda h, p, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", p))])
    req = urllib.request.Request("https://evil.host/x")
    with pytest.raises(urllib.error.URLError):
        cloud._open_cloud(req, "https://evil.host/x", 5.0)
