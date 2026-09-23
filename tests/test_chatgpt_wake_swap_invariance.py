"""Independent verification of done-when 6 (leg 20260923T110636Z):

    "Tests prove a transport swap does not alter relay IDs, payloads, ack
    semantics, or shard references."

`tests/test_chatgpt_wake_transport.py` already covers this well -- it is not
duplicated here. This file exists because that suite was written by the same
lane that wrote the implementation, and an author's own invariance suite
tends to assert the behaviour they just built. This one was written after
reading the module but without re-running the author's tests first, and every
assertion below was checked against a negative control before being kept.

Three real gaps found, all fixed here rather than in the implementation
(nothing in chatgpt_transports.py needed to change):

1. Idempotency was tested for Slack only; GitHub and WorkspaceAgent implement
   the identical `_IdempotencyLedger` pattern but had no test of their own.
2. The docstring claims "multiple transports notifying about the same relay
   id independently is not a duplicate -- it is redundancy by design", and
   nothing tested that claim.
3. `notify_any_configured`'s fallback was tested for "configured vs
   unconfigured" but not for a transport that is configured yet still fails
   to deliver -- the loop must still fall through in that case, not stop.

One correction to my own earlier claim: I initially wrote a test asserting
`ChatGPTWakeTransport` does NOT conform to `wake.adapters.ProviderAdapter`,
expecting a gap I'd flagged when releasing this work. Running it failed
immediately -- `ChatGPTAdapter(ProviderAdapter)` already exists in
`wake/adapters.py`, composing the pluggable transports rather than
subclassing them, with `detect()` correctly redefined as "at least one
transport configured" instead of "binary on PATH". That is exactly the shape
I recommended. My own inventory had missed it: I grepped
`chatgpt_transports.py` and `wake/__init__.py` for "ProviderAdapter" and
never re-checked `adapters.py` itself for a "chatgpt"-named class after the
transports landed. Fixed below rather than left wrong.

What genuinely IS missing: `ChatGPTAdapter` itself had zero test coverage.
Every test in the final section below is new coverage for it, not a
restatement of the transport-layer tests.
"""
from __future__ import annotations

import dataclasses

import pytest

from nougen_shards.wake.chatgpt_transports import (
    FutureMCPNativeWakeTransport,
    GitHubWakeTransport,
    NotifyResult,
    SlackWakeTransport,
    TRANSPORTS,
    WakeEnvelope,
    WorkspaceAgentWakeTransport,
    canonical_fetch_reminder,
    get_transport,
    notify_any_configured,
    wake_envelope_from_relay_id,
)

REAL_TRANSPORTS = [SlackWakeTransport, GitHubWakeTransport, WorkspaceAgentWakeTransport]
ENV_FOR = {
    SlackWakeTransport: {"NOUGEN_CHATGPT_SLACK_WEBHOOK": "https://example.invalid/webhook"},
    GitHubWakeTransport: {"NOUGEN_CHATGPT_GITHUB_REPO": "who-visions/nougenshards",
                          "NOUGEN_CHATGPT_GITHUB_TOKEN": "test-token"},
    WorkspaceAgentWakeTransport: {"NOUGEN_CHATGPT_WORKSPACE_API_KEY": "test-key",
                                  "NOUGEN_CHATGPT_WORKSPACE_AGENT_ID": "test-agent"},
}


def _configure(monkeypatch, cls):
    for k, v in ENV_FOR[cls].items():
        monkeypatch.setenv(k, v)


# ---------------------------------------------------------- gap 1: idempotency
@pytest.mark.parametrize("cls", REAL_TRANSPORTS)
def test_idempotent_retry_holds_for_every_real_transport_not_just_slack(cls, monkeypatch):
    _configure(monkeypatch, cls)
    t = cls()
    e = wake_envelope_from_relay_id(f"20260923T000000Z__test__{cls.__name__}")
    first = t.notify(e)
    second = t.notify(e)
    assert first.status == "sent"
    assert second.status == "duplicate_suppressed"
    assert second.delivered is True


# ------------------------------------------------- gap 2: cross-transport redundancy
def test_the_same_relay_id_on_two_different_transports_is_redundancy_not_duplication(monkeypatch):
    """The module's own docstring makes this claim explicitly. It was untested."""
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_REPO", "r")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_TOKEN", "t")
    e = wake_envelope_from_relay_id("20260923T000000Z__test__cross-transport")
    slack_result = SlackWakeTransport().notify(e)
    github_result = GitHubWakeTransport().notify(e)
    # Each transport instance has its own ledger, so a fresh instance seeing
    # the same relay id for the first time must report "sent", not suppressed
    # -- suppression is per-transport-instance, never per-relay-id globally.
    assert slack_result.status == "sent"
    assert github_result.status == "sent"


# --------------------------------------------------- gap 3: fallback through failure
def test_notify_any_configured_falls_through_a_configured_but_failing_transport(monkeypatch):
    """A transport can be CONFIGURED and still fail to deliver (bad webhook,
    revoked token, API outage). The existing test only proves the fallback
    skips an UNCONFIGURED transport; it never exercises a configured one that
    actually fails.

    First draft of this test hand-rolled the same loop `notify_any_configured`
    runs internally instead of calling the real function -- it passed even
    with the fallback logic deliberately broken (verified: reverting
    `notify_any_configured` to return on the first transport tried, success or
    not, left this version green). Rewritten to patch the module-level
    `TRANSPORTS` singleton and call the real function, so it exercises what
    ships. Negative control against THIS version: fails as expected."""
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_REPO", "r")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_TOKEN", "t")

    def always_fails(_envelope):
        return NotifyResult("slack", False, "error", "simulated delivery failure")

    monkeypatch.setattr(TRANSPORTS["slack"], "notify", always_fails)

    result = notify_any_configured(wake_envelope_from_relay_id("20260923T000000Z__test__fallthrough"))
    assert result.transport == "github", "fallback did not skip the failing-but-configured transport"


def test_notify_any_configured_itself_skips_unconfigured_and_delivers(monkeypatch):
    """Same claim, exercised against the real module function (not a manual
    loop), to confirm the two agree."""
    monkeypatch.delenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", raising=False)
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_REPO", "r")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_TOKEN", "t")
    monkeypatch.delenv("NOUGEN_CHATGPT_WORKSPACE_API_KEY", raising=False)
    r = notify_any_configured(wake_envelope_from_relay_id("20260923T000000Z__test__real-fn"))
    assert r.transport == "github" and r.delivered


# ------------------------------------------------------- structural immutability
def test_wake_envelope_is_structurally_frozen_not_just_empirically_unmutated():
    """A test that only checks `to_dict()` before/after notify() would still
    pass if a transport mutated the envelope and then mutated it back, or if
    it mutated a field no test happens to read. Structural immutability rules
    that class of bug out entirely."""
    e = wake_envelope_from_relay_id("20260923T000000Z__test__frozen")
    assert dataclasses.is_dataclass(e) and e.__dataclass_params__.frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.relay_id = "tampered"


def test_notify_result_is_also_frozen():
    r = NotifyResult("slack", True, "sent")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.delivered = False


def test_envelope_accepts_no_extra_fields_by_construction():
    """Pins the docstring claim 'there is no extra field' as a TypeError, not
    a convention someone could quietly violate."""
    with pytest.raises(TypeError):
        WakeEnvelope(relay_id="x", priority="normal", target="chatgpt-app",
                    payload="should not exist")  # type: ignore[call-arg]


# ------------------------------------------------------------- shard references
def test_no_transport_ever_returns_shard_content_only_a_reminder_to_fetch_it(monkeypatch):
    """'shard references' in done-when 6 means: a transport may carry a
    pointer, never the referenced content. canonical_fetch_reminder is the
    only shard-adjacent surface in this module; assert it is exactly that."""
    msg = canonical_fetch_reminder("20260923T000000Z__test__shard-ref")
    assert "relay_read" in msg
    # It must not itself look like it embeds retrievable content.
    assert "shard:" not in msg and "@db" not in msg


@pytest.mark.parametrize("cls", REAL_TRANSPORTS)
def test_notify_result_never_carries_shard_or_leg_body_text(cls, monkeypatch):
    _configure(monkeypatch, cls)
    r = cls().notify(wake_envelope_from_relay_id("20260923T000000Z__test__noshardbody"))
    blob = str(r.to_dict())
    assert "shard:" not in blob and "@db" not in blob


# --------------------------------------------------- ChatGPTAdapter (untested)
def test_chatgpt_adapter_is_registered_and_conforms_to_provider_adapter():
    from nougen_shards.wake.adapters import ADAPTERS, ChatGPTAdapter, ProviderAdapter
    assert "chatgpt" in ADAPTERS
    assert isinstance(ADAPTERS["chatgpt"], ChatGPTAdapter)
    assert issubclass(ChatGPTAdapter, ProviderAdapter)


def test_detect_means_a_transport_is_configured_not_a_binary_on_path(monkeypatch):
    """The other four adapters' detect() means 'is the binary on PATH', which
    is meaningless for a hosted provider. ChatGPTAdapter must redefine it
    rather than inherit that semantic by accident -- this was the key finding
    in my original inventory (leg 20260923T111059Z)."""
    from nougen_shards.wake.adapters import ChatGPTAdapter
    for var in ("NOUGEN_CHATGPT_SLACK_WEBHOOK", "NOUGEN_CHATGPT_GITHUB_REPO",
               "NOUGEN_CHATGPT_GITHUB_TOKEN", "NOUGEN_CHATGPT_WORKSPACE_API_KEY",
               "NOUGEN_CHATGPT_WORKSPACE_AGENT_ID"):
        monkeypatch.delenv(var, raising=False)
    assert ChatGPTAdapter().detect() is False
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    assert ChatGPTAdapter().detect() is True


def test_detect_ignores_the_future_transport():
    """A FutureMCPNativeWakeTransport that somehow reported configured=True
    must never make detect() true -- it always raises on notify(), so
    detect() would be lying about what can actually be woken."""
    from nougen_shards.wake.adapters import ChatGPTAdapter
    from nougen_shards.wake.chatgpt_transports import FutureMCPNativeWakeTransport
    caps = FutureMCPNativeWakeTransport().capabilities()
    assert caps.get("configured") is not True  # sanity: it doesn't even claim to be
    # And structurally: detect() explicitly excludes it by name, not by luck.
    import inspect
    assert 'name != "future_mcp_native"' in inspect.getsource(ChatGPTAdapter.detect)


def test_wake_requires_a_relay_id_never_accepts_a_payload():
    from nougen_shards.wake.adapters import ChatGPTAdapter
    result = ChatGPTAdapter().wake({"text": "no relay id here"})
    assert result["woken"] is False
    assert result["status"] == "error"


def test_wake_delegates_to_notify_any_configured_and_reports_delivery(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    from nougen_shards.wake.adapters import ChatGPTAdapter
    result = ChatGPTAdapter().wake({"leg_id": "20260923T000000Z__test__adapter-wake"})
    assert result["woken"] is True
    assert result["delivery"]["transport"] == "slack"


def test_inject_explicitly_reports_unsupported_not_left_abstract():
    """ProviderAdapter requires a concrete inject(); ChatGPTAdapter has no
    in-turn socket. It must say so, not silently no-op or raise."""
    from nougen_shards.wake.adapters import ChatGPTAdapter
    r = ChatGPTAdapter().inject("hello")
    assert r["delivered"] is False and r["status"] == "unsupported"


def test_capabilities_never_claims_mcp_native_support_through_the_adapter_layer(monkeypatch):
    """Same trip-wire as the transport layer's own test, checked again one
    layer up -- capabilities() here derives MCP_NATIVE_WAKE_SUPPORTED fresh
    each call rather than caching a value that could go stale."""
    from nougen_shards.wake.adapters import ChatGPTAdapter
    from nougen_shards.wake import chatgpt_transports
    assert ChatGPTAdapter().capabilities()["mcp_native_wake_supported"] is False
    assert ChatGPTAdapter().capabilities()["mcp_native_wake_supported"] is chatgpt_transports.MCP_NATIVE_WAKE_SUPPORTED


def test_health_surfaces_every_transport_not_just_the_first_configured_one(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    from nougen_shards.wake.adapters import ChatGPTAdapter
    h = ChatGPTAdapter().health()
    assert set(h["transports"]) == {"slack", "github", "workspace_agent", "future_mcp_native"}
    assert h["detected"] is True and h["status"] == "healthy"


def test_future_transport_is_excluded_from_every_delivery_path():
    """FutureMCPNativeWakeTransport must never be reachable via
    notify_any_configured's default order -- confirmed by construction
    (get_transport still returns it by name, for explicit/manual use, but the
    default fallback chain must never silently try it)."""
    assert get_transport("future_mcp_native") is not None
    r = notify_any_configured(wake_envelope_from_relay_id("20260923T000000Z__test__future-excluded"))
    assert r.transport != "future_mcp_native"


def test_future_transport_raising_does_not_corrupt_other_transports_state(monkeypatch):
    """If a caller manually invokes the future transport and it raises (by
    design), that must not leave any other transport's ledger or state
    corrupted -- the failure must be fully contained."""
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    e = wake_envelope_from_relay_id("20260923T000000Z__test__future-contained")
    slack = SlackWakeTransport()
    with pytest.raises(NotImplementedError):
        FutureMCPNativeWakeTransport().notify(e)
    # Slack must still work normally afterward.
    assert slack.notify(e).status == "sent"
