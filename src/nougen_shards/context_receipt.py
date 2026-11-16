"""Shards-first context receipts (issue #1084).

The prompt hook runs a budgeted recall. Before this module that result was only
advisory text: nothing downstream could tell a healthy "no matching shards" from
"recall never finished". A receipt records what actually happened, per tenant and
per session, so the PreToolUse gate can refuse protected mutations (commit, push,
PR merge, deploy, fleet-memory deletes) when the memory step did not complete.

Status values:
  COMPLETE  recall finished (zero matches is still COMPLETE) and the relay/claims
            check ran.
  DEGRADED  recall returned something but partially, or the relay check failed.
  UNKNOWN   recall did not finish at all. Never report this as "no memory".

Receipts hold shard refs (ids), counts and lane state only: no shard bodies, no
prompt text (only its hash), no secrets.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA = "nougen.context.receipt.v1"
COMPLETE, DEGRADED, UNKNOWN = "COMPLETE", "DEGRADED", "UNKNOWN"

#: Prompts that touch NouGen-internal state. Anything else may bypass the gate
#: (explicit classification, per #1084 item 2). Extend via NOUGEN_SENSITIVE_RE.
_DEFAULT_SENSITIVE = (r"\b(nougen|shards?|relay|vault|keymaker|fleet|gateway|destiny|handoff|"
                      r"blade|phoebus|whoart|ccr|rhea|kaedra|dav1d|sol-?ai|valerion|mesh|"
                      r"deploy|merge|commit|push|pr\b|pull request)")

#: Commands that change shared state and need a fresh COMPLETE receipt.
_PROTECTED_CMD = re.compile(
    r"(\bgit\s+(commit|push|merge|rebase)\b|\bgh\s+pr\s+(create|merge)\b|"
    r"\b(wrangler|netlify|vercel|flyctl|gcloud\s+run)\s+deploy\b|\bnpm\s+publish\b|"
    r"\bnougen(\.bat)?\s+(forget|retract)\b)", re.I)
_PROTECTED_TOOL = re.compile(r"(shards_forget|shards_retract|merge_pull_request|create_deployment|cf_deploy_worker)", re.I)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def tenant() -> str:
    """Tenant/vault identity. Receipts never cross this boundary."""
    raw = os.environ.get("NOUGEN_TENANT") or os.environ.get("NOUGEN_VAULT_ID") or "default"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", raw)[:64] or "default"


def receipts_dir(tenant_id: Optional[str] = None) -> Path:
    base = os.environ.get("NOUGEN_RECEIPTS_DIR")
    root = Path(base) if base else Path.home() / ".nougen" / "state" / "receipts"
    return root / (tenant_id or tenant())


def _safe_sid(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosid")[:128]


def receipt_path(session_id: str, tenant_id: Optional[str] = None) -> Path:
    return receipts_dir(tenant_id) / f"{_safe_sid(session_id)}.json"


def is_sensitive(prompt: str) -> bool:
    pattern = os.environ.get("NOUGEN_SENSITIVE_RE") or _DEFAULT_SENSITIVE
    try:
        return bool(re.search(pattern, prompt or "", re.I))
    except re.error:
        return bool(re.search(_DEFAULT_SENSITIVE, prompt or "", re.I))


def protected_reason(tool_name: str, command: str) -> str:
    """Name of the protected action, or "" when the call is not protected."""
    if _PROTECTED_TOOL.search(tool_name or ""):
        return tool_name
    m = _PROTECTED_CMD.search(command or "")
    return m.group(0) if m else ""


def relay_check() -> dict[str, Any]:
    """Count open relay legs and claims from the local registry. Read-only."""
    out: dict[str, Any] = {"ok": False, "legs": 0, "claims": 0}
    try:
        from . import lane_claim  # pylint: disable=import-outside-toplevel
        relay_dir = Path(os.environ.get("NOUGEN_RELAY_DIR") or Path.home() / ".nougen" / "relay")
        if not relay_dir.exists():
            out["error"] = "relay dir missing"
            return out
        claims = lane_claim.resolve_claims_dir()
        if not claims.exists() and (relay_dir / "claims").exists():
            claims = relay_dir / "claims"
        claim_files = set(claims.glob("*.json")) if claims.exists() else set()
        out["claims"] = len(claim_files)
        out["legs"] = sum(1 for p in relay_dir.glob("**/*.json") if p not in claim_files)
        out["ok"] = True
    except OSError as exc:
        out["error"] = type(exc).__name__
    return out


def classify(recall: dict[str, Any], relay: dict[str, Any]) -> tuple[str, str]:
    tier = str(recall.get("tier") or "none")
    if tier == "none":
        return UNKNOWN, str(recall.get("reason") or "recall did not finish")
    if recall.get("partial"):
        return DEGRADED, str(recall.get("reason") or "partial recall")
    if not relay.get("ok"):
        return DEGRADED, "relay/claims check failed: " + str(relay.get("error") or "unknown")
    return COMPLETE, ""


def build(session_id: str, prompt: str, recall: dict[str, Any],
          relay: Optional[dict[str, Any]] = None, agent: str = "") -> dict[str, Any]:
    relay = relay if relay is not None else relay_check()
    status, reason = classify(recall, relay)
    now = time.time()
    shards = recall.get("shards") or []
    refs = [str(s.get("id") or s.get("ref") or "") for s in shards if isinstance(s, dict)]
    return {
        "schema": SCHEMA,
        "tenant": tenant(),
        "session_id": session_id,
        "agent": agent or os.environ.get("NOUGEN_AGENT", "claude-cli"),
        "task_hash": hashlib.sha256((prompt or "").encode("utf-8", "replace")).hexdigest()[:16],
        "status": status,
        "reason": reason,
        "recall": {"tier": recall.get("tier", "none"), "partial": bool(recall.get("partial")),
                   "fanout": len(shards), "elapsed_ms": recall.get("elapsed_ms"),
                   "shard_refs": [r for r in refs if r][:20]},
        "relay": {k: relay.get(k) for k in ("ok", "legs", "claims", "error") if k in relay},
        "created": datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat(),
        "created_ts": now,
        "ttl_s": _int_env("NOUGEN_RECEIPT_TTL_S", 4 * 3600),
    }


def save(receipt: dict[str, Any]) -> Path:
    path = receipt_path(receipt["session_id"], receipt["tenant"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def invalidate(session_id: str, tenant_id: Optional[str] = None) -> None:
    """Replace any prior receipt with an UNKNOWN tombstone (or delete if write fails)."""
    tombstone = {
        "schema": SCHEMA,
        "tenant": tenant_id or tenant(),
        "session_id": session_id,
        "agent": os.environ.get("NOUGEN_AGENT", "claude-cli"),
        "task_hash": "",
        "status": UNKNOWN,
        "reason": "receipt could not be recorded for current prompt",
        "recall": {"tier": "none", "partial": True, "fanout": 0, "shard_refs": []},
        "relay": {"ok": False},
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "created_ts": time.time(),
        "ttl_s": _int_env("NOUGEN_RECEIPT_TTL_S", 4 * 3600),
    }
    try:
        save(tombstone)
        return
    except OSError:
        pass
    try:
        receipt_path(session_id, tenant_id).unlink(missing_ok=True)
    except OSError:
        pass


def load(session_id: str) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(receipt_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def validate(receipt: Optional[dict[str, Any]], session_id: str) -> tuple[bool, str]:
    """(ok, reason). ok only for a fresh COMPLETE receipt of this tenant+session."""
    if not receipt:
        return False, "no context receipt for this session (recall never ran)"
    if receipt.get("schema") != SCHEMA:
        return False, "receipt schema mismatch"
    if receipt.get("tenant") != tenant():
        return False, "receipt belongs to another tenant"
    if receipt.get("session_id") != session_id:
        return False, "receipt belongs to another session"
    age = time.time() - float(receipt.get("created_ts") or 0)
    if age > float(receipt.get("ttl_s") or 0) or age < -60:
        return False, f"receipt is stale ({int(age)}s old)"
    if receipt.get("status") != COMPLETE:
        return False, f"Shards {receipt.get('status')}: {receipt.get('reason') or 'not verified'}"
    return True, ""


def degraded_mode() -> str:
    """Explicit operator override. Only 'reviewed' lets mutations through degraded."""
    return (os.environ.get("NOUGEN_DEGRADED_MODE") or "").strip().lower()


def status_line(receipt: dict[str, Any]) -> str:
    st = receipt.get("status")
    rc = receipt.get("recall", {})
    if st == COMPLETE:
        return (f"Shards receipt: COMPLETE (tier {rc.get('tier')}, {rc.get('fanout')} shard(s), "
                f"relay legs {receipt.get('relay', {}).get('legs')}). Zero matches here is a real 'no match'.")
    return (f"Shards receipt: {st} ({receipt.get('reason')}). Memory state is NOT verified: do not "
            "say 'no memory' or 'nothing found'; report DEGRADED/UNKNOWN. Protected mutations "
            "(commit/push/merge/deploy/forget) are blocked until recall completes or "
            "NOUGEN_DEGRADED_MODE=reviewed is set.")
