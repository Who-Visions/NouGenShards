"""One-command tenant onboarding.

A tenant is one identity spread over four stores: the node registry (digest only),
the worker's TENANTS KV (keyed by email), a Cloudflare tunnel with its DNS record,
and the tenant's own machine. ``onboard`` creates or repairs all of them from an
email address and is safe to re-run; ``status`` says in plain English what is
still missing. Nothing here prints a credential: the kit file holds them.

Everything environment-shaped resolves env -> existing KV records -> keymaker ->
a logged fallback (see the "dynamic over hardcode" rule).
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import socket
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import tenants

CF_API = os.environ.get("CLOUDFLARE_API_BASE", "https://api.cloudflare.com/client/v4")
TOKEN_KEY = "CLOUDFLARE_API_TOKEN_NOUGEN_FULL"
KV_TITLE = os.environ.get("NOUGEN_TENANTS_KV_TITLE", "TENANTS")
FALLBACK_DOMAIN = "nougenai.com"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OnboardError(RuntimeError):
    """A step failed; the message says what to do next."""


class CloudflareAPI:
    """Minimal Cloudflare REST client. Tests substitute any object with ``call``."""

    def __init__(self, token: Optional[str] = None, account_id: Optional[str] = None):
        self.token = token or _resolve_cf_token()
        self._account = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")

    def call(self, method: str, path: str, body: Any = None, query: Optional[dict] = None,
             raw: bool = False) -> Any:
        url = CF_API + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None
        headers = {"Authorization": f"Bearer {self.token}"}
        if raw:
            data = (body or "").encode("utf-8")
            headers["Content-Type"] = "text/plain"
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as resp:
                text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and method == "GET":
                return None
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise OnboardError(f"Cloudflare {method} {path} -> HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OnboardError(f"Cloudflare unreachable ({exc.reason}); check the internet connection") from exc
        try:
            parsed = json.loads(text)
        except ValueError:
            return text  # a raw KV value that is not JSON
        if isinstance(parsed, dict) and "success" in parsed:
            if not parsed["success"]:
                raise OnboardError(f"Cloudflare {method} {path} failed: {parsed.get('errors')}")
            return parsed.get("result")
        return parsed

    @property
    def account_id(self) -> str:
        if not self._account:
            accounts = self.call("GET", "/accounts") or []
            if len(accounts) != 1:
                raise OnboardError("set CLOUDFLARE_ACCOUNT_ID: the token sees "
                                   f"{len(accounts)} accounts")
            self._account = accounts[0]["id"]
        return self._account


def _resolve_cf_token() -> str:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        try:
            from . import keymaker
            token = keymaker.get_secret(TOKEN_KEY)
        except Exception:  # keymaker absent or locked: fall through to the clear error
            token = None
    if not token:
        raise OnboardError("no Cloudflare credential: set CLOUDFLARE_API_TOKEN or store "
                           f"{TOKEN_KEY} in the keymaker")
    return token


# --------------------------------------------------------------------------- helpers

def slugify(text: str, limit: int = 24) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "tenant")[:limit].strip("-") or "tenant"


def derive_identity(email: str, name: Optional[str], tenant_id: Optional[str],
                    label: Optional[str]) -> tuple[str, str]:
    """Pick the tenant slug and label a person would expect from just an email."""
    if not EMAIL_RE.fullmatch(email or ""):
        raise OnboardError(f"not an email address: {email!r}")
    base = slugify(name) if name else slugify(email.split("@")[0].split("+")[0])
    tid = tenant_id or f"{base}-shards"
    if not tenants.TENANT_ID_RE.fullmatch(tid):
        raise OnboardError(f"tenant id {tid!r} must be lowercase letters, digits, - or _ (max 32)")
    return tid, (label or f"{name or base} - own shards/MCP, isolated").strip()


def _kv_get(cf, ns: str, key: str) -> Optional[str]:
    path = f"/accounts/{cf.account_id}/storage/kv/namespaces/{ns}/values/{urllib.parse.quote(key, safe='')}"
    out = cf.call("GET", path)
    if out is None:
        return None
    return out if isinstance(out, str) else json.dumps(out)


def _kv_put(cf, ns: str, key: str, value: dict | str) -> None:
    path = f"/accounts/{cf.account_id}/storage/kv/namespaces/{ns}/values/{urllib.parse.quote(key, safe='')}"
    cf.call("PUT", path, body=value if isinstance(value, str) else json.dumps(value), raw=True)


def _kv_json(cf, ns: str, key: str) -> Optional[dict]:
    raw = _kv_get(cf, ns, key)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _find_namespace(cf) -> str:
    for ns in cf.call("GET", f"/accounts/{cf.account_id}/storage/kv/namespaces",
                      query={"per_page": 100}) or []:
        if ns.get("title") == KV_TITLE:
            return ns["id"]
    raise OnboardError(f"no KV namespace titled {KV_TITLE!r} on this Cloudflare account")


def _resolve_domain(cf, ns: str, explicit: Optional[str]) -> str:
    """env/flag -> parent domain of an existing tenant node_url -> logged fallback."""
    domain = explicit or os.environ.get("NOUGEN_TENANT_DOMAIN")
    if domain:
        return domain
    keys = cf.call("GET", f"/accounts/{cf.account_id}/storage/kv/namespaces/{ns}/keys",
                   query={"prefix": "tenant:", "limit": 20}) or []
    for key in keys:
        rec = _kv_json(cf, ns, key["name"]) or {}
        host = urllib.parse.urlparse(rec.get("node_url", "")).hostname
        if host and host.count(".") >= 2:
            return host.split(".", 1)[1]
    return FALLBACK_DOMAIN


def _zone_for(cf, hostname: str) -> str:
    parts = hostname.split(".")
    for i in range(len(parts) - 1):
        zones = cf.call("GET", "/zones", query={"name": ".".join(parts[i:])}) or []
        if zones:
            return zones[0]["id"]
    raise OnboardError(f"no Cloudflare zone on this account covers {hostname}")


def _tunnel_id_from_token(tunnel_token: Optional[str]) -> Optional[str]:
    """A tunnel token is base64 JSON {a: account, t: tunnel id, s: secret}."""
    try:
        padded = tunnel_token + "=" * (-len(tunnel_token) % 4)
        return json.loads(base64.b64decode(padded))["t"]
    except Exception:
        return None


def _ensure_tunnel(cf, name: str, hostname: str, port: int,
                   known_id: Optional[str] = None) -> tuple[str, str, bool, int]:
    found = []
    if known_id:  # reuse the tunnel the tenant's records already name
        got = cf.call("GET", f"/accounts/{cf.account_id}/cfd_tunnel/{known_id}")
        if got and not got.get("deleted_at"):
            found = [got]
    found = found or cf.call("GET", f"/accounts/{cf.account_id}/cfd_tunnel",
                             query={"name": name, "is_deleted": "false"}) or []
    created = not found
    if found:
        tunnel_id = found[0]["id"]
    else:
        secret = base64.b64encode(secrets.token_bytes(32)).decode()
        made = cf.call("POST", f"/accounts/{cf.account_id}/cfd_tunnel",
                       body={"name": name, "config_src": "cloudflare", "tunnel_secret": secret})
        tunnel_id = made["id"]
    # A live tunnel already names the tenant's real port; never overwrite it.
    current = cf.call("GET", f"/accounts/{cf.account_id}/cfd_tunnel/{tunnel_id}/configurations") or {}
    for rule in (current.get("config") or {}).get("ingress") or []:
        if rule.get("hostname") == hostname and rule.get("service", "").startswith("http://"):
            port = int(rule["service"].rsplit(":", 1)[1])
            break
    else:
        cf.call("PUT", f"/accounts/{cf.account_id}/cfd_tunnel/{tunnel_id}/configurations",
                body={"config": {"ingress": [{"hostname": hostname, "service": f"http://127.0.0.1:{port}"},
                                             {"service": "http_status:404"}]}})
    token = cf.call("GET", f"/accounts/{cf.account_id}/cfd_tunnel/{tunnel_id}/token")
    if not isinstance(token, str) or not token:
        raise OnboardError("Cloudflare returned no tunnel token")
    return tunnel_id, token.strip().strip('"'), created, port


def _ensure_dns(cf, zone: str, hostname: str, tunnel_id: str) -> None:
    target = f"{tunnel_id}.cfargotunnel.com"
    body = {"type": "CNAME", "name": hostname, "content": target, "proxied": True}
    existing = cf.call("GET", f"/zones/{zone}/dns_records", query={"name": hostname}) or []
    if existing:
        if existing[0].get("content") != target:
            cf.call("PUT", f"/zones/{zone}/dns_records/{existing[0]['id']}", body=body)
    else:
        cf.call("POST", f"/zones/{zone}/dns_records", body=body)


def probe(url: str, timeout: float = 10.0) -> tuple[Optional[int], str]:
    """Reachability of a tenant node: (status, plain-English reading)."""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, "online"
    except urllib.error.HTTPError as exc:
        if exc.code in (530, 502, 1033):
            return exc.code, "offline: the tunnel is not running on the tenant's computer yet"
        if exc.code in (401, 403):
            return exc.code, "online (the node answered and wants a token)"
        return exc.code, f"answered HTTP {exc.code}"
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        return None, f"unreachable: {getattr(exc, 'reason', exc)}"


# --------------------------------------------------------------------------- kit

KIT_PS1 = r"""# NouGen tenant join kit for {tenant_id}. Double-click, or right-click > Run with PowerShell.
# Contains secrets: keep it private and delete it once the tunnel is installed as a service.
$ErrorActionPreference = 'Stop'
$env:NGS_NODE_TOKEN = '{token}'
$env:NGS_PORT = '{port}'
$repo = if ($env:NOUGEN_HOME) {{ $env:NOUGEN_HOME }} else {{ Join-Path $HOME 'Watchtower\NouGenShards' }}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {{
    Write-Host 'Installing cloudflared...'
    winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
    $env:Path += ';' + [Environment]::GetEnvironmentVariable('Path','Machine')
}}
if (Test-NetConnection 127.0.0.1 -Port {port} -InformationLevel Quiet -WarningAction SilentlyContinue) {{
    Write-Host 'Your node is already running.'
}} elseif (Test-Path (Join-Path $repo 'app.py')) {{
    Write-Host "Starting your node from $repo ..."
    Start-Process -WindowStyle Hidden -FilePath python -ArgumentList 'app.py' -WorkingDirectory $repo
}} else {{
    Write-Host "NouGenShards was not found at $repo. Install it there (or set NOUGEN_HOME) and run this again." -ForegroundColor Yellow
}}
Write-Host 'Connecting to NouGen... leave this window open.'
cloudflared tunnel run --token {tunnel_token}
"""

KIT_SH = """#!/bin/sh
# NouGen tenant join kit for {tenant_id}. Contains secrets: keep private.
export NGS_NODE_TOKEN='{token}' NGS_PORT='{port}'
command -v cloudflared >/dev/null || {{ echo 'Install cloudflared first: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/'; exit 1; }}
REPO="${{NOUGEN_HOME:-$HOME/NouGenShards}}"
[ -f "$REPO/app.py" ] && (cd "$REPO" && nohup python app.py >/dev/null 2>&1 &)
exec cloudflared tunnel run --token {tunnel_token}
"""


def write_kit(tenant_id: str, token: str, tunnel_token: str, port: int,
              root: Optional[Path] = None) -> Path:
    """Write the join kit for the tenant's computer.

    The kit holds the node and tunnel tokens, so by default it goes to a private (0700)
    throwaway folder, not into the owner's persistent ~/.nougen. Re-running onboard
    rebuilds it at any time, so nothing needs to be kept. Pass `root` to choose a folder.
    """
    base = Path(root) if root else Path(tempfile.mkdtemp(prefix="nougen-kit-"))
    kit_dir = base / "tenant-kits" / tenant_id
    kit_dir.mkdir(parents=True, exist_ok=True)
    vals = dict(tenant_id=tenant_id, token=token, tunnel_token=tunnel_token, port=port)
    for name, template in (("join.ps1", KIT_PS1), ("join.sh", KIT_SH)):
        path = kit_dir / name
        path.write_text(template.format(**vals), encoding="utf-8", newline="\n")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return kit_dir


# --------------------------------------------------------------------------- onboard

@dataclass
class Result:
    tenant_id: str
    email: str
    hostname: str
    node_url: str
    kit_dir: Optional[Path]
    steps: list = field(default_factory=list)
    probe_status: Optional[int] = None
    probe_reading: str = ""

    def as_dict(self) -> dict:
        return {"tenant_id": self.tenant_id, "email": self.email, "node_url": self.node_url,
                "kit_dir": str(self.kit_dir) if self.kit_dir else None, "steps": self.steps,
                "probe_status": self.probe_status, "probe_reading": self.probe_reading}


def onboard(email: str, name: Optional[str] = None, tenant_id: Optional[str] = None,
            label: Optional[str] = None, domain: Optional[str] = None,
            port: Optional[int] = None, rotate: bool = False, dry_run: bool = False,
            cf=None, registry_path: Optional[Path] = None,
            kit_root: Optional[Path] = None,
            prober: Callable[[str], tuple] = probe) -> Result:
    email = (email or "").strip().lower()
    tid, label = derive_identity(email, name, tenant_id, label)
    port = port or int(os.environ.get("NGS_PORT", "4444"))
    steps: list[str] = []
    cf = cf or CloudflareAPI()
    ns = _find_namespace(cf)

    existing = _kv_json(cf, ns, f"tenant:{email}") or {}
    if existing.get("tenant_id") and not tenant_id:
        tid = existing["tenant_id"]
    domain = _resolve_domain(cf, ns, domain)
    host = urllib.parse.urlparse(existing.get("node_url", "")).hostname or \
        f"{slugify(tid, 20)}-{secrets.token_hex(2)}.{domain}"
    node_url = f"https://{host}"

    records = tenants.load_registry(Path(registry_path) if registry_path else None)
    record = next((r for r in records if r.tenant_id == tid), None)
    kv_token = existing.get("token") if isinstance(existing.get("token"), str) else None

    # 1. credential: reuse the one KV already holds when it matches the registry digest
    if record and kv_token and tenants.token_sha256(kv_token) == record.token_sha256 and not rotate:
        token = kv_token
        steps.append("credential: already consistent (registry and KV agree)")
    else:
        if dry_run:
            steps.append("credential: would " + ("rotate" if record else "mint") + " a token")
            token = "DRYRUN"
        else:
            if record:
                tenants.remove_tenant(tid, registry_path)
                steps.append("credential: rotated (old token no longer valid)")
            else:
                steps.append("credential: minted")
            token = secrets.token_urlsafe(32)
            tenants.register_tenant(tid, label, token, path=registry_path)

    if dry_run:
        steps.append(f"would ensure tunnel tenant-{tid} -> {host} -> 127.0.0.1:{port}")
        steps.append(f"would write allow/tenant/tunnel KV records for {email}")
        return Result(tid, email, host, node_url, None, steps)

    # 2. tunnel + DNS
    zone = _zone_for(cf, host)
    prior = _kv_json(cf, ns, f"tunnel:{email}") or {}
    tunnel_id, tunnel_token, created, port = _ensure_tunnel(
        cf, f"tenant-{tid}", host, port, _tunnel_id_from_token(prior.get("tunnel_token")))
    _ensure_dns(cf, zone, host, tunnel_id)
    steps.append(f"tunnel: {'created' if created else 'reused'} tenant-{tid}; DNS {host} points at it")

    # 3. worker routing (KV is keyed by email)
    _kv_put(cf, ns, f"allow:{email}", "1")
    _kv_put(cf, ns, f"tenant:{email}", {**existing, "token": token, "node_url": node_url,
                                        "tenant_id": tid})
    _kv_put(cf, ns, f"tunnel:{email}", {"tunnel_token": tunnel_token, "hostname": host})
    steps.append(f"worker: {email} allowed and routed to {node_url}")

    # 4. the join kit for the tenant's computer
    kit_dir = write_kit(tid, token, tunnel_token, port, kit_root)
    steps.append(f"kit: {kit_dir}")

    status, reading = prober(node_url)
    return Result(tid, email, host, node_url, kit_dir, steps, status, reading)


def status(email_or_id: str, cf=None, registry_path: Optional[Path] = None,
           prober: Callable[[str], tuple] = probe) -> list[tuple[bool, str]]:
    """Plain-English health of one tenant: (ok, sentence) per check."""
    cf = cf or CloudflareAPI()
    ns = _find_namespace(cf)
    checks: list[tuple[bool, str]] = []
    key = email_or_id.strip().lower()
    rec = None
    if "@" in key:
        rec = _kv_json(cf, ns, f"tenant:{key}")
        email = key
    else:
        email = None
        for k in cf.call("GET", f"/accounts/{cf.account_id}/storage/kv/namespaces/{ns}/keys",
                         query={"prefix": "tenant:", "limit": 100}) or []:
            cand = _kv_json(cf, ns, k["name"]) or {}
            if cand.get("tenant_id") == key:
                rec, email = cand, k["name"].split(":", 1)[1]
    if not rec or not email:
        return [(False, f"{email_or_id} is not set up. Run: nougen tenant onboard <their email>")]
    tid = rec.get("tenant_id") or ""
    registry = tenants.load_registry(Path(registry_path) if registry_path else None)
    record = next((r for r in registry if r.tenant_id == tid), None)
    checks.append((bool(record), "node knows this tenant" if record else
                   "node registry has no such tenant: run onboard --rotate"))
    token = rec.get("token")
    match = bool(record and isinstance(token, str) and tenants.token_sha256(token) == record.token_sha256)
    checks.append((match, "token is the same everywhere" if match else
                   "token mismatch between worker and node: run onboard --rotate"))
    allowed = _kv_get(cf, ns, f"allow:{email}") in ("1", "true")
    checks.append((allowed, "email is allowed to sign in" if allowed else "email is not allowed: run onboard"))
    node_url = rec.get("node_url") or ""
    code, reading = prober(node_url) if node_url else (None, "no node address stored")
    checks.append((code is not None and code < 500, f"their computer is {reading}"))
    return checks
