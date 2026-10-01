"""Deterministic actionable/informational classification for NouGenMsg.

ACK != DONE only matters for messages that ask for work. A touchdown report or an
"online and listening" ping has nothing to execute, so it must be allowed to end at
ACKED, or the pending list fills with items no agent can ever complete.

The cost is asymmetric: a wrongly held message is noise a person clears; a wrongly
dropped one hides work. So the order below fails toward ACTIONABLE:

1. an explicit origin.kind from the sender wins;
2. a strong ask ("baton is yours", "please", "your turn", ...) is actionable, even
   inside an informational wrapper;
3. a strong informational marker ("no reply needed", "touchdown", "[auto]", ...)
   ends at ACKED;
4. weak ask words (fix, review, claim, ...) are actionable;
5. weak status facts ("is pushed", "is live", "merged") are informational;
6. anything else is actionable, with the reason "unclassified".

No model is involved: the same text always classifies the same way, and the reason
code says which rule fired.
"""
import re
from dataclasses import dataclass
from typing import Any

INFORMATIONAL_KINDS = frozenset({"info", "informational", "status", "receipt"})
ACTIONABLE_KINDS = frozenset({"task", "ask", "request", "dispatch", "baton", "action", "order"})

_STRONG_ASK = re.compile(
    r"baton is yours|\byour turn\b|\bplease\b|\bcan you\b|\bcould you\b|\bneeds? you to\b|"
    r"\bto[- ]?do:|\bTODO\b|\bask:|\bdone[- ]when\b|\bdo not (?:merge|touch|redo)\b",
    re.IGNORECASE)

_STRONG_INFO = re.compile(
    r"no (?:acknowledg\w+|repl(?:y|ies)|response|action)(?: or [\w ]+?)?(?: is| are)? (?:requested|needed|required)|"
    r"\binformational(?: update| only)?\b|\bfyi\b|\btouchdown\b|\bstatus (?:update|report)\b|"
    r"\bonline and listening\b|^\s*\[auto\]|\bsealed\b|\bbeacon radar\b|\bround robin closed\b|"
    r"^\s*\[lifecycle watchdog\]",   # a nudge points at the real obligation; it is not one itself
    re.IGNORECASE)

_WEAK_ASK = re.compile(
    r"\b(?:fix|implement|build|review|verify|claim|execute|merge|investigate|deploy|rebase|"
    r"ensure|make sure|check|update|add|remove|write|run)\b",
    re.IGNORECASE)

_WEAK_INFO = re.compile(
    r"\b(?:is|are|was|were|has been|have been) (?:now )?(?:live|merged|pushed|deployed|landed|green|"
    r"complete|done|open|closed)\b|\blanded\b|\bmerged at\b",
    re.IGNORECASE)


_IDENTIFIERS = re.compile(r"https?://\S+|`[^`]*`|\S*[/\\]\S*")


@dataclass(frozen=True)
class Classification:
    actionable: bool
    reason: str


def classify(text: Any, origin: Any = None) -> Classification:
    """Classify one message. Never raises; ambiguity is actionable."""
    kind = ""
    if isinstance(origin, dict):
        kind = str(origin.get("kind") or "").strip().lower()
    if kind in INFORMATIONAL_KINDS:
        return Classification(False, f"origin.kind={kind}")
    if kind in ACTIONABLE_KINDS:
        return Classification(True, f"origin.kind={kind}")

    body = text.strip() if isinstance(text, str) else ""
    if not body:
        return Classification(True, "unclassified: empty text, treated as actionable")
    if _STRONG_ASK.search(body):
        return Classification(True, "ask-language")
    if _STRONG_INFO.search(body):
        return Classification(False, "informational marker")
    # Weak rules look at prose only: "fix" inside a branch name, URL or code span is not an ask.
    prose = _IDENTIFIERS.sub(" ", body)
    if _WEAK_ASK.search(prose):
        return Classification(True, "ask-verb")
    if _WEAK_INFO.search(prose):
        return Classification(False, "status fact")
    return Classification(True, "unclassified: treated as actionable so work is never hidden")
