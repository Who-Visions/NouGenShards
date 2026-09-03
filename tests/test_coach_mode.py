"""Coach mode in the provider scheduler (Rule 0.0 as routing policy): delegable
roles never reach a judgment lane without an escalate reason, privileged roles
never leave one, judgment roles prefer one but keep free lanes eligible; every
decision lands in the JSONL log with provider, reason, fallback reason and the
estimated cloud tokens avoided. Hermetic: tmp log, tmp GLOBAL_DIR, no network."""
import json

import pytest

import nougen_shards.core as core
from nougen_shards import provider_scheduler as ps

FREE_LANES = {"ollama-local", "ollama-cloud", "openrouter-free", "hf-router"}


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    for k in ("NOUGEN_PROVIDER_REGISTRY", "NOUGEN_HF_CREDIT_BUDGET_USD", "NOUGEN_HF_CREDITS_SPENT_USD",
              "NOUGEN_SCHEDULER_PROVENANCE", "NOUGEN_COACH_MODE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NOUGEN_ROUTING_LOG", str(tmp_path / "routing.jsonl"))
    yield


def cand(d, lane):
    return next(c for c in d["candidates"] if c["lane"] == lane)


def test_registry_carries_coach_block_and_codes():
    reg = ps.load_registry()
    cm = reg["coach_mode"]
    assert cm["enabled"] and cm["judgment_lanes"] == ["premium-first-party"]
    assert set(cm["tiers"]) == {"delegable", "judgment", "privileged"}
    for code in ("COACH_DELEGATE", "COACH_ESCALATE", "COACH_JUDGMENT", "COACH_PRIVILEGED", "ESCALATE_REQUIRED"):
        assert code in reg["reason_codes"]
    assert ps.coach_tier("bulk_draft", reg) == "delegable" and ps.coach_tier("code_review", reg) == "judgment"
    assert ps.coach_tier("privileged", reg) == "privileged" and ps.coach_tier("recon", reg) == "delegable"


def test_delegable_task_never_reaches_premium():
    d = ps.route("draft 40 captions for the reel", harness="claude-cli")
    assert d["tier"] == "delegable" and d["lane"] in FREE_LANES and d["coach_mode"] is True
    prem = cand(d, "premium-first-party")
    assert prem["eligible"] is False and prem["reasons"] == ["COACH_DELEGATE"]
    assert d["fallback_reason"] is None and d["escalate_required"] is False


def test_delegable_with_free_lanes_down_requires_escalate_then_escalates():
    down = sorted(FREE_LANES)
    d = ps.route("summarize the relay daemon findings", unavailable=down)
    assert d["lane"] is None and d["escalate_required"] is True and "ESCALATE_REQUIRED" in d["reason_codes"]
    d2 = ps.route("summarize the relay daemon findings", unavailable=down, escalate="free lanes quota exhausted 01:20Z")
    assert d2["lane"] == "premium-first-party" and "COACH_ESCALATE" in d2["reason_codes"]
    assert d2["fallback_reason"] == "free lanes quota exhausted 01:20Z" and d2["escalate_required"] is False


def test_privileged_task_only_reaches_judgment_lane_even_when_pinned_local():
    d = ps.route("grant access: change the production deploy permission for the gateway", pinned_lane="ollama-local")
    assert d["role"] == "privileged" and d["tier"] == "privileged" and d["lane"] == "premium-first-party"
    assert cand(d, "ollama-local")["reasons"] == ["COACH_PRIVILEGED"]
    assert "DEGRADE_SWAP" in d["reason_codes"], "the pin was refused, and the envelope says so"


def test_judgment_role_prefers_premium_but_free_lanes_stay_eligible():
    d = ps.route("code review of the relay_live diff", harness="claude-cli")
    assert d["tier"] == "judgment" and d["lane"] == "premium-first-party" and "COACH_JUDGMENT" in d["reason_codes"]
    assert any(c["eligible"] for c in d["candidates"] if c["lane"] in FREE_LANES), "second opinions stay possible"


def test_recon_role_is_classified_and_delegable():
    d = ps.route("dig through the relay daemon log and distill the last 3 sync passes")
    assert d["role"] == "recon" and d["tier"] == "delegable" and d["lane"] in FREE_LANES


def test_coach_mode_off_by_env_or_argument_leaves_classic_scoring(monkeypatch):
    d = ps.route("draft 40 captions for the reel", coach_mode=False)
    assert d["coach_mode"] is False and d["tier"] is None
    assert not any(code.startswith("COACH") for c in d["candidates"] for code in c["reasons"])
    monkeypatch.setenv("NOUGEN_COACH_MODE", "0")
    assert ps.route("draft 40 captions for the reel")["coach_mode"] is False
    monkeypatch.setenv("NOUGEN_COACH_MODE", "1")
    assert ps.route("draft 40 captions for the reel")["coach_mode"] is True


def test_registry_without_coach_block_is_off():
    reg = ps.load_registry()
    reg.pop("coach_mode")
    d = ps.route("draft 40 captions for the reel", registry=reg)
    assert d["coach_mode"] is False and d["tier"] is None


def test_decision_log_records_provider_reason_fallback_and_tokens_avoided(tmp_path):
    log = tmp_path / "routing.jsonl"
    task = "summarize the relay daemon findings " * 20
    free = ps.route(task)
    prem = ps.route("code review of the relay_live diff")
    assert free["logged"] and prem["logged"]
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and "task" not in rows[0] and len(rows[0]["task_sha12"]) == 12
    assert rows[0]["lane"] in FREE_LANES and rows[0]["cloud_tokens_avoided_est"] == rows[0]["est_input_tokens"] + rows[0]["est_output_tokens"] > 0
    assert rows[1]["lane"] == "premium-first-party" and rows[1]["cloud_tokens_avoided_est"] == 0
    assert set(rows[0]) >= {"decided_utc", "role", "tier", "lane", "model", "reason_codes", "fallback_reason", "escalate_required"}
    rep = ps.coach_report(log)
    assert rep["decisions"] == 2 and rep["by_tier"] == {"delegable": 1, "judgment": 1}
    assert rep["cloud_tokens_avoided_est"] == rows[0]["cloud_tokens_avoided_est"] and rep["escalations"] == 0


def test_routing_log_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_ROUTING_LOG", "0")
    d = ps.route("draft 40 captions for the reel")
    assert d["logged"] is False and not (tmp_path / "routing.jsonl").exists()


def test_cli_route_prints_slim_envelope_and_report(capsys, tmp_path):
    assert ps.main(["--route", "draft 40 captions for the reel"]) == 0
    slim = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert slim["tier"] == "delegable" and slim["lane"] in FREE_LANES and slim["logged"] is True
    assert ps.main(["--report"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["decisions"] == 1 and rep["cloud_tokens_avoided_est"] > 0


def test_ollama_candidates_normalise_bind_address_and_add_missing_port(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0")
    monkeypatch.delenv("NOUGEN_OLLAMA_PORTS", raising=False)
    monkeypatch.delenv("NOUGEN_OLLAMA_PORT", raising=False)
    c = ps.ollama_candidates()
    assert c[0] == "http://127.0.0.1:11434" and "http://127.0.0.1:11436" in c and len(c) == len(set(c))
    monkeypatch.setenv("OLLAMA_HOST", "http://10.0.0.5:11500")
    monkeypatch.setenv("NOUGEN_OLLAMA_PORTS", "11436")
    assert ps.ollama_candidates() == ["http://10.0.0.5:11500", "http://127.0.0.1:11436"]
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:1")
    monkeypatch.setenv("NOUGEN_OLLAMA_PORTS", "2")
    assert ps.ollama_base_url(probe_timeout_s=0.2) == "http://127.0.0.1:1", "no endpoint answers: first candidate, logged fallback"


def test_run_on_lane_refuses_non_ollama_lane_honestly():
    res = ps.run_on_lane({"lane": "premium-first-party", "model": "claude-fable-5-1"}, "hi")
    assert res["ok"] is False and "not wired" in res["error"]
