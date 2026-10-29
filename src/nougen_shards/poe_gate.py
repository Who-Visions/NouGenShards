"""Write-time Proof-of-Execution gate for completion claims (Truth Anchor layer 4).

A shard tagged as a completion claim ("fixed", "resolved", "verified", ...) is
durable memory that later sessions trust. Prompt rules ask agents not to claim
success without evidence; this gate enforces it at the write: a completion-
tagged shard must carry a PoE block that `PoEValidator.validate_poe_block`
accepts (real commit, passing test run, observer attestation).

Untagged shards are untouched, so ordinary notes, relay mirrors and migrations
keep writing as before. Mode comes from NOUGEN_POE_GATE: enforce (default),
warn, or off.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .poe_validator import PoEValidator

logger = logging.getLogger(__name__)

_DEFAULT_COMPLETION_TAGS = "completed,resolved,fixed,verified,done"
_POE_FENCE = re.compile(r"```poe\s*\n(.*?)\n```", re.DOTALL)


def gate_mode() -> str:
    mode = os.getenv("NOUGEN_POE_GATE", "enforce").strip().lower()
    if mode not in {"enforce", "warn", "off"}:
        logger.warning("poe_gate: unknown NOUGEN_POE_GATE=%r; using enforce", mode)
        return "enforce"
    return mode


def completion_tags() -> set:
    raw = os.getenv("NOUGEN_POE_COMPLETION_TAGS", _DEFAULT_COMPLETION_TAGS)
    return {t.strip().lower() for t in raw.split(",") if t.strip()}


def is_completion_claim(tags: Optional[List[str]]) -> bool:
    wanted = completion_tags()
    for tag in tags or []:
        norm = str(tag).strip().lower()
        if norm.startswith("status:"):
            norm = norm[len("status:"):]
        if norm in wanted:
            return True
    return False


def extract_poe(content: str) -> Optional[Dict[str, Any]]:
    """The PoE dict from a fenced ```poe JSON block in the shard body, if any."""
    match = _POE_FENCE.search(content or "")
    if not match:
        return None
    try:
        poe = json.loads(match.group(1))
    except ValueError:
        return None
    return poe if isinstance(poe, dict) else None


def check(tags: Optional[List[str]], content: str,
          poe: Optional[Dict[str, Any]] = None,
          workspace_root: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """(allowed, reasons). Non-completion shards and mode=off always pass."""
    mode = gate_mode()
    if mode == "off" or not is_completion_claim(tags):
        return True, []
    block = poe if poe is not None else extract_poe(content)
    if block is None:
        errors = ["completion-tagged shard has no PoE block (pass poe= or a ```poe JSON fence)"]
    else:
        _ok, errors = PoEValidator.validate_poe_block(block, workspace_root)
    if not errors:
        return True, []
    if mode == "warn":
        logger.warning("poe_gate (warn): unproven completion claim: %s", "; ".join(errors))
        return True, errors
    return False, errors
