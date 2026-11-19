# tests/test_coaching_staff_orchestrator.py
from __future__ import annotations

import json

from nougen_shards.coaching_staff_orchestrator import (
    CoachingStaffBooth,
    CoordinatorSeat,
    CrossBoothShadowCache,
    EVIGatekeeper,
    SwarmPlayer,
    TaskSignal,
)


def _make_signal(**overrides) -> TaskSignal:
    defaults = {
        "goal": "stabilize distributed shard sync",
        "domain_tags": ["shards"],
        "structural_divergence_jsd": 0.25,
        "cyclomatic_complexity": 8,
        "concurrency_depth": 1,
        "schema_surface_count": 1,
        "algorithmic_depth": 0.2,
        "latency_budget_ms": 5000,
        "local_fumble_streak": 0,
    }
    defaults.update(overrides)
    return TaskSignal(**defaults)


def test_evi_gatekeeper_keeps_routine_tasks_on_free_swarm():
    gk = EVIGatekeeper(hard_cap_ratio=0.0001)
    seat, reason = gk.select_coordinator(_make_signal())
    assert seat is None
    assert reason == "SWARM_AUTONOMOUS_EXECUTION"


def test_evi_gatekeeper_routes_each_orthogonally_specialized_seat():
    gk = EVIGatekeeper(hard_cap_ratio=0.005)

    # 1. Argon: high structural divergence + architecture tags
    s_argon = _make_signal(
        domain_tags=["architecture", "dag", "mesh", "topology", "lineage"],
        structural_divergence_jsd=0.92,
    )
    seat, reason = gk.select_coordinator(s_argon)
    assert seat == CoordinatorSeat.HEAD_COACH_ARGON
    assert "SUMMONED_HEAD_COACH_ARGON" in reason

    # 2. Opus: deep concurrency + race/security + cyclomatic complexity
    s_opus = _make_signal(
        domain_tags=["security", "race"],
        concurrency_depth=4,
        cyclomatic_complexity=45,
        local_fumble_streak=2,
    )
    seat, _ = gk.select_coordinator(s_opus)
    assert seat == CoordinatorSeat.DEFENSIVE_COORD_OPUS

    # 3. Fable: schema surface + protocol/interface
    s_fable = _make_signal(
        domain_tags=["protocol", "interface"],
        schema_surface_count=6,
        local_fumble_streak=2,
    )
    seat, _ = gk.select_coordinator(s_fable)
    assert seat == CoordinatorSeat.SPECIAL_TEAMS_FABLE

    # 4. Astra: algorithmic depth + math/optimization
    s_astra = _make_signal(
        domain_tags=["math", "optimization"],
        algorithmic_depth=0.95,
        local_fumble_streak=2,
    )
    seat, _ = gk.select_coordinator(s_astra)
    assert seat == CoordinatorSeat.OFFENSIVE_COORD_ASTRA

    # 5. Sol: sub-2500ms latency budget + relay/hotfix
    s_sol = _make_signal(
        domain_tags=["relay", "hotfix"],
        latency_budget_ms=1200,
        local_fumble_streak=2,
    )
    seat, _ = gk.select_coordinator(s_sol)
    assert seat == CoordinatorSeat.TEMPO_COORD_SOL


def test_evi_gatekeeper_enforces_99_99_booth_cap_unless_deadlocked():
    gk = EVIGatekeeper(hard_cap_ratio=0.0001)
    # Burn booth tokens past 0.01% of 1,000,000 (= 100 tokens)
    gk.record_usage(CoordinatorSeat.HEAD_COACH_ARGON.value, 250)
    assert gk.current_free_ratio < 0.9999

    # Fumble streak 2 is blocked by BOOTH_CAP_GUARD
    s_blocked = _make_signal(
        domain_tags=["architecture", "dag", "mesh", "topology"],
        structural_divergence_jsd=0.9,
        local_fumble_streak=2,
    )
    seat, reason = gk.select_coordinator(s_blocked)
    assert seat is None
    assert "BOOTH_CAP_GUARD" in reason

    # Confirmed deadlock (fumble_streak >= 3) overrides cap
    s_deadlock = _make_signal(
        domain_tags=["architecture", "dag", "mesh", "topology"],
        structural_divergence_jsd=0.9,
        local_fumble_streak=3,
    )
    seat2, _ = gk.select_coordinator(s_deadlock)
    assert seat2 == CoordinatorSeat.HEAD_COACH_ARGON


def test_dual_coordinator_algebraic_synthesis_and_field_execution():
    gk = EVIGatekeeper(hard_cap_ratio=0.01)

    def fake_frontier(seat: CoordinatorSeat, sys_prompt: str, state: str):
        if seat == CoordinatorSeat.HEAD_COACH_ARGON:
            return (
                json.dumps(
                    {
                        "target_files": ["src/nougen_shards/router.py"],
                        "formal_invariants": ["free_ratio >= 0.9999"],
                        "ast_signature_map": {"route_play": ["signal", "budget"]},
                        "assigned_swarm_lanes": {
                            "src/nougen_shards/router.py": SwarmPlayer.QB_KAEDRA.value
                        },
                        "verification_commands": ["pytest tests/test_router.py -q"],
                        "confidence_weight": 0.92,
                    }
                ),
                40,
            )
        return (
            json.dumps(
                {
                    "target_files": [
                        "src/nougen_shards/router.py",
                        "src/nougen_shards/locks.py",
                    ],
                    "formal_invariants": [
                        "free_ratio >= 0.9999",
                        "no_unbounded_mutex_wait",
                    ],
                    "ast_signature_map": {
                        "route_play": ["signal"],
                        "acquire_guard": ["timeout_ms"],
                    },
                    "assigned_swarm_lanes": {
                        "src/nougen_shards/locks.py": SwarmPlayer.SAFETY_IRIS.value
                    },
                    "verification_commands": [
                        "pytest tests/test_router.py -q",
                        "pytest tests/test_locks.py -q",
                    ],
                    "confidence_weight": 0.88,
                }
            ),
            45,
        )

    booth = CoachingStaffBooth(
        gatekeeper=gk,
        frontier_call_fn=fake_frontier,
        swarm_call_fn=lambda player, prompt: ("def route_play(): pass", 4000),
        sandbox_run_fn=lambda cmd: (0, "2 passed"),
    )

    directive = booth.synthesize_dual_coordinator_directive(
        primary_seat=CoordinatorSeat.HEAD_COACH_ARGON,
        secondary_seat=CoordinatorSeat.DEFENSIVE_COORD_OPUS,
        compressed_state_json='{"goal":"lockfree_router"}',
    )

    assert directive.target_files == [
        "src/nougen_shards/router.py",
        "src/nougen_shards/locks.py",
    ]
    assert directive.formal_invariants == [
        "free_ratio >= 0.9999",
        "no_unbounded_mutex_wait",
    ]
    # Argon (0.92) beats Opus (0.88) on route_play signature tie, while preserving acquire_guard
    assert directive.ast_signature_map["route_play"] == ["signal", "budget"]
    assert directive.ast_signature_map["acquire_guard"] == ["timeout_ms"]
    assert directive.confidence_weight == 0.9

    result = booth.run_field_execution(directive, context_slice="router context")
    assert result["status"] == "CHAMPIONSHIP_DRIVE_COMPLETE"
    assert result["free_ratio"] > 0.9999
    assert len(result["execution_log"]) == 2


def test_cross_booth_shadow_cache_rebinds_isomorphic_ast_at_zero_frontier_cost():
    cache = CrossBoothShadowCache(":memory:")
    gk = EVIGatekeeper(hard_cap_ratio=0.01)
    frontier_calls = 0

    def fake_frontier(seat: CoordinatorSeat, sys_prompt: str, state: str):
        nonlocal frontier_calls
        frontier_calls += 1
        return (
            json.dumps(
                {
                    "target_files": ["src/service_a/handler.py"],
                    "formal_invariants": ["idempotent_write_key_required"],
                    "ast_signature_map": {"handle_capture": ["payload", "idempotency_key"]},
                    "assigned_swarm_lanes": {
                        "src/service_a/handler.py": SwarmPlayer.ANCHOR_DAV1D.value
                    },
                    "verification_commands": ["pytest -k test_idempotent_capture"],
                    "confidence_weight": 0.95,
                }
            ),
            50,
        )

    booth = CoachingStaffBooth(
        gatekeeper=gk,
        frontier_call_fn=fake_frontier,
        swarm_call_fn=lambda player, prompt: ("patched", 2500),
        sandbox_run_fn=lambda cmd: (0, "ok"),
        shadow_cache=cache,
    )

    first = booth.summon_coordinator(
        CoordinatorSeat.SPECIAL_TEAMS_FABLE, '{"service":"a"}'
    )
    assert frontier_calls == 1

    # Isomorphic AST problem appears in service_b -> served from SQLite FTS5 shadow cache with 0 frontier calls
    rebound = cache.lookup_isomorphic(
        first.ast_signature_map,
        rebind_files=["src/service_b/ingest.py"],
    )
    assert rebound is not None
    assert frontier_calls == 1
    assert rebound.target_files == ["src/service_b/ingest.py"]
    assert rebound.assigned_swarm_lanes["src/service_b/ingest.py"] == SwarmPlayer.ANCHOR_DAV1D
    assert rebound.formal_invariants == ["idempotent_write_key_required"]
