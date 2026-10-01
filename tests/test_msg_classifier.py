"""Actionable vs informational, from real fleet messages.

The lifecycle treats every acked message as an obligation unless the sender marked
it informational (origin.kind). Real senders do not: Codex ack chains, touchdown
reports, round-robin batons and dispatches all arrive with no kind. Without a
classifier an informational message becomes a permanent pending item, and the
pending list floods until nobody reads it. The rule that keeps this safe is the
same asymmetry as autoclose: a wrongly held message is noise, a wrongly dropped
one hides work. So ambiguity is ACTIONABLE; only clear informational markers
(and no ask) close at ACKED.
"""
import pytest

from nougen_shards.msg_classifier import classify

ACTIONABLE = [
    ("[RELAY DISPATCH 20261001T081134Z__whoart__claude-cli] needs a mac | Baton is yours: execute, verify, then close with `relay checkpoint`", "dispatch"),
    ("ROUND ROBIN baton -> antigravity. Your turn: report (a) what landed, (b) blockers, (c) corrections.", "your turn"),
    ("Please review NouGenShards PR #620 and post findings as a PR comment. Do NOT merge.", "please"),
    ("Dave's order: fix the arXiv radar false-positive tag. Ask: tighten _MEMORY_CTX.", "order + ask"),
    ("FLEET WORK ORDER: Claim leg 20261001T011200Z (validate and merge the 23 PRs).", "claim"),
    ("Can you re-send the body of leg 053746Z? I cannot read it.", "can you"),
    ("TODO: design/implement durable claim lifecycle", "todo"),
    ("Build the watchdog and add tests.", "imperative"),
    ("ok", "short unknown: fail toward action"),
    ("Something happened and here is some text with no clear marker either way", "unknown: fail toward action"),
]

INFORMATIONAL = [
    ("Informational update: no acknowledgement reply or new task is requested, to avoid the auto-ack chain.", "explicit"),
    ("TOUCHDOWN 1:42 AM EDT: nougen-desktop probes deployed, 56 tests pass, pushed 68dd0f1.", "touchdown"),
    ("Antigravity online and listening on WhoArt. Connected to relay bus.", "online"),
    ("[auto] NouGen@main: session ended with 1 uncommitted file(s)", "auto"),
    ("[LIFECYCLE & CANON SEALED] arXiv tools deployed, durable claim lifecycle active, chronology locked.", "sealed"),
    ("PR #632 (fix/memory-hub-search) is pushed and open: https://github.com/x/y/pull/632", "status fact"),
    ("FYI the radar tagger was tightened; counts are 3 beacon / 13 review.", "fyi"),
    ("[ARXIV BEACON RADAR] 1 Breakthrough Papers for Wed, 30 Sep 2026: 1. [2609.38081] Hessian Null Space Continuation", "beacon radar"),
]


@pytest.mark.parametrize("text,why", ACTIONABLE)
def test_actionable_messages_stay_actionable(text, why):
    c = classify(text)
    assert c.actionable is True, (why, c)
    assert c.reason


@pytest.mark.parametrize("text,why", INFORMATIONAL)
def test_clearly_informational_messages_end_at_ack(text, why):
    c = classify(text)
    assert c.actionable is False, (why, c)
    assert c.reason


def test_an_ask_inside_a_touchdown_wins():
    c = classify("TOUCHDOWN: PR merged. Please verify the deploy and report back.")
    assert c.actionable is True


def test_a_baton_inside_an_informational_wrapper_wins():
    c = classify("FYI the radar is fixed. Baton is yours: re-run the preview from chatgpt-app.")
    assert c.actionable is True


def test_explicit_origin_kind_overrides_the_text():
    assert classify("Please fix this", {"kind": "status"}).actionable is False
    assert classify("TOUCHDOWN done", {"kind": "task"}).actionable is True
    assert classify("TOUCHDOWN done", {"kind": "dispatch"}).actionable is True
    assert "origin.kind" in classify("x", {"kind": "info"}).reason


def test_empty_and_odd_inputs_never_hide_work():
    for text in ("", None, "   ", 12345):
        assert classify(text).actionable is True
    assert classify("hello", {"kind": None}).actionable is True
    assert classify("hello", "not-a-dict").actionable is True


def test_classification_is_deterministic_and_reports_a_reason():
    a = classify("Please review the PR")
    b = classify("Please review the PR")
    assert a == b and a.reason


def test_a_watchdog_nudge_is_a_pointer_not_a_new_obligation():
    """The nudge says 'run take-msg <id>'. Acking it must not create its own obligation, or an
    un-taken nudge would be nudged again, and that one nudged again, without end. The obligation
    is the ORIGINAL message the nudge points at."""
    from nougen_shards.lifecycle_watchdog import wake_text
    nudge = wake_text({"message_id": "abc", "age_s": 660})
    c = classify(nudge)
    assert c.actionable is False and "marker" in c.reason


def test_a_real_ask_quoted_inside_a_nudge_wrapper_still_wins():
    c = classify("[LIFECYCLE WATCHDOG] message abc is stale. Please review PR 12 before you take it.")
    assert c.actionable is True
