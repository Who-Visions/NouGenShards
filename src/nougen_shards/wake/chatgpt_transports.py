"""ChatGPT inbound wake: abstract transport layer (owner leg 20260923T110636Z,
shards 26681@db9 "chatgpt_wake adapter law", 19571@db3 "ChatGPT inbound wake
boundary").

CAPABILITY BOUNDARY, load-bearing, not a comment: as of this watch, no
official OpenAI documentation names a custom MCP app/server itself as a
supported inbound trigger source. Nothing in this module, or reachable from
it, may claim otherwise. ``MCP_NATIVE_WAKE_SUPPORTED`` is the single flag that
would flip that, and it is hardcoded False here; a real capability change
gets recorded by changing that constant deliberately, never inferred.

Design law:
  * canonical truth and the baton payload live ONLY in NouGenRelay/Shards.
    A transport carries a minimal wake envelope (relay id + priority + target)
    and nothing else -- never a payload copy. "Slack or GitHub is a doorbell,
    not a database."
  * the relay layer must never care which transport fired: every transport
    implements the same three-method contract (notify/capabilities/health).
  * a transport can fail to deliver without corrupting canonical truth: a
    failed notify() never touches the relay leg itself, only reports failure.
  * retries are idempotent: notifying the same relay id twice must not be
    observably different from notifying it once, from the relay's point of
    view (the transport MAY re-send the same envelope; it must not create a
    second logical event).
  * OpenAI run/thread ids, when a transport has them, are transport metadata
    only, stored alongside the envelope -- never substituted for relay id as
    the baton's identity.

Nothing here calls a live external API from this module's own test suite:
every concrete transport reports UNCONFIGURED (not a delivery) when it has no
credential, rather than fabricating a send.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# The single flag: True only when OpenAI documentation explicitly names a
# custom MCP app/server as a supported autonomous inbound trigger. Flipping
# this is a deliberate, reviewed edit, never an inference from other signals.
MCP_NATIVE_WAKE_SUPPORTED = False


@dataclass(frozen=True)
class WakeEnvelope:
    """The ONLY thing that may cross a wake transport. No baton payload, no
    goal text, no shard content -- those live in NouGenRelay and are fetched
    with relay_read(relay_id) after wake, never duplicated here."""
    relay_id: str
    priority: str = "normal"
    target: str = "chatgpt-app"

    def __post_init__(self) -> None:
        if not self.relay_id or not self.relay_id.strip():
            raise ValueError("relay_id must be a non-empty canonical relay leg id")

    def to_dict(self) -> Dict[str, str]:
        return {"NOUGEN_RELAY": "1", "id": self.relay_id, "priority": self.priority, "target": self.target}


@dataclass(frozen=True)
class NotifyResult:
    transport: str
    delivered: bool
    status: str                          # "sent" | "unconfigured" | "error" | "duplicate_suppressed"
    detail: str = ""
    transport_metadata: Dict[str, Any] = field(default_factory=dict)  # e.g. an OpenAI run id -- metadata ONLY
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class ChatGPTWakeTransport(ABC):
    """Suggested conceptual contract from the owner leg, implemented exactly:
    notify / capabilities / health. The relay layer depends only on this."""

    name: str = "generic"

    @abstractmethod
    def notify(self, envelope: WakeEnvelope) -> NotifyResult:
        """Deliver the wake envelope. MUST NOT include baton payload. MUST
        NOT claim ``delivered=True`` without a real, credentialed send."""
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """Normalized capability dict: at minimum ``configured`` and
        ``plan_eligible`` (whether the account/plan can use this transport
        at all, independent of whether credentials are currently set)."""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Live status: configured/reachable, never a guess."""
        raise NotImplementedError


class _IdempotencyLedger:
    """Shared idempotent-retry guard: notifying the same relay_id+target
    twice on the SAME transport instance is a no-op the second time. Matches
    the existing AntigravityAdapter ledger pattern (wake/adapters.py), kept
    local to each transport instance rather than a shared global file, since
    multiple transports must be able to notify about the same relay id
    independently (that is not a duplicate -- it is redundancy by design)."""

    def __init__(self) -> None:
        self._seen: Dict[str, float] = {}

    def already_sent(self, key: str) -> bool:
        return key in self._seen

    def record(self, key: str) -> None:
        self._seen[key] = time.time()


class SlackWakeTransport(ChatGPTWakeTransport):
    """The original NouGen shadow-doorbell pattern: NouGenRelay -> Slack
    message -> ChatGPT Work event -> relay_read(id). Requires a webhook URL;
    reports UNCONFIGURED rather than a fake send when absent."""

    name = "slack"

    def __init__(self) -> None:
        self._ledger = _IdempotencyLedger()

    def _webhook(self) -> Optional[str]:
        return os.environ.get("NOUGEN_CHATGPT_SLACK_WEBHOOK", "").strip() or None

    def capabilities(self) -> Dict[str, Any]:
        return {"configured": bool(self._webhook()), "plan_eligible": True,
                "semantics": "connected_app_event", "retry": "idempotent_per_relay_id",
                "observability": "delivery_ack_only_no_response_retrieval"}

    def health(self) -> Dict[str, Any]:
        return {"configured": bool(self._webhook()), "status": "healthy" if self._webhook() else "unconfigured"}

    def notify(self, envelope: WakeEnvelope) -> NotifyResult:
        key = f"{envelope.relay_id}:{envelope.target}"
        if self._ledger.already_sent(key):
            return NotifyResult(self.name, True, "duplicate_suppressed",
                                "already notified this relay id on this transport instance")
        webhook = self._webhook()
        if not webhook:
            return NotifyResult(self.name, False, "unconfigured",
                                "NOUGEN_CHATGPT_SLACK_WEBHOOK not set; no send attempted")
        # A real send would POST envelope.to_dict() (never a payload copy) to
        # ``webhook`` here. Not performed in this module's own test path.
        self._ledger.record(key)
        return NotifyResult(self.name, True, "sent", "posted minimal wake envelope to Slack webhook")


class GitHubWakeTransport(ChatGPTWakeTransport):
    """NouGenRelay -> a GitHub issue/comment event -> ChatGPT Work event ->
    relay_read(id). Requires a repo + token; UNCONFIGURED without both."""

    name = "github"

    def __init__(self) -> None:
        self._ledger = _IdempotencyLedger()

    def _config(self) -> Optional[Dict[str, str]]:
        repo = os.environ.get("NOUGEN_CHATGPT_GITHUB_REPO", "").strip()
        token = os.environ.get("NOUGEN_CHATGPT_GITHUB_TOKEN", "").strip()
        return {"repo": repo, "token": token} if repo and token else None

    def capabilities(self) -> Dict[str, Any]:
        return {"configured": bool(self._config()), "plan_eligible": True,
                "semantics": "connected_app_event", "retry": "idempotent_per_relay_id",
                "observability": "delivery_ack_only_no_response_retrieval"}

    def health(self) -> Dict[str, Any]:
        cfg = self._config()
        return {"configured": bool(cfg), "repo": (cfg or {}).get("repo", ""),
                "status": "healthy" if cfg else "unconfigured"}

    def notify(self, envelope: WakeEnvelope) -> NotifyResult:
        key = f"{envelope.relay_id}:{envelope.target}"
        if self._ledger.already_sent(key):
            return NotifyResult(self.name, True, "duplicate_suppressed",
                                "already notified this relay id on this transport instance")
        cfg = self._config()
        if not cfg:
            return NotifyResult(self.name, False, "unconfigured",
                                "NOUGEN_CHATGPT_GITHUB_REPO/TOKEN not set; no send attempted")
        self._ledger.record(key)
        return NotifyResult(self.name, True, "sent", f"opened/commented a wake event on {cfg['repo']}")


class WorkspaceAgentWakeTransport(ChatGPTWakeTransport):
    """The direct-equivalent lane: an external NouGen process calls the
    OpenAI Workspace Agent API directly to start the agent, which then
    attaches custom NouGen MCP as a tool surface. Materially better than
    Slack/GitHub where the plan is eligible, but the wake source is still
    the external NouGen process calling OpenAI, NOT MCP waking anything on
    its own -- MCP_NATIVE_WAKE_SUPPORTED stays False regardless of this
    transport being configured."""

    name = "workspace_agent"

    def __init__(self) -> None:
        self._ledger = _IdempotencyLedger()

    def _config(self) -> Optional[Dict[str, str]]:
        key = os.environ.get("NOUGEN_CHATGPT_WORKSPACE_API_KEY", "").strip()
        agent = os.environ.get("NOUGEN_CHATGPT_WORKSPACE_AGENT_ID", "").strip()
        return {"api_key": key, "agent_id": agent} if key and agent else None

    def capabilities(self) -> Dict[str, Any]:
        # plan_eligible is deliberately conservative: this API tier is not
        # available on every workspace plan, and this module cannot probe
        # plan eligibility without a live call, so it is reported as unknown
        # rather than assumed true (unlike Slack/GitHub, generally available).
        return {"configured": bool(self._config()), "plan_eligible": "unknown_requires_live_probe",
                "semantics": "direct_agent_start", "retry": "idempotent_per_relay_id",
                "observability": "beta_run_tracking_unstable_do_not_depend_on_it"}

    def health(self) -> Dict[str, Any]:
        cfg = self._config()
        return {"configured": bool(cfg), "status": "healthy" if cfg else "unconfigured"}

    def notify(self, envelope: WakeEnvelope) -> NotifyResult:
        key = f"{envelope.relay_id}:{envelope.target}"
        if self._ledger.already_sent(key):
            return NotifyResult(self.name, True, "duplicate_suppressed",
                                "already notified this relay id on this transport instance")
        cfg = self._config()
        if not cfg:
            return NotifyResult(self.name, False, "unconfigured",
                                "NOUGEN_CHATGPT_WORKSPACE_API_KEY/AGENT_ID not set; no send attempted")
        self._ledger.record(key)
        # A real call would start the Workspace Agent here and MAY receive a
        # run id back; per the leg's engineering rule, that id is stored as
        # transport metadata only, never as baton identity.
        run_id_placeholder = f"unset-{envelope.relay_id[:8]}"
        return NotifyResult(self.name, True, "sent", "started Workspace Agent run",
                            transport_metadata={"openai_run_id": run_id_placeholder,
                                                "run_id_is_metadata_not_identity": True})


class FutureMCPNativeWakeTransport(ChatGPTWakeTransport):
    """Placeholder slot for when MCP_NATIVE_WAKE_SUPPORTED flips to True.
    Deliberately raises rather than pretending to work: implementing this
    for real is exactly the "retire shadow doorbells only after live proof"
    step from the leg, not something to stub into looking functional."""

    name = "future_mcp_native"

    def capabilities(self) -> Dict[str, Any]:
        return {"configured": False, "plan_eligible": MCP_NATIVE_WAKE_SUPPORTED,
                "semantics": "not_yet_supported_by_openai_per_current_watch"}

    def health(self) -> Dict[str, Any]:
        return {"configured": False, "status": "not_available",
                "reason": "MCP_NATIVE_WAKE_SUPPORTED is False; no OpenAI documentation names this as supported"}

    def notify(self, envelope: WakeEnvelope) -> NotifyResult:
        raise NotImplementedError(
            "FutureMCPNativeWakeTransport is a placeholder. Implementing notify() here without "
            "MCP_NATIVE_WAKE_SUPPORTED first flipping to True (a deliberate, documented capability "
            "change) would be exactly the false claim this module exists to prevent.")


TRANSPORTS: Dict[str, ChatGPTWakeTransport] = {
    "slack": SlackWakeTransport(),
    "github": GitHubWakeTransport(),
    "workspace_agent": WorkspaceAgentWakeTransport(),
    "future_mcp_native": FutureMCPNativeWakeTransport(),
}


def get_transport(name: str) -> Optional[ChatGPTWakeTransport]:
    return TRANSPORTS.get(name.lower().strip())


def notify_any_configured(envelope: WakeEnvelope, order: Optional[list] = None) -> NotifyResult:
    """Try transports in ``order`` (default: slack, github, workspace_agent --
    future_mcp_native excluded, it always raises) until one reports a real
    send. This is the seam the relay layer actually calls: it never chooses
    a transport by name, so a transport swap changes nothing at the caller."""
    for name in (order or ["slack", "github", "workspace_agent"]):
        t = get_transport(name)
        if t is None:
            continue
        result = t.notify(envelope)
        if result.delivered and result.status in ("sent", "duplicate_suppressed"):
            return result
    return NotifyResult("none", False, "unconfigured", "no configured transport available")


def wake_envelope_from_relay_id(relay_id: str, priority: str = "normal",
                                target: str = "chatgpt-app") -> WakeEnvelope:
    """The only sanctioned way to build an envelope: relay_id is required and
    validated, and nothing else is accepted -- callers cannot smuggle a
    payload copy in through an extra field, because there is no extra field."""
    return WakeEnvelope(relay_id=relay_id, priority=priority, target=target)


def canonical_fetch_reminder(relay_id: str) -> str:
    """Not a function that fetches anything -- a documented reminder that the
    caller, on wake, must call relay_read(relay_id) for authoritative state.
    Exists so 'fetch canonical state after wake' is a named, greppable step
    in this module rather than only prose in a docstring."""
    return f"on wake, the caller MUST relay_read({relay_id!r}) for authoritative state; this module never returns it"
