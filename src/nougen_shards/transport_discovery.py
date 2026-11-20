"""Runtime transport discovery: how does this node reach the public internet?

One canonical answer per account, worked out by probes that READ BYTES (a TCP
connect that succeeds proves nothing: a sandbox interceptor accepts the socket
and answers in plain text). The decision is a pure function of the probe
results, so the same evidence always yields the same transport.

Order (documented, fixed): quic -> http2 -> relay -> none.

- quic   only when cloudflared itself has already reported a quic connection
         (Python cannot test QUIC/UDP to the edge).
- http2  when edge DNS resolves to real addresses AND a real TLS handshake to
         the edge on 7844 completes.
- relay  when the relay answers ``/_relay/status`` (401 unauthenticated = live).
- none   otherwise.

The result is cached in ``<account dir>/transport.json`` and mirrored into the
``TUNNEL_TRANSPORT_PROTOCOL`` key of ``tunnel.env``, the file the supervisor
already reads (tools/nougen-supervisor/supervisor.go ``tunnelEnv``).
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import select
import socket
import ssl
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

# The product domain, same fallback tenant_onboard uses; a deployment overrides
# it with NOUGEN_TENANT_DOMAIN. The relay lives at relay.<domain>.
FALLBACK_DOMAIN = "nougenai.com"
PRODUCT_DOMAIN = (os.environ.get("NOUGEN_TENANT_DOMAIN") or FALLBACK_DOMAIN).strip().lower()
DEFAULT_RELAY_URL = f"wss://relay.{PRODUCT_DOMAIN}/_relay/connect"
RELAY_PATH = "/_relay/connect"
EDGE_SRV = "_v2-origintunneld._tcp.argotunnel.com"
EDGE_FALLBACK_HOST = "region1.v2.argotunnel.com"
EDGE_PORT = 7844
PROBE_TIMEOUT_S = 5.0
EARLY_BYTES_WAIT_S = 0.3
CACHE_TTL_S = 15 * 60
FAKE_IP_NET = ipaddress.ip_network("198.18.0.0/15")
_TENANT_HOST = re.compile(r"^[a-z0-9-]+-[0-9a-f]{3,}\." + re.escape(PRODUCT_DOMAIN) + "$", re.I)
PROBE_ORDER = ("edge_tls_7844", "edge_dns", "relay_https")
TRANSPORTS = ("quic", "http2", "relay", "none")


# --------------------------------------------------------------- relay_url
def resolve_relay_url(env: Optional[dict] = None, node: Optional[dict] = None) -> tuple[str, list[str]]:
    """Canonical relay URL plus the reasons behind it.

    Order: env NOUGEN_RELAY_URL, then the endpoints-file key ``relay_url``
    (both via relay_client.default_relay_url, the one existing loader), then
    node.json ``relay_url``, then DEFAULT_RELAY_URL.
    """
    reasons: list[str] = []
    raw, source = None, None
    if env is None:
        # The existing loader: env NOUGEN_RELAY_URL, then the endpoints file.
        from nougen_shards import relay_client
        raw = relay_client.default_relay_url()
        source = ("env NOUGEN_RELAY_URL" if os.environ.get("NOUGEN_RELAY_URL", "").strip()
                  else "endpoints file relay_url")
    else:
        v = str(env.get("NOUGEN_RELAY_URL", "") or "").strip()
        if v:
            raw, source = v, "env NOUGEN_RELAY_URL"
        else:
            from nougen_shards import endpoints
            raw, source = endpoints._from_file("relay_url"), "endpoints file relay_url"
    if not raw and node and node.get("relay_url"):
        raw, source = str(node["relay_url"]), "node.json relay_url"
    if not raw:
        return DEFAULT_RELAY_URL, ["relay_url: built-in default"]
    url, why = normalize_relay_url(raw)
    reasons.append(f"relay_url: from {source}" + (f" ({why})" if why else ""))
    return url, reasons


def normalize_relay_url(raw: str) -> tuple[str, Optional[str]]:
    """Bare host / https:// / ws(s):// -> ``wss://<host>/_relay/connect``.

    Per-tenant hosts (``*-<hex>.nougenai.com``) are not relays: fall back to the
    default and say why.
    """
    s = (raw or "").strip()
    if not s:
        return DEFAULT_RELAY_URL, "empty, using default"
    if "://" not in s:
        s = "wss://" + s
    p = urllib.parse.urlsplit(s)
    host = (p.hostname or "").lower()
    if not host:
        return DEFAULT_RELAY_URL, f"no host in {raw!r}, using default"
    if _TENANT_HOST.match(host):
        return DEFAULT_RELAY_URL, f"rejected per-tenant host {host}, using default"
    port = f":{p.port}" if p.port else ""
    path = p.path if p.path and p.path != "/" else RELAY_PATH
    if p.scheme in ("http", "ws") and host in ("localhost", "127.0.0.1"):
        scheme = "ws"
    else:
        scheme = "wss"
    out = f"{scheme}://{host}{port}{path}"
    return out, (None if out == s else f"normalized {raw!r}")


def relay_https_base(relay_url: str) -> str:
    p = urllib.parse.urlsplit(relay_url)
    scheme = "http" if p.scheme == "ws" else "https"
    return f"{scheme}://{p.netloc}"


# ------------------------------------------------------------------ probes
@dataclass
class Probe:
    ok: bool
    reason: str
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "reason": self.reason, **self.detail}


def _printable(b: bytes, n: int = 64) -> str:
    return b[:n].decode("latin-1").encode("unicode_escape").decode("ascii")


def probe_edge_tls(host: str, port: int = EDGE_PORT, timeout: float = PROBE_TIMEOUT_S,
                   server_name: str = EDGE_FALLBACK_HOST,
                   ctx: Optional[ssl.SSLContext] = None) -> Probe:
    """TCP connect, then a real TLS handshake driven over memory BIOs.

    Every byte the server sends passes through our hands first, so non-TLS
    bytes (an interceptor's plain-text notice) fail the probe and are quoted.
    """
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        return Probe(False, f"tcp connect {host}:{port} failed: {e.__class__.__name__}")
    if ctx is None:
        ctx = ssl.create_default_context()
        # Proving "this is a TLS speaker", not authenticating the edge's origin CA.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    inc, out = ssl.MemoryBIO(), ssl.MemoryBIO()
    obj = ctx.wrap_bio(inc, out, server_hostname=server_name)
    first = b""
    try:
        sock.settimeout(timeout)
        # Interceptors often talk first (and hang up); a TLS server never does.
        readable, _, _ = select.select([sock], [], [], min(EARLY_BYTES_WAIT_S, timeout))
        if readable:
            early = sock.recv(4096)
            if not early:
                return Probe(False, f"connection closed before TLS handshake on {port}")
            first = early[:64]
            if first[0] != 0x16:
                return Probe(False, f"non-TLS bytes on {port}: {_printable(first)!r}")
            inc.write(early)
        while True:
            try:
                obj.do_handshake()
                break
            except ssl.SSLWantReadError:
                pending = out.read()
                if pending:
                    sock.sendall(pending)
                data = sock.recv(4096)
                if not data:
                    tail = f": {_printable(first)!r}" if first else ""
                    return Probe(False, f"connection closed during TLS handshake on {port}{tail}")
                if not first:
                    first = data[:64]
                    if first[0] != 0x16:
                        return Probe(False, f"non-TLS bytes on {port}: {_printable(first)!r}")
                inc.write(data)
            except ssl.SSLError as e:
                return Probe(False, f"TLS handshake failed on {port} ({e.reason or e}): {_printable(first)!r}")
        pending = out.read()
        if pending:
            sock.sendall(pending)
        ver = obj.version()
        return Probe(True, f"TLS handshake ok on {host}:{port} ({ver})", {"tls": ver})
    except OSError as e:
        tail = f": {_printable(first)!r}" if first else ""
        return Probe(False, f"TLS handshake on {port} failed: {e.__class__.__name__}{tail}")
    finally:
        sock.close()


def _system_srv(name: str, timeout: float) -> list[tuple[str, int]]:
    """SRV via dnspython when installed; otherwise empty (A-lookup still runs)."""
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        return []
    r = dns.resolver.Resolver()
    r.lifetime = timeout
    ans = r.resolve(name, "SRV")
    return sorted((str(a.target).rstrip("."), int(a.port)) for a in ans)


def _system_a(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, EDGE_PORT, socket.AF_INET, socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


def probe_edge_dns(timeout: float = PROBE_TIMEOUT_S,
                   srv: Callable[[str, float], list[tuple[str, int]]] = _system_srv,
                   a: Callable[[str], list[str]] = _system_a) -> Probe:
    targets: list[tuple[str, int]] = []
    srv_note = ""
    try:
        targets = srv(EDGE_SRV, timeout)
    except Exception as e:  # noqa: BLE001
        srv_note = f"SRV {EDGE_SRV} failed: {e.__class__.__name__}; "
    if not targets:
        srv_note = srv_note or "SRV unavailable; "
        targets = [(EDGE_FALLBACK_HOST, EDGE_PORT)]
    addrs: list[str] = []
    for host, _port in targets:
        try:
            addrs.extend(a(host))
        except OSError:
            continue
    addrs = sorted(set(addrs))
    if not addrs:
        return Probe(False, srv_note + "no A records for edge")
    fake = [x for x in addrs if ipaddress.ip_address(x) in FAKE_IP_NET]
    if fake:
        return Probe(False, srv_note + f"fake-IP answers in 198.18.0.0/15: {','.join(fake)}",
                     {"addrs": addrs})
    return Probe(True, srv_note + f"edge resolves to {len(addrs)} real address(es)",
                 {"addrs": addrs, "srv": [f"{h}:{p}" for h, p in targets]})


def _http_status(url: str, headers: dict, timeout: float,
                 env: Optional[dict] = None,
                 tunnel: Optional[Callable[..., socket.socket]] = None) -> int:
    """GET url and return the status, dialling through the relay client's
    proxy-aware tunnel (HTTPS_PROXY / ALL_PROXY / NO_PROXY, DoH fallback) so
    discovery sees the same network path the relay client will use."""
    import http.client
    from nougen_shards import relay_client
    p = urllib.parse.urlsplit(url)
    https = p.scheme == "https"
    port = p.port or (443 if https else 80)
    sock = (tunnel or relay_client.open_tunnel)(p.hostname, port, timeout=timeout, env=env)
    try:
        sock.settimeout(timeout)
        if https:
            sock = relay_client.tls_context(env).wrap_socket(sock, server_hostname=p.hostname)
    except Exception:
        sock.close()
        raise
    cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
    c = cls(p.hostname, port, timeout=timeout)
    c.sock = sock  # pre-connected: http.client skips its own direct connect()
    try:
        c.request("GET", p.path + (f"?{p.query}" if p.query else ""), headers=headers)
        return c.getresponse().status
    finally:
        c.close()


def probe_relay(relay_url: str, node_id: str, token: Optional[str] = None,
                timeout: float = PROBE_TIMEOUT_S,
                http_status: Callable[[str, dict, float], int] = _http_status) -> Probe:
    """401 without auth = live. With token: 200 = provisioned, 401 = RELAY_AUTH missing."""
    base = relay_https_base(relay_url)
    url = f"{base}/_relay/status?id={urllib.parse.quote(node_id or 'probe')}"
    hdr = {"User-Agent": "nougen-transport-discovery"}
    try:
        st = http_status(url, hdr, timeout)
    except Exception as e:  # noqa: BLE001
        return Probe(False, f"relay {base} unreachable: {e.__class__.__name__}")
    if st != 401:
        return Probe(False, f"relay {base} answered {st} unauthenticated (want 401)", {"status": st})
    detail = {"status": st, "auth": "untested"}
    reason = f"relay {base} live (401 unauthenticated)"
    if token:
        try:
            st2 = http_status(url, {**hdr, "Authorization": f"Bearer {token}"}, timeout)
        except Exception as e:  # noqa: BLE001
            st2 = None
            reason += f"; authed probe failed: {e.__class__.__name__}"
        if st2 == 200:
            detail["auth"] = "provisioned"
            reason += "; token accepted"
        elif st2 == 401:
            detail["auth"] = "missing"
            reason += "; token rejected (RELAY_AUTH record missing)"
        elif st2 is not None:
            detail["auth"] = f"status {st2}"
    return Probe(True, reason, detail)


# ---------------------------------------------------------------- decision
def decide(probes: dict, relay_url: str,
           observed_cloudflared_connections: Optional[Iterable[str]] = None,
           extra_reasons: Iterable[str] = ()) -> dict:
    """Pure: probe results (dicts with ``ok``/``reason``) -> transport decision."""
    reasons = list(extra_reasons)
    for k in PROBE_ORDER:
        p = probes.get(k)
        reasons.append(f"{k}: {'ok' if p and p.get('ok') else 'fail'} - "
                       f"{(p or {}).get('reason', 'not run')}")
    seen = sorted({str(c).lower() for c in (observed_cloudflared_connections or ())})
    ok = {k: bool((probes.get(k) or {}).get("ok")) for k in PROBE_ORDER}
    edge = ok["edge_dns"] and ok["edge_tls_7844"]
    if edge and "quic" in seen:
        t = "quic"
        reasons.append("chose quic: cloudflared reported a quic connection")
    elif edge:
        t = "http2"
        reasons.append("chose http2: edge DNS real and TLS on 7844 verified (quic untestable from Python)")
    elif ok["relay_https"]:
        t = "relay"
        reasons.append("chose relay: edge unusable, relay live")
    else:
        t = "none"
        reasons.append("chose none: edge unusable and relay not live")
    return {"transport": t, "relay_url": relay_url, "reasons": reasons,
            "probes": {k: probes[k] for k in PROBE_ORDER if k in probes}}


# ------------------------------------------------------------------ cache
def cache_path(account_dir: Path) -> Path:
    return Path(account_dir) / "transport.json"


def load_cache(account_dir: Path) -> Optional[dict]:
    try:
        return json.loads(cache_path(account_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cache_fresh(cached: Optional[dict], now: float, ttl: float = CACHE_TTL_S) -> bool:
    return bool(cached) and (now - float(cached.get("checked_at", 0))) < ttl


def write_cache(account_dir: Path, decision: dict, now: float) -> None:
    d = Path(account_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = {**decision, "checked_at": now,
           "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))}
    tmp = cache_path(d).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, cache_path(d))
    _sync_tunnel_env(d, decision["transport"])


def _sync_tunnel_env(d: Path, transport: str) -> None:
    """Mirror quic/http2 into tunnel.env's TUNNEL_TRANSPORT_PROTOCOL (supervisor format)."""
    if transport not in ("quic", "http2"):
        return
    p = d / "tunnel.env"
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    lines = [ln for ln in lines if not ln.strip().startswith("TUNNEL_TRANSPORT_PROTOCOL=")]
    lines.append(f"TUNNEL_TRANSPORT_PROTOCOL={transport}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


# -------------------------------------------------------------- discovery
def _load_node(account_dir: Path) -> dict:
    try:
        return json.loads((Path(account_dir) / "node.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_probes(relay_url: str, node: dict, timeout: float = PROBE_TIMEOUT_S,
               edge_tls: Callable[..., Probe] = probe_edge_tls,
               edge_dns: Callable[..., Probe] = probe_edge_dns,
               relay: Callable[..., Probe] = probe_relay) -> dict:
    """Fixed order: edge_tls_7844, edge_dns, relay_https."""
    out: dict = {}
    dns = edge_dns(timeout=timeout)
    addrs = [a for a in dns.detail.get("addrs", [])
             if ipaddress.ip_address(a) not in FAKE_IP_NET]
    # Try every real address in deterministic order; one unreachable edge IP
    # must not reject HTTP2 while another resolved address accepts TLS.
    targets = addrs or [EDGE_FALLBACK_HOST]
    tls = None
    tried: list[str] = []
    for target in targets:
        tls = edge_tls(target, EDGE_PORT, timeout)
        tried.append(target)
        if tls.ok:
            break
    tls_d = tls.as_dict()
    if len(targets) > 1:
        tls_d["tried"] = tried
    out["edge_tls_7844"] = tls_d
    out["edge_dns"] = dns.as_dict()
    node_id = ""
    if node:
        try:
            from nougen_shards.relay_client import relay_id
            node_id = relay_id(node)
        except (KeyError, ImportError):
            node_id = ""
    out["relay_https"] = relay(relay_url, node_id, node.get("token") or None, timeout).as_dict()
    return out


def discover(account_dir: Path, refresh: bool = False, failing: bool = False,
             env: Optional[dict] = None, now: Optional[float] = None,
             observed_cloudflared_connections: Optional[Iterable[str]] = None,
             prober: Callable[[str, dict], dict] = run_probes) -> dict:
    now = time.time() if now is None else now
    cached = load_cache(account_dir)
    if not refresh and not failing and cache_fresh(cached, now):
        return {**cached, "cached": True}
    node = _load_node(account_dir)
    relay_url, why = resolve_relay_url(env, node)
    probes = prober(relay_url, node)
    d = decide(probes, relay_url, observed_cloudflared_connections, why)
    write_cache(account_dir, d, now)
    return {**d, "checked_at": now, "cached": False}


def default_account_dir() -> Path:
    return Path(os.environ.get("NOUGEN_ACCOUNT_DIR") or Path.home() / ".nougen" / "node")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nougen transport discover")
    ap.add_argument("--account-dir", default=None)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--failing", action="store_true", help="current transport is failing: re-probe")
    ap.add_argument("--observed", action="append", default=[],
                    help="protocol cloudflared reported (repeatable), e.g. quic")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    d = discover(Path(a.account_dir) if a.account_dir else default_account_dir(),
                 refresh=a.refresh, failing=a.failing, observed_cloudflared_connections=a.observed)
    if a.json:
        print(json.dumps(d, indent=2, sort_keys=True))
    else:
        print(f"transport: {d['transport']}{' (cached)' if d.get('cached') else ''}")
        print(f"relay_url: {d['relay_url']}")
        for r in d["reasons"]:
            print(f"  - {r}")
    return 0 if d["transport"] != "none" else 2


if __name__ == "__main__":
    sys.exit(main())
