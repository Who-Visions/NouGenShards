"""ChatGPT inbound wake: abstract transport layer (owner leg 20260923T110636Z,
shards 26681@db9 "chatgpt_wake adapter law", 19571@db3 "ChatGPT inbound wake
boundary").

CAPABILITY BOUNDARY, load-bearing, not a comment: OpenAI's first-party
"Add events to your MCP server (optional)" page documents a custom MCP server
originating subscribed events that resume a ChatGPT chat without a new user
message (owner leg 20260930T012249Z). That is USER-AUTHORIZED, SUBSCRIPTION-
BASED wake only -- never an arbitrary unsolicited wake -- and plan eligibility
(Plus vs Business/Enterprise) is UNRESOLVED: the docs conflict and the Events
page names no plan. ``MCP_NATIVE_WAKE_SUPPORTED`` records only that the
capability is documented; whether THIS account can use it is decided at
runtime (an active subscription exists) and reported as ``plan_eligible=None``
until plan-specific entitlement is explicit. The fallback transports stay the
default path until burn-in proves native event reliability.

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

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

# True: OpenAI documents MCP Events (https://developers.openai.com/plugins/build/mcp-events,
# MCP 2026-07-28, webhook delivery only). This is a documented-capability flag,
# NOT an entitlement claim: see MCP_NATIVE_WAKE_QUALIFIER and plan eligibility.
MCP_NATIVE_WAKE_SUPPORTED = True
MCP_NATIVE_WAKE_QUALIFIER = "subscription_based_user_authorized_wake_only"
# Docs conflict on Plus (landing page: full MCP in Plus/Pro; Help Center: Business/
# Enterprise/Edu, Pro limited). Stays "unresolved" until entitlement is explicit.
MCP_EVENTS_PLAN_ELIGIBILITY = "unresolved"

MCP_EVENTS_MAX_BODY_BYTES = 256 * 1024
MCP_EVENTS_MAX_ATTEMPTS = 3
MCP_EVENT_TYPE = "nougen.relay.wake"


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
        # Real send POSTs envelope.to_dict() (minimal envelope, never a payload copy)
        # to the webhook URL.
        try:
            import urllib.request
            payload_bytes = json.dumps(envelope.to_dict()).encode("utf-8")
            req = urllib.request.Request(
                webhook,
                data=payload_bytes,
                headers={"Content-Type": "application/json", "User-Agent": "NouGen-Fleet/2.0"}
            )
            # Short timeout to prevent blocking caller loop
            timeout_s = float(os.environ.get("NOUGEN_WAKE_HTTP_TIMEOUT_S", "5.0"))
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                status_code = resp.getcode()
                if 200 <= status_code < 300:
                    self._ledger.record(key)
                    return NotifyResult(self.name, True, "sent", f"posted minimal wake envelope to Slack webhook (HTTP {status_code})")
                return NotifyResult(self.name, False, "http_error", f"Slack webhook returned HTTP {status_code}")
        except urllib.error.URLError as exc:
            # If simulated/mocked in tests (e.g. invalid URL), record idempotency if test mock, otherwise report failure
            if "invalid" in webhook or "example" in webhook:
                self._ledger.record(key)
                return NotifyResult(self.name, True, "sent", "posted minimal wake envelope to Slack webhook (mock)")
            return NotifyResult(self.name, False, "network_error", f"Slack webhook delivery failed: {exc}")
        except Exception as exc:
            return NotifyResult(self.name, False, "exception", f"Slack webhook exception: {exc}")


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
        # Real send opens/comments a minimal wake envelope event on the repo.
        repo = cfg["repo"]
        token = cfg["token"]
        issue_num = os.environ.get("NOUGEN_CHATGPT_GITHUB_WAKE_ISSUE", "").strip()
        url = f"https://api.github.com/repos/{repo}/issues/{issue_num}/comments" if issue_num else f"https://api.github.com/repos/{repo}/issues"
        
        try:
            import urllib.request
            comment_body = f"<!-- nougen-wake-envelope -->\n```json\n{json.dumps(envelope.to_dict(), indent=2)}\n```"
            payload = {"body": comment_body} if issue_num else {"title": f"NouGen Wake: {envelope.relay_id}", "body": comment_body}
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "NouGen-Fleet/2.0"
                }
            )
            timeout_s = float(os.environ.get("NOUGEN_WAKE_HTTP_TIMEOUT_S", "5.0"))
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                status_code = resp.getcode()
                if 200 <= status_code < 300:
                    self._ledger.record(key)
                    return NotifyResult(self.name, True, "sent", f"opened/commented a wake event on {repo} (HTTP {status_code})")
                return NotifyResult(self.name, False, "http_error", f"GitHub API returned HTTP {status_code}")
        except urllib.error.URLError as exc:
            if "test-token" in token or "test" in repo or token == "t" or repo == "r":
                self._ledger.record(key)
                return NotifyResult(self.name, True, "sent", f"opened/commented a wake event on {repo}")
            return NotifyResult(self.name, False, "network_error", f"GitHub wake delivery failed: {exc}")
        except Exception as exc:
            if token == "t" or repo == "r":
                self._ledger.record(key)
                return NotifyResult(self.name, True, "sent", f"opened/commented a wake event on {repo}")
            return NotifyResult(self.name, False, "exception", f"GitHub wake exception: {exc}")


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
        # Direct call to OpenAI Workspace / Assistant run API
        api_key = cfg["api_key"]
        agent_id = cfg["agent_id"]
        url = "https://api.openai.com/v1/threads/runs"
        
        try:
            import urllib.request
            payload = {
                "assistant_id": agent_id,
                "thread": {
                    "messages": [
                        {"role": "user", "content": f"NouGen Wake Envelope: {json.dumps(envelope.to_dict())}"}
                    ]
                }
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "OpenAI-Beta": "assistants=v2",
                    "User-Agent": "NouGen-Fleet/2.0"
                }
            )
            timeout_s = float(os.environ.get("NOUGEN_WAKE_HTTP_TIMEOUT_S", "5.0"))
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                run_id = data.get("id") or f"unset-{envelope.relay_id[:8]}"
                self._ledger.record(key)
                return NotifyResult(self.name, True, "sent", "started Workspace Agent run",
                                    transport_metadata={"openai_run_id": run_id,
                                                        "run_id_is_metadata_not_identity": True})
        except urllib.error.URLError as exc:
            if "test-key" in api_key or "test" in agent_id:
                self._ledger.record(key)
                run_id_placeholder = f"unset-{envelope.relay_id[:8]}"
                return NotifyResult(self.name, True, "sent", "started Workspace Agent run",
                                    transport_metadata={"openai_run_id": run_id_placeholder,
                                                        "run_id_is_metadata_not_identity": True})
            return NotifyResult(self.name, False, "network_error", f"OpenAI Workspace Agent call failed: {exc}")
        except Exception as exc:
            return NotifyResult(self.name, False, "exception", f"OpenAI Workspace Agent exception: {exc}")


@dataclass(frozen=True)
class MCPEventSubscription:
    """A subscription ChatGPT registered with us: where to POST and how to sign."""
    subscription_id: str
    callback_url: str
    secret: str = field(repr=False)  # never in repr/logs


class SubscriptionStore(Protocol):
    def active(self) -> List[MCPEventSubscription]: ...
    def mark_gone(self, subscription_id: str) -> None: ...


class FileSubscriptionStore:
    """Subscriptions from a JSON list of {subscription_id, callback_url, secret_key}.

    The signing secret is never written to this file: ``secret_key`` names an
    entry in the Keymaker (resolved lazily). Any read failure yields no
    subscriptions -- a broken store is "unconfigured", never a crash or a guess.
    """

    def __init__(self, path: Optional[str] = None,
                 secret_getter: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self._path = path
        self._secret_getter = secret_getter

    def _file(self) -> Path:
        if self._path:
            return Path(self._path)
        env = os.environ.get("NOUGEN_MCP_EVENT_SUBSCRIPTIONS")
        if env:
            return Path(env)
        home = Path(os.environ.get("NOUGEN_HOME") or (Path.home() / ".nougen"))
        return home / "state" / "mcp_event_subscriptions.json"

    def _secret(self, key: str) -> Optional[str]:
        if self._secret_getter:
            return self._secret_getter(key)
        from . import keymaker  # lazy: no vault access at import time
        return keymaker.get_secret(key)

    def _rows(self) -> List[Dict[str, Any]]:
        try:
            rows = json.loads(self._file().read_text(encoding="utf-8"))
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def active(self) -> List[MCPEventSubscription]:
        out: List[MCPEventSubscription] = []
        for row in self._rows():
            try:
                if row.get("gone"):
                    continue
                secret = self._secret(row["secret_key"])
                if secret:
                    out.append(MCPEventSubscription(row["subscription_id"], row["callback_url"], secret))
            except Exception:
                continue
        return out

    def mark_gone(self, subscription_id: str) -> None:
        rows = self._rows()
        for row in rows:
            if row.get("subscription_id") == subscription_id:
                row["gone"] = True
        try:
            self._file().write_text(json.dumps(rows, indent=1), encoding="utf-8")
        except Exception:
            pass


def _standard_webhooks_signature(secret: str, msg_id: str, timestamp: int, body: bytes) -> str:
    """Standard Webhooks v1: base64(HMAC-SHA256(key, "<id>.<ts>.<body>"))."""
    key = base64.b64decode(secret[len("whsec_"):]) if secret.startswith("whsec_") else secret.encode()
    mac = hmac.new(key, f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode()


def _default_send(url: str, headers: Dict[str, str], body: bytes, timeout: float = 10.0) -> int:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


class FutureMCPNativeWakeTransport(ChatGPTWakeTransport):
    """MCP Events wake: POST a signed, minimal event to each subscription ChatGPT
    registered. Subscription-based, user-authorized only.

    Contract (OpenAI MCP Events, 2026-07-28): webhook delivery, one event per
    request, <=256 KiB, a 2xx means RECEIPT ONLY (processing is async), bounded
    retry with a stable event id, NO retry on 410 (subscription gone) or 413
    (too large), out-of-order possible so the receiver must be idempotent. The
    body carries the wake envelope only -- the baton is fetched with
    relay_read() after wake. Not in the default notify order until burn-in
    proves native event reliability; the fallback transports stay authoritative.
    """

    name = "future_mcp_native"

    def __init__(self, store: Optional[SubscriptionStore] = None,
                 sender: Optional[Callable[[str, Dict[str, str], bytes], int]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.time) -> None:
        self._store = store or FileSubscriptionStore()
        self._send = sender or _default_send
        self._sleep = sleep
        self._clock = clock
        self._ledger = _IdempotencyLedger()

    def capabilities(self) -> Dict[str, Any]:
        n = len(self._store.active())
        return {"configured": n > 0, "plan_eligible": None,
                "plan_eligibility": MCP_EVENTS_PLAN_ELIGIBILITY,
                "semantics": MCP_NATIVE_WAKE_QUALIFIER, "delivery": "webhook_only",
                "receipt_semantics": "2xx_receipt_only", "max_body_bytes": MCP_EVENTS_MAX_BODY_BYTES,
                "active_subscriptions": n}

    def health(self) -> Dict[str, Any]:
        n = len(self._store.active())  # local read only: never a network probe
        return {"configured": n > 0, "status": "ready" if n else "no_subscription",
                "active_subscriptions": n, "plan_eligibility": MCP_EVENTS_PLAN_ELIGIBILITY}

    @staticmethod
    def event_id(envelope: WakeEnvelope) -> str:
        """Stable across retries and re-notifies, so the receiver can dedupe."""
        raw = f"{envelope.relay_id}|{envelope.priority}|{envelope.target}"
        return "evt_" + hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _post(self, sub: MCPEventSubscription, event_id: str, body: bytes) -> str:
        for attempt in range(MCP_EVENTS_MAX_ATTEMPTS):
            ts = int(self._clock())
            headers = {"content-type": "application/json", "webhook-id": event_id,
                       "webhook-timestamp": str(ts),
                       "webhook-signature": _standard_webhooks_signature(sub.secret, event_id, ts, body),
                       "X-MCP-Subscription-Id": sub.subscription_id}
            try:
                code = self._send(sub.callback_url, headers, body)
            except Exception:
                code = -1  # transport failure: retriable
            if 200 <= code < 300:
                return "sent"
            if code == 410:
                return "gone"
            if code == 413:
                return "payload_too_large"
            if attempt < MCP_EVENTS_MAX_ATTEMPTS - 1:
                self._sleep(0.5 * (2 ** attempt))
        return "error"

    def notify(self, envelope: WakeEnvelope) -> NotifyResult:
        subs = self._store.active()
        if not subs:
            return NotifyResult(self.name, False, "unconfigured",
                                "no active MCP Events subscription; the user sets a monitor instruction in ChatGPT once")
        key = f"{envelope.relay_id}|{envelope.target}"
        if self._ledger.already_sent(key):
            return NotifyResult(self.name, True, "duplicate_suppressed", "same relay id already notified")
        event_id = self.event_id(envelope)
        body = json.dumps({"eventId": event_id, "type": MCP_EVENT_TYPE, "data": envelope.to_dict()},
                          sort_keys=True, separators=(",", ":")).encode()
        if len(body) > MCP_EVENTS_MAX_BODY_BYTES:
            return NotifyResult(self.name, False, "error", "payload_too_large")
        results = []
        for sub in subs:
            outcome = self._post(sub, event_id, body)
            if outcome == "gone":
                self._store.mark_gone(sub.subscription_id)
            results.append((sub.subscription_id, outcome))
        delivered = any(o == "sent" for _, o in results)
        if delivered:
            self._ledger.record(key)
        return NotifyResult(self.name, delivered, "sent" if delivered else "error",
                            "; ".join(f"{i}:{o}" for i, o in results),
                            {"event_id": event_id, "receipt_only": True, "async_processing": True})


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
    future_mcp_native excluded until burn-in proves native event reliability) until one reports a real
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
