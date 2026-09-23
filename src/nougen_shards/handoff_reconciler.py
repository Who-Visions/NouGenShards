r"""Zero-Drift Handoff & Claim Reconciler (Wishlist Item #1).

Authority: ~/.nougen/AUTHORITY.md
Mission:
    Autonomous reconciler that audits .handoffs/claims across fleet repositories,
    identifies stale or orphaned active claims, reconciles their status to 'released'
    (with provenance logs), and archives ancient claims to prevent file ceiling
    truncation (GitHub Contents API 1000-file cap).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ClaimAuditRecord:
    path: Path
    claim_id: str
    machine: str
    agent: str
    goal: str
    created_utc: Optional[str]
    status: str
    age_hours: float
    ttl_hours: float
    is_stale: bool
    action: str = "none"
    error: Optional[str] = None


@dataclass
class ReconciliationSummary:
    timestamp_utc: str
    target_dir: str
    total_claims_examined: int
    active_claims_found: int
    stale_claims_reconciled: int
    archived_claims_moved: int
    errors: int
    reconciled_details: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)


def parse_claim_created_dt(created_str: Optional[str]) -> Optional[datetime]:
    if not created_str:
        return None
    try:
        clean = created_str.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


def audit_claim_file(file_path: Path, now_utc: Optional[datetime] = None) -> ClaimAuditRecord:
    now = now_utc or datetime.now(timezone.utc)
    claim_id = file_path.stem
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as e:
        return ClaimAuditRecord(
            path=file_path,
            claim_id=claim_id,
            machine="unknown",
            agent="unknown",
            goal="",
            created_utc=None,
            status="corrupt",
            age_hours=0.0,
            ttl_hours=0.0,
            is_stale=False,
            error=str(e),
        )

    status = (data.get("status") or "active").strip().lower()
    created_str = data.get("created_utc") or data.get("created_at") or data.get("timestamp")
    created_dt = parse_claim_created_dt(created_str)

    ttl = float(data.get("ttl_hours") or data.get("ttl") or 8.0)
    age_hours = 0.0
    if created_dt:
        age_hours = max(0.0, (now - created_dt).total_seconds() / 3600.0)

    # Stale condition: active status and age > ttl_hours (or fallback default 2.0h if ttl <= 0)
    effective_ttl = ttl if ttl > 0 else 8.0
    is_stale = (status == "active") and (age_hours > effective_ttl)

    return ClaimAuditRecord(
        path=file_path,
        claim_id=claim_id,
        machine=data.get("machine") or "unknown",
        agent=data.get("agent") or "unknown",
        goal=data.get("goal") or "",
        created_utc=created_str,
        status=status,
        age_hours=round(age_hours, 2),
        ttl_hours=round(ttl, 2),
        is_stale=is_stale,
    )


def reconcile_claims_directory(
    claims_dir: Path,
    dry_run: bool = False,
    archive_older_than_days: Optional[int] = 7,
    now_utc: Optional[datetime] = None,
) -> ReconciliationSummary:
    """Audit and reconcile a .handoffs/claims directory.

    1. Reconcile stale active claims -> status: "released" (with release_reason: "stale_ttl_expired").
    2. Optional archival: moves released claims older than `archive_older_than_days` into `claims/archive/`.
    """
    now = now_utc or datetime.now(timezone.utc)
    summary = ReconciliationSummary(
        timestamp_utc=now.isoformat(),
        target_dir=str(claims_dir),
        total_claims_examined=0,
        active_claims_found=0,
        stale_claims_reconciled=0,
        archived_claims_moved=0,
        errors=0,
    )

    if not claims_dir.exists():
        return summary

    archive_dir = claims_dir / "archive"
    if not dry_run and archive_older_than_days is not None:
        archive_dir.mkdir(parents=True, exist_ok=True)

    for p in sorted(claims_dir.glob("*.json")):
        if p.name.startswith("."):
            continue
        summary.total_claims_examined += 1
        rec = audit_claim_file(p, now_utc=now)

        if rec.status == "active":
            summary.active_claims_found += 1

        if rec.is_stale:
            # Reconcile stale claim
            summary.stale_claims_reconciled += 1
            rec.action = "released_stale"
            summary.reconciled_details.append({
                "claim_id": rec.claim_id,
                "file": p.name,
                "machine": rec.machine,
                "agent": rec.agent,
                "age_hours": rec.age_hours,
                "ttl_hours": rec.ttl_hours,
                "goal": rec.goal[:80],
                "action": "released_stale",
            })

            if not dry_run:
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    data["status"] = "released"
                    data["released_utc"] = now.isoformat()
                    data["release_reason"] = f"stale_ttl_expired (age={rec.age_hours}h > ttl={rec.ttl_hours}h)"
                    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception as e:
                    summary.errors += 1
                    logger.error("Failed to update claim %s: %s", p, e)

        # Check for archive candidacy
        if archive_older_than_days is not None and rec.status in ("released", "expired", "archived") or rec.action == "released_stale":
            if rec.age_hours >= (archive_older_than_days * 24.0):
                summary.archived_claims_moved += 1
                if not dry_run:
                    dest = archive_dir / p.name
                    try:
                        p.replace(dest)
                    except Exception as e:
                        summary.errors += 1
                        logger.error("Failed to archive claim %s: %s", p, e)

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Zero-Drift Handoff & Claim Reconciler")
    parser.add_argument("--dir", default=str(Path.home() / "Outpost" / "NouGenRelay" / ".handoffs" / "claims"), help="Target claims dir")
    parser.add_argument("--dry-run", action="store_true", help="Audit without mutating")
    parser.add_argument("--archive-days", type=int, default=7, help="Archive released claims older than N days")
    args = parser.parse_args()

    s = reconcile_claims_directory(Path(args.dir), dry_run=args.dry_run, archive_older_than_days=args.archive_days)
    print(s.to_json())
