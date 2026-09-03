"""Owner-origin signature contract: the one thing every node MUST agree on.

Durable form of the tools/sig_eval.py battery. sig_eval needs a real vault
token and is an operator check; this needs nothing but pytest, so it runs in
CI and fails loudly if the canonical signing bytes ever drift. Two verifiers
that disagree make a signed message pass on one node and fail on another.

Runs against an isolated nonce store and a fixed test token — it never
touches production state or a real secret.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
TEST_TOKEN = "test-token-not-a-real-secret"
# Shared worked example, byte-checked on every node: goal "restart relay",
# nonce "n1", ts "1788433000", body "do the thing".
WORKED_EXAMPLE = b"13:restart relay|2:n1|10:1788433000|12:do the thing"
WORKED_EXAMPLE_SHA16 = "cb955f7584fe7ca3"


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """Import the gate module fresh with test env, since it reads env at import."""
    monkeypatch.setenv("NOUGEN_USER_ORIGIN_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("NOUGEN_USED_NONCES_FILE", str(tmp_path / "nonces.json"))
    monkeypatch.setenv("KAEDRA_GATEWAY_TOKEN", "")  # content gate not under test here
    sys.path.insert(0, str(TOOLS))
    sys.modules.pop("_agy_live_delivery", None)
    mod = importlib.import_module("_agy_live_delivery")
    yield mod
    sys.modules.pop("_agy_live_delivery", None)
    sys.path.remove(str(TOOLS))


def _sign(mod, goal, nonce, ts, body):
    return hmac.new(TEST_TOKEN.encode(), mod.canonical_signing_input(goal, nonce, ts, body), hashlib.sha256).hexdigest()


def _now() -> str:
    return str(int(time.time()))


def test_canonical_bytes_match_fleet_worked_example(gate):
    got = gate.canonical_signing_input("restart relay", "n1", "1788433000", "do the thing")
    assert got == WORKED_EXAMPLE
    assert hashlib.sha256(got).hexdigest()[:16] == WORKED_EXAMPLE_SHA16


def test_limits_are_the_agreed_contract(gate):
    assert gate.SIGNATURE_MAX_AGE_S == 900
    assert gate.SIGNATURE_FUTURE_SKEW_S == 120


def test_fresh_correct_signature_verifies(gate):
    g, b, n, t = "goal", "body", "n-1", _now()
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, t, b), timestamp=t) == "user_verified"


def test_replayed_nonce_is_rejected(gate):
    g, b, n, t = "goal", "body", "n-1", _now()
    sig = _sign(gate, g, n, t, b)
    assert gate.verify_user_origin_signature(g, b, n, sig, timestamp=t) == "user_verified"
    assert gate.verify_user_origin_signature(g, b, n, sig, timestamp=t) == "user_claimed_unverified"


def test_stale_timestamp_rejected_and_does_not_burn_nonce(gate):
    """The property that makes nonce eviction safe rather than nearly safe:
    a stale leg must not consume its nonce, or an attacker pre-poisons the
    store against a nonce the owner is about to use — replay defence turned
    into denial of service."""
    g, b, n = "goal", "body", "n-2"
    stale = str(int(time.time()) - 1000)
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, stale, b), timestamp=stale) == "user_claimed_unverified"
    fresh = _now()
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, fresh, b), timestamp=fresh) == "user_verified"


def test_future_dated_timestamp_rejected(gate):
    g, b, n = "goal", "body", "n-3"
    future = str(int(time.time()) + 600)
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, future, b), timestamp=future) == "user_claimed_unverified"


def test_timestamp_edited_under_kept_signature_rejected_and_does_not_burn_nonce(gate):
    """The timestamp is a signed field: refreshing the line breaks the HMAC,
    so check order (age vs signature) is not exploitable either way."""
    g, b, n = "goal", "body", "n-4"
    stale, fresh = str(int(time.time()) - 1000), _now()
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, stale, b), timestamp=fresh) == "user_claimed_unverified"
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, fresh, b), timestamp=fresh) == "user_verified"


def test_body_swap_under_kept_signature_rejected(gate):
    """A signature over the goal alone authenticates a headline while the
    instruction underneath is attacker-replaceable. Body must be signed."""
    g, b, n, t = "goal", "real body", "n-5", _now()
    assert gate.verify_user_origin_signature(g, "attacker body", n, _sign(gate, g, n, t, b), timestamp=t) == "user_claimed_unverified"


def test_goal_swap_under_kept_signature_rejected(gate):
    g, b, n, t = "goal", "body", "n-6", _now()
    assert gate.verify_user_origin_signature("evil goal", b, n, _sign(gate, g, n, t, b), timestamp=t) == "user_claimed_unverified"


def test_delimiter_confusion_rejected(gate):
    """goal 'a|b' + nonce 'c' must not hash like goal 'a' + nonce 'b|c'.
    Length prefixes are what make this hold."""
    b, t = "body", _now()
    assert gate.verify_user_origin_signature("a|b", b, "c", _sign(gate, "a", "b|c", t, b), timestamp=t) == "user_claimed_unverified"


def test_missing_timestamp_rejected(gate):
    g, b, n = "goal", "body", "n-7"
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, _now(), b)) == "user_claimed_unverified"


def test_non_integer_timestamp_rejected(gate):
    g, b, n = "goal", "body", "n-8"
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, "soon", b), timestamp="soon") == "user_claimed_unverified"


def test_garbage_signature_rejected_and_does_not_burn_nonce(gate):
    g, b, n, t = "goal", "body", "n-9", _now()
    assert gate.verify_user_origin_signature(g, b, n, "0" * 64, timestamp=t) == "user_claimed_unverified"
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, t, b), timestamp=t) == "user_verified"


def test_no_token_configured_never_verifies(gate, monkeypatch):
    """A node with no owner token falls through to the judged peer path —
    it must never auto-verify. Fail closed."""
    monkeypatch.setattr(gate, "USER_ORIGIN_TOKEN", "")
    g, b, n, t = "goal", "body", "n-10", _now()
    assert gate.verify_user_origin_signature(g, b, n, _sign(gate, g, n, t, b), timestamp=t) == "user_claimed_unverified"


def test_nonce_store_survives_reimport(gate, tmp_path, monkeypatch):
    """Replay protection must be durable across a daemon restart, not in
    memory only — these daemons restart on failure by design."""
    g, b, n, t = "goal", "body", "n-11", _now()
    sig = _sign(gate, g, n, t, b)
    assert gate.verify_user_origin_signature(g, b, n, sig, timestamp=t) == "user_verified"
    sys.modules.pop("_agy_live_delivery", None)
    reloaded = importlib.import_module("_agy_live_delivery")
    assert reloaded.verify_user_origin_signature(g, b, n, sig, timestamp=t) == "user_claimed_unverified"


# --- normalisation cases the worked example structurally cannot catch ------
# The shared example's body has no origin lines, so it passes whether origin
# lines are dropped as whole lines or substituted as text. These three are
# where the two approaches diverge, found by running both implementations
# side by side on the same inputs.

def test_origin_line_in_the_middle_leaves_no_blank_line(gate):
    assert gate.normalise_body("line A\norigin_nonce: n1\nline B") == "line A\nline B"


def test_interleaved_origin_lines_leave_no_blank_lines(gate):
    body = "A\norigin_nonce: n1\nB\norigin_ts: 1788433000\nC\norigin_sig: " + "a" * 64
    assert gate.normalise_body(body) == "A\nB\nC"


def test_prefix_inside_prose_is_not_an_origin_line(gate):
    """A leg that merely DISCUSSES the scheme must normalise unchanged."""
    prose = "the origin_nonce: field is described here, and origin_sig: too"
    assert gate.normalise_body(prose) == prose
    assert gate.parse_origin_lines(prose) == (None, None, None)


def test_prose_mention_before_real_line_is_not_extracted(gate):
    body = "note: origin_nonce: fake in prose\norigin_nonce: real-1\norigin_ts: 1788433000\norigin_sig: " + "b" * 64
    nonce, ts, sig = gate.parse_origin_lines(body)
    assert (nonce, ts, sig) == ("real-1", "1788433000", "b" * 64)
    assert gate.normalise_body(body) == "note: origin_nonce: fake in prose"


def test_signature_over_body_with_mid_origin_lines_verifies(gate):
    """End to end: a signer that signs the body minus the origin lines must
    verify when the receiver sees those lines mid-body, not only at the end."""
    g, n, t = "goal", "n-12", _now()
    signed_body = "A\nB\nC"
    sent_body = "A\norigin_nonce: {}\nB\norigin_ts: {}\nC".format(n, t)
    sig = _sign(gate, g, n, t, signed_body)
    assert gate.verify_user_origin_signature(g, sent_body, n, sig, timestamp=t) == "user_verified"


def test_module_imports_without_fcntl(gate, monkeypatch):
    """The canonical module must be importable on Windows: no POSIX-only
    import at module scope. Simulate fcntl being absent and re-import."""
    monkeypatch.setitem(sys.modules, "fcntl", None)  # makes `import fcntl` raise ImportError
    sys.modules.pop("_agy_live_delivery", None)
    mod = importlib.import_module("_agy_live_delivery")
    assert mod.canonical_signing_input("restart relay", "n1", "1788433000", "do the thing") == WORKED_EXAMPLE


# --- duplicate origin lines are malformed, never resolved --------------------
# First-match vs last-match resolution would let an attacker who can append
# one line make two nodes extract different nonces for the same leg and burn
# different replay slots. Both nodes reject outright instead.

@pytest.mark.parametrize("dup", [
    "origin_nonce: a\norigin_nonce: b",
    "origin_ts: 1788433000\norigin_ts: 1788433001",
    "origin_sig: " + "a" * 64 + "\norigin_sig: " + "b" * 64,
])
def test_duplicate_origin_line_is_malformed(gate, dup):
    with pytest.raises(gate.MalformedOriginLines):
        gate.parse_origin_lines("body\n" + dup)


def test_markdown_quoted_origin_line_is_neither_counted_nor_dropped(gate):
    """The safe way to quote a signed leg inside another leg: a '> ' prefix.
    Not an origin line on either node, so it does not trip the duplicate
    check and it survives normalisation byte-for-byte."""
    body = "quoting the earlier leg:\n> origin_nonce: earlier\n> origin_sig: " + "c" * 64 + "\norigin_nonce: mine"
    assert gate.parse_origin_lines(body) == ("mine", None, None)
    assert gate.normalise_body(body) == "quoting the earlier leg:\n> origin_nonce: earlier\n> origin_sig: " + "c" * 64
