"""The evidence chain behind a league award.

Every test here encodes something this fleet measured on 2026-09-07/08 rather
than something the doctrine merely says.
"""

import pytest

from nougen_shards import league


def _full(subject="x") -> league.Chain:
    c = league.Chain(subject)
    for name in league.LINKS:
        c.record(name, league.VERIFIED, "evidence")
    return c


def test_a_complete_chain_is_eligible():
    ok, why = league.award_eligible(_full())
    assert ok and "all links verified" in why


def test_merged_without_production_is_not_eligible():
    """The exact failure that motivated the module.

    A redaction fix merged, three nodes independently verified it, and it ran
    on none of them. Every link through merge_sha was green.
    """
    c = _full()
    c.record("production", league.UNVERIFIABLE, "node publishes no health fields")
    ok, why = league.award_eligible(c)
    assert not ok
    assert "production" in why and "UNVERIFIABLE" in why


def test_unverifiable_is_not_partial_credit():
    """Unmeasured is not a weaker form of verified.

    Treating a green proxy as the thing itself is the whole failure this
    fleet spent a night on.
    """
    c = _full()
    c.record("tests", league.UNVERIFIABLE, "no tests ran")
    assert league.award_eligible(c)[0] is False


def test_missing_evidence_defaults_to_unverifiable_not_pass():
    """Silence must never be success.

    A same-machine lane published '11 PRs merged and RUNNING IN RAM' when one
    request would have returned ABSENT. A default pass rewards that.
    """
    c = league.Chain("nothing recorded")
    assert c.state_of("production") == league.UNVERIFIABLE
    assert league.award_eligible(c)[0] is False


def test_weakest_names_the_first_failing_link_in_order():
    """The useful output is WHICH link failed, not a verdict.

    'Not eligible' tells a lane nothing; 'production is UNVERIFIABLE' tells it
    to deploy.
    """
    c = _full()
    c.record("claim", league.BROKEN, "two lanes did the same work")
    c.record("production", league.UNVERIFIABLE, "")
    assert c.weakest() == "claim"


def test_broken_link_reports_its_evidence():
    c = _full()
    c.record("merge_sha", league.BROKEN, "commit reachable from no ref")
    ok, why = league.award_eligible(c)
    assert not ok and "reachable from no ref" in why


def test_telemetry_cannot_make_a_chain_eligible():
    """Anti-farming law: telemetry is recorded, never scored.

    Measured: 11 PRs that honestly represented 5 chains. A PR-count metric
    would have scored the worst habit of that night as the best.
    """
    c = league.Chain("farmer")
    c.record("production", league.UNVERIFIABLE, "")
    c.telemetry = {"pr_count": 999, "tokens_spent": 10_000_000, "commit_count": 500}
    assert league.award_eligible(c)[0] is False


def test_telemetry_cannot_lower_a_complete_chain():
    """Efficiency is not the same as correctness; a cheap chain is not better."""
    c = _full()
    c.telemetry = {"tokens_spent": 50_000_000}
    assert league.award_eligible(c)[0] is True


def test_the_farmable_metrics_are_named_and_frozen():
    """Naming them stops a later scorer quietly promoting one."""
    for metric in ("pr_count", "commit_count", "lines_changed",
                   "tool_calls", "tokens_spent"):
        assert metric in league.TELEMETRY_ONLY
    assert isinstance(league.TELEMETRY_ONLY, frozenset)


def test_production_is_the_last_link():
    """Order is load-bearing: everything else can be green while it does not run."""
    assert league.LINKS[-1] == "production"
    assert league.LINKS.index("merge_sha") < league.LINKS.index("production")


def test_unknown_links_and_states_are_rejected():
    with pytest.raises(ValueError):
        league.Link("vibes", league.VERIFIED)
    with pytest.raises(ValueError):
        league.Link("production", "PROBABLY")


def test_summary_lists_every_link_even_unrecorded_ones():
    """A chain must not look shorter than it is by omitting what was skipped."""
    c = league.Chain("partial")
    c.record("relay_leg", league.VERIFIED, "leg id")
    rows = c.summary()
    assert len(rows) == len(league.LINKS)
    assert rows[0] == ("relay_leg", league.VERIFIED, "leg id")
    assert all(state == league.UNVERIFIABLE for _, state, _ in rows[1:])
