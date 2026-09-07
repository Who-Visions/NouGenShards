"""
NouGenWake: Account Usage & Quota Wake Circuit.
Inspects account /usage, /status, or quota error strings (e.g., "Resets in 2h57m49s")
and automatically schedules a durable WakeTicket to ping agents back up when limits reset.
"""

import re
import sys
import json
import time
import uuid
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from nougen_shards.nougenmsg import NouGenMsgBus, get_current_node

DEFAULT_TICKET_DIR = Path.home() / ".nougen" / "wake_tickets"
RELAY_WAKE_DIR = Path.home() / "Outpost" / "NouGenRelay" / ".relay" / "wake"


class QuotaWakeParser:
    """Extracts rate-limit reset times and error IDs from account errors or status outputs."""

    # Patterns for durations like "Resets in 2h57m49s", "resets in 45m", "retry after 120s"
    DURATION_PATTERN = re.compile(
        r"resets?\s+in\s+(?:(\d+)\s*d\s*)?(?:(\d+)\s*h\s*)?(?:(\d+)\s*m\s*)?(?:(\d+)\s*s)?",
        re.IGNORECASE
    )
    RETRY_AFTER_PATTERN = re.compile(
        r"retry[- ]after[:\s]+(\d+)\s*(?:s|sec|seconds)?",
        re.IGNORECASE
    )
    # Pattern for clock times like "try again at 6:02 AM", "available at 06:02 AM"
    TIME_PATTERN = re.compile(
        r"(?:try again|available|resets?)\s+at\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)",
        re.IGNORECASE
    )
    # Pattern for Error IDs
    ERROR_ID_PATTERN = re.compile(
        r"(?:Error\s*ID|Request\s*ID|trace_id)[:\s]+([a-zA-Z0-9_\-]+)",
        re.IGNORECASE
    )

    @classmethod
    def parse(cls, text: str, now_dt: Optional[datetime.datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Parses text for quota / usage reset information.
        Returns a dict with reset_seconds, wake_at_utc, error_id, and matched_pattern.
        """
        if not text:
            return None

        if now_dt is None:
            now_dt = datetime.datetime.now(datetime.timezone.utc)

        error_id_match = cls.ERROR_ID_PATTERN.search(text)
        error_id = error_id_match.group(1) if error_id_match else None

        # 1. Try Duration pattern (e.g., "Resets in 2h57m49s")
        dur_match = cls.DURATION_PATTERN.search(text)
        if dur_match:
            days = int(dur_match.group(1) or 0)
            hours = int(dur_match.group(2) or 0)
            minutes = int(dur_match.group(3) or 0)
            seconds = int(dur_match.group(4) or 0)
            total_seconds = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
            if total_seconds > 0:
                wake_dt = now_dt + datetime.timedelta(seconds=total_seconds)
                return {
                    "reset_seconds": total_seconds,
                    "wake_at_utc": wake_dt.isoformat(),
                    "error_id": error_id,
                    "matched_pattern": dur_match.group(0),
                    "parser_type": "duration"
                }

        # 2. Try Retry-After pattern (e.g., "Retry after 180s")
        retry_match = cls.RETRY_AFTER_PATTERN.search(text)
        if retry_match:
            total_seconds = int(retry_match.group(1))
            wake_dt = now_dt + datetime.timedelta(seconds=total_seconds)
            return {
                "reset_seconds": total_seconds,
                "wake_at_utc": wake_dt.isoformat(),
                "error_id": error_id,
                "matched_pattern": retry_match.group(0),
                "parser_type": "retry_after"
            }

        # 3. Try Time pattern (e.g., "try again at 6:02 AM")
        time_match = cls.TIME_PATTERN.search(text)
        if time_match:
            time_str = time_match.group(1).strip()
            # Attempt to parse time in local/target timezone
            parsed_seconds = cls._seconds_until_time_str(time_str)
            if parsed_seconds is not None:
                wake_dt = now_dt + datetime.timedelta(seconds=parsed_seconds)
                return {
                    "reset_seconds": parsed_seconds,
                    "wake_at_utc": wake_dt.isoformat(),
                    "error_id": error_id,
                    "matched_pattern": time_match.group(0),
                    "parser_type": "clock_time"
                }

        return None

    @staticmethod
    def _seconds_until_time_str(time_str: str) -> Optional[int]:
        now = datetime.datetime.now()
        for fmt in ["%I:%M %p", "%I:%M:%S %p", "%H:%M", "%H:%M:%S"]:
            try:
                t = datetime.datetime.strptime(time_str.upper(), fmt).time()
                target_dt = datetime.datetime.combine(now.date(), t)
                if target_dt <= now:
                    target_dt += datetime.timedelta(days=1)
                return int((target_dt - now).total_seconds())
            except ValueError:
                continue
        return None


class NouGenWakeEngine:
    """Manages creation, persistence, checking, and firing of WakeTickets."""

    def __init__(self, ticket_dir: Path = DEFAULT_TICKET_DIR):
        self.ticket_dir = ticket_dir
        self.ticket_dir.mkdir(parents=True, exist_ok=True)

    def create_ticket(
        self,
        target_agent: str,
        target_node: Optional[str] = None,
        reason: str = "quota_reset",
        raw_error: str = "",
        resume_payload: str = "",
        buffer_seconds: int = 5
    ) -> Dict[str, Any]:
        """
        Creates a durable WakeTicket by parsing the raw error or using defaults.
        """
        if not target_node:
            target_node = get_current_node()

        parsed = QuotaWakeParser.parse(raw_error)
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        
        if parsed:
            total_sec = parsed["reset_seconds"] + buffer_seconds
            wake_dt = now_dt + datetime.timedelta(seconds=total_sec)
            error_id = parsed.get("error_id")
            matched = parsed.get("matched_pattern")
        else:
            total_sec = 3600
            wake_dt = now_dt + datetime.timedelta(seconds=total_sec)
            error_id = None
            matched = "default_fallback"

        ticket_id = f"wake-{int(now_dt.timestamp())}-{uuid.uuid4().hex[:8]}"
        ticket = {
            "ticket_id": ticket_id,
            "status": "pending",
            "target_agent": target_agent.lower(),
            "target_node": target_node.lower(),
            "reason": reason,
            "error_id": error_id,
            "matched_pattern": matched,
            "reset_seconds": total_sec,
            "created_utc": now_dt.isoformat(),
            "wake_at_utc": wake_dt.isoformat(),
            "wake_at_epoch": wake_dt.timestamp(),
            "raw_error": raw_error[:500],
            "resume_payload": resume_payload or f"Quota reset completed. Resuming execution for @{target_agent}."
        }

        # Save to local wake tickets
        ticket_file = self.ticket_dir / f"{ticket_id}.json"
        ticket_file.write_text(json.dumps(ticket, indent=2), encoding="utf-8")

        # Mirror to NouGenRelay wake dir if present
        try:
            if RELAY_WAKE_DIR.is_dir():
                relay_file = RELAY_WAKE_DIR / f"{ticket_id}.wake.json"
                relay_file.write_text(json.dumps(ticket, indent=2), encoding="utf-8")
        except Exception:
            pass

        return ticket

    def list_tickets(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists existing wake tickets, sorted by wake_at_epoch."""
        tickets = []
        for p in self.ticket_dir.glob("wake-*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if status is None or data.get("status") == status:
                    tickets.append(data)
            except Exception:
                pass
        tickets.sort(key=lambda x: x.get("wake_at_epoch", 0))
        return tickets

    def run_due_tickets(self) -> List[Dict[str, Any]]:
        """
        Checks all pending tickets. Any whose wake_at_epoch <= now are fired via NouGenMsgBus.
        """
        now_epoch = time.time()
        fired = []

        for p in self.ticket_dir.glob("wake-*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("status") != "pending":
                    continue

                wake_epoch = data.get("wake_at_epoch", 0)
                if now_epoch >= wake_epoch:
                    target_agent = data.get("target_agent", "all")
                    target_node = data.get("target_node") or get_current_node()
                    resume_text = data.get("resume_payload") or "🔔 Quota reset detected! Resuming execution."
                    
                    # Fire live ping to wake the agent
                    dest = f"@{target_node}:{target_agent}"
                    res = NouGenMsgBus.live_ping(
                        target=dest,
                        text=f"🔔 WAKE ALERT: {resume_text} (Ticket: {data.get('ticket_id')})"
                    )

                    data["status"] = "fired"
                    data["fired_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    data["dispatch_result"] = res
                    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    fired.append(data)
            except Exception as e:
                print(f"[!] Error processing wake ticket {p}: {e}", file=sys.stderr)

        return fired
