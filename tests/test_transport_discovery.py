"""transport_discovery: decision table, URL normalization, byte-reading probes (no network)."""
import json
import socket
import ssl
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from nougen_shards import transport_discovery as td

DEF = td.DEFAULT_RELAY_URL


# ------------------------------------------------------------ normalization
@pytest.mark.parametrize("raw,want", [
    ("relay.nougenai.com", DEF),
    ("https://relay.nougenai.com", DEF),
    ("https://relay.nougenai.com/", DEF),
    ("wss://relay.nougenai.com/_relay/connect", DEF),
    ("relay.example.org:8443", "wss://relay.example.org:8443/_relay/connect"),
    ("dave-abc-d334.nougenai.com", DEF),
    ("https://monna-9f3a1c.nougenai.com", DEF),
    ("", DEF),
])
def test_normalize(raw, want):
    assert td.normalize_relay_url(raw)[0] == want


def test_tenant_host_rejected_with_reason():
    url, why = td.normalize_relay_url("dave-abc-d334.nougenai.com")
    assert url == DEF and "per-tenant" in why


def test_resolve_order(tmp_path, monkeypatch):
    ep = tmp_path / "endpoints.json"
    monkeypatch.setenv("NOUGEN_ENDPOINTS_FILE", str(ep))
    assert td.resolve_relay_url({})[0] == DEF
    ep.write_text(json.dumps({"relay_url": "relay.example.org"}))
    url, why = td.resolve_relay_url({})
    assert url == "wss://relay.example.org/_relay/connect" and "endpoints file" in why[0]
    url, why = td.resolve_relay_url({"NOUGEN_RELAY_URL": "https://r2.example.org"})
    assert url == "wss://r2.example.org/_relay/connect" and "env" in why[0]


def test_https_base():
    assert td.relay_https_base(DEF) == "https://relay.nougenai.com"


# ----------------------------------------------------------- decision table
def P(ok, reason="x"):
    return {"ok": ok, "reason": reason}


CASES = [
    # name, tls, dns, relay, observed, want
    ("all good", True, True, True, [], "http2"),
    ("all good + cloudflared quic", True, True, True, ["quic"], "quic"),
    ("quic seen but tls fails", False, True, True, ["quic"], "relay"),
    ("edge only", True, True, False, [], "http2"),
    ("dns ok tls blocked", False, True, True, [], "relay"),
    ("tls ok dns fake", True, False, True, [], "relay"),
    ("nothing", False, False, False, [], "none"),
    ("muse-vm: interceptor, 198.18, relay 401", False, False, True, [], "relay"),
]


@pytest.mark.parametrize("name,tls,dns,relay,obs,want", CASES, ids=[c[0] for c in CASES])
def test_decide_table(name, tls, dns, relay, obs, want):
    probes = {"edge_tls_7844": P(tls), "edge_dns": P(dns), "relay_https": P(relay)}
    d1 = td.decide(probes, DEF, obs)
    d2 = td.decide(dict(reversed(list(probes.items()))), DEF, list(reversed(obs)))
    assert d1["transport"] == want
    assert d1 == d2  # deterministic regardless of input ordering


def test_never_quic_without_observation():
    probes = {k: P(True) for k in td.PROBE_ORDER}
    assert td.decide(probes, DEF, None)["transport"] == "http2"


# ------------------------------------------------------------ fake servers
def _serve_once(handler):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def run():
        try:
            c, _ = srv.accept()
            with c:
                handler(c)
        except OSError:
            pass
        finally:
            srv.close()
    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


def test_tls_probe_rejects_plaintext_interceptor():
    port = _serve_once(lambda c: c.sendall(b"Connection intercepted by sandbox egress proxy\r\n"))
    p = td.probe_edge_tls("127.0.0.1", port, timeout=3)
    assert not p.ok
    assert "non-TLS bytes" in p.reason and "intercepted" in p.reason


def test_tls_probe_interceptor_that_waits_for_client():
    def h(c):
        c.recv(4096)
        c.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\nblocked")
    p = td.probe_edge_tls("127.0.0.1", _serve_once(h), timeout=3)
    assert not p.ok and "HTTP/1.1 403" in p.reason


def test_tls_probe_accepts_real_tls(tmp_path):
    crypto = pytest.importorskip("cryptography")  # noqa: F841
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "edge.test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    cf, kf = tmp_path / "c.pem", tmp_path / "k.pem"
    cf.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    kf.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(cf, kf)

    def h(c):
        try:
            with sctx.wrap_socket(c, server_side=True) as t:
                t.recv(1)
        except (ssl.SSLError, OSError):
            pass
    p = td.probe_edge_tls("127.0.0.1", _serve_once(h), timeout=3)
    assert p.ok, p.reason


def test_tls_probe_connect_refused():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert not td.probe_edge_tls("127.0.0.1", port, timeout=1).ok


def test_dns_probe_flags_fake_ip():
    p = td.probe_edge_dns(srv=lambda n, t: [("region1.v2.argotunnel.com", 7844)],
                          a=lambda h: ["198.18.0.7", "198.19.3.1"])
    assert not p.ok and "198.18.0.0/15" in p.reason


def test_dns_probe_real():
    p = td.probe_edge_dns(srv=lambda n, t: [("region1.v2.argotunnel.com", 7844)],
                          a=lambda h: ["198.41.192.7"])
    assert p.ok


def test_relay_probe_states():
    calls = []

    def status(codes):
        def f(url, hdr, timeout):
            calls.append(hdr)
            return codes["auth" if "Authorization" in hdr else "anon"]
        return f
    p = td.probe_relay(DEF, "n1", "s3cret", http_status=status({"anon": 401, "auth": 200}))
    assert p.ok and p.detail["auth"] == "provisioned" and "s3cret" not in p.reason
    p = td.probe_relay(DEF, "n1", "s3cret", http_status=status({"anon": 401, "auth": 401}))
    assert p.ok and p.detail["auth"] == "missing"
    p = td.probe_relay(DEF, "n1", None, http_status=status({"anon": 404, "auth": 0}))
    assert not p.ok and "404" in p.reason

    def boom(url, hdr, timeout):
        raise ConnectionRefusedError
    assert not td.probe_relay(DEF, "n1", None, http_status=boom).ok


def test_relay_probe_against_fake_http_server():
    def h(c):
        c.recv(4096)
        c.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    port = _serve_once(h)
    p = td.probe_relay(f"ws://127.0.0.1:{port}/_relay/connect", "n1", None, timeout=3)
    assert p.ok, p.reason


# ------------------------------------------------------------------ cache
def _muse(relay_url, node):
    return {
        "edge_tls_7844": {"ok": False, "reason": "non-TLS bytes on 7844: 'Connection intercepted'"},
        "edge_dns": {"ok": False, "reason": "fake-IP answers in 198.18.0.0/15: 198.18.0.7"},
        "relay_https": {"ok": True, "reason": "relay https://relay.nougenai.com live (401 unauthenticated)"},
    }


def test_discover_caches_and_refreshes(tmp_path):
    n = {"count": 0}

    def prober(u, node):
        n["count"] += 1
        return _muse(u, node)
    d = td.discover(tmp_path, env={}, now=1000.0, prober=prober)
    assert d["transport"] == "relay" and not d["cached"]
    assert json.loads((tmp_path / "transport.json").read_text())["transport"] == "relay"
    assert td.discover(tmp_path, env={}, now=1100.0, prober=prober)["cached"]
    assert n["count"] == 1
    td.discover(tmp_path, env={}, now=1100.0, refresh=True, prober=prober)
    td.discover(tmp_path, env={}, now=1100.0, failing=True, prober=prober)
    td.discover(tmp_path, env={}, now=1100.0 + td.CACHE_TTL_S + 1, prober=prober)
    assert n["count"] == 4


def test_http2_writes_supervisor_tunnel_env(tmp_path):
    (tmp_path / "tunnel.env").write_text("TUNNEL_REGION=us\nTUNNEL_TRANSPORT_PROTOCOL=quic\n")
    td.discover(tmp_path, env={}, now=1.0,
                prober=lambda u, node: {k: {"ok": True, "reason": "ok"} for k in td.PROBE_ORDER})
    lines = (tmp_path / "tunnel.env").read_text().splitlines()
    assert lines == ["TUNNEL_REGION=us", "TUNNEL_TRANSPORT_PROTOCOL=http2"]


def test_cli_exit_codes(tmp_path):
    src = str(Path(td.__file__).resolve().parents[1])
    code = ("import sys; sys.path.insert(0, %r); from nougen_shards import transport_discovery as td;"
            "td.run_probes = lambda u, n, **k: {k2: {'ok': False, 'reason': 'x'} for k2 in td.PROBE_ORDER};"
            "td.discover.__defaults__ = (False, False, None, None, None, td.run_probes);"
            "sys.exit(td.main(['--account-dir', %r, '--json']))") % (src, str(tmp_path))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                       env={"NOUGEN_ENDPOINTS_FILE": str(tmp_path / "none.json"), "SYSTEMROOT": "C:\\Windows"})
    assert r.returncode == 2, r.stderr
    assert json.loads(r.stdout)["transport"] == "none"
