"""
Unit tests for control_loop_elevated module.
"""
from datetime import datetime, timezone
from nougen_shards.control_loop import ALIGNED, CONFLICTED, UNKNOWN
from nougen_shards.control_loop_elevated import compute_alignment_transfer, AlignmentVector

def test_alignment_transfer_clean():
    now_dt = datetime.fromisoformat("2026-09-27T13:00:00+00:00")
    goal = {"constraints": {"dynamic_failover": True, "preserve_canon": True}}
    execution = {"provider_affinity": {"pinned": "blade"}, "tool_health": {"blade": {"status": "GREEN", "observed_utc": "2026-09-27T13:00:00Z"}}}
    
    vec, status = compute_alignment_transfer(goal, execution, now=now_dt)
    assert isinstance(vec, AlignmentVector)
    assert vec.total_alignment_index == 1.0
    assert status == ALIGNED

def test_alignment_transfer_conflict():
    now_dt = datetime.fromisoformat("2026-09-27T13:00:00+00:00")
    goal = {"constraints": {"dynamic_failover": True}}
    execution = {"provider_affinity": {"pinned": "blade"}, "tool_health": {"blade": {"status": "RED", "observed_utc": "2026-09-27T13:00:00Z"}}}
    
    vec, status = compute_alignment_transfer(goal, execution, now=now_dt)
    assert vec.failover_score == 0.0
    assert vec.total_alignment_index == 0.0
    assert status == CONFLICTED
