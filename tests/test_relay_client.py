"""NouGen Relay node client against a mock HTTP CONNECT proxy and a TLS relay with a private CA."""
import base64
import datetime
import hashlib
import http.server
import json
import os
import socket
import socketserver
import ssl
import struct
import threading
import time

import pytest

cryptography = pytest.importorskip("cryptography")
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from nougen_shards import relay_client as rc  # noqa: E402

TOKEN = "tok-" + "x" * 20
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    d = tmp_path_factory.mktemp("pki")
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NouGen Test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(1).not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "relay.test")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(2)
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("relay.test")]), critical=False).sign(ca_key, hashes.SHA256()))
    (d / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (d / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (d / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return d


def _frame(text: str) -> bytes:
    b = text.encode()
    n = len(b)
    if n < 126:
        return bytes([0x81, n]) + b
    if n < 65536:
        return bytes([0x81, 126]) + struct.pack("!H", n) + b
    return bytes([0x81, 127]) + struct.pack("!Q", n) + b


class FakeRelay:
    """TLS WebSocket server speaking the relay protocol (server side)."""

    def __init__(self, pki):
        self.ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        self.ctx.load_cert_chain(pki / "cert.pem", pki / "key.pem")
        self.srv = socket.create_server(("127.0.0.1", 0))
        self.port = self.srv.getsockname()[1]
        self.sessions, self.pings, self.auth = [], 0, []
        self.drop_first = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                raw, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._session, args=(raw,), daemon=True).start()

    def _session(self, raw):
        try:
            s = self.ctx.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError):
            raw.close()
            return
        head = rc._read_head(s).decode()
        lines = dict(l.split(": ", 1) for l in head.split("\r\n")[1:] if ": " in l)
        self.auth.append(lines.get("Authorization"))
        if lines.get("Authorization") != f"Bearer {TOKEN}":
            s.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")
            s.close()
            return
        acc = base64.b64encode(hashlib.sha1((lines["Sec-WebSocket-Key"] + GUID).encode()).digest()).decode()
        s.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n".encode())
        s.sendall(_frame('{"t":"ready","v":1}'))
        ws = rc.WebSocket(s)
        sess = {"ws": ws, "res": {}, "event": threading.Event()}
        self.sessions.append(sess)
        if self.drop_first and len(self.sessions) == 1:
            s.close()
            return
        try:
            while True:
                m = ws.recv()
                if m is None:
                    return
                f = json.loads(m)
                if f["t"] == "ping":
                    self.pings += 1
                elif f["t"] == "res":
                    sess["res"][f["rid"]] = f
                    sess["event"].set()
        except (OSError, ConnectionError):
            return

    def request(self, path, method="GET", body=b"", timeout=5):
        sess = self.sessions[-1]
        sess["event"].clear()
        sess["ws"].sock.sendall(_frame(json.dumps({"t": "req", "rid": "r1", "method": method, "path": path,
                                                   "headers": {"x-test": "1"}, "body": base64.b64encode(body).decode()})))
        assert sess["event"].wait(timeout), "node never answered"
        return sess["res"]["r1"]


class MockProxy:
    """HTTP CONNECT proxy; records every CONNECT target and pipes bytes both ways."""

    def __init__(self, require_auth=None):
        self.connects, self.require_auth = [], require_auth
        self.srv = socket.create_server(("127.0.0.1", 0))
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(c,), daemon=True).start()

    def _handle(self, c):
        head = rc._read_head(c).decode()
        first = head.split("\r\n")[0].split()
        if first[0] != "CONNECT":
            c.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return c.close()
        if self.require_auth and f"Proxy-Authorization: Basic {self.require_auth}" not in head:
            c.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
            return c.close()
        self.connects.append(first[1])
        _, port = first[1].rsplit(":", 1)
        up = socket.create_connection(("127.0.0.1", int(os.environ.get("_RELAY_TEST_UPSTREAM", port))))
        c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        for a, b in ((c, up), (up, c)):
            threading.Thread(target=self._pipe, args=(a, b), daemon=True).start()

    @staticmethod
    def _pipe(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except OSError:
            pass
        for x in (a, b):
            try:
                x.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


@pytest.fixture(scope="module")
def local_node():
    class H(http.server.BaseHTTPRequestHandler):
        def _go(self):
            n = int(self.headers.get("content-length") or 0)
            body = json.dumps({"method": self.command, "path": self.path, "x": self.headers.get("x-test"),
                               "body": self.rfile.read(n).decode()}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = _go

        def log_message(self, *a):
            pass
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def _env(proxy_port, pki, **extra):
    e = {"HTTPS_PROXY": f"http://127.0.0.1:{proxy_port}", "NOUGEN_RELAY_CA_BUNDLE": str(pki / "ca.pem")}
    e.update(extra)
    return e


def _client(relay, env, node_port, **kw):
    # relay.test is not resolvable: only the proxy can reach it (like the proxy-only VM).
    os.environ["_RELAY_TEST_UPSTREAM"] = str(relay.port)
    return rc.RelayClient("wss://relay.test/_relay/connect", "alice", TOKEN, node_port, env=env, **kw)


def test_proxy_selection_honors_no_proxy():
    env = {"https_proxy": "proxy.corp:3128", "NO_PROXY": "localhost,.internal"}
    assert rc.proxy_for("relay.nougenai.com", env).hostname == "proxy.corp"
    assert rc.proxy_for("a.internal", env) is None
    assert rc.proxy_for("x", {}) is None


def test_requests_flow_through_connect_proxy_with_custom_ca(pki, local_node):
    relay, proxy = FakeRelay(pki), MockProxy()
    c = _client(relay, _env(proxy.port, pki), local_node, heartbeat=0.2)
    threading.Thread(target=c.run, daemon=True).start()
    assert c.connected.wait(5)
    assert proxy.connects == ["relay.test:443"]
    res = relay.request("/api/x?q=1", "POST", b"hello")
    assert res["status"] == 200
    got = json.loads(base64.b64decode(res["body"]))
    assert got == {"method": "POST", "path": "/api/x?q=1", "x": "1", "body": "hello"}
    time.sleep(0.7)
    assert relay.pings >= 2, "heartbeat not sent"
    c.stop.set()


def test_untrusted_ca_is_refused(pki, local_node):
    relay, proxy = FakeRelay(pki), MockProxy()
    c = _client(relay, {"HTTPS_PROXY": f"http://127.0.0.1:{proxy.port}"}, local_node)
    with pytest.raises(ssl.SSLError):
        c.dial(5)


def test_proxy_auth_from_url_userinfo(pki, local_node):
    relay, proxy = FakeRelay(pki), MockProxy(require_auth=base64.b64encode(b"bob:s3cr t").decode())
    env = _env(0, pki, HTTPS_PROXY=f"http://bob:s3cr%20t@127.0.0.1:{proxy.port}")
    _client(relay, env, local_node).dial(5).close()
    assert proxy.connects == ["relay.test:443"]


def test_bad_token_is_permission_error(pki, local_node):
    relay, proxy = FakeRelay(pki), MockProxy()
    c = _client(relay, _env(proxy.port, pki), local_node)
    c.token = "wrong"
    with pytest.raises(PermissionError):
        c.dial(5)


def test_reconnects_with_backoff_after_drop(pki, local_node):
    relay, proxy = FakeRelay(pki), MockProxy()
    relay.drop_first = True
    c = _client(relay, _env(proxy.port, pki), local_node, heartbeat=0.3, backoff_max=0.5)
    threading.Thread(target=c.run, daemon=True).start()
    deadline = time.time() + 8
    while c.sessions < 2 and time.time() < deadline:
        time.sleep(0.05)
    assert c.sessions >= 2 and c.connected.wait(3)
    assert json.loads(base64.b64decode(relay.request("/health")["body"]))["path"] == "/health"
    c.stop.set()


def test_local_node_down_returns_502(pki):
    relay, proxy = FakeRelay(pki), MockProxy()
    dead = socket.create_server(("127.0.0.1", 0))
    port = dead.getsockname()[1]
    dead.close()
    c = _client(relay, _env(proxy.port, pki), port)
    threading.Thread(target=c.run, daemon=True).start()
    assert c.connected.wait(5)
    assert relay.request("/x")["status"] == 502
    c.stop.set()


def test_dns_failure_without_proxy_uses_internal_resolver(pki, local_node):
    relay = FakeRelay(pki)
    asked = []
    sock = rc.open_tunnel("relay.invalid", relay.port, 5, {}, resolver=lambda h: asked.append(h) or "127.0.0.1")
    sock.close()
    assert asked == ["relay.invalid"]


def test_probe_cli_exit_codes(pki, local_node, tmp_path, monkeypatch, capsys):
    relay, proxy = FakeRelay(pki), MockProxy()
    os.environ["_RELAY_TEST_UPSTREAM"] = str(relay.port)
    nj = tmp_path / "node.json"
    nj.write_text(json.dumps({"id": "Alice", "port": local_node, "token": TOKEN, "relay_url": "wss://relay.test/_relay/connect"}))
    for k, v in _env(proxy.port, pki).items():
        monkeypatch.setenv(k, v)
    assert rc.main(["probe", "--node-json", str(nj), "--timeout", "5"]) == 0
    nj.write_text(json.dumps({"id": "alice", "port": local_node, "token": "bad", "relay_url": "wss://relay.test/_relay/connect"}))
    assert rc.main(["probe", "--node-json", str(nj), "--timeout", "5"]) == 2
    assert "unavailable" in capsys.readouterr().out
