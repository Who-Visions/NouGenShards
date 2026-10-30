"""Write-time evidence gate for completion claims (Truth Anchor layer 4).

A shard that claims completion ("fixed", "resolved", "verified", ...) is durable
memory that later sessions trust. Prompt rules ask agents not to claim success
without evidence; this gate enforces it at the write.

A shard is a completion claim when its event_type or a tag says so (and, opt-in,
when its title or body matches a success phrase). It must then carry either:

  * a full PoE block that `PoEValidator.validate_poe_block` accepts (existing
    commit, passing test run with stdout hash, observer attestation), or
  * scoreboard evidence for work with no commit: a non-empty command, exit_code
    0, and non-empty output or output hash.

Evidence comes from `capture(poe=...)` / `capture(evidence=...)` or a fenced
```poe / ```scoreboard / ```evidence block in the body (JSON or `key: value`
lines). Ordinary shards are untouched.

Env: NOUGEN_POE_GATE=enforce|warn|off (default enforce);
NOUGEN_POE_COMPLETION_TAGS, NOUGEN_POE_COMPLETION_EVENTS override the trigger
sets; NOUGEN_POE_TEXT_DETECT=1 also treats success phrases in the title/body as
claims (off by default: relay mirrors and logs quote such phrases routinely).
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .poe_validator import PoEValidator

logger = logging.getLogger(__name__)

_DEFAULT_COMPLETION_TAGS = "completed,resolved,fixed,fix,bugfix,verified,passed,solution,done"
_DEFAULT_COMPLETION_EVENTS = ("completion,resolution,task_completion,task_complete,fix,"
                              "bugfix,success,verified,passed,milestone_complete")
_EVIDENCE_FENCE = re.compile(r"```(?:poe|scoreboard|evidence|test-evidence)\s*\n(.*?)\n?```",
                             re.DOTALL | re.IGNORECASE)
_TEXT_SCAN_CHARS = 2000
_SUCCESS_PATTERNS = [
    re.compile(r"\b(?:task|issue|bug|problem|ticket)\s+(?:is\s+)?"
               r"(?:fixed|resolved|completed|closed|solved)\b", re.I),
    re.compile(r"\b(?:fix|solution|resolution|patch)\s+"
               r"(?:landed|deployed|verified|complete|successful)\b", re.I),
    re.compile(r"\ball\s+tests?\s+(?:pass|passed|passing)\b", re.I),
    re.compile(r"\bverification\s+(?:passed|successful|complete)\b", re.I),
    re.compile(r"^\[(?:FIX|RESOLVED|COMPLETED|SUCCESS|VERIFIED)\]", re.I),
]


def gate_mode() -> str:
    mode = os.getenv("NOUGEN_POE_GATE", "enforce").strip().lower()
    if mode not in {"enforce", "warn", "off"}:
        logger.warning("poe_gate: unknown NOUGEN_POE_GATE=%r; using enforce", mode)
        return "enforce"
    return mode


def _env_set(name: str, default: str) -> set:
    return {t.strip().lower() for t in os.getenv(name, default).split(",") if t.strip()}


def completion_tags() -> set:
    return _env_set("NOUGEN_POE_COMPLETION_TAGS", _DEFAULT_COMPLETION_TAGS)


def completion_events() -> set:
    return _env_set("NOUGEN_POE_COMPLETION_EVENTS", _DEFAULT_COMPLETION_EVENTS)


def claim_reason(tags: Optional[List[str]], event_type: str = "",
                 title: str = "", content: str = "") -> Optional[str]:
    """Why this shard counts as a completion claim, or None if it does not."""
    event = str(event_type or "").strip().lower()
    if event and event in completion_events():
        return f"event_type '{event}'"
    wanted = completion_tags()
    for tag in tags or []:
        norm = str(tag).strip().lower().lstrip("#")
        if norm.startswith("status:"):
            norm = norm[len("status:"):]
        if norm in wanted:
            return f"tag '{tag}'"
    if os.getenv("NOUGEN_POE_TEXT_DETECT") == "1":
        for where, text in (("title", title or ""), ("content", (content or "")[:_TEXT_SCAN_CHARS])):
            for pattern in _SUCCESS_PATTERNS:
                if pattern.search(text):
                    return f"{where} matches {pattern.pattern!r}"
    return None


def is_completion_claim(tags: Optional[List[str]], event_type: str = "",
                        title: str = "", content: str = "") -> bool:
    return claim_reason(tags, event_type, title, content) is not None


def _parse_block(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None
    parsed: Dict[str, Any] = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            parsed[key.strip().lower()] = value.strip()
    return parsed or None


def extract_evidence(content: str) -> Optional[Dict[str, Any]]:
    """Evidence dict from a fenced poe/scoreboard/evidence block, if any."""
    match = _EVIDENCE_FENCE.search(content or "")
    return _parse_block(match.group(1)) if match else None


# Kept for callers of the original name.
extract_poe = extract_evidence


def _scoreboard_errors(block: Mapping[str, Any]) -> List[str]:
    inner = block.get("test_evidence") if isinstance(block.get("test_evidence"), Mapping) else block
    command = inner.get("command") or inner.get("runner")
    exit_code = inner.get("exit_code")
    output = (inner.get("stdout") or inner.get("output")
              or inner.get("stdout_hash") or inner.get("stdout_digest"))
    errors = []
    if not str(command or "").strip():
        errors.append("scoreboard evidence needs a non-empty command")
    try:
        if exit_code is None or int(exit_code) != 0:
            errors.append(f"scoreboard evidence needs exit_code 0, got {exit_code!r}")
    except (TypeError, ValueError):
        errors.append(f"scoreboard evidence has a non-integer exit_code {exit_code!r}")
    if not str(output or "").strip():
        errors.append("scoreboard evidence needs non-empty output or output hash")
    return errors


def evidence_errors(block: Optional[Mapping[str, Any]],
                    workspace_root: Optional[Path] = None) -> List[str]:
    """[] when the block proves the claim; otherwise the reasons it does not."""
    if not block:
        return ["completion claim has no evidence (pass poe=/evidence= or a "
                "```poe / ```scoreboard fenced block)"]
    if isinstance(block.get("git"), Mapping):
        _ok, errors = PoEValidator.validate_poe_block(dict(block), workspace_root)
        return errors
    return _scoreboard_errors(block)


def check(tags: Optional[List[str]], content: str,
          poe: Optional[Mapping[str, Any]] = None,
          workspace_root: Optional[Path] = None,
          event_type: str = "", title: str = "") -> Tuple[bool, List[str]]:
    """(allowed, reasons). Non-claims and mode=off always pass."""
    mode = gate_mode()
    if mode == "off":
        return True, []
    reason = claim_reason(tags, event_type, title, content)
    if reason is None:
        return True, []
    block = dict(poe) if poe is not None else extract_evidence(content)
    errors = evidence_errors(block, workspace_root)
    if not errors:
        return True, []
    errors = [f"completion claim ({reason}) rejected"] + errors
    if mode == "warn":
        logger.warning("poe_gate (warn): %s", "; ".join(errors))
        return True, errors
    return False, errors
