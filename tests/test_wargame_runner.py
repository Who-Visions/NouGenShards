"""War Games first implementation slice (docs/wargames-doctrine.md §83).

Definition of Done: scenario file → deterministic runner → controlled inject
→ invariant evaluated → JSON receipt → Markdown AAR → elevation candidate
→ replay command. Each arrow has a test below.
"""
import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.wargames import (  # noqa: E402
    list_scenarios, load_scenario, run_game, replay_receipt, write_receipt,
    render_aar, validate_scenario, POLICIES,
)
from nougen_shards.wargames.adjudication import CONDITIONS, INVARIANTS  # noqa: E402
from nougen_shards.wargames.model import ScenarioError  # noqa: E402
from nougen_shards.wargames.runner import ACTIONS, INJECTS  # noqa: E402

SCENARIOS = ["false-green-scheduler", "memory-blackout", "port-4444-split-brain"]


# --------------------------------------------------------------------------
# scenario file
# --------------------------------------------------------------------------

def test_three_opening_games_ship():
    names = sorted(Path(g.source).stem for g in list_scenarios())
    assert names == sorted(SCENARIOS)


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_references_only_registered_machinery(name):
    g = load_scenario(name)
    assert g.blue.policy in POLICIES
    assert g.blue.naive_policy in POLICIES
    for inj in g.injects:
        assert inj.type in INJECTS, inj.type
    for inv in g.invariants:
        assert inv in INVARIANTS, inv
    for cond in g.victory + g.catastrophic_failure:
        assert cond in CONDITIONS, cond


def test_validate_reports_missing_keys_and_bad_turns():
    errs = validate_scenario({"id": "WG-2026-9999"})
    assert any("missing required key: mission" in e for e in errs)
    raw = load_scenario("memory-blackout").to_dict()
    raw["injects"][0]["at_turn"] = 99
    errs = validate_scenario(raw)
    assert any("at_turn" in e for e in errs)
    raw["invariants"] = []
    assert any("hitbox" in e for e in validate_scenario(raw))


def test_load_scenario_rejects_unknown_and_invalid(tmp_path):
    with pytest.raises(ScenarioError):
        load_scenario("no-such-game")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ScenarioError):
        load_scenario(bad)
    missing = tmp_path / "missing.json"
    missing.write_text(json.dumps({"id": "WG-2026-0009", "title": "x"}), encoding="utf-8")
    with pytest.raises(ScenarioError, match="missing required key"):
        load_scenario(missing)


# --------------------------------------------------------------------------
# deterministic runner + controlled inject + invariant evaluated
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", SCENARIOS)
def test_hardened_policy_survives(name):
    g = load_scenario(name)
    r = run_game(g, seed=1)
    assert r.status == "PASS", r.breaches
    assert r.breaches == []
    assert all(r.victory.values()), r.victory
    assert not any(r.catastrophic.values()), r.catastrophic
    assert r.elevation["status"] == "verified"
    assert r.score["final"] >= 90


@pytest.mark.parametrize("name", SCENARIOS)
def test_naive_policy_breaches_the_hitbox(name):
    g = load_scenario(name)
    r = run_game(g, policy_name="naive", seed=1)
    assert r.status == "FAIL"
    assert r.blue_policy == g.blue.naive_policy
    breached = {b["invariant"] for b in r.breaches}
    assert breached == set(g.invariants)
    assert any(r.catastrophic.values())
    assert r.elevation["status"] == "candidate"
    # doctrine §25: a false PASS on critical truth caps the score
    assert r.score["final"] <= 49
    assert any(c["reason"].startswith("false PASS") for c in r.score["caps"])


def test_false_green_turn_by_turn():
    r = run_game(load_scenario("false-green-scheduler"), seed=0)
    statuses = [t["claim"]["status"] for t in r.turns]
    assert statuses == ["GREEN", "GREEN", "RED", "GREEN", "GREEN"]
    t3 = r.turns[2]
    assert t3["injects"][0]["type"] == "scheduler_expiry"
    assert t3["counteraction"]["action"] == "recreate_schedule"
    assert t3["state_after"]["task"]["next_run_time"] is not None
    # the naive policy keeps saying GREEN with no future run: the boss lands
    n = run_game(load_scenario("false-green-scheduler"), policy_name="naive", seed=0)
    assert [t["claim"]["status"] for t in n.turns] == ["GREEN"] * 5
    assert n.turns[2]["state_after"]["task"]["next_run_time"] is None
    assert n.breaches[0]["turn"] == 3


def test_memory_blackout_never_claims_absence_and_retries_within_budget():
    r = run_game(load_scenario("memory-blackout"), seed=0)
    after = [t for t in r.turns if t["turn"] >= 2]
    assert all(t["claim"]["status"] == "UNKNOWN" for t in after)
    assert all(t["claim"]["evidence"]["fleet_complete"] is False for t in after)
    assert "blade" in after[0]["claim"]["evidence"]["lanes_silent"]
    retries = [t for t in r.turns if t["counteraction"]]
    assert len(retries) == 1  # retry_budget = 1: bounded, not a loop
    assert r.final_state["retries"] == 1


def test_split_brain_halts_rollout_on_identity_mismatch():
    r = run_game(load_scenario("port-4444-split-brain"), seed=0)
    t4 = r.turns[3]
    assert t4["injects"][0]["type"] == "patch_deployed"
    assert t4["claim"]["status"] == "MISMATCH"
    assert t4["claim"]["evidence"]["owner_tree"] == "tree_b"
    assert t4["claim"]["evidence"]["expected_sha"] == "ccc333"
    assert t4["counteraction"]["action"] == "halt_rollout"
    assert r.final_state["rollout"] == "halted"
    n = run_game(load_scenario("port-4444-split-brain"), policy_name="naive", seed=0)
    assert n.turns[3]["claim"]["status"] == "DEPLOYED"
    assert n.catastrophic["patch_declared_live_on_wrong_tree"] is True


def test_runner_is_deterministic_for_a_seed():
    g = load_scenario("memory-blackout")
    a = run_game(g, seed=1337)
    b = run_game(g, seed=1337)
    strip = lambda r: [(t["claim"], t["packets"], t["counteraction"], t["state_after"]) for t in r.turns]  # noqa: E731
    assert strip(a) == strip(b)
    assert a.score == b.score


def test_seeded_greyout_is_reproducible_and_seed_sensitive(tmp_path):
    raw = load_scenario("memory-blackout").to_dict()
    raw["id"] = "WG-2026-0099"
    raw["injects"] = [{"type": "lane_greyout", "at_turn": t, "params": {"lane": "blade", "p_up": 0.5}}
                      for t in range(1, 5)]
    path = tmp_path / "greyout.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    g = load_scenario(path)
    pattern = lambda seed: [t["state_after"]["lanes"]["blade"]["answered"] for t in run_game(g, seed=seed).turns]  # noqa: E731
    assert pattern(3) == pattern(3)
    assert any(pattern(s) != pattern(3) for s in range(4, 20))
    assert run_game(g, seed=3).breaches == []  # coverage-aware policy survives greyout


def test_unknown_policy_and_inject_fail_loudly(tmp_path):
    g = load_scenario("false-green-scheduler")
    with pytest.raises(KeyError, match="unknown blue policy"):
        run_game(g, policy_name="does-not-exist")
    raw = g.to_dict()
    raw["injects"][0]["type"] = "meteor"
    path = tmp_path / "meteor.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(KeyError, match="unknown inject"):
        run_game(load_scenario(path))


def test_unregistered_invariant_yields_unknown_not_pass(tmp_path):
    raw = load_scenario("false-green-scheduler").to_dict()
    raw["invariants"].append("gravity_still_works")
    raw["victory"].append("sun_rises")
    path = tmp_path / "unk.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    r = run_game(load_scenario(path))
    verdicts = {p["invariant"]: p["verdict"] for p in r.turns[0]["packets"]}
    assert verdicts["gravity_still_works"] == "UNKNOWN"  # §21 rule 7
    assert r.victory["sun_rises"] is None
    assert r.status == "FAIL"  # an unproven victory condition is not a win


def test_registries_expose_the_named_counteractions():
    assert {"recreate_schedule", "bounded_retry", "halt_rollout"} <= set(ACTIONS)


# --------------------------------------------------------------------------
# JSON receipt → Markdown AAR → elevation candidate → replay
# --------------------------------------------------------------------------

def test_receipt_aar_ledger_and_replay(tmp_path):
    g = load_scenario("port-4444-split-brain")
    r = run_game(g, seed=5)
    paths = write_receipt(r, tmp_path)
    receipt = json.loads(Path(paths["receipt"]).read_text(encoding="utf-8"))
    for key in ("id", "scenario", "seed", "blue_policy", "initial_state", "assumptions",
                "injects", "turns", "breaches", "victory", "catastrophic", "final_state",
                "status", "score", "elevation"):
        assert key in receipt, key
    assert receipt["seed"] == 5 and receipt["scenario"] == "port-4444-split-brain"

    aar = Path(paths["aar"]).read_text(encoding="utf-8")
    assert aar.startswith("# AAR: Port 4444 Split Brain")
    for heading in ("What did we expect?", "What actually happened?", "Which assumption failed?",
                    "Score", "Elevation", "Replay"):
        assert f"## {heading}" in aar
    assert "nougen wargame run port-4444-split-brain --policy runtime_identity --seed 5" in aar
    assert render_aar(r) == aar

    ledger_lines = Path(paths["ledger"]).read_text(encoding="utf-8").splitlines()
    assert len(ledger_lines) == 1
    row = json.loads(ledger_lines[0])
    assert row["status"] == "PASS" and row["elevations"] == ["ELEV-WG-2026-0003"]
    write_receipt(run_game(g, policy_name="naive", seed=5), tmp_path)
    assert len(Path(paths["ledger"]).read_text(encoding="utf-8").splitlines()) == 2

    elev = receipt["elevation"]
    assert elev["status"] == "verified"
    assert elev["invariant"] == "port_open_is_not_runtime_identity"
    assert elev["change"] == {"component": "runtime_ownership_proof", "type": "identity_check",
                              "from": "port_open_means_deployed", "to": "runtime_identity"}
    assert elev["root_cause"]["assumption"] == "port_open_means_correct_runtime"

    result = replay_receipt(paths["receipt"])
    assert result["replay"] == "PASS"
    assert result["diverged_turns"] == []


def test_replay_detects_divergence(tmp_path):
    r = run_game(load_scenario("false-green-scheduler"), seed=2)
    paths = write_receipt(r, tmp_path)
    doc = json.loads(Path(paths["receipt"]).read_text(encoding="utf-8"))
    doc["turns"][2]["claim"]["status"] = "GREEN"   # pretend history said something else
    Path(paths["receipt"]).write_text(json.dumps(doc), encoding="utf-8")
    result = replay_receipt(paths["receipt"])
    assert result["replay"] == "DIVERGED"
    assert result["diverged_turns"] == [3]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_wargame_run_and_replay(tmp_path, capsys):
    from nougen_shards.cli import cmd_wargame, get_parser
    parser = get_parser()
    args = parser.parse_args(["wargame", "run", "memory-blackout", "--seed", "9",
                              "--out", str(tmp_path), "--json"])
    cmd_wargame(args)
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "PASS" and out["seed"] == 9
    receipt = out["paths"]["receipt"]
    assert Path(receipt).exists()

    cmd_wargame(parser.parse_args(["wargame", "replay", receipt, "--json"]))
    assert json.loads(capsys.readouterr().out)["replay"] == "PASS"

    cmd_wargame(parser.parse_args(["wargame", "list", "--json"]))
    listed = json.loads(capsys.readouterr().out)
    assert sorted(x["scenario"] for x in listed) == sorted(SCENARIOS)

    cmd_wargame(parser.parse_args(["wargame", "run", "false-green-scheduler", "--policy", "naive",
                                   "--no-write"]))
    text = capsys.readouterr().out
    assert "FAIL" in text and "repeating_task_must_have_future_run" in text
    assert not list((tmp_path / "receipts").glob("*0001*"))

    cmd_wargame(argparse.Namespace(wargame_action=None, json=False))
    assert "false-green-scheduler" in capsys.readouterr().out
