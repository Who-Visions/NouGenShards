"""ChatGPT inbound wake transport abstraction (owner leg 20260923T110636Z).

Every test here is a required invariant from the leg's "Done when" list:
relay ids/payload unchanged across a transport swap, idempotent retries,
NouGen-native ack semantics, a failed transport never corrupting canonical
truth, and no code path claiming custom MCP itself can wake ChatGPT.
"""
import pytest

from nougen_shards.wake.chatgpt_transports import (
    MCP_NATIVE_WAKE_SUPPORTED,
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

RELAY_ID = "20260923T110636Z__chatgpt-app__g-whoentertains"


# --- envelope: canonical payload never crosses the wire -----------------------
def test_envelope_carries_only_relay_id_priority_target_no_payload_fields():
    e = wake_envelope_from_relay_id(RELAY_ID, priority="high")
    d = e.to_dict()
    assert set(d) == {"NOUGEN_RELAY", "id", "priority", "target"}
    assert d["id"] == RELAY_ID


def test_envelope_requires_a_real_relay_id():
    with pytest.raises(ValueError):
        WakeEnvelope(relay_id="")
    with pytest.raises(ValueError):
        WakeEnvelope(relay_id="   ")


# --- relay id and payload identical across a transport swap --------------------
@pytest.mark.parametrize("transport_cls", [SlackWakeTransport, GitHubWakeTransport, WorkspaceAgentWakeTransport])
def test_envelope_is_identical_regardless_of_which_transport_sends_it(transport_cls, monkeypatch):
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_REPO", "who-visions/nougenshards")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("NOUGEN_CHATGPT_WORKSPACE_API_KEY", "test-key")
    monkeypatch.setenv("NOUGEN_CHATGPT_WORKSPACE_AGENT_ID", "test-agent")
    e = wake_envelope_from_relay_id(RELAY_ID)
    before = e.to_dict()
    transport_cls().notify(e)
    assert e.to_dict() == before  # notify() never mutates the envelope


def test_relay_layer_seam_does_not_choose_a_transport_by_name(monkeypatch):
    """notify_any_configured is the actual caller-facing seam: swapping which
    transport is configured changes nothing about how the caller invokes it."""
    e = wake_envelope_from_relay_id(RELAY_ID)
    monkeypatch.delenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", raising=False)
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_REPO", "who-visions/nougenshards")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_TOKEN", "test-token")
    only_github = notify_any_configured(e)
    assert only_github.transport == "github" and only_github.delivered
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    slack_preferred = notify_any_configured(WakeEnvelope(relay_id=RELAY_ID + "-2"))
    assert slack_preferred.transport == "slack" and slack_preferred.delivered


# --- idempotent retries ----------------------------------------------------------
def test_retrying_the_same_relay_id_is_idempotent_not_a_second_event(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    t = SlackWakeTransport()
    e = wake_envelope_from_relay_id(RELAY_ID)
    first = t.notify(e)
    second = t.notify(e)
    assert first.status == "sent"
    assert second.status == "duplicate_suppressed"
    assert second.delivered is True  # the caller sees success either way


# --- ack semantics stay NouGen-native; run ids are metadata, never identity ------
def test_workspace_agent_run_id_is_metadata_never_baton_identity(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHATGPT_WORKSPACE_API_KEY", "test-key")
    monkeypatch.setenv("NOUGEN_CHATGPT_WORKSPACE_AGENT_ID", "test-agent")
    result = WorkspaceAgentWakeTransport().notify(wake_envelope_from_relay_id(RELAY_ID))
    assert result.transport_metadata.get("run_id_is_metadata_not_identity") is True
    assert result.transport_metadata["openai_run_id"] != RELAY_ID  # never substituted for the relay id


def test_ack_is_a_nougen_notify_result_shape_regardless_of_transport(monkeypatch):
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "https://example.invalid/webhook")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_REPO", "r")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_TOKEN", "t")
    for cls in (SlackWakeTransport, GitHubWakeTransport):
        r = cls().notify(wake_envelope_from_relay_id(RELAY_ID))
        assert isinstance(r, NotifyResult)
        assert set(r.to_dict()) >= {"transport", "delivered", "status", "detail", "transport_metadata", "timestamp"}


# --- a failed/unconfigured transport never corrupts canonical truth -------------
def test_unconfigured_transport_reports_failure_and_never_raises():
    for cls in (SlackWakeTransport, GitHubWakeTransport, WorkspaceAgentWakeTransport):
        r = cls().notify(wake_envelope_from_relay_id(RELAY_ID))
        assert r.delivered is False and r.status == "unconfigured"


def test_no_configured_transport_reports_failure_not_a_silent_success(monkeypatch):
    for var in ("NOUGEN_CHATGPT_SLACK_WEBHOOK", "NOUGEN_CHATGPT_GITHUB_REPO", "NOUGEN_CHATGPT_GITHUB_TOKEN",
               "NOUGEN_CHATGPT_WORKSPACE_API_KEY", "NOUGEN_CHATGPT_WORKSPACE_AGENT_ID"):
        monkeypatch.delenv(var, raising=False)
    # a relay id not used by any other test: the module-level TRANSPORTS
    # singletons carry a real idempotency ledger by design, so a shared id
    # would leak "already sent" state across tests, not a code defect.
    r = notify_any_configured(wake_envelope_from_relay_id(RELAY_ID + "-unconfigured-check"))
    assert r.delivered is False and r.status == "unconfigured"


def test_canonical_fetch_reminder_names_relay_read_not_a_local_cache():
    msg = canonical_fetch_reminder(RELAY_ID)
    assert "relay_read" in msg and RELAY_ID in msg


# --- the capability boundary itself: never claim MCP native wake exists ---------
@pytest.fixture(autouse=True)
def _no_real_mcp_subscriptions(monkeypatch, tmp_path):
    """The default store reads a state file; tests must never see a real one."""
    monkeypatch.setenv("NOUGEN_MCP_EVENT_SUBSCRIPTIONS", str(tmp_path / "none.json"))


def test_mcp_native_wake_is_documented_but_qualified_and_plan_unresolved():
    from nougen_shards.wake import chatgpt_transports as ct
    assert MCP_NATIVE_WAKE_SUPPORTED is True
    assert ct.MCP_NATIVE_WAKE_QUALIFIER == "subscription_based_user_authorized_wake_only"
    assert ct.MCP_EVENTS_PLAN_ELIGIBILITY == "unresolved"


def test_future_transport_without_a_subscription_is_unconfigured_not_a_delivery():
    t = FutureMCPNativeWakeTransport()
    r = t.notify(wake_envelope_from_relay_id(RELAY_ID))
    assert r.delivered is False and r.status == "unconfigured"
    assert t.health()["status"] == "no_subscription"


def test_no_transport_capability_dict_ever_claims_mcp_native_support(monkeypatch):
    """A source-level trip-wire, same spirit as PR-A's 'NOT measured' test:
    if a transport's capabilities() ever reports plan_eligible=True for
    future_mcp_native, or configured=True for it, that is exactly the false
    claim this module exists to prevent."""
    monkeypatch.setenv("NOUGEN_CHATGPT_SLACK_WEBHOOK", "x")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_REPO", "r")
    monkeypatch.setenv("NOUGEN_CHATGPT_GITHUB_TOKEN", "t")
    for name, t in TRANSPORTS.items():
        caps = t.capabilities()
        if name == "future_mcp_native":
            assert caps["configured"] is False
            assert caps["plan_eligible"] is None  # unresolved: never claimed True
            assert caps["plan_eligibility"] == "unresolved"


def test_get_transport_is_case_and_whitespace_insensitive():
    assert isinstance(get_transport(" Slack "), SlackWakeTransport)
    assert get_transport("nonexistent") is None
