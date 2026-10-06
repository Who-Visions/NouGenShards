import pytest

from nougen_shards.evidence_label import LABEL, has_evidence, label_claim
from nougen_shards.nougenmsg import AgentPinger


@pytest.mark.parametrize("text", [
    "ROUND ROBIN 5 PASSES COMPLETED & VERIFIED: all lanes reconciled.",
    "All 19 equations operationalized into NouGen runtime.",
    "Snapshotting landed, TOCTOU fixed.",
])
def test_unreferenced_claims_are_labeled(text):
    assert label_claim(text).startswith(LABEL)


@pytest.mark.parametrize("text", [
    "Merged PR #705 into main.",
    "Fix landed in Who-Visions/NouGenShards#711.",
    "Passed: https://github.com/Who-Visions/NouGenShards/pull/716",
    "Fixed at commit 8549b95.",
    "Entry is present at mcp_config.json:92, resolved.",
    "Completed leg 20261004T181440Z__claude-app__g-whoentertains.",
    "Done, see shard 30744.",
])
def test_referenced_claims_pass_through(text):
    assert label_claim(text) == text


@pytest.mark.parametrize("text", [
    "LANE_CAPACITY lane=claude-app node=blade state=idle",
    "Your turn: read the leg and add one step.",
    "",
])
def test_non_claims_untouched(text):
    assert label_claim(text) == text


def test_label_is_idempotent():
    once = label_claim("Everything merged.")
    assert label_claim(once) == once


def test_sha_and_issue_patterns():
    assert has_evidence("see 2c3a8f807d7bba53fc72a7706bddde61ea2200c4")
    assert has_evidence("PR 709 is open")
    assert not has_evidence("version 3 shipped")


def test_claude_wire_applies_label():
    wire = AgentPinger.cc_wire_lines("tok", "NouGenMsg from x: Pass 3 landed.").decode()
    assert LABEL in wire
    wire = AgentPinger.cc_wire_lines("tok", "NouGenMsg from x: Pass 3 landed in #711.").decode()
    assert LABEL not in wire


# --- referenced-but-false merge claims ------------------------------------------------------
from nougen_shards.evidence_label import MISMATCH, check_merge_claims, pr_refs  # noqa: E402

STATES = {("Who-Visions/NouGenShards", 711): "OPEN", ("Who-Visions/NouGenShards", 705): "MERGED"}


def _lookup(repo, n):
    return STATES.get((repo, n))


def test_merge_claim_on_open_pr_is_flagged():
    out = check_merge_claims("Snapshot fix landed in Who-Visions/NouGenShards#711.", _lookup)
    assert MISMATCH in out and "Who-Visions/NouGenShards#711 is OPEN" in out


def test_merge_claim_on_merged_pr_passes():
    t = "Ledger merged: https://github.com/Who-Visions/NouGenShards/pull/705"
    assert check_merge_claims(t, _lookup) == t


def test_bare_ref_uses_default_repo():
    out = check_merge_claims("PR #711 merged.", _lookup, default_repo="Who-Visions/NouGenShards")
    assert MISMATCH in out
    assert check_merge_claims("PR #711 merged.", _lookup) == "PR #711 merged."  # no repo known -> no guess


def test_non_merge_claims_and_unknown_state_untouched():
    assert check_merge_claims("PR #711 is open for review.", _lookup, "Who-Visions/NouGenShards").endswith("review.")
    assert MISMATCH not in check_merge_claims("Merged Who-Visions/Other#1.", _lookup)


def test_pr_refs_dedup_forms():
    refs = list(pr_refs("o/r#5 and https://github.com/o/r/pull/6 and #77", default_repo="o/r"))
    assert refs == [("o/r", 5), ("o/r", 6), ("o/r", 77)]


def test_wire_check_is_opt_in(monkeypatch):
    import nougen_shards.evidence_label as el
    monkeypatch.setattr(el, "gh_pr_state", _lookup)
    monkeypatch.setattr(el.check_merge_claims, "__defaults__", (_lookup, None))
    text = "NouGenMsg from x: fix landed in Who-Visions/NouGenShards#711."
    assert MISMATCH not in AgentPinger.cc_wire_lines("t", text).decode()
    monkeypatch.setenv("NOUGEN_CLAIM_PR_CHECK", "1")
    assert MISMATCH in AgentPinger.cc_wire_lines("t", text).decode()


# --- PASS 3 review fixes (2026-10-04): hex-lookalikes, honest negatives, 'checkpointed' -----------

@pytest.mark.parametrize("text", [
    "Everything is merged and green, ticket 1234567.",       # a bare 7+ digit run is not a commit sha
    "The schema was defaced and fixed.",                     # an all-a-f-letter word is not a commit sha
    "Phoebus PASS 1/5 turn is checkpointed (claude-app, phoebus).",  # new claim word
])
def test_hex_lookalikes_and_checkpointed_are_labeled(text):
    assert label_claim(text).startswith(LABEL)


@pytest.mark.parametrize("text", [
    "Not done: the gate is not wired and nothing has landed.",
    "It has not been merged yet.",
    "Never shipped, still blocked.",
    "The test isn't green.",
])
def test_honest_negatives_are_not_labeled(text):
    assert label_claim(text) == text


def test_real_shas_still_count_as_evidence():
    for text in ("fix landed in 3a7f9c2", "merged as 8bf4842c01d3e5f6a7b8c9d0e1f2a3b4c5d6e7f8"):
        assert label_claim(text) == text


def test_positive_claim_after_a_negation_is_still_caught():
    assert label_claim("Not blocked anymore. Everything is merged.").startswith(LABEL)


@pytest.mark.xfail(strict=True, reason="residual: a hex session id (8c26a120) is indistinguishable from a short commit sha")
def test_session_id_is_not_evidence():
    # This is the exact text of the 2026-10-04 'checkpointed' ping that was false when sent.
    assert label_claim("Phoebus PASS 1/5 turn is checkpointed (claude-app, session 8c26a120, phoebus).").startswith(LABEL)
