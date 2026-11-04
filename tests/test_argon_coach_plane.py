"""Unit tests for nougen_shards.argon_coach_plane."""
from __future__ import annotations

import json
import pytest

from nougen_shards.argon_coach_plane import (
    ArgonHeadCoach,
    BudgetGovernor,
    LaneTier,
)


def test_budget_governor_enforces_99_99_ratio():
    gov = BudgetGovernor(max_argon_invocation_ratio=0.005, hard_floor_free_calls=200)
    assert gov.free_token_ratio == 1.0

    # Simulate 1 Argon coach call (500 tokens) and 250 local free calls (250,000 tokens)
    gov.record_call(LaneTier.HEAD_COACH_ARGON, 500)
    for _ in range(250):
        gov.record_call(LaneTier.LOCAL_KAEDRA, 1000)

    # 1 / 251 = 0.00398 (< 0.005 cap)
    assert gov.free_token_ratio > 0.998

    # Another Argon call pushes ratio to 2 / 252 = 0.0079 (> 0.005 cap)
    gov.record_call(LaneTier.HEAD_COACH_ARGON, 500)
    allowed, reason = gov.can_summon_coach(
        complexity_score=0.88,
        is_architectural_fork=False,
        local_fumble_count=0,
    )
    assert not allowed
    assert "BUDGET_CAP_ACTIVE" in reason

    # Architectural fork or 3 local fumbles overrides cap
    allowed_fork, reason_fork = gov.can_summon_coach(0.5, is_architectural_fork=True, local_fumble_count=0)
    assert allowed_fork
    assert reason_fork == "ARCHITECTURAL_FORK_OVERRIDE"

    allowed_fumble, reason_fumble = gov.can_summon_coach(0.5, is_architectural_fork=False, local_fumble_count=3)
    assert allowed_fumble
    assert reason_fumble == "LOCAL_QB_FUMBLE_ESCALATION"


def test_mst_projection_is_bounded_and_deterministic():
    gov = BudgetGovernor()
    coach = ArgonHeadCoach(
        governor=gov,
        argon_dispatch_fn=lambda s, p: ("{}", 0),
        worker_dispatch_fn=lambda lane, p: ("", 0),
        sandbox_verify_fn=lambda c, t: (0, "ok"),
        shard_capture_fn=lambda t, c, tags: None,
    )

    shards = [
        {"id": i, "_db_index": 1, "title": f"Shard {i}", "content": "x" * 1000, "density_score": 0.9, "utility_score": 0.8}
        for i in range(15)
    ]
    asts = {"core.py": "def retrieve(): ..." * 200}

    packet1, hash1 = coach.build_mst_projection("Harden hallway router", shards, asts, ["blade1tb"], max_chars=4000)
    packet2, hash2 = coach.build_mst_projection("Harden hallway router", shards, asts, ["blade1tb"], max_chars=4000)

    assert len(packet1) <= 4000
    assert hash1 == hash2
    assert len(hash1) == 16


def test_draft_and_execute_playbook_with_self_healing_retry():
    gov = BudgetGovernor()
    captured_shards = []

    playbook_payload = {
        "invariants": ["Zero dropped shards", "All tests pass"],
        "rollback_strategy": "git checkout -- .",
        "steps": [
            {
                "step_id": "step_1_circuit_breaker",
                "assigned_lane": "phoebus:ollama:kaedracode",
                "target_files": ["src/hallway.py"],
                "objective": "Add HTTP 206/503 circuit breaker",
                "prompt_template": "Implement circuit breaker",
                "verification_cmd": "pytest tests/test_hallway.py",
                "timeout_s": 60,
                "max_local_retries": 3,
                "depends_on": [],
            },
            {
                "step_id": "step_2_verify_surface",
                "assigned_lane": "blade:ollama:dav1d:e2b",
                "target_files": ["tests/test_hallway.py"],
                "objective": "Verify edge cases",
                "prompt_template": "Add edge tests",
                "verification_cmd": "pytest tests/test_hallway.py -k edge",
                "timeout_s": 60,
                "max_local_retries": 2,
                "depends_on": ["step_1_circuit_breaker"],
            },
        ],
    }

    def fake_argon(sys_prompt: str, mst: str):
        return f"```json\n{json.dumps(playbook_payload)}\n```", 400

    worker_calls = []

    def fake_worker(lane: LaneTier, prompt: str):
        worker_calls.append((lane, prompt))
        return f"patched by {lane.value}", 50000

    verify_attempts = {"count": 0}

    def fake_sandbox(cmd: str, timeout: int):
        verify_attempts["count"] += 1
        # Fail first attempt of step 1 to test self-healing retry
        if verify_attempts["count"] == 1:
            return 1, "AssertionError: HTTP 206 not handled"
        return 0, "1 passed"

    coach = ArgonHeadCoach(
        governor=gov,
        argon_dispatch_fn=fake_argon,
        worker_dispatch_fn=fake_worker,
        sandbox_verify_fn=fake_sandbox,
        shard_capture_fn=lambda title, content, tags: captured_shards.append((title, content, tags)),
    )

    mst, h = coach.build_mst_projection("Fix HF Space pause", [], {}, [])
    dag = coach.draft_playbook("Fix HF Space pause", mst, h)
    result = coach.execute_playbook(dag)

    assert result["status"] == "TOUCHDOWN"
    assert len(result["telemetry"]) == 3  # 2 attempts on step_1 + 1 attempt on step_2
    assert gov.free_token_ratio > 0.997
    assert len(captured_shards) == 1
    assert "PREVIOUS_ATTEMPT_STDERR" in worker_calls[1][1]


def test_argon_cannot_assign_step_to_itself():
    gov = BudgetGovernor()
    bad_payload = {
        "steps": [
            {
                "step_id": "bad_step",
                "assigned_lane": "antigravity:argon",
                "target_files": [],
                "objective": "Run ball",
                "prompt_template": "Code it",
                "verification_cmd": "pytest",
            }
        ]
    }
    coach = ArgonHeadCoach(
        governor=gov,
        argon_dispatch_fn=lambda s, m: (json.dumps(bad_payload), 100),
        worker_dispatch_fn=lambda lane, p: ("", 0),
        sandbox_verify_fn=lambda c, t: (0, ""),
        shard_capture_fn=lambda t, c, tags: None,
    )
    with pytest.raises(ValueError, match="illegally assigned"):
        coach.draft_playbook("Goal", "{}", "deadbeef12345678")


def test_fumble_halt_escalates_to_local_iris():
    gov = BudgetGovernor()
    payload = {
        "steps": [
            {
                "step_id": "step_fail",
                "assigned_lane": "phoebus:ollama:kaedracode",
                "target_files": ["a.py"],
                "objective": "Fix bug",
                "prompt_template": "Patch a.py",
                "verification_cmd": "pytest",
                "max_local_retries": 2,
            }
        ]
    }
    coach = ArgonHeadCoach(
        governor=gov,
        argon_dispatch_fn=lambda s, m: (json.dumps(payload), 100),
        worker_dispatch_fn=lambda lane, p: ("DIAGNOSIS: missing import" if lane == LaneTier.LOCAL_IRIS else "patch", 1000),
        sandbox_verify_fn=lambda c, t: (1, "ImportError: no module"),
        shard_capture_fn=lambda t, c, tags: None,
    )
    dag = coach.draft_playbook("Goal", "{}", "1234567890abcdef")
    res = coach.execute_playbook(dag)
    assert res["status"] == "FUMBLE_HALTED"
    assert res["failed_step"] == "step_fail"
    assert "DIAGNOSIS" in res["iris_diagnosis"]


# --- Review fixes (agy Argon low/medium/high review, 2026-11-04) -----------------------------

import subprocess

from nougen_shards.argon_coach_plane import GamePlanDAG, PlayStep, resolve_argon_model


def _step(step_id, deps=(), cmd="true", retries=1):
    return PlayStep(step_id=step_id, assigned_lane=LaneTier.LOCAL_DAV1D, target_files=[], objective=step_id,
                    prompt_template=step_id, verification_cmd=cmd, timeout_s=5, max_local_retries=retries,
                    depends_on=list(deps))


def _coach(gov=None, verify=None, argon=None, worker=None):
    return ArgonHeadCoach(
        gov or BudgetGovernor(),
        argon or (lambda s, m: ("{}", 1)),
        worker or (lambda lane, p: ("ok", 1)),
        verify or (lambda cmd, t: (0, "")),
        lambda *a: None,
    )


def test_mst_packet_stays_valid_json_when_over_budget():
    coach = _coach()
    shards = [{"id": i, "title": f"t{i}", "content": "x" * 450, "density_score": 1, "utility_score": 1} for i in range(8)]
    packet, _ = coach.build_mst_projection("goal", shards, {"a.py": "y" * 1200, "b.py": "z" * 1200}, [], max_chars=1500)
    assert len(packet) <= 1500
    data = json.loads(packet)  # a raw character cut would raise here
    assert data["mission_goal"] == "goal"
    assert len(data["high_density_shards"]) < 8


def test_steps_run_in_dependency_order_even_when_listed_out_of_order():
    ran = []
    coach = _coach(worker=lambda lane, p: (ran.append(p) or "ok", 1))
    dag = GamePlanDAG("p", "g", "h", [], [_step("b", deps=["a"]), _step("a")], "", 0.0)
    assert coach.execute_playbook(dag)["status"] == "TOUCHDOWN"
    assert ran == ["a", "b"]


def test_unknown_dependency_and_cycle_are_rejected():
    coach = _coach()
    with pytest.raises(RuntimeError, match="not in the plan"):
        coach.execute_playbook(GamePlanDAG("p", "g", "h", [], [_step("a", deps=["ghost"])], "", 0.0))
    with pytest.raises(RuntimeError, match="cycle"):
        coach.execute_playbook(GamePlanDAG("p", "g", "h", [], [_step("a", deps=["b"]), _step("b", deps=["a"])], "", 0.0))


def test_verify_timeout_is_a_failed_attempt_not_a_crash_and_rollback_runs():
    cmds = []

    def verify(cmd, t):
        cmds.append(cmd)
        if cmd == "git checkout -- .":
            return 0, "restored"
        raise subprocess.TimeoutExpired(cmd, t)

    coach = _coach(verify=verify)
    dag = GamePlanDAG("p", "g", "h", [], [_step("a", cmd="pytest", retries=2)], "git checkout -- .", 0.0)
    out = coach.execute_playbook(dag)
    assert out["status"] == "FUMBLE_HALTED"
    assert [t["exit_code"] for t in out["telemetry"]] == [124, 124]
    assert out["rollback"]["exit_code"] == 0 and cmds[-1] == "git checkout -- ."


def _payload(**step):
    base = {"step_id": "s", "assigned_lane": LaneTier.LOCAL_DAV1D.value, "objective": "o", "prompt_template": "p",
            "verification_cmd": "pytest"}
    base.update(step)
    return json.dumps({"steps": [base]})


def test_draft_rejects_empty_verification_and_clamps_bad_numbers():
    with pytest.raises(ValueError, match="verification_cmd"):
        _coach(argon=lambda s, m: (_payload(verification_cmd="  "), 1)).draft_playbook("g", "{}", "h")
    dag = _coach(argon=lambda s, m: (_payload(timeout_s=0, max_local_retries=-1), 1)).draft_playbook("g", "{}", "h")
    assert dag.steps[0].timeout_s > 0 and dag.steps[0].max_local_retries > 0


def test_draft_asks_the_governor_first():
    calls = []
    gov = BudgetGovernor(warmup_argon_calls=0)
    coach = _coach(gov=gov, argon=lambda s, m: (calls.append(1) or _payload(), 1))
    with pytest.raises(PermissionError):
        coach.draft_playbook("g", "{}", "h", complexity_score=0.5)
    assert calls == []


def test_draft_reads_json_wrapped_in_prose_and_names_the_argon_model():
    dag = _coach(argon=lambda s, m: (f"Here is the plan:\n```json\n{_payload()}\n```\nGood luck.", 1)).draft_playbook(
        "g", "{}", "h", complexity_score=0.9, served_models=["gemini-4-argon-medium", "gemini-4-argon-high"])
    assert dag.argon_model == "gemini-4-argon-high"


def test_resolve_argon_model_tiers_pin_and_fallback(monkeypatch):
    monkeypatch.delenv("NOUGEN_ARGON_MODEL", raising=False)
    assert resolve_argon_model(0.9) == "gemini-4-argon-high"
    assert resolve_argon_model(0.6) == "gemini-4-argon-medium"
    assert resolve_argon_model(0.1) == "gemini-4-argon-low"
    assert resolve_argon_model(0.9, served=["gemini-4-argon-medium"]) == "gemini-4-argon-medium"
    monkeypatch.setenv("NOUGEN_ARGON_MODEL", "gemini-4-argon-low")
    assert resolve_argon_model(0.99) == "gemini-4-argon-low"


def test_governor_caps_warmup_and_token_share():
    gov = BudgetGovernor(warmup_argon_calls=1, min_free_token_ratio=0.9)
    assert gov.can_summon_coach(0.86, False, 0)[0] is True
    gov.record_call(LaneTier.HEAD_COACH_ARGON, 10)
    allowed, reason = gov.can_summon_coach(0.86, False, 0)
    assert allowed is False and reason.startswith("BUDGET_WARMUP_CAP")
    gov2 = BudgetGovernor(warmup_argon_calls=99, min_free_token_ratio=0.9)
    gov2.record_call(LaneTier.HEAD_COACH_ARGON, 5000)
    gov2.record_call(LaneTier.LOCAL_DAV1D, 100)
    allowed, reason = gov2.can_summon_coach(0.86, False, 0)
    assert allowed is False and reason.startswith("TOKEN_BUDGET_CAP")
    assert gov2.can_summon_coach(0.95, False, 0)[0] is True  # the override still wins
    assert 0 < gov2.free_invocation_ratio < 1


def test_dag_to_dict_serializes_lanes():
    d = GamePlanDAG("p", "g", "h", [], [_step("a")], "", 0.0).to_dict()
    assert d["steps"][0]["assigned_lane"] == LaneTier.LOCAL_DAV1D.value
    json.dumps(d)
