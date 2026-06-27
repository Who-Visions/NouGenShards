"""Cloud Connector for remote NouGenShards instances."""
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
    attacker DNS record pointing at 169.254.169.254 is rejected. (This is not
    full DNS-rebinding protection — that needs pinning the validated IP through
    to the request; a follow-up. A name that does not resolve here is allowed,
    matching the prior behavior, since the request itself will fail.)

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

            with urllib.request.urlopen(req, timeout=5.0) as res:
                remote_data = json.loads(res.read().decode())
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

        with urllib.request.urlopen(req, timeout=10.0) as res:
            return json.loads(res.read().decode())
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

        with urllib.request.urlopen(req, timeout=10.0) as res:
            return json.loads(res.read().decode())
    except _NET_ERRORS as exc:
        # No longer silent — a failed pull is logged, then degrades to empty.
        logger.warning("cloud pull failed: %s: %s", type(exc).__name__, exc)
        return []
