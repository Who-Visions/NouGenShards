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
