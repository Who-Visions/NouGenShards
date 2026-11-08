"""
DavOs's own identity resolver - "names are state, not vibes."

DavOs (the NouGenAI app's assistant) asked for Zero Ambiguity: no more
mix-ups between names that sound alike. This module is his canonical
"who is who" for the fleet, and the backing for the `persona_resolve` tool.

Three tiers, cheapest and most certain first (Rule 0.2: discover, don't
assume; nothing operator- or lore-shaped is hardcoded in the public repo):

  1. BUILT-IN  - derived at runtime from the fleet's own identity sources
                 (nougenmsg.fleet_identity_maps(), the current node), plus
                 the NouGen agent/product lanes the playbook already names.
  2. REGISTRY  - a private JSON file (NOUGEN_PERSONA_REGISTRY, default
                 ~/.nougen/persona_registry.json). This is where private
                 characters and personas live - never this repo.
  3. VAULT     - shard titles matching the name, so DavOs can cite real
                 records instead of guessing when 1 and 2 are silent.

resolve() never invents a match: a fuzzy hit is labelled fuzzy, and no hit
is labelled none with a ready-made "I'm not certain who X is" sentence.
"""
from __future__ import annotations

import difflib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SELF_NAMES = {"davos", "dav os", "me", "you", "yourself", "nougenai assistant"}
FUZZY_CUTOFF = 0.8


@dataclass(frozen=True)
class Identity:
    canonical: str
    kind: str                       # agent | node | person | persona | model | project
    aliases: Tuple[str, ...] = ()
    role: str = ""
    home: str = ""                  # machine / lane / where it lives
    source: str = "builtin"         # builtin | registry | vault

    def names(self) -> Tuple[str, ...]:
        return (self.canonical,) + self.aliases


def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().replace("_", " ").replace("-", " ").split())


def self_identity() -> Identity:
    """DavOs's own card. Lane comes from env so it reads true on any node."""
    return Identity(
        canonical="DavOs",
        kind="agent",
        aliases=("davos", "nougenai assistant", "the app"),
        role="NouGenAI's assistant - the operator's working style embodied: local-first, "
             "evidence over memory, verified state over assumption; holds the mutation gates.",
        # No operator host in shipped code (public repo); the real lane name is env-supplied.
        home=os.environ.get("NOUGEN_DAVOS_LANE", "the NouGenAI app lane (Worker -> node bridge)"),
        source="builtin",
    )


def builtin_identities() -> List[Identity]:
    """Fleet identities discovered at call time, not memorised."""
    out: List[Identity] = [self_identity()]

    # Machines and the coach lane that drives each one, from the live map.
    try:
        from .nougenmsg import fleet_identity_maps, get_current_node
        machine_to_coach, coach_to_machine = fleet_identity_maps()
        current = get_current_node()
        for machine, coach in sorted(machine_to_coach.items()):
            out.append(Identity(
                canonical=machine, kind="node",
                aliases=tuple(a for a in (coach,) if a and a != machine),
                role="fleet node" + (" (this node)" if machine == current else ""),
                home=f"coach lane: {coach}" if coach else "",
            ))
        for coach, machine in sorted(coach_to_machine.items()):
            if coach and coach not in machine_to_coach:
                out.append(Identity(canonical=coach, kind="agent", role="coach lane", home=f"drives {machine}"))
    except Exception as exc:  # pylint: disable=broad-except
        logger.info("fleet identity map unavailable (%s); built-ins limited to self + lanes", exc)

    # Agent/product lanes the playbook itself names (Rule 0.4 custom fleet
    # models and the NouGen agent roster). These are product names, not lore.
    for canonical, kind, role, aliases in (
        ("Kaedra", "agent", "autonomous agent lane (kaedra_tools, tool-calling)", ("kaedra ai",)),
        ("dav1d", "model", "custom fleet model, e2b", ("david",)),
        ("Sol-Ai", "model", "the Player - local gemma4 fleet model", ("sol ai", "solai", "sol")),
        ("Iris-Ai", "model", "custom fleet model, e4b", ("iris", "iris ai")),
        ("Rhea-Noir", "model", "custom fleet model, e2b", ("rhea", "rhea noir")),
        ("Griot", "model", "custom fleet model, e2b", ()),
        ("Mrs. B", "persona", "Learn With Mrs. B publishing project persona", ("mrs b", "mrsb")),
        ("Apollo", "agent", "the Coach - designated coding agent (Claude Code)", ("coach",)),
        ("Antigravity", "agent", "Google Antigravity IDE lane", ("agy",)),
        ("Codex", "agent", "OpenAI Codex CLI lane", ()),
    ):
        out.append(Identity(canonical=canonical, kind=kind, aliases=aliases, role=role))
    return out


def registry_path() -> Path:
    return Path(os.environ.get("NOUGEN_PERSONA_REGISTRY") or (Path.home() / ".nougen" / "persona_registry.json"))


def registry_identities(path: Optional[Path] = None) -> List[Identity]:
    """Private entries. Shape: [{"canonical": "...", "kind": "persona", "aliases": [...], "role": "...", "home": "..."}]"""
    p = path or registry_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("persona registry %s unreadable: %s", p, exc)
        return []
    entries = raw.get("identities", raw) if isinstance(raw, dict) else raw
    out: List[Identity] = []
    for e in entries or []:
        if not isinstance(e, dict) or not e.get("canonical"):
            continue
        out.append(Identity(
            canonical=str(e["canonical"]), kind=str(e.get("kind", "persona")),
            aliases=tuple(str(a) for a in e.get("aliases", []) or []),
            role=str(e.get("role", "")), home=str(e.get("home", "")), source="registry",
        ))
    return out


def all_identities(path: Optional[Path] = None) -> List[Identity]:
    # Registry entries override built-ins with the same canonical name.
    merged: Dict[str, Identity] = {_norm(i.canonical): i for i in builtin_identities()}
    for i in registry_identities(path):
        merged[_norm(i.canonical)] = i
    return list(merged.values())


def _vault_hits(name: str, limit: int = 3) -> List[Dict[str, Any]]:
    try:
        from . import core
        hits = core._title_retrieve(query=name, limit=limit, domain_key=None, include_research=False)  # pylint: disable=protected-access
        return [{"title": h.get("title"), "id": h.get("id"), "db_index": h.get("db_index", h.get("_db_index"))}
                for h in (hits or []) if isinstance(h, dict) and h.get("title")]
    except Exception as exc:  # pylint: disable=broad-except
        logger.info("vault tier unavailable for %r: %s", name, exc)
        return []


def resolve(name: str, *, vault_fallback: bool = True, registry: Optional[Path] = None) -> Dict[str, Any]:
    """Who/what is `name`? Returns a dict DavOs can answer from and cite."""
    query = str(name or "").strip()
    q = _norm(query)
    if not q:
        return {"query": query, "confidence": "none", "match": None, "candidates": [],
                "disambiguation": "No name given."}
    if q in SELF_NAMES:
        return {"query": query, "confidence": "exact", "match": asdict(self_identity()), "candidates": [],
                "disambiguation": ""}

    ids = all_identities(registry)
    by_name: Dict[str, Identity] = {}
    for i in ids:
        for n in i.names():
            by_name.setdefault(_norm(n), i)

    if q in by_name:
        i = by_name[q]
        conf = "exact" if _norm(i.canonical) == q else "alias"
        return {"query": query, "confidence": conf, "match": asdict(i), "candidates": [], "disambiguation": ""}

    close = difflib.get_close_matches(q, list(by_name.keys()), n=3, cutoff=FUZZY_CUTOFF)
    candidates = []
    seen = set()
    for c in close:
        i = by_name[c]
        if i.canonical in seen:
            continue
        seen.add(i.canonical)
        candidates.append(asdict(i))

    vault = _vault_hits(query) if vault_fallback else []

    if len(candidates) == 1 and not vault:
        return {"query": query, "confidence": "fuzzy", "match": candidates[0], "candidates": candidates,
                "disambiguation": f"'{query}' is not an exact name here; closest known is '{candidates[0]['canonical']}' - confirm before relying on it."}
    if candidates or vault:
        names = ", ".join(c["canonical"] for c in candidates) or "no close fleet names"
        return {"query": query, "confidence": "ambiguous", "match": None, "candidates": candidates, "vault_hits": vault,
                "disambiguation": f"I'm not certain who/what '{query}' is. Close fleet names: {names}. "
                                  f"Vault records mentioning it: {len(vault)}. Ask, or check those records, before naming anyone."}
    return {"query": query, "confidence": "none", "match": None, "candidates": [], "vault_hits": [],
            "disambiguation": f"I'm not certain who/what '{query}' is - nothing in the fleet roster, private registry, or vault matches. Don't guess."}
