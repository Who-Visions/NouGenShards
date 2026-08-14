"""Serve this box as an NGS node so peer lanes can federate its shards.

Everything environment-shaped is probed or resolved at run time (Rule 0.2):

  bind host  <- NGS_BIND_HOST, else 0.0.0.0 (LAN federation is the point)
  port       <- NGS_PORT, else first free port from NGS_PORT_CANDIDATES
  token      <- NGS_NODE_TOKEN env, else the keymaker secret of the same name
  advertise  <- the live non-loopback IPv4 of the default route, discovered here

No secret value is ever printed; the token is reported as a SHA-256 fingerprint.

The HUD is intentionally left unmounted: app.py fails closed when the bind is
network-exposed and NGS_HUD_USER/NGS_HUD_PASSWORD are unset. Federation needs
only the token-gated REST surface (/search, /capture, /sync/*) plus /mcp, so we
do not hand an unauthenticated vault UI to the LAN.
"""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PORT_CANDIDATES = "4444,4445,8766,8767"


def _repo_python() -> str:
    """The venv interpreter when there is one, else whatever is running us."""
    venv = REPO / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python")
    return str(venv) if venv.exists() else sys.executable


def _port_is_free(port: int, host: str = "0.0.0.0") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def resolve_port() -> int:
    """NGS_PORT when set (and free), else the first free candidate."""
    pinned = os.environ.get("NGS_PORT")
    if pinned:
        port = int(pinned)
        if not _port_is_free(port):
            raise SystemExit(f"[!] NGS_PORT={port} is already in use; free it or unset NGS_PORT.")
        return port
    candidates = os.environ.get("NGS_PORT_CANDIDATES", DEFAULT_PORT_CANDIDATES)
    for raw in candidates.split(","):
        raw = raw.strip()
        if raw and _port_is_free(int(raw)):
            return int(raw)
    raise SystemExit(f"[!] No free port among candidates: {candidates}")


def advertised_ip() -> str:
    """The IPv4 this box actually reaches the LAN with.

    Uses a connect-less UDP socket to the default route rather than a hostname
    lookup, which on this box returns link-local/mDNS answers that nothing
    listens on.
    """
    probe_target = os.environ.get("NGS_ROUTE_PROBE", "10.255.255.255")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(0.2)
        try:
            s.connect((probe_target, 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def resolve_token() -> str | None:
    """Env first (an operator override outranks stored state), then keymaker."""
    tok = os.environ.get("NGS_NODE_TOKEN")
    if tok:
        return tok
    sys.path.insert(0, str(REPO / "src"))
    try:
        from nougen_shards import keymaker
        return keymaker.get_secret("NGS_NODE_TOKEN")
    except Exception as exc:  # noqa: BLE001 - report, don't crash the launcher
        print(f"[!] keymaker lookup failed ({type(exc).__name__}: {exc})", file=sys.stderr)
        return None


def main() -> int:
    host = os.environ.get("NGS_BIND_HOST", "0.0.0.0")
    port = resolve_port()
    ip = advertised_ip()
    token = resolve_token()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    if token:
        env["NGS_NODE_TOKEN"] = token
        fp = hashlib.sha256(token.encode()).hexdigest()[:12]
        print(f"[*] node token: configured (fp={fp})")
    else:
        print("[!] node token: MISSING - every data endpoint will return 503 "
              "(deny-by-default). Ingest NGS_NODE_TOKEN into keymaker first.",
              file=sys.stderr)

    print(f"[*] bind      : {host}:{port}")
    print(f"[*] federate  : http://{ip}:{port}   <- peers link this URL")
    print("[*] HUD       : not mounted (network-exposed, no NGS_HUD_USER/PASSWORD) - intended")
    print(f"[*] peers need NGS_ALLOW_INSECURE_CLOUD=1 for plaintext http to {ip}")

    cmd = [_repo_python(), "-m", "uvicorn", "app:app", "--host", host, "--port", str(port)]
    print(f"[*] exec      : {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=str(REPO), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
