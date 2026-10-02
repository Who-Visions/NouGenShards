"""Bounded session tool activity tracking and telemetry projection.

Part of NouGen information dynamics and context-bloat mitigation.
Tracks, bounds, redacts, and projects tool execution activity across agent sessions
without leaking sensitive secrets or blowing primary context tokens.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_MAX_ACTIVITY_RECORDS = 50
DEFAULT_MAX_ARG_CHARS = 500
DEFAULT_MAX_RESULT_CHARS = 1000

# Secret scrub patterns
SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z\-_]{30,50})"),
    re.compile(r"(ghp_[0-9A-Za-z]{36,})"),
    re.compile(r"(sk-[0-9A-Za-z]{20,})"),
    re.compile(r"(bearer\s+[A-Za-z0-9_\-\.]+)", re.IGNORECASE),
    re.compile(r"(['\"]?(?:api[_-]?key|token|secret|password)['\"]?\s*[:=]\s*['\"])([^'\"]+)(['\"])", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Scrub known secret and token patterns from tool args or result payloads."""
    if not isinstance(text, str):
        return text

    scrubbed = text
    # Direct matches
    scrubbed = SECRET_PATTERNS[0].sub("[REDACTED_GOOGLE_KEY]", scrubbed)
    scrubbed = SECRET_PATTERNS[1].sub("[REDACTED_GH_TOKEN]", scrubbed)
    scrubbed = SECRET_PATTERNS[2].sub("[REDACTED_API_KEY]", scrubbed)
    scrubbed = SECRET_PATTERNS[3].sub("Bearer [REDACTED_TOKEN]", scrubbed)

    # Key-value matches
    def _kv_repl(m: re.Match) -> str:
        return f"{m.group(1)}[REDACTED]{m.group(3)}"

    scrubbed = SECRET_PATTERNS[4].sub(_kv_repl, scrubbed)
    return scrubbed


@dataclass
class ToolActivityRecord:
    session_id: str
    tool_name: str
    arguments: Dict[str, Any]
    ok: bool
    result_size: int
    duration_ms: float
    timestamp: float = field(default_factory=time.time)
    digest: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if not self.digest:
            # Deterministic SHA256 of tool invocation
            canon = f"{self.session_id}:{self.tool_name}:{json.dumps(self.arguments, sort_keys=True, default=str)}"
            self.digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


class SessionToolActivityTracker:
    """Thread-safe bounded recorder of tool invocations within a session."""

    def __init__(
        self,
        session_id: str,
        max_records: int = DEFAULT_MAX_ACTIVITY_RECORDS,
        max_arg_chars: int = DEFAULT_MAX_ARG_CHARS,
        max_result_chars: int = DEFAULT_MAX_RESULT_CHARS,
    ):
        self.session_id = session_id
        self.max_records = max_records
        self.max_arg_chars = max_arg_chars
        self.max_result_chars = max_result_chars
        self._records: List[ToolActivityRecord] = []
        self._counts: Dict[str, int] = {}

    def record_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        ok: bool,
        result_size: int,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
    ) -> ToolActivityRecord:
        """Record a single tool call with bounding and secret redaction."""
        # Clean and redact args
        redacted_args: Dict[str, Any] = {}
        for k, v in arguments.items():
            s = json.dumps(v, default=str)
            s_clean = redact_secrets(s)
            if len(s_clean) > self.max_arg_chars:
                s_clean = s_clean[: self.max_arg_chars] + "...[truncated]"
            try:
                redacted_args[k] = json.loads(s_clean)
            except Exception:
                redacted_args[k] = s_clean

        rec = ToolActivityRecord(
            session_id=self.session_id,
            tool_name=tool_name,
            arguments=redacted_args,
            ok=ok,
            result_size=result_size,
            duration_ms=duration_ms,
            error=redact_secrets(error) if error else None,
        )

        self._records.append(rec)
        self._counts[tool_name] = self._counts.get(tool_name, 0) + 1

        # Enforce bounding
        if len(self._records) > self.max_records:
            # Drop oldest records to stay strictly within bounded budget
            self._records = self._records[-self.max_records :]

        return rec

    @property
    def total_calls(self) -> int:
        return sum(self._counts.values())

    @property
    def counts(self) -> Dict[str, int]:
        return dict(self._counts)

    def get_records(self, limit: Optional[int] = None) -> List[ToolActivityRecord]:
        if limit is None:
            return list(self._records)
        return self._records[-limit:]

    def summarize(self) -> Dict[str, Any]:
        """Compact summary HUD suitable for low-token context injection."""
        success_count = sum(1 for r in self._records if r.ok)
        failure_count = len(self._records) - success_count
        return {
            "session_id": self.session_id,
            "total_calls": self.total_calls,
            "recent_count": len(self._records),
            "success_count": success_count,
            "failure_count": failure_count,
            "tools_used": self._counts,
            "recent_tools": [r.tool_name for r in self._records[-5:]],
        }

    def project_bounded_context(self, max_tokens_approx: int = 500) -> str:
        """Render ultra-dense human-readable HUD string for context injection."""
        s = self.summarize()
        lines = [
            f"[TOOL_ACTIVITY | Session: {self.session_id}]",
            f"Total: {s['total_calls']} calls | OK: {s['success_count']} | Fail: {s['failure_count']}",
            f"Tool breakdown: {', '.join(f'{k}:{v}' for k, v in sorted(self._counts.items()))}",
        ]
        if self._records:
            lines.append("Recent executions:")
            for r in self._records[-3:]:
                status = "OK" if r.ok else f"ERR({r.error})"
                lines.append(f"  • {r.tool_name}(...) -> {status} [{r.result_size} bytes, {r.duration_ms:.1f}ms]")
        rendered = "\n".join(lines)
        # Cap approx chars (1 token ≈ 4 chars)
        max_chars = max_tokens_approx * 4
        if len(rendered) > max_chars:
            rendered = rendered[:max_chars] + "\n...[activity truncated]"
        return rendered
