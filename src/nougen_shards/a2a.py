"""
A2A — Agent-to-Agent messaging for the NouGen roster.

A lightweight, in-process message bus that lets any roster agent address any
other by name, with a typed envelope (sender, recipient, intent, content).

Routing is two-tier:
    1. If the recipient registered a rich handler (e.g. Griot), the bus calls
       it directly and returns its reply envelope.
    2. Otherwise the bus falls back to ``agents.run_agent`` — every persona in
       the roster is reachable over A2A even without a custom handler.

Every exchange is appended to an in-memory log for observability and testing.
The bus is synchronous request/reply: ``send`` returns the reply envelope.
"""

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional

# Recognized intents. Handlers may support a subset; "chat" is the default.
CHAT = "chat"
RECALL = "recall"
CONSOLIDATE = "consolidate"
QUERY = "query"


@dataclass
class A2AMessage:
    """A single agent-to-agent envelope."""
    sender: str
    recipient: str
    content: str
    intent: str = CHAT
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    metadata: Dict[str, Any] = field(default_factory=dict)

    def reply(self, content: str, sender: Optional[str] = None,
              metadata: Optional[Dict[str, Any]] = None) -> "A2AMessage":
        """Build a reply envelope, preserving the correlation id."""
        return A2AMessage(
            sender=sender or self.recipient,
            recipient=self.sender,
            content=content,
            intent=self.intent,
            correlation_id=self.correlation_id,
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# recipient name (lowercased) -> handler(A2AMessage) -> A2AMessage
_HANDLERS: Dict[str, Callable[[A2AMessage], A2AMessage]] = {}

# Append-only exchange log (each entry: {"request": {...}, "reply": {...}}).
MESSAGE_LOG: List[Dict[str, Any]] = []


def register_handler(agent_name: str, handler: Callable[[A2AMessage], A2AMessage]) -> None:
    """Register a rich A2A handler for an agent (overrides run_agent fallback)."""
    _HANDLERS[agent_name.lower()] = handler


def unregister_handler(agent_name: str) -> None:
    _HANDLERS.pop(agent_name.lower(), None)


def has_handler(agent_name: str) -> bool:
    return agent_name.lower() in _HANDLERS


def registered_handlers() -> List[str]:
    return sorted(_HANDLERS)


def _fallback_to_roster(message: A2AMessage) -> A2AMessage:
    """Route to a roster persona via run_agent when no rich handler exists."""
    from . import agents
    spec = agents.get_agent(message.recipient)
    if spec is None:
        return message.reply(
            f"[a2a] No agent named '{message.recipient}'.",
            sender="a2a-bus",
            metadata={"error": "unknown_recipient"},
        )
    answer = agents.run_agent(spec.name, message.content)
    return message.reply(answer, sender=spec.name)


def send(message: A2AMessage) -> A2AMessage:
    """Deliver a message and return the reply envelope."""
    handler = _HANDLERS.get(message.recipient.lower())
    try:
        reply = handler(message) if handler else _fallback_to_roster(message)
    except Exception as exc:  # a misbehaving handler must not kill the caller
        reply = message.reply(
            f"[a2a] handler error: {exc}",
            sender="a2a-bus",
            metadata={"error": "handler_exception"},
        )
    MESSAGE_LOG.append({"request": message.to_dict(), "reply": reply.to_dict()})
    return reply


def ask(sender: str, recipient: str, content: str,
        intent: str = CHAT, **metadata: Any) -> str:
    """Convenience: send a message and return just the reply text."""
    msg = A2AMessage(sender=sender, recipient=recipient, content=content,
                     intent=intent, metadata=metadata or {})
    return send(msg).content
