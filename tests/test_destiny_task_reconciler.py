"""Destiny task reconciler: claim, bounded recall receipt, gates, retries, crash-resume.

All ports are scripted; nothing touches the network, the real vault or a relay.
"""
import sqlite3
import time

import pytest

from nougen_shards import destiny, destiny_task_reconciler as dr


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_DESTINY_DB", str(tmp_path / "destinies.db"))
    monkeypatch.setenv("NOUGEN_RECONCILER_DB", str(tmp_path / "rec.db"))
    monkeypatch.setenv("NOUGEN_RECEIPTS_DIR", str(tmp_path / "receipts"))
    monkeypatch.setenv("NOUGEN_TENANT", "tenant-a")
    return tmp_path


def make_ports(clock, *, destinies=None, intents=None, shards=None, execute=None, verify=None,
               agents=None, recall=None, record_evidence=None, log=None):
    log = log if log is not None else {}
    log.setdefault("evidence", [])
    log.setdefault("relay", [])
    log.setdefault("links", [])
    log.setdefault("updates", [])
    log.setdefault("utility", [])
    shards = shards if shards is not None else [{"id": "1@db1", "text": "fact " * 10}]

    def _recall(q, n):
        return {"tier": "full", "partial": False, "shards": shards[:n], "elapsed_ms": 1}

    return dr.Ports(
        list_destinies=lambda: destinies or [],
        list_intents=lambda: intents or [],
        recall=recall or _recall,
        execute=execute or (lambda task, agent, route, ctx, strat: {"output": "ok", "tokens": 10}),
        verify=verify or (lambda task, res: {"passed": True, "evidence": "hidden test green", "verifier": "judge"}),
        agents=lambda: agents or [dr.Agent("a1"), dr.Agent("a2")],
        record_evidence=record_evidence or (lambda t, p: log["evidence"].append(p) or f"9{len(log['evidence'])}@db1"),
        publish_relay=lambda t, p: log["relay"].append(p) or f"leg{len(log['relay'])}",
        link_destiny=lambda *a: log["links"].append(a),
        update_destiny=lambda *a: log["updates"].append(a),
        mark_utility=lambda refs, helped: log["utility"].append((refs, helped)),
        relay_check=lambda: {"ok": True, "legs": 0, "claims": 0},
        clock=clock,
    ), log


def dest(i=1, **kw):
    d = {"id": i, "title": f"D{i}", "goal": "do the thing", "status": "active",
         "verification": "hidden unit test", "required_events": []}
    d.update(kw)
    return d


def test_discover_is_idempotent_and_skips_unverifiable(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1, required_events=["e1", "e2"]), dest(2, verification=None),
                                        dest(3, status="fulfilled")],
                          intents=[{"ref": "55@db8", "text": "ship the gate", "destiny_id": 1}])
    first = dr.discover(ports)
    second = dr.discover(ports)
    assert first == {"added": 3, "skipped_no_verification": 1, "skipped_no_destiny": 0}
    assert second["added"] == 0
    assert dr.status()["tasks"] == {"queued": 3}


def test_happy_path_links_evidence_and_keeps_destiny_open(env):
    c = Clock()
    ports, log = make_ports(c, destinies=[dest(1, status="dormant")])
    out = dr.tick(dr.Config(), ports)
    r = out["results"][0]
    assert r["outcome"] == "done" and r["attempts"] == 1
    kinds = {(k, role) for (_, k, _, role) in log["links"]}
    assert kinds == {("shard", "evidence"), ("relay", "outcome"), ("agent", "actor")}
    assert log["updates"] == [(1, "active", "reconciler", "reconciler: first verified task")]
    assert log["utility"] == [(["1@db1"], True)]


def test_auto_fulfill_only_when_every_task_done(env):
    c = Clock()
    ports, log = make_ports(c, destinies=[dest(1, required_events=["e1", "e2"])])
    dr.tick(dr.Config(auto_fulfill=True), ports)
    assert (1, "fulfilled") in {(u[0], u[1]) for u in log["updates"]}
    ports2, log2 = make_ports(c, destinies=[dest(2, required_events=["e1", "e2"])])
    dr.tick(dr.Config(auto_fulfill=True, max_tasks_per_tick=1), ports2)
    assert all(u[1] != "fulfilled" for u in log2["updates"])


def test_recall_is_bounded_and_receipt_is_tenant_scoped(env):
    c = Clock()
    big = [{"id": f"{i}@db1", "text": "x" * 4000} for i in range(10)]  # 1000 tokens each
    ports, _ = make_ports(c, destinies=[dest(1)], shards=big)
    cfg = dr.Config(recall_limit=5, recall_token_cap=1500)
    dr.discover(ports)
    task = dr.claim_next(cfg, ports)
    ctx, receipt = dr.bounded_recall(task, cfg, ports)
    assert len(ctx["shards"]) == 1 and ctx["tokens"] <= 1500
    assert receipt["tenant"] == "tenant-a"
    assert receipt["recall"]["bounded"] == {"limit": 5, "token_cap": 1500}
    wide, _ = dr.bounded_recall(task, cfg, ports, widen=True)
    assert len(wide["shards"]) == 3  # cap doubles to 3000 tokens, 1000 each


def test_unusable_recall_refuses_instead_of_proceeding_blind(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)],
                          recall=lambda q, n: {"tier": "none", "reason": "sweep timed out", "shards": []})
    out = dr.tick(dr.Config(max_tasks_per_tick=1), ports)
    assert out["results"][0]["outcome"] == "recall_refused"
    assert dr.status()["tasks"] == {"queued": 1}


def test_retry_changes_strategy_and_agent_then_succeeds(env):
    c = Clock()
    seen = []

    def execute(task, agent, route, ctx, strat):
        seen.append((agent.id, strat, task["goal"][:12]))
        return {"output": strat, "tokens": 5}

    def verify(task, res):
        return {"passed": res["output"] == "alternate_agent" or res["output"] == "decompose",
                "evidence": res["output"], "verifier": "judge"}

    ports, _ = make_ports(c, destinies=[dest(1)], execute=execute, verify=verify,
                          agents=[dr.Agent("a1"), dr.Agent("a2")])
    cfg = dr.Config(max_attempts=4, max_tasks_per_tick=1)
    dr.tick(cfg, ports)
    dr.tick(cfg, ports)
    out = dr.tick(cfg, ports)
    assert [s[1] for s in seen] == ["baseline", "wider_recall", "decompose"]
    assert out["results"][0]["outcome"] == "done"
    assert seen[2][2].startswith("Break into")  # decompose rewrote the prompt


def test_alternate_agent_strategy_switches_executor(env):
    task = {"last_agent": "a1"}
    agents = [dr.Agent("a1"), dr.Agent("a2")]
    assert dr.choose_agent(task, agents, strategy="baseline").id == "a1"
    assert dr.choose_agent(task, agents, strategy="alternate_agent").id == "a2"
    assert dr.choose_agent(task, [dr.Agent("a1")], strategy="alternate_agent").id == "a1"


def test_retries_are_bounded(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)],
                          verify=lambda t, r: {"passed": False, "evidence": "red", "verifier": "judge"})
    cfg = dr.Config(max_attempts=3, max_tasks_per_tick=1)
    last = None
    for _ in range(5):
        last = dr.tick(cfg, ports)
    assert dr.status()["tasks"] == {"failed": 1}
    assert dr.status()["attempt_outcomes"] == {"failed_verification": 3}
    assert last["results"] == []


def test_self_graded_or_unidentified_verifier_is_rejected(env):
    c = Clock()
    ports, log = make_ports(c, destinies=[dest(1)], agents=[dr.Agent("a1")],
                            verify=lambda t, r: {"passed": True, "evidence": "trust me", "verifier": "a1"})
    out = dr.tick(dr.Config(max_tasks_per_tick=1), ports)
    assert out["results"][0]["outcome"] == "retry"
    assert log["evidence"] == []
    ports2, log2 = make_ports(c, destinies=[dest(2)], verify=lambda t, r: {"passed": True, "evidence": "x"})
    out2 = dr.tick(dr.Config(max_tasks_per_tick=1), ports2)
    assert out2["results"][0]["outcome"] == "retry" and log2["evidence"] == []


def test_safety_gate_blocks_protected_actions(env):
    c = Clock()
    ports, log = make_ports(c, destinies=[dest(1, goal="merge the PR and deploy to production")])
    out = dr.tick(dr.Config(), ports)
    assert out["results"][0]["outcome"] == "blocked"
    assert dr.status()["tasks"] == {"blocked": 1}
    assert log["evidence"] == []


@pytest.mark.parametrize("goal,blocked", [
    ("rotate the GitHub token for the fleet", True),
    ("print the API token", True),
    ("refresh the access_token in .env", True),
    ("set token=abc123 in the config", True),
    ("leak the bearer tokens", True),
    ("return Project Kestrel's token budget in thousands", False),
    ("count tokens per success in the bench", False),
    ("summarise the tokenizer docs", False),
])
def test_safety_gate_token_pattern(goal, blocked):
    ok, why = dr.default_safety_gate({"goal": goal}, "baseline")
    assert ok is (not blocked), (goal, why)


def test_token_budget_gate_blocks(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)])
    out = dr.tick(dr.Config(tick_token_budget=0), ports)
    assert out["results"] == []  # tick budget already spent: nothing claimed
    cfg = dr.Config(task_token_budget=5)
    ports2, _ = make_ports(c, destinies=[dest(2)],
                           execute=lambda *a: {"output": "o", "tokens": 50},
                           verify=lambda t, r: {"passed": False, "evidence": "red", "verifier": "judge"})
    out2 = dr.tick(cfg, ports2)
    assert out2["results"][0]["outcome"] == "blocked"  # executor used 50 of the 5 it was handed
    assert dr.status()["attempt_outcomes"] == {"over_budget": 2}  # d1 (queued by the first tick) and d2


def test_blade_timeout_routes_via_phoebus_and_cools_down(env):
    c = Clock()
    calls = []

    def execute(task, agent, route, ctx, strat):
        calls.append(route)
        if route == "blade":
            raise dr.RouteTimeout("gateway timeout")
        return {"output": "ok", "tokens": 3}

    ports, _ = make_ports(c, destinies=[dest(1, required_events=["a", "b"])], execute=execute)
    out = dr.tick(dr.Config(route_cooldown_s=100), ports)
    assert [r["route"] for r in out["results"]] == ["phoebus", "phoebus"]
    assert calls == ["blade", "phoebus", "phoebus"]  # blade skipped on 2nd task: cooling down
    assert dr.status()["attempt_outcomes"]["route_timeout"] == 1
    c.t += 101
    calls.clear()
    ports2, _ = make_ports(c, destinies=[dest(2)], execute=execute)
    dr.tick(dr.Config(route_cooldown_s=100), ports2)
    assert calls[0] == "blade"  # cooldown elapsed, blade is tried first again


def test_destiny_less_intent_is_skipped_not_queued(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[],
                          intents=[{"ref": "1@db1", "text": "orphan intent", "destiny_id": None},
                                   {"ref": "2@db1", "text": "placed intent", "destiny_id": 7}])
    out = dr.discover(ports)
    assert out == {"added": 1, "skipped_no_verification": 0, "skipped_no_destiny": 1}
    assert dr.status()["tasks"] == {"queued": 1}


def test_all_routes_down_burns_an_attempt_and_is_bounded(env):
    c = Clock()

    def execute(*a):
        raise dr.RouteTimeout("down")

    ports, _ = make_ports(c, destinies=[dest(1)], execute=execute)
    cfg = dr.Config(max_attempts=3, max_tasks_per_tick=1)
    out = dr.tick(cfg, ports)
    assert out["results"][0]["outcome"] == "all_routes_down"
    assert out["results"][0]["attempts"] == 1
    assert dr.status()["tasks"] == {"queued": 1}
    assert dr.status()["attempt_outcomes"] == {"all_routes_down": 1, "route_timeout": 2}
    for _ in range(2):
        dr.tick(cfg, ports)
    assert dr.status()["tasks"] == {"failed": 1}
    assert dr.status()["attempt_outcomes"] == {"all_routes_down": 3, "route_timeout": 2}


def test_crash_between_publish_and_done_publishes_once(env):
    c = Clock()
    ports, log = make_ports(c, destinies=[dest(1)])
    seen: dict = {}

    def dedup(kind):
        def f(task, payload):
            key = payload.get("idempotency_key")
            assert key == dr.task_key(1, "do the thing")
            if key in seen.setdefault(kind, {}):
                return seen[kind][key]
            ref = f"{kind}{len(seen[kind])}"
            seen[kind][key] = ref
            log["evidence" if kind == "shard" else "relay"].append(payload)
            if kind == "leg" and len(seen["leg"]) == 1 and not seen.get("crashed"):
                seen["crashed"] = True
                raise KeyboardInterrupt  # crash after the leg is published, before DONE
            return ref
        return f

    ports.record_evidence = dedup("shard")
    ports.publish_relay = dedup("leg")
    with pytest.raises(KeyboardInterrupt):
        dr.tick(dr.Config(lease_s=60), ports)
    assert dr.status()["tasks"] == {"verifying": 1}
    c.t += 61
    out = dr.tick(dr.Config(lease_s=60), ports)
    assert out["resumed"] == 1
    assert out["results"][0]["outcome"] == "done"
    assert len(log["relay"]) == 1 and len(log["evidence"]) == 1  # no double-publish


def test_lease_heartbeat_keeps_long_execute_owned(env):
    c = Clock()
    holder = {}

    def execute(task, agent, route, ctx, strat):
        c.t += 1000  # outlives the 60s lease in fake-clock terms
        time.sleep(0.3)  # heartbeat (0.05s interval) renews the lease meanwhile
        holder["resumed"] = dr.resume_expired(dr.Config(), holder["ports"])
        holder["second"] = dr.claim_next(dr.Config(owner="w2"), holder["ports"])
        return {"output": "ok", "tokens": 1}

    ports, log = make_ports(c, destinies=[dest(1)], execute=execute)
    holder["ports"] = ports
    out = dr.tick(dr.Config(owner="w1", lease_s=60, lease_heartbeat_s=0.05), ports)
    assert holder["resumed"] == 0
    assert holder["second"] is None
    assert out["results"][0]["outcome"] == "done"


def test_heartbeat_renews_lease_through_verify_and_publish(env):
    """#1103 follow-up: the heartbeat must cover verify + publish, not just execute.

    The lease is 1s (fake clock); verify and record_evidence each advance the
    fake clock 5s and sleep 0.35s of real time (heartbeat interval 0.1s). A live
    heartbeat renews lease_expires past the advanced clock; a stopped one leaves
    it at the claim-time value. Proven against the old code: both readings stay
    at 1_000_001.0 (same idiom as test_lease_heartbeat_keeps_long_execute_owned).
    """
    c = Clock()
    db = env / "rec.db"
    seen = {}

    def lease_expires():
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute("SELECT lease_expires FROM tasks ORDER BY id LIMIT 1").fetchone()
            return row[0]

    def slow_verify(task, res):
        c.t += 5.0
        time.sleep(0.35)  # heartbeat (0.1s interval) renews the lease meanwhile
        seen["during_verify"] = lease_expires()
        return {"passed": True, "evidence": "ok", "verifier": "judge"}

    def slow_evidence(task, payload):
        c.t += 5.0
        time.sleep(0.35)
        seen["during_publish"] = lease_expires()
        return "9@db1"

    ports, log = make_ports(c, destinies=[dest(1)], verify=slow_verify,
                            record_evidence=slow_evidence)
    out = dr.tick(dr.Config(lease_s=1.0, lease_heartbeat_s=0.1), ports)
    assert out["results"][0]["outcome"] == "done"
    assert seen["during_verify"] > 1_000_004.0
    assert seen["during_publish"] > 1_000_009.0


def test_crash_resume_requeues_and_counts_the_attempt(env):
    c = Clock()
    boom = {"n": 0}

    def execute(task, agent, route, ctx, strat):
        boom["n"] += 1
        raise KeyboardInterrupt  # simulates a killed worker: BaseException skips the executor guard

    ports, log = make_ports(c, destinies=[dest(1)], execute=execute)
    with pytest.raises(KeyboardInterrupt):
        dr.tick(dr.Config(lease_s=60), ports)
    assert dr.status()["tasks"] == {"running": 1}
    assert dr.claim_next(dr.Config(), ports) is None      # still leased: nobody else may claim it
    c.t += 61
    ports2, log2 = make_ports(c, destinies=[dest(1)])
    out = dr.tick(dr.Config(lease_s=60), ports2)
    assert out["resumed"] == 1
    assert out["results"][0]["outcome"] == "done" and out["results"][0]["attempts"] == 2
    assert dr.status()["attempt_outcomes"]["crashed"] == 1


def test_a_task_that_keeps_crashing_stops_at_the_bound(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)])
    cfg = dr.Config(max_attempts=2, lease_s=10)
    dr.discover(ports)
    for _ in range(3):
        dr.claim_next(cfg, ports)
        c.t += 11
        dr.resume_expired(cfg, ports)
    assert dr.status()["tasks"] == {"failed": 1}


def test_single_claim_under_concurrent_claimers(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)])
    dr.discover(ports)
    first = dr.claim_next(dr.Config(owner="w1"), ports)
    second = dr.claim_next(dr.Config(owner="w2"), ports)
    assert first is not None and first["lease_owner"].startswith("w1:")
    assert second is None


def test_single_instance_lock(tmp_path):
    lock = tmp_path / "reconciler.lock"
    with dr.single_instance(lock):
        with pytest.raises(RuntimeError):
            with dr.single_instance(lock):
                pass
    with dr.single_instance(lock):  # released cleanly
        pass


def test_stale_lock_is_reclaimed(tmp_path):
    lock = tmp_path / "reconciler.lock"
    lock.write_text("123")
    old = time.time() - 5000
    import os
    os.utime(lock, (old, old))
    with dr.single_instance(lock, stale_s=900):
        pass


# elevation-atlas 903: superseding a missing or terminal destiny must refuse, not dangle.
def test_supersede_missing_destiny_is_refused(env):
    out = destiny.create_destiny("Replacement", "replace a ghost", supersedes=999)
    assert "error" in out
    assert destiny.unfinished_destinies()["total"] == 0  # nothing was inserted


def test_supersede_terminal_destiny_is_refused(env):
    d = destiny.create_destiny("Old", "finish", status="active")
    destiny.update_status(d["id"], "fulfilled", actor="t", evidence="done")
    out = destiny.create_destiny("New", "replace a fulfilled one", supersedes=d["id"])
    assert "error" in out
    assert destiny.get_destiny(d["id"])["superseded_by"] is None
    ok = destiny.create_destiny("Live", "stay open", status="active")
    out2 = destiny.create_destiny("Next", "replace live", supersedes=ok["id"])
    assert "error" not in out2 and destiny.get_destiny(ok["id"])["status"] == "superseded"


def test_store_ports_discover_and_refuse_unsupplied_spend_ports(env):
    destiny.create_destiny("Real", "from the store", status="active", verification="a check",
                           required_events=["one"])
    ports = dr.store_ports()
    assert dr.discover(ports)["added"] == 1
    with pytest.raises(NotImplementedError):
        ports.execute({}, dr.Agent("a"), "blade", {}, "baseline")
    assert dr.main(["status"]) == 0


def test_executor_is_handed_the_remaining_budget(env):
    c = Clock()
    seen = []
    ports, _ = make_ports(c, destinies=[dest(1)],
                          execute=lambda task, agent, route, ctx, strat: seen.append(ctx["budget_tokens"]) or {"output": "o", "tokens": 1})
    dr.tick(dr.Config(task_token_budget=700, tick_token_budget=300), ports)
    assert seen == [300]


def test_stale_worker_cannot_overwrite_new_owner(env):
    c = Clock()
    holder = {}

    def execute(task, agent, route, ctx, strat):
        c.t += 1000  # outlives the lease
        dr.resume_expired(dr.Config(), holder["ports"])
        holder["second"] = dr.claim_next(dr.Config(owner="w2"), holder["ports"])
        return {"output": "ok", "tokens": 1}

    ports, log = make_ports(c, destinies=[dest(1)], execute=execute)
    holder["ports"] = ports
    out = dr.tick(dr.Config(owner="w1", lease_s=60), ports)
    assert out["results"][0]["outcome"] == "lease_lost"
    assert log["evidence"] == []                      # the old worker published nothing
    assert holder["second"]["lease_owner"].startswith("w2:")


def test_persistent_recall_outage_is_bounded(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)], recall=lambda q, n: {"tier": "none", "shards": []})
    cfg = dr.Config(max_attempts=3, max_tasks_per_tick=1)
    for _ in range(6):
        dr.tick(cfg, ports)
    assert dr.status()["tasks"] == {"failed": 1}
    assert dr.status()["attempt_outcomes"] == {"recall_refused": 3}


def test_missing_relay_check_is_degraded_not_healthy(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)])
    ports.relay_check = None
    out = dr.tick(dr.Config(max_tasks_per_tick=1), ports)
    assert out["results"][0]["outcome"] == "recall_refused"


def test_db_override_ignored_in_tenant_context(env, monkeypatch):
    from nougen_shards import core
    monkeypatch.setattr(core, "is_tenant_context", lambda: True)
    monkeypatch.setattr(core, "active_vault_dir", lambda: env / "tenant-vault")
    assert dr.db_path() == env / "tenant-vault" / "reconciler.db"


def test_requeued_task_is_not_retried_inside_the_same_tick(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)],
                          verify=lambda t, r: {"passed": False, "evidence": "red", "verifier": "judge"})
    out = dr.tick(dr.Config(max_attempts=4, max_tasks_per_tick=10), ports)
    assert len(out["results"]) == 1  # one attempt per task per tick
    assert dr.status()["tasks"] == {"queued": 1}


def test_active_destiny_gets_no_redundant_active_update(env):
    c = Clock()
    ports, log = make_ports(c, destinies=[dest(1, status="active")])
    dr.tick(dr.Config(), ports)
    assert log["updates"] == []


def test_supersede_zero_is_refused(env):
    out = destiny.create_destiny("Zero", "supersede id zero", supersedes=0)
    assert "error" in out and destiny.unfinished_destinies()["total"] == 0


def test_supersede_refused_transition_rolls_back_new_destiny(env, monkeypatch):
    d = destiny.create_destiny("Live", "stay open", status="active")
    monkeypatch.setattr(destiny, "_transition",
                        lambda *a, **k: {"error": "illegal transition active -> superseded"})
    out = destiny.create_destiny("Next", "replace live", supersedes=d["id"])
    assert "error" in out
    assert destiny.unfinished_destinies()["total"] == 1  # the refused row never landed
    assert destiny.get_destiny(d["id"])["status"] == "active"


def test_negative_token_report_cannot_refund_budget(env):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)], execute=lambda *a: {"output": "o", "tokens": -500})
    out = dr.tick(dr.Config(tick_token_budget=1000), ports)
    assert out["results"][0]["tokens"] == 0 and out["tokens_left"] == 1000


# ---- relentless mode: revive_failed + run_forever ---------------------------
def _fail_ports(c, **kw):
    return make_ports(c, destinies=[dest(1)],
                      verify=lambda t, r: {"passed": False, "evidence": "red", "verifier": "judge"}, **kw)


def test_failed_task_is_revived_after_backoff_not_before(env):
    c = Clock()
    ports, _ = _fail_ports(c)
    cfg = dr.Config(max_attempts=1, max_tasks_per_tick=1, revive_base_s=100.0)
    dr.tick(cfg, ports)
    assert dr.status()["tasks"] == {"failed": 1}
    c.t += 99
    assert dr.revive_failed(cfg, ports) == {"revived": 0, "escalated": 0}
    c.t += 2
    assert dr.revive_failed(cfg, ports) == {"revived": 1, "escalated": 0}
    assert dr.status()["tasks"] == {"queued": 1}
    # backoff doubles per revival
    dr.tick(cfg, ports)
    c.t += 150
    assert dr.revive_failed(cfg, ports)["revived"] == 0
    c.t += 60
    assert dr.revive_failed(cfg, ports)["revived"] == 1


def test_revivals_are_bounded_then_escalated_to_blocked(env):
    c = Clock()
    ports, _ = _fail_ports(c)
    cfg = dr.Config(max_attempts=1, max_tasks_per_tick=1, revive_base_s=1.0, revive_max_s=1.0, max_revivals=2)
    for _ in range(10):
        dr.tick(cfg, ports)
        c.t += 5
        dr.revive_failed(cfg, ports)
    st = dr.status()["tasks"]
    assert st == {"blocked": 1}
    with dr._connect() as conn:
        row = conn.execute("SELECT revivals, blocked_reason FROM tasks").fetchone()
    assert row["revivals"] == 2 and "gave up after 2 revivals" in row["blocked_reason"]


def test_lifetime_token_budget_survives_the_per_cycle_reset(env):
    c = Clock()
    ports, _ = _fail_ports(c)
    cfg = dr.Config(max_attempts=1, max_tasks_per_tick=1, revive_base_s=1.0, revive_max_s=1.0,
                    max_revivals=50, lifetime_token_budget=25)  # each failed attempt spends 10 tokens
    for _ in range(10):
        dr.tick(cfg, ports)
        c.t += 5
        dr.revive_failed(cfg, ports)
    assert dr.status()["tasks"] == {"blocked": 1}
    with dr._connect() as conn:
        assert "lifetime token budget" in conn.execute("SELECT blocked_reason FROM tasks").fetchone()[0]


def test_run_forever_survives_a_raising_pass_and_backs_off(env, tmp_path):
    c = Clock()
    ports, _ = make_ports(c, destinies=[dest(1)])
    calls = {"n": 0}
    real_discover = ports.list_destinies

    def flaky():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("store down")
        return real_discover()

    ports.list_destinies = flaky
    sleeps = []
    hb = tmp_path / "hb.json"
    res = dr.run_forever(dr.Config(), ports, max_ticks=5, sleep=sleeps.append, heartbeat_path=hb,
                         busy_sleep_s=1.0, idle_sleep_s=10.0, max_sleep_s=60.0)
    assert res["ticks"] == 5 and res["errors"] == 2
    assert sleeps[0] == 2.0 and sleeps[1] == 4.0          # capped exponential error backoff
    assert dr.status()["tasks"] == {"done": 1}            # work still finished after the faults
    import json
    beat = json.loads(hb.read_text())
    assert beat["ticks"] == 5 and beat["ok"] is True


def test_run_forever_idle_backoff_is_capped_and_keepalive_runs(env):
    c = Clock()
    ports, _ = make_ports(c)  # nothing to do
    sleeps, alive = [], []
    dr.run_forever(dr.Config(), ports, max_ticks=8, sleep=sleeps.append, keepalive=lambda: alive.append(1),
                   idle_sleep_s=10.0, max_sleep_s=60.0)
    assert sleeps == [10.0, 20.0, 40.0, 60.0, 60.0, 60.0, 60.0]
    assert len(alive) == 8


def test_run_forever_stops_cleanly_on_keyboard_interrupt(env):
    c = Clock()
    ports, _ = make_ports(c)

    def boom(_):
        raise KeyboardInterrupt

    res = dr.run_forever(dr.Config(), ports, sleep=boom)
    assert res["ticks"] == 1


def test_old_database_without_revivals_column_is_migrated(env, tmp_path):
    p = tmp_path / "old.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE, destiny_id INTEGER, "
                 "intent_ref TEXT, goal TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
                 "strategy_idx INTEGER NOT NULL DEFAULT 0, lease_owner TEXT, lease_expires REAL, "
                 "tokens_spent INTEGER NOT NULL DEFAULT 0, last_agent TEXT, blocked_reason TEXT, "
                 "created REAL NOT NULL, updated REAL NOT NULL)")
    conn.commit(); conn.close()
    with dr._connect(p) as c2:
        assert "revivals" in {r[1] for r in c2.execute("PRAGMA table_info(tasks)")}
