"""Synthetic scenarios for control_loop tests and eval. All names are invented."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

NOW = datetime(2030, 1, 15, 12, 0, tzinfo=timezone.utc)


def iso(delta_s: float = 0) -> str:
    return (NOW + timedelta(seconds=delta_s)).isoformat()


def aligned_execution() -> dict:
    return {
        "provider_affinity": {"pinned": "node-alpha", "source": "cache:affinity"},
        "tool_health": {"node-alpha": {"status": "GREEN", "observed_utc": iso(-30)}},
        "branch_claims": [{"id": "claim-1", "state": "live", "source": "branch:main"}],
        "leases": [{"id": "lease-1", "token_cap": 5000, "source": "lease-table"}],
        "claims": [{"task_id": "task-9", "owner": "agent-a", "expires_utc": iso(3600), "source": "claim-registry"}],
        "revealed_share": {"correctness": 0.6, "speed": 0.4},
    }


def full_goal() -> dict:
    return {"task_id": "task-9", "actor": "agent-a",
            "constraints": {"dynamic_failover": True, "preserve_canon": True,
                            "token_budget": 10000, "no_duplicate": True},
            "priorities": ["correctness", "speed"]}


def scenarios() -> list:
    """(name, goal, execution, expected_verdict, expected_check)."""
    out = [("aligned", full_goal(), aligned_execution(), "ALIGNED", None)]

    e = aligned_execution()
    e["tool_health"]["node-alpha"]["status"] = "RED"
    out.append(("dead_pinned_provider", full_goal(), e, "CONFLICTED", "provider_affinity"))

    e = aligned_execution()
    e["branch_claims"].append({"id": "claim-2", "state": "draft", "source": "branch:wip"})
    out.append(("stale_draft_claim", full_goal(), e, "CONFLICTED", "canon_state"))

    e = aligned_execution()
    e["leases"].append({"id": "lease-sub", "token_cap": None, "source": "subagent"})
    out.append(("runaway_lease", full_goal(), e, "CONFLICTED", "lease_budget"))

    e = aligned_execution()
    e["claims"] = [{"task_id": "task-9", "owner": "agent-b", "expires_utc": iso(3600), "source": "claim-registry"}]
    out.append(("duplicate_claim", full_goal(), e, "CONFLICTED", "duplicate_claim"))

    e = aligned_execution()
    e["revealed_share"] = {"correctness": 0.2, "speed": 0.8}
    out.append(("priority_inversion", full_goal(), e, "CONFLICTED", "priority_inversion"))

    e = aligned_execution()
    e["tool_health"]["node-alpha"]["observed_utc"] = iso(-86400)
    out.append(("stale_health_unknown", full_goal(), e, "UNKNOWN", None))

    e = aligned_execution()
    del e["claims"]
    out.append(("claims_unread_unknown", full_goal(), e, "UNKNOWN", None))

    e = aligned_execution()
    e["claims"] = [{"task_id": "task-9", "owner": "agent-b", "expires_utc": iso(-60), "source": "claim-registry"}]
    out.append(("expired_claim_control", full_goal(), e, "ALIGNED", None))
    return out
