"""Memory consolidation: decide what a NEW fact does to the shards it neighbours.

Valerion port of Mem0's update phase (ADD / UPDATE / DELETE / NONE), changed
where NouGen's invariants differ:

* No DELETE. Shards are append-only history, so Mem0's UPDATE/DELETE become
  SUPERSEDE: the new shard carries ``supersedes`` and the old one stays.
* A model only PROPOSES. Code verifies the proposal (target must be one of the
  retrieved neighbours) and applies the guards below, so a 2B model that
  rubber-stamps "ADD" cannot silently leave a retracted fact standing.
* Locked/canon neighbours are never superseded by a lower-authority fact: the
  result is CONFLICT and the GM rules (canon_pressure quarantine rule: density
  and models never pick between locked sources).

Regression this exists for (Mem0 demo): "I had pizza, I like pasta now" was
extracted as a plain ADD and "likes pizza" stayed live. ``RETRACTION_CUE``
catches that in code, whatever the model says.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List

ACTIONS = ("ADD", "SUPERSEDE", "NONE", "CONFLICT", "REVIEW")
LOCKED_STATUSES = {"locked", "corrected", "canon"}

RETRACTION_CUE = re.compile(
    r"\b(no longer|not anymore|any ?more|don'?t (?:like|want|use|love)\w*|doesn'?t (?:like|want)|"
    r"instead of|rather than|switched to|changed (?:my|his|her|their) mind|used to|"
    r"now (?:i|he|she|they|we)\b|actually|correction)\b|\bis not\b|\bnot\b.*\bnow\b", re.I)

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["ADD", "SUPERSEDE", "NONE"]},
        "target_id": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["action", "target_id", "reason"],
}

Decider = Callable[[str, List[Dict[str, Any]]], Dict[str, Any]]


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(t) > 3}


def _overlap(a: str, b: str) -> int:
    return len(_tokens(a) & _tokens(b))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def build_prompt(new_fact: str, neighbours: List[Dict[str, Any]]) -> str:
    lines = [f'- id={n["id"]}: {n["text"]}' for n in neighbours]
    return (
        "You maintain a fact store. Existing facts:\n" + "\n".join(lines or ["- (none)"]) +
        f'\n\nNew fact: "{new_fact}"\n'
        "Decide: NONE if an existing fact already says this; SUPERSEDE (target_id = the existing "
        "fact it replaces or contradicts) if the new fact retracts or updates it; else ADD. "
        "Preferences that reverse (likes X -> likes Y instead) are SUPERSEDE of the X fact. "
        "Answer JSON only."
    )


def ollama_decider(model: str = "gemma4:e2b-qat", host: str = "http://127.0.0.1:11434",
                   timeout: float = 60.0) -> Decider:
    """Local-lane decider (Rule 0.7): OpenAI-compatible path, schema-constrained,
    max_tokens >= 1400 because E-series reasoning eats the budget first."""
    import urllib.request

    def decide(new_fact: str, neighbours: List[Dict[str, Any]]) -> Dict[str, Any]:
        body = {"model": model, "temperature": 0, "seed": 7, "max_tokens": 2048,
                "messages": [{"role": "user", "content": build_prompt(new_fact, neighbours)}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "decision", "schema": DECISION_SCHEMA}}}
        req = urllib.request.Request(host + "/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        raw = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        return json.loads(raw["choices"][0]["message"]["content"])
    return decide


def consolidate(new_fact: str, neighbours: List[Dict[str, Any]], decide: Decider,
                new_status: str = "candidate") -> Dict[str, Any]:
    """neighbours: [{"id", "text", "status"?}] nearest existing shards (caller retrieves).

    Returns {"action", "supersedes", "reason", "guards"}; ``supersedes`` is the
    marker to stamp on the new shard (never a deletion)."""
    ids = {str(n["id"]): n for n in neighbours}
    guards: List[str] = []
    try:
        d = decide(new_fact, neighbours) or {}
    except Exception as exc:  # a dead decider must not lose the fact
        d, guards = {"action": "ADD", "target_id": None, "reason": f"decider failed: {exc}"}, ["decider_failed"]
    action = d.get("action") if d.get("action") in ("ADD", "SUPERSEDE", "NONE") else "ADD"
    target = str(d["target_id"]) if d.get("target_id") is not None else None
    reason = str(d.get("reason", ""))

    if action == "SUPERSEDE" and target in ids and _jaccard(new_fact, ids[target]["text"]) >= 0.8             and not RETRACTION_CUE.search(new_fact):
        guards.append("supersede_of_identical_fact")      # a restatement is a duplicate, not an update
        action, target = "NONE", None
    if action == "SUPERSEDE" and target not in ids:        # hallucinated id
        guards.append("target_not_in_neighbours")
        action, target = "REVIEW", None
    if action == "NONE" and RETRACTION_CUE.search(new_fact):
        guards.append("none_despite_retraction_cue")       # "no longer X" is not a duplicate
        action = "REVIEW"

    if action == "ADD" and RETRACTION_CUE.search(new_fact):
        hit = max(neighbours, key=lambda n: _overlap(new_fact, n["text"]), default=None)
        if hit is not None and _overlap(new_fact, hit["text"]) >= 1:
            guards.append("add_despite_retraction_cue")    # the pizza/pasta case
            action, target = "SUPERSEDE", str(hit["id"])
            reason = f"retraction cue overlaps {hit['id']}; model said ADD"

    if action == "SUPERSEDE":
        old_locked = str(ids[target].get("status", "")).lower() in LOCKED_STATUSES
        if old_locked and new_status.lower() not in LOCKED_STATUSES:
            guards.append("locked_target")
            return {"action": "CONFLICT", "supersedes": None, "target": target,
                    "reason": "locked/canon neighbour vs lower-authority fact: GM rules", "guards": guards}
        return {"action": "SUPERSEDE", "supersedes": target, "as_of_ms": int(time.time() * 1000),
                "reason": reason, "guards": guards}
    return {"action": action, "supersedes": None, "reason": reason, "guards": guards}


# --------------------------------------------------------------------------- #
# capture wiring
# --------------------------------------------------------------------------- #
MAX_FACT_CHARS = 4000          # bigger bodies are documents, not facts; never consolidated
_LOCK_TAGS = {"canon-lock", "locked", "canon"}


def enabled(flag: "bool | None" = None) -> bool:
    """Opt-in: explicit argument wins, else NOUGEN_CONSOLIDATE=1."""
    import os
    if flag is not None:
        return bool(flag)
    return os.environ.get("NOUGEN_CONSOLIDATE", "").strip() in ("1", "true", "yes")


def _status_from_tags(tags: List[str]) -> str:
    return "locked" if any(str(t).lower() in _LOCK_TAGS for t in (tags or [])) else "candidate"


def neighbours_from_hits(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for h in hits or []:
        tags = h.get("tags") or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except ValueError:
                tags = []
        text = f'{h.get("title", "")}: {str(h.get("content", ""))[:400]}'
        out.append({"id": f'{h.get("id")}@db{h.get("_db_index")}', "text": text,
                    "status": _status_from_tags(tags)})
    return out


def consolidation_tags(title: str, content: str, tags: List[str], retrieve_fn: Callable[..., list],
                       decide: "Decider | None" = None, limit: int = 5) -> List[str]:
    """Extra tags for a capture about to be written. NEVER raises and never blocks:
    any failure returns [] and the shard is written exactly as before.

    SUPERSEDE -> ``supersedes:<id@dbN>``; CONFLICT/REVIEW -> ``consolidate:<action>`` and
    ``consolidate-target:<id>``; ADD/NONE add nothing (exact duplicates are already dropped by
    capture's content hash). The write still happens in every case (append-only history); the tags are what recall/bridges key on."""
    try:
        if len(content or "") > MAX_FACT_CHARS:
            return []
        hits = retrieve_fn(f"{title} {(content or '')[:300]}", limit=limit)
        nb = neighbours_from_hits(hits)
        if not nb:
            return []
        res = consolidate(f"{title}: {content}", nb, decide or ollama_decider(timeout=10.0),
                          new_status=_status_from_tags(tags))
    except Exception:  # pylint: disable=broad-except
        return []
    act = res["action"]
    if act == "SUPERSEDE":
        return [f'supersedes:{res["supersedes"]}']
    if act in ("CONFLICT", "REVIEW"):
        extra = [f"consolidate:{act.lower()}"]
        if res.get("target"):
            extra.append(f'consolidate-target:{res["target"]}')
        return extra
    return []
