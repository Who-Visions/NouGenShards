"""TaskFlow Inbox Triage 2 Engine for NouGen Shards Substrate.

Provides deterministic parsing, classification, urgency scoring, deduplication,
and stateful triage of inbound fleet messages, socket streams, and relays.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class UrgencyLevel(str, Enum):
    P0_CRITICAL = "P0"
    P1_ACTIONABLE = "P1"
    P2_WAITING = "P2"
    P3_FYI = "P3"


class TriageCategory(str, Enum):
    RELAY_WORK = "relay_work"
    SECURITY_ALERT = "security_alert"
    HEARTBEAT_TELEMETRY = "heartbeat_telemetry"
    WAITING_DEPENDENCY = "waiting_dependency"
    GENERAL = "general"


@dataclass
class TriagedItem:
    message_id: str
    source_file: Optional[str]
    sender: str
    timestamp: float
    urgency: UrgencyLevel
    category: TriageCategory
    action_required: str
    payload: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "source_file": self.source_file,
            "sender": self.sender,
            "timestamp": self.timestamp,
            "urgency": self.urgency.value,
            "category": self.category.value,
            "action_required": self.action_required,
            "summary": self.summary,
            "payload": self.payload,
        }


class TaskFlowTriageEngine:
    """Core triage classifier and state manager."""

    def __init__(self, inbox_dir: Optional[Path] = None):
        self.inbox_dir = inbox_dir or (Path.home() / ".nougen" / "agy_inbox")

    def classify_payload(self, filename: str, data: Dict[str, Any]) -> TriagedItem:
        msg_id = data.get("id") or data.get("message_id") or filename
        sender = data.get("sender") or data.get("sender_node") or "unknown"
        ts = float(data.get("timestamp") or data.get("created_at") or 0.0)
        text = (data.get("text") or data.get("message") or data.get("body") or "").strip()
        event_type = (data.get("type") or data.get("event") or "").lower()

        # Classification heuristics
        # 1. P0 Critical
        critical_keywords = ["red card", "failure", "outage", "emergency", "fatal", "broken pipe", "blocked"]
        if (
            "red_card" in filename.lower()
            or any(kw in text.lower() for kw in critical_keywords)
            or data.get("priority") in ["high", "critical", "P0"]
        ):
            return TriagedItem(
                message_id=msg_id,
                source_file=filename,
                sender=sender,
                timestamp=ts,
                urgency=UrgencyLevel.P0_CRITICAL,
                category=TriageCategory.SECURITY_ALERT,
                action_required="IMMEDIATE_INTERVENTION",
                summary=f"Critical fleet alert: {text[:100]}",
                payload=data,
            )

        # 2. P2 Waiting
        waiting_keywords = ["waiting", "in_progress", "pending", "awaiting_approval", "pr checks"]
        if (
            any(kw in text.lower() for kw in waiting_keywords)
            or data.get("state") in ["waiting", "pending"]
        ):
            return TriagedItem(
                message_id=msg_id,
                source_file=filename,
                sender=sender,
                timestamp=ts,
                urgency=UrgencyLevel.P2_WAITING,
                category=TriageCategory.WAITING_DEPENDENCY,
                action_required="SCHEDULE_IDLE_TIMER",
                summary=f"Waiting state: {text[:100]}",
                payload=data,
            )

        # 3. P3 FYI / Telemetry
        telemetry_prefixes = ["ping_", "probe_", "rollcall_", "canary_"]
        is_telemetry = (
            any(filename.startswith(p) for p in telemetry_prefixes)
            or event_type in ["ping", "pong", "heartbeat", "rollcall"]
            or "keepalive" in text.lower()
        )
        if is_telemetry and not any(kw in text.lower() for kw in ["relay", "leg", "task", "todo"]):
            return TriagedItem(
                message_id=msg_id,
                source_file=filename,
                sender=sender,
                timestamp=ts,
                urgency=UrgencyLevel.P3_FYI,
                category=TriageCategory.HEARTBEAT_TELEMETRY,
                action_required="DEDUP_AND_ARCHIVE",
                summary=f"Telemetry keepalive from {sender}",
                payload=data,
            )

        # 4. P1 Actionable Work (Default for relay legs, tasks, handoffs)
        return TriagedItem(
            message_id=msg_id,
            source_file=filename,
            sender=sender,
            timestamp=ts,
            urgency=UrgencyLevel.P1_ACTIONABLE,
            category=TriageCategory.RELAY_WORK,
            action_required="DISPATCH_TASKFLOW_LANE",
            summary=f"Actionable baton: {text[:100]}",
            payload=data,
        )

    def triage_directory(self, limit: int = 100) -> List[TriagedItem]:
        if not self.inbox_dir.exists():
            return []

        triaged = []
        files = sorted(self.inbox_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

        for p in files[:limit]:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                item = self.classify_payload(p.name, data)
                triaged.append(item)
            except Exception:
                continue

        return triaged

    def generate_report(self, items: List[TriagedItem]) -> str:
        p0 = [i for i in items if i.urgency == UrgencyLevel.P0_CRITICAL]
        p1 = [i for i in items if i.urgency == UrgencyLevel.P1_ACTIONABLE]
        p2 = [i for i in items if i.urgency == UrgencyLevel.P2_WAITING]
        p3 = [i for i in items if i.urgency == UrgencyLevel.P3_FYI]

        lines = [
            "### 📥 NouGen TaskFlow Triage Report",
            f"- **Total Ingested**: {len(items)} items",
            f"- 🔴 **P0 Critical**: {len(p0)}",
            f"- 🟡 **P1 Actionable**: {len(p1)}",
            f"- 🔵 **P2 Waiting**: {len(p2)}",
            f"- 🟢 **P3 Archived / FYI**: {len(p3)}",
            "",
        ]

        if p0:
            lines.append("#### 🔴 P0 Critical Items:")
            for item in p0[:5]:
                lines.append(f"- **{item.sender}** (`{item.source_file}`): {item.summary}")
            lines.append("")

        if p1:
            lines.append("#### 🟡 P1 Actionable Items:")
            for item in p1[:5]:
                lines.append(f"- **{item.sender}** (`{item.source_file}`): {item.summary}")
            lines.append("")

        return "\n".join(lines)
