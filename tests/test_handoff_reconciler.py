"""Unit tests for Zero-Drift Handoff & Claim Reconciler (tests/test_handoff_reconciler.py)."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import pytest

from nougen_shards.handoff_reconciler import (
    audit_claim_file,
    reconcile_claims_directory,
)


def test_audit_claim_file_active_and_stale(tmp_path):
    now = datetime(2026, 9, 23, 14, 0, 0, tzinfo=timezone.utc)
    
    # 1. Fresh claim (1 hour old, 8h TTL) -> not stale
    fresh_file = tmp_path / "fresh_claim.json"
    fresh_file.write_text(json.dumps({
        "machine": "whoart",
        "agent": "antigravity",
        "goal": "implement test feature",
        "created_utc": (now - timedelta(hours=1)).isoformat(),
        "ttl_hours": 8.0,
        "status": "active"
    }), encoding="utf-8")
    
    rec_fresh = audit_claim_file(fresh_file, now_utc=now)
    assert rec_fresh.status == "active"
    assert rec_fresh.is_stale is False
    assert rec_fresh.age_hours == 1.0

    # 2. Stale claim (10 hours old, 8h TTL) -> is stale
    stale_file = tmp_path / "stale_claim.json"
    stale_file.write_text(json.dumps({
        "machine": "blade1tb",
        "agent": "claude-cli",
        "goal": "abandoned task",
        "created_utc": (now - timedelta(hours=10)).isoformat(),
        "ttl_hours": 8.0,
        "status": "active"
    }), encoding="utf-8")

    rec_stale = audit_claim_file(stale_file, now_utc=now)
    assert rec_stale.status == "active"
    assert rec_stale.is_stale is True
    assert rec_stale.age_hours == 10.0


def test_reconcile_claims_directory_dry_run_and_execution(tmp_path):
    now = datetime(2026, 9, 23, 14, 0, 0, tzinfo=timezone.utc)
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()

    # Create 1 fresh active, 1 stale active, 1 old released
    (claims_dir / "fresh.json").write_text(json.dumps({
        "machine": "whoart",
        "agent": "antigravity",
        "created_utc": (now - timedelta(minutes=30)).isoformat(),
        "ttl_hours": 2.0,
        "status": "active"
    }), encoding="utf-8")

    (claims_dir / "stale.json").write_text(json.dumps({
        "machine": "phoebus",
        "agent": "keadracode",
        "created_utc": (now - timedelta(hours=5)).isoformat(),
        "ttl_hours": 2.0,
        "status": "active"
    }), encoding="utf-8")

    (claims_dir / "ancient_released.json").write_text(json.dumps({
        "machine": "whoart",
        "agent": "antigravity",
        "created_utc": (now - timedelta(days=10)).isoformat(),
        "ttl_hours": 2.0,
        "status": "released"
    }), encoding="utf-8")

    # Dry-run audit
    summary_dry = reconcile_claims_directory(claims_dir, dry_run=True, archive_older_than_days=7, now_utc=now)
    assert summary_dry.total_claims_examined == 3
    assert summary_dry.active_claims_found == 2
    assert summary_dry.stale_claims_reconciled == 1
    assert summary_dry.archived_claims_moved == 1

    # Verify no mutation occurred during dry-run
    stale_data_pre = json.loads((claims_dir / "stale.json").read_text(encoding="utf-8"))
    assert stale_data_pre["status"] == "active"

    # Execution run
    summary_live = reconcile_claims_directory(claims_dir, dry_run=False, archive_older_than_days=7, now_utc=now)
    assert summary_live.stale_claims_reconciled == 1

    # Verify mutation: stale claim transitioned to released
    stale_data_post = json.loads((claims_dir / "stale.json").read_text(encoding="utf-8"))
    assert stale_data_post["status"] == "released"
    assert "stale_ttl_expired" in stale_data_post["release_reason"]
    assert "released_utc" in stale_data_post

    # Verify archival: ancient_released.json was moved to archive/
    assert not (claims_dir / "ancient_released.json").exists()
    assert (claims_dir / "archive" / "ancient_released.json").exists()
