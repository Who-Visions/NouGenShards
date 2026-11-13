"""NouGen Relay node client: keep a node reachable when cloudflared cannot get out.

The node dials OUT to ``wss://<relay>/_relay/connect?id=<id>`` on port 443 and holds
that socket open. Requests for the node's public address arrive as JSON frames, are
replayed against the local node (``http://127.0.0.1:<port>``), and the answer goes back
up the same socket.

Works on locked-down networks:
  * honors HTTPS_PROXY / https_proxy / ALL_PROXY and NO_PROXY, tunnelling with HTTP
    CONNECT (Basic proxy auth from the proxy URL's userinfo);
  * honors custom CA bundles: NOUGEN_RELAY_CA_BUNDLE, SSL_CERT_FILE,
    REQUESTS_CA_BUNDLE, CURL_CA_BUNDLE (first one that exists wins);
  * if the system resolver cannot find the relay host and there is no proxy, falls
    back internally to DNS-over-HTTPS. Users never configure this.

Standard library only, so the setup script can run it before anything else is installed.

    python -m nougen_shards.relay_client probe --node-json node.json   # exit 0 = relay live
    python -m nougen_shards.relay_client run   --node-json node.json   # serve forever
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import logging
import os
import random
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.parse
from typing import Callable, Optional

log = logging.getLogger("nougen.relay")

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
HOP = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer", "content-length"}


def _envf(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        v = float(raw) if raw else default
        return v if v > 0 else default
    except ValueError:
        log.warning("ignoring bad %s=%r, using %s", name, raw, default)
        return default


def default_relay_url() -> Optional[str]:
    """Relay URL from NOUGEN_RELAY_URL, else the endpoints file key ``relay_url``.

    node.json's own ``relay_url`` (written at provisioning) takes precedence over both.
    No built-in host: a deployment names its relay, the client never guesses one.
    """
    v = os.environ.get("NOUGEN_RELAY_URL", "").strip()
    if v:
        return v
    try:
        from nougen_shards import endpoints
        return endpoints._from_file("relay_url")
    except ImportError:
        return None


# ------------------------------------------------------------------ proxy / TLS / DNS
def proxy_for(host: str, env: Optional[dict] = None) -> Optional[urllib.parse.SplitResult]:
    env = os.environ if env is None else env
    raw = None
    for k in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        if env.get(k):
            raw = env[k]
            break
    if not raw:
        return None
    no = env.get("NO_PROXY") or env.get("no_proxy") or ""
    h = host.lower()
    for item in (x.strip().lower() for x in no.split(",")):
        if not item:
            continue
        if item == "*" or h == item.lstrip(".") or h.endswith("." + item.lstrip(".")):
            return None
    if "://" not in raw:
        raw = "http://" + raw
    p = urllib.parse.urlsplit(raw)
    if p.scheme not in ("http", "https"):
        log.warning("unsupported proxy scheme %s; trying direct", p.scheme)
        return None
    return p


def ca_bundle(env: Optional[dict] = None) -> Optional[str]:
    env = os.environ if env is None else env
    for k in ("NOUGEN_RELAY_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        v = env.get(k)
        if v and os.path.isfile(v):
            return v
    return None


def tls_context(env: Optional[dict] = None) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    extra = ca_bundle(env)
    if extra:
        ctx.load_verify_locations(cafile=extra)  # added to, not instead of, the system store
    return ctx


DOH_ENDPOINTS = (("1.1.1.1", "cloudflare-dns.com", "/dns-query"), ("8.8.8.8", "dns.google", "/resolve"))


def doh_resolve(host: str, timeout: float = 5.0) -> Optional[str]:
    """Internal fallback only: resolve an A record over HTTPS to a well-known IP."""
    for ip, sni, path in DOH_ENDPOINTS:
        try:
            raw = socket.create_connection((ip, 443), timeout=timeout)
            s = tls_context().wrap_socket(raw, server_hostname=sni)
            conn = http.client.HTTPSConnection(sni, timeout=timeout)
            conn.sock = s
            q = urllib.parse.urlencode({"name": host, "type": "A"})
            conn.request("GET", f"{path}?{q}", headers={"accept": "application/dns-json"})
            data = json.loads(conn.getresponse().read())
            conn.close()
            for a in data.get("Answer", []):
                if a.get("type") == 1:
                    log.info("resolved %s via DoH (%s)", host, sni)
                    return a["data"]
        except Exception as e:  # noqa: BLE001 - try the next endpoint
            log.debug("DoH via %s failed: %s", sni, e)
    return None


def _connect_direct(host: str, port: int, timeout: float, resolver: Callable[[str], Optional[str]]) -> socket.socket:
    try:
        return socket.create_connection((host, port), timeout=timeout)
    except socket.gaierror:
        ip = resolver(host)
        if not ip:
            raise
        return socket.create_connection((ip, port), timeout=timeout)


def open_tunnel(host: str, port: int, timeout: float = 15.0, env: Optional[dict] = None,
                resolver: Callable[[str], Optional[str]] = doh_resolve) -> socket.socket:
    """A TCP socket to host:port: through HTTP CONNECT if a proxy applies, else direct."""
    p = proxy_for(host, env)
    if not p:
        return _connect_direct(host, port, timeout, resolver)
    s = socket.create_connection((p.hostname, p.port or (443 if p.scheme == "https" else 8080)), timeout=timeout)
    if p.scheme == "https":
        s = tls_context(env).wrap_socket(s, server_hostname=p.hostname)
    req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\nUser-Agent: nougen-relay\r\n"
    if p.username:
        cred = f"{urllib.parse.unquote(p.username)}:{urllib.parse.unquote(p.password or '')}"
        req += "Proxy-Authorization: Basic " + base64.b64encode(cred.encode()).decode() + "\r\n"
    s.sendall((req + "\r\n").encode())
    head = _read_head(s)
    status = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    parts = status.split()
    if len(parts) < 2 or parts[1] != "200":
        s.close()
        raise ConnectionError(f"proxy refused CONNECT: {status}")
    return s


def _read_head(s: socket.socket, limit: int = 65536) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf:
        c = s.recv(1)
        if not c:
            raise ConnectionError("connection closed during handshake")
        buf += c
        if len(buf) > limit:
            raise ConnectionError("handshake header too large")
    return buf


# ------------------------------------------------------------------ minimal WebSocket
class WebSocket:
    def __init__(self, sock):
        self.sock = sock
        self.lock = threading.Lock()

    @classmethod
    def connect(cls, url: str, headers: dict, timeout: float = 15.0, env: Optional[dict] = None,
                resolver: Callable[[str], Optional[str]] = doh_resolve) -> "WebSocket":
        u = urllib.parse.urlsplit(url)
        secure = u.scheme == "wss"
        port = u.port or (443 if secure else 80)
        raw = open_tunnel(u.hostname, port, timeout, env, resolver)
        sock = tls_context(env).wrap_socket(raw, server_hostname=u.hostname) if secure else raw
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + (("?" + u.query) if u.query else "")
        host = u.hostname if u.port in (None, 443, 80) else f"{u.hostname}:{u.port}"
        lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket", "Connection: Upgrade",
                 f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13", "User-Agent: nougen-relay"]
        lines += [f"{k}: {v}" for k, v in headers.items()]
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        head = _read_head(sock).decode("latin-1", "replace")
        status = head.split("\r\n", 1)[0]
        if " 101 " not in status + " ":
            sock.close()
            raise PermissionError(status) if (" 401" in status or " 403" in status) else ConnectionError(status)
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if accept.lower() not in head.lower():
            sock.close()
            raise ConnectionError("bad Sec-WebSocket-Accept")
        sock.settimeout(None)
        return cls(sock)

    def _send(self, opcode: int, data: bytes) -> None:
        n = len(data)
        hdr = bytes([0x80 | opcode])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack("!Q", n)
        mask = os.urandom(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(data)) if n < 4096 else _mask_fast(data, mask)
        with self.lock:
            self.sock.sendall(hdr + mask + body)

    def send_text(self, s: str) -> None:
        self._send(0x1, s.encode())

    def close(self, code: int = 1000) -> None:
        try:
            self._send(0x8, struct.pack("!H", code))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            c = self.sock.recv(n - len(buf))
            if not c:
                raise ConnectionError("socket closed")
            buf += c
        return buf

    def recv(self) -> Optional[str]:
        """Next text/binary message as str; None on close. Answers pings itself."""
        parts: list[bytes] = []
        while True:
            b1, b2 = self._exact(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._exact(8))[0]
            mask = self._exact(4) if b2 & 0x80 else None
            data = self._exact(n) if n else b""
            if mask:
                data = _mask_fast(data, mask)
            if op == 0x8:
                return None
            if op == 0x9:
                self._send(0xA, data)
                continue
            if op == 0xA:
                continue
            parts.append(data)
            if b1 & 0x80:
                return b"".join(parts).decode("utf-8", "replace")


def _mask_fast(data: bytes, mask: bytes) -> bytes:
    n = len(data)
    m = int.from_bytes((mask * (n // 4 + 1))[:n], "big") if n else 0
    return (int.from_bytes(data, "big") ^ m).to_bytes(n, "big") if n else b""


# ------------------------------------------------------------------ client
class RelayClient:
    def __init__(self, relay_url: str, node_id: str, token: str, local_port: int,
                 local_host: str = "127.0.0.1", env: Optional[dict] = None,
                 heartbeat: Optional[float] = None, backoff_max: Optional[float] = None):
        sep = "&" if "?" in relay_url else "?"
        self.url = f"{relay_url}{sep}id={urllib.parse.quote(node_id)}"
        self.node_id, self.token = node_id, token
        self.local = (local_host, local_port)
        self.env = env
        self.heartbeat = heartbeat or _envf("NOUGEN_RELAY_HEARTBEAT_S", 20.0)
        self.backoff_max = backoff_max or _envf("NOUGEN_RELAY_BACKOFF_MAX_S", 60.0)
        self.stop = threading.Event()
        self.connected = threading.Event()
        self.ws: Optional[WebSocket] = None
        self.last_rx = 0.0
        self.sessions = 0

    def dial(self, timeout: float = 15.0) -> WebSocket:
        ws = WebSocket.connect(self.url, {"Authorization": f"Bearer {self.token}"}, timeout, self.env)
        ws.sock.settimeout(self.heartbeat * 3)
        first = ws.recv()
        f = json.loads(first or "{}")
        if f.get("t") != "ready":
            ws.close()
            raise ConnectionError(f"relay did not say ready: {first!r}")
        return ws

    def _beat(self, ws: WebSocket) -> None:
        while not self.stop.wait(self.heartbeat) and self.ws is ws:
            try:
                ws.send_text('{"t":"ping"}')
            except OSError:
                return

    def _handle(self, ws: WebSocket, f: dict) -> None:
        try:
            conn = http.client.HTTPConnection(*self.local, timeout=_envf("NOUGEN_RELAY_LOCAL_TIMEOUT_S", 25.0))
            hdrs = {k: v for k, v in (f.get("headers") or {}).items() if k.lower() not in HOP}
            conn.request(f.get("method", "GET"), f.get("path", "/"), base64.b64decode(f.get("body") or ""), hdrs)
            r = conn.getresponse()
            body = r.read()
            out_h: dict = {}
            for k, v in r.getheaders():
                if k.lower() not in HOP:
                    out_h[k] = f"{out_h[k]}, {v}" if k in out_h and k.lower() != "set-cookie" else v
            res = {"t": "res", "rid": f.get("rid"), "status": r.status, "headers": out_h,
                   "body": base64.b64encode(body).decode()}
            conn.close()
        except Exception as e:  # noqa: BLE001 - the caller gets a 502, the node keeps running
            res = {"t": "res", "rid": f.get("rid"), "status": 502, "headers": {"content-type": "text/plain"},
                   "body": base64.b64encode(f"local node error: {e}".encode()).decode()}
        try:
            ws.send_text(json.dumps(res))
        except OSError:
            pass

    def serve_once(self, ws: WebSocket) -> None:
        self.ws = ws
        self.sessions += 1
        self.connected.set()
        threading.Thread(target=self._beat, args=(ws,), daemon=True).start()
        try:
            while not self.stop.is_set():
                msg = ws.recv()  # times out after 3 missed heartbeats -> reconnect
                if msg is None:
                    return
                self.last_rx = time.time()
                f = json.loads(msg)
                if f.get("t") == "req":
                    threading.Thread(target=self._handle, args=(ws, f), daemon=True).start()
        finally:
            self.connected.clear()
            self.ws = None
            ws.close()

    def run(self) -> None:
        delay = 1.0
        while not self.stop.is_set():
            started = time.time()
            try:
                ws = self.dial()
                log.info("relay connected for %s", self.node_id)
                self.serve_once(ws)
                log.info("relay disconnected")
            except PermissionError as e:
                log.error("relay rejected this node's token (%s); retrying slowly", e)
                delay = self.backoff_max
            except (OSError, ConnectionError, ValueError, ssl.SSLError) as e:
                log.warning("relay connect failed: %s", e)
            if self.stop.is_set():
                break
            if time.time() - started > 60:
                delay = 1.0  # it was a healthy session; come back fast
            wait = min(self.backoff_max, delay) * (0.5 + random.random() / 2)
            self.stop.wait(wait)
            delay = min(self.backoff_max, delay * 2)


def _load_node(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="nougen-relay")
    ap.add_argument("cmd", choices=["run", "probe"])
    ap.add_argument("--node-json", default=os.environ.get("NOUGEN_NODE_JSON", "node.json"))
    ap.add_argument("--relay-url", default=None)
    ap.add_argument("--timeout", type=float, default=_envf("NOUGEN_RELAY_PROBE_TIMEOUT_S", 20.0))
    a = ap.parse_args(argv)
    logging.basicConfig(level=os.environ.get("NOUGEN_RELAY_LOG", "INFO"), format="%(asctime)s relay %(message)s")
    n = _load_node(a.node_json)
    url = a.relay_url or n.get("relay_url") or default_relay_url()
    if not url:
        print("relay: unavailable (no relay_url in node.json, NOUGEN_RELAY_URL or endpoints file)")
        return 2
    c = RelayClient(url, str(n["id"]).lower(),
                    str(n["token"]), int(n["port"]))
    if a.cmd == "probe":
        try:
            c.dial(a.timeout).close()
            print("relay: live")
            return 0
        except Exception as e:  # noqa: BLE001
            print(f"relay: unavailable ({e})")
            return 2
    try:
        c.run()
    except KeyboardInterrupt:
        c.stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
