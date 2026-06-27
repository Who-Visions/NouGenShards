"""Cloud Connector for remote NouGenShards instances."""
import contextlib
import ipaddress
import json
import logging
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# Network/parse failures that should degrade gracefully, not crash federation.
_NET_ERRORS = (urllib.error.URLError, json.JSONDecodeError, KeyError,
               ValueError, TimeoutError, OSError)


def _is_safe_cloud_url(url: str) -> bool:
    """Guard cloud node URLs against SSRF and token leakage.

    - Rejects non-http(s) schemes (file://, gopher://, ...).
    - Blocks link-local/metadata (169.254.169.254), multicast, reserved and
      unspecified IP literals on any scheme — the classic cloud-metadata SSRF.
    - Refuses plaintext http to non-loopback hosts (would send X-NGS-Token in
      cleartext); override knowingly with NGS_ALLOW_INSECURE_CLOUD=1.

    For hostnames (not IP literals) the name is resolved and EVERY resolved
    address is checked, so a name like `metadata.google.internal` or an
    attacker DNS record pointing at 169.254.169.254 is rejected. The validated
    address is then pinned through to the request (see _open_cloud / _pin_dns),
    so a second resolution can't rebind to an internal target. A name that does
    not resolve here is allowed, matching prior behavior (the request fails).

    Note: private LAN ranges (10/8, 192.168/16) are intentionally allowed since
    self-hosted nodes legitimately live there; do not feed this fully untrusted
    URLs without an additional egress allowlist.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except (ValueError, AttributeError):
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    # A malformed port (e.g. ':bad', ':999999') makes parsed.port raise
    # ValueError. This guard is called outside push/pull's network-error try,
    # so reject rather than crash the caller.
    try:
        port = parsed.port
    except ValueError:
        return False

    # Is the host an IP literal?
    host_ip = None
    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        pass

    # Explicit loopback — a literal loopback IP the operator typed, or a known
    # loopback name — is the ONLY sanctioned loopback target, allowed on any
    # scheme. Short-circuit before DNS so the result is deterministic.
    if (host_ip is not None and host_ip.is_loopback) \
            or host in ("localhost",) or host.endswith(".localhost"):
        return True

    # Candidate IPs: the literal itself, or every DNS-resolved address.
    candidates = [host_ip] if host_ip is not None else []
    if host_ip is None:
        try:
            for info in socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80),
                                           proto=socket.IPPROTO_TCP):
                candidates.append(ipaddress.ip_address(info[4][0]))
        except (socket.gaierror, ValueError, OSError):
            candidates = []  # unresolvable: allow (request will fail anyway)

    # Reject internal/dangerous targets. is_loopback is included here: only the
    # explicit literal/name above may target loopback, so a NON-local hostname
    # that resolves to 127.0.0.1/::1 is a DNS alias to a loopback-only service
    # and is rejected (would otherwise leak X-NGS-Token to it).
    for ip in candidates:
        if (ip.is_link_local or ip.is_multicast or ip.is_reserved
                or ip.is_unspecified or ip.is_loopback):
            return False

    # Plaintext http to a non-loopback host would send X-NGS-Token in the clear.
    if parsed.scheme == "http" and os.environ.get("NGS_ALLOW_INSECURE_CLOUD") != "1":
        return False
    return True


def _pinned_ip_for(url: str):
    """Return the single validated IP to pin a request to (defeating DNS
    rebinding between validation and connect), or None when pinning does not
    apply: IP-literal hosts (no DNS to rebind), loopback names, or unresolvable
    hosts. Only addresses that pass the same safety checks as _is_safe_cloud_url
    are returned, so a host whose records are all internal yields None."""
    try:
        parsed = urllib.parse.urlparse(url)
    except (ValueError, AttributeError):
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    try:
        ipaddress.ip_address(host)
        return None  # IP literal: urllib connects to it directly, nothing to rebind
    except ValueError:
        pass
    if host in ("localhost",) or host.endswith(".localhost"):
        return None
    try:
        infos = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError):
        return None
    for info in infos:
        try:
            ipobj = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not (ipobj.is_link_local or ipobj.is_multicast or ipobj.is_reserved
                or ipobj.is_unspecified or ipobj.is_loopback):
            return info[4][0]  # first safe resolved address -> pin to it
    return None


@contextlib.contextmanager
def _pin_dns(host: str, ip: str):
    """Force getaddrinfo(host) to return only `ip` for the duration of a request,
    so urllib connects to the pre-validated address instead of re-resolving (DNS
    rebinding TOCTOU). TLS still uses `host` for SNI/cert verification. Note:
    getaddrinfo is process-global; the connector sweeps are sequential, so this
    is safe here but is not thread-safe."""
    real_getaddrinfo = socket.getaddrinfo
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET

    def pinned(h, port, *args, **kwargs):
        if isinstance(h, str) and h.lower() == host:
            sockaddr = (ip, port) if family == socket.AF_INET else (ip, port, 0, 0)
            return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]
        return real_getaddrinfo(h, port, *args, **kwargs)

    socket.getaddrinfo = pinned
    try:
        yield
    finally:
        socket.getaddrinfo = real_getaddrinfo


def _open_cloud(req, url: str, timeout: float) -> bytes:
    """urlopen that pins a hostname target to its pre-validated IP, so the
    connection cannot rebind to an internal address after _is_safe_cloud_url
    accepted it. Returns the response body bytes."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    pin = _pinned_ip_for(url)
    if pin and host:
        with _pin_dns(host, pin):
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def query_cloud_shards(query: str, cloud_configs: list, limit: int = 3) -> list:
    """
    Queries remote NouGenShards nodes and maps results to standard format.
    """
    results = []

    for conf in cloud_configs:
        name = conf.get('name', '?')
        try:
            # Read config inside the try so a malformed row skips this node
            # instead of aborting the whole federation sweep.
            url = conf['url'].rstrip('/')
            name = conf['name']
            if not _is_safe_cloud_url(url):
                logger.warning("cloud node skipped (%s): unsafe/insecure URL rejected", name)
                continue
            # POST /search
            payload = {"query": query, "limit": limit}
            req = urllib.request.Request(
                f"{url}/search",
                data=json.dumps(payload).encode(),
                method="POST"
            )
            req.add_header("Content-Type", "application/json")

            remote_data = json.loads(_open_cloud(req, url, 5.0).decode())
            if isinstance(remote_data, list):
                for r in remote_data:
                    # Normalize to local shard shape
                    results.append({
                        "id": f"cloud_{conf['id']}_{r.get('id')}",
                        "event_type": f"CLOUD_{r.get('event_type', 'SHARD')}",
                        "title": r.get('title', 'Untitled Cloud Shard'),
                        "content": r.get('content', ''),
                        "tags": r.get('tags', '[]'),
                        "utility_score": r.get('utility_score', 1.0),
                        "access_count": r.get('access_count', 0),
                        "file_hash": r.get('file_hash', ''),
                        "final_score": r.get('final_score', 0.45),
                        "_db_index": f"cloud_{name}"
                    })
        except _NET_ERRORS as exc:
            # Resilient (one unreachable node must not kill federation) but no
            # longer silent. (Module 10: Graceful Degradation)
            logger.warning("cloud node skipped (%s): %s: %s",
                           name, type(exc).__name__, exc)
            continue

    return results


def push_to_cloud(shards: list, cloud_url: str, token: str) -> dict:
    """Pushes a list of shards to a remote cloud node."""
    url = cloud_url.rstrip('/')
    if not _is_safe_cloud_url(url):
        return {"status": "error", "message": "unsafe/insecure cloud URL rejected"}
    payload = {"shards": shards}
    try:
        req = urllib.request.Request(
            f"{url}/sync/push",
            data=json.dumps(payload).encode(),
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("X-NGS-Token", token)

        return json.loads(_open_cloud(req, url, 10.0).decode())
    except _NET_ERRORS as exc:
        return {"status": "error", "message": f"{type(exc).__name__}: {exc}"}


def pull_from_cloud(cloud_url: str, token: str) -> list:
    """Pulls all shards from a remote cloud node."""
    url = cloud_url.rstrip('/')
    if not _is_safe_cloud_url(url):
        logger.warning("cloud pull skipped: unsafe/insecure URL rejected")
        return []
    try:
        req = urllib.request.Request(f"{url}/sync/pull", method="GET")
        req.add_header("X-NGS-Token", token)

        return json.loads(_open_cloud(req, url, 10.0).decode())
    except _NET_ERRORS as exc:
        # No longer silent — a failed pull is logged, then degrades to empty.
        logger.warning("cloud pull failed: %s: %s", type(exc).__name__, exc)
        return []
