"""Tenant credential registry and vault mapping for the network node.

The owner credential remains in ``NGS_NODE_TOKEN`` for backwards
compatibility.  Additional credentials are stored only as SHA-256 digests in
the tenant registry.
"""
from __future__ import annotations

import hashlib
import hmac
import errno
import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
TOKEN_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
OWNER_TENANT_ID = "owner"


class TenantRegistryError(ValueError):
    """The configured registry is unsafe or malformed."""


class RegistryUnreadableError(TenantRegistryError):
    """The registry could not be READ — a transient local resource failure.

    Deliberately a subclass, so every existing `except TenantRegistryError`
    keeps catching it and no caller changes behaviour by accident. What it adds
    is the ability to tell two categorically different things apart:

      * malformed/unsafe registry -> a configuration fault. Operator must fix
        the file. Retrying is pointless.
      * unreadable registry       -> this box ran out of a local resource
        (descriptors, memory). The config is fine. Retrying later works.

    Measured on phoebus 2026-09-04: the node exhausted its 256-descriptor
    launchd limit, could not open tenants.json, and returned
    `503 {"detail":"Tenant registry is invalid."}` on every data endpoint —
    byte-identical to a node with no token configured. Peers recorded it as
    unauthenticated. /health stayed 200 throughout, because it never opens the
    registry. The node was serving a lie about its own configuration for as
    long as the pressure lasted.
    """

    #: errnos that mean "the box is out of something", not "the file is wrong".
    TRANSIENT_ERRNOS = frozenset({
        errno.EMFILE,   # per-process descriptor limit
        errno.ENFILE,   # system-wide descriptor table full
        errno.ENOMEM,   # out of memory
        errno.ENOSPC,   # no space left
    })


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    label: str
    vault_dir: Path


@dataclass(frozen=True)
class TenantRecord:
    tenant_id: str
    label: str
    token_sha256: str

    def as_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "label": self.label,
            "token_sha256": self.token_sha256,
        }


def tenants_file() -> Path:
    configured = os.environ.get("NOUGEN_TENANTS_FILE")
    return Path(configured).expanduser() if configured else Path.home() / ".nougen" / "tenants.json"


def tenant_vault_root() -> Path:
    configured = os.environ.get("NOUGEN_TENANT_VAULT_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / ".nougen" / "tenants"


def token_sha256(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _validate_record(raw: object, position: int) -> TenantRecord:
    if not isinstance(raw, dict):
        raise TenantRegistryError(f"tenant record {position} must be an object")
    tenant_id = raw.get("tenant_id")
    label = raw.get("label")
    digest = raw.get("token_sha256")
    if not isinstance(tenant_id, str) or not TENANT_ID_RE.fullmatch(tenant_id):
        raise TenantRegistryError(f"invalid tenant_id at record {position}: {tenant_id!r}")
    if tenant_id == OWNER_TENANT_ID:
        raise TenantRegistryError("tenant_id 'owner' is reserved for NGS_NODE_TOKEN")
    if not isinstance(label, str) or not label.strip():
        raise TenantRegistryError(f"tenant {tenant_id!r} must have a non-empty label")
    if not isinstance(digest, str) or not TOKEN_HASH_RE.fullmatch(digest):
        raise TenantRegistryError(f"tenant {tenant_id!r} has an invalid token_sha256")
    return TenantRecord(tenant_id=tenant_id, label=label.strip(), token_sha256=digest)


def load_registry(path: Optional[Path] = None) -> list[TenantRecord]:
    """Load and fully validate the registry; a missing file means no extras."""
    registry_path = Path(path) if path is not None else tenants_file()
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except OSError as exc:
        # Out of descriptors is not a malformed registry. Conflating them is
        # what let a resource failure impersonate an auth failure.
        if exc.errno in RegistryUnreadableError.TRANSIENT_ERRNOS:
            raise RegistryUnreadableError(
                f"cannot read tenant registry {registry_path}: {exc.strerror} "
                f"(errno {exc.errno}) — local resource exhaustion, not a "
                "configuration fault") from exc
        raise TenantRegistryError(f"cannot load tenant registry {registry_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise TenantRegistryError(f"cannot load tenant registry {registry_path}: {exc}") from exc

    records_raw = raw.get("tenants") if isinstance(raw, dict) else raw
    if not isinstance(records_raw, list):
        raise TenantRegistryError("tenant registry must be a list or an object with a 'tenants' list")

    records = [_validate_record(item, i) for i, item in enumerate(records_raw)]
    ids = [record.tenant_id for record in records]
    digests = [record.token_sha256 for record in records]
    if len(ids) != len(set(ids)):
        raise TenantRegistryError("tenant registry contains duplicate tenant_id values")
    if len(digests) != len(set(digests)):
        raise TenantRegistryError("tenant registry maps one credential to multiple tenants")
    return records


def vault_dir_for(tenant_id: str, owner_vault_dir: Path) -> Path:
    if tenant_id == OWNER_TENANT_ID:
        return Path(owner_vault_dir)
    if not TENANT_ID_RE.fullmatch(tenant_id):
        raise TenantRegistryError(f"invalid tenant_id: {tenant_id!r}")

    root = tenant_vault_root().resolve()
    candidate = (root / tenant_id).resolve()
    if candidate.parent != root:
        raise TenantRegistryError(f"tenant vault escapes configured root: {tenant_id!r}")
    return candidate


def resolve_token(token: Optional[str], owner_token: Optional[str], owner_vault_dir: Path) -> Optional[Tenant]:
    """Resolve exactly one credential, never defaulting an unknown token."""
    if not token:
        return None
    supplied_hash = token_sha256(token)
    matches: list[tuple[str, str]] = []

    if owner_token:
        owner_hash = token_sha256(owner_token)
        if hmac.compare_digest(supplied_hash, owner_hash):
            matches.append((OWNER_TENANT_ID, "Owner"))

    for record in load_registry():
        if hmac.compare_digest(supplied_hash, record.token_sha256):
            matches.append((record.tenant_id, record.label))

    # Ambiguous credentials are configuration errors from an authorization
    # perspective: do not let record order decide which vault opens.
    if len(matches) != 1:
        return None
    tenant_id, label = matches[0]
    return Tenant(tenant_id, label, vault_dir_for(tenant_id, owner_vault_dir))


def tenant_by_id(tenant_id: str, owner_vault_dir: Path) -> Optional[Tenant]:
    """Resolve an already-authenticated tenant id without an owner fallback."""
    if tenant_id == OWNER_TENANT_ID:
        return Tenant(OWNER_TENANT_ID, "Owner", Path(owner_vault_dir))
    for record in load_registry():
        if hmac.compare_digest(record.tenant_id, tenant_id):
            return Tenant(record.tenant_id, record.label,
                          vault_dir_for(record.tenant_id, owner_vault_dir))
    return None


def credentials_configured(owner_token: Optional[str]) -> bool:
    return bool(owner_token) or bool(load_registry())


def mint_tenant(tenant_id: str, label: str, path: Optional[Path] = None) -> str:
    """Generate a credential, persist only its digest, and return it once."""
    if not TENANT_ID_RE.fullmatch(tenant_id) or tenant_id == OWNER_TENANT_ID:
        raise TenantRegistryError(f"invalid or reserved tenant_id: {tenant_id!r}")
    if not label or not label.strip():
        raise TenantRegistryError("label must not be empty")

    registry_path = Path(path) if path is not None else tenants_file()
    records = load_registry(registry_path)
    if any(record.tenant_id == tenant_id for record in records):
        raise TenantRegistryError(f"tenant_id already exists: {tenant_id}")

    token = secrets.token_urlsafe(32)
    records.append(TenantRecord(tenant_id, label.strip(), token_sha256(token)))
    payload = {"tenants": [record.as_dict() for record in records]}

    registry_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp_path = registry_path.with_name(f".{registry_path.name}.{secrets.token_hex(8)}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            tmp_path.chmod(0o600)
        except OSError:
            pass
        tmp_path.replace(registry_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return token
