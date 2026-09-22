"""xoah_science_sandbox (tool 10), engine side: test a speculative Veil claim
against real science BEFORE it can be promoted toward canon.

Lore-free: the ledgers (real-science facts, provisional canon rulings,
exclusion rules) load at runtime from a private path (``NOUGEN_XOAH_SCIENCE``,
default ~/.nougen/canon/science_ledger.json). Verdict names match blade's
lore-side ``science_sandbox.py`` so receipts from either side interoperate.

Deterministic token overlap only -- no model call -- and it never mutates
canon. A match is evidence of RELEVANCE, not proof: the receipt shows the
matched tokens so a reader can see exactly why a fact was pulled in.

Fact labels (the REALITY axis of blade's legend, drafts/
DRAFT_sun_backlore_veil_science.md lines 6-33) map to layers through the
LEDGER's own ``labels`` map; the built-in default reproduces that legend:

  R   established science              -> real          (supports a claim)
  H   historical record                -> historical    (partial: the event, not its reading)
  E   plausible extrapolation from R   -> extrapolation (partial: must show the step)
  R~  real but contested/preliminary   -> contested
  E-  speculative, color only          -> speculative   (NEVER load-bearing)

Joined labels ("R/R~", "R/H") take their WEAKEST part: a fact that is
partly contested cannot support a claim as if it were settled. Every receipt
names the map it used (``label_map_source``).
"""
from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .types import CanonPacket, Provenance, ToolReceipt, receipt

# Blade's six verdicts, plus two this engine adds (review of #483):
#   CONTRADICTS_REAL_SCIENCE -- a matched fact's own contradiction pattern fired
#   CANNOT_EVALUATE          -- empty ledger or contentless claim: unmeasured,
#                               which must never read as "no match"
VERDICTS = ("CANNOT_EVALUATE", "EXCLUDED_O1", "CONTRADICTS_REAL_SCIENCE",
            "CONFLICTS_WITH_CANON_RULING", "SUPPORTED_BY_REAL_SCIENCE",
            "PARTIAL_MATCH_ONLY", "CONTESTED_ONLY", "NO_REAL_SCIENCE_MATCH")
# strongest first; a joined label resolves to the weakest (highest index) part
LAYERS = ("real", "historical", "extrapolation", "contested", "speculative")
DEFAULT_LABELS = {"R": "real", "H": "historical", "E": "extrapolation", "R~": "contested",
                  "E-": "speculative"}
DEFAULT_SOURCE = "default:blade_legend(DRAFT_sun_backlore_veil_science.md:6-33)"
MIN_OVERLAP = 2        # a fact is RELEVANT when it shares >= 2 content words with the claim
SUPPORT_COVERAGE = 0.5  # ...but SUPPORTS it only if the claim covers >= half the fact's words
_STOP = frozenset(
    "the and are was were for but not you she her his him has had its our out who how why "
    "all any can did get got one two may yes use that this with from have been they them "
    "their there what when where which will would could should about into over under after "
    "before while than then also very only just more most some such like does onto is it".split())


def content_words(text: str) -> frozenset:
    """Lower-case words of 3+ letters, possessives stripped ("sun's" -> "sun"),
    stopwords removed. 3-letter words matter here: sun, gas, ion, ice."""
    out = set()
    for w in re.findall(r"[a-z0-9][a-z0-9'-]*", (text or "").lower()):
        w = re.sub(r"'s?$", "", w)
        if len(w) >= 3 and w not in _STOP:
            out.add(w)
    return frozenset(out)


@dataclass(frozen=True)
class Fact:
    id: str
    statement: str
    label: str                      # R | R~ | H | E | E- (joinable: R/R~)
    keywords: Tuple[str, ...] = ()  # optional extra match terms
    provenance: Tuple[Provenance, ...] = ()
    contradicts: Tuple[str, ...] = ()  # regexes a claim matching this fact must NOT say

    def words(self) -> frozenset:
        return content_words(self.statement) | {k.lower() for k in self.keywords}


@dataclass(frozen=True)
class Ruling:
    """A provisional canon ruling about how the fiction treats a science topic."""
    id: str
    statement: str
    topics: Tuple[str, ...]
    contradicts: Tuple[str, ...] = ()
    provenance: Tuple[Provenance, ...] = ()


@dataclass(frozen=True)
class Exclusion:
    """Blade's O1 rule set: claim shapes the sandbox refuses to evaluate."""
    id: str
    pattern: str
    reason: str
    provenance: Tuple[Provenance, ...] = ()


@dataclass(frozen=True)
class ScienceLedger:
    revision: str
    facts: Tuple[Fact, ...] = ()
    rulings: Tuple[Ruling, ...] = ()
    exclusions: Tuple[Exclusion, ...] = ()
    labels: Mapping[str, str] = None  # label -> layer; None means DEFAULT_LABELS

    def label_map(self) -> Tuple[Mapping[str, str], str]:
        return (self.labels, "ledger") if self.labels else (DEFAULT_LABELS, DEFAULT_SOURCE)


# --------------------------------------------------------------------------- loading
def _prov(items) -> Tuple[Provenance, ...]:
    return tuple(Provenance(p.get("shard_id"), p["db"], p["node"], p["phrase"]) for p in items or ())


def _need(obj: Dict[str, Any], what: str) -> Tuple[Provenance, ...]:
    prov = _prov(obj.get("provenance"))
    if not prov:
        raise ValueError(f"{what} {obj.get('id')!r} has no provenance")
    return prov


def _parts(label: str):
    return [p.strip().strip("[]").upper() for p in str(label or "").split("/") if p.strip()]


def _label(raw: Any, labels: Mapping[str, str]) -> str:
    parts = _parts(raw)
    bad = [p for p in parts if p not in labels]
    if not parts or bad:
        raise ValueError(f"unknown fact label {raw!r}; expected one of {sorted(labels)} (joinable with '/')")
    return "/".join(parts)


def layer_of(label: str, labels: Mapping[str, str]) -> str:
    """Weakest part wins: 'R/R~' is contested, 'R/H' is historical."""
    return max((labels[p] for p in _parts(label)), key=LAYERS.index)


def _label_map(raw: Optional[Mapping[str, str]]) -> Optional[Dict[str, str]]:
    if not raw:
        return None
    out = {str(k).strip().upper(): str(v).strip().lower() for k, v in raw.items()}
    bad = sorted(v for v in out.values() if v not in LAYERS)
    if bad:
        raise ValueError(f"label map points at unknown layer(s) {bad}; layers are {LAYERS}")
    return out


def ledger_from_dict(d: Dict[str, Any]) -> ScienceLedger:
    labels = _label_map(d.get("labels"))
    lm = labels or DEFAULT_LABELS
    return ScienceLedger(
        revision=str(d["revision"]),
        labels=labels,
        facts=tuple(Fact(f["id"], f["statement"], _label(f.get("label"), lm),
                         tuple(f.get("keywords", ())), _need(f, "fact"),
                         tuple(f.get("contradicts", ())))
                    for f in d.get("facts", ())),
        rulings=tuple(Ruling(r["id"], r["statement"], tuple(r.get("topics", ())),
                             tuple(r.get("contradicts", ())), _need(r, "ruling"))
                      for r in d.get("rulings", ())),
        exclusions=tuple(Exclusion(e["id"], e["pattern"], e.get("reason", ""), _need(e, "exclusion"))
                         for e in d.get("exclusions", ())),
    )


def facts_from_csv(path: Path, node: str, db: str = "ledger",
                   labels: Optional[Mapping[str, str]] = None) -> Tuple[Fact, ...]:
    """Read a facts CSV. Needs columns id, statement (or fact/text), label (or tier);
    optional keywords (';'-separated). Provenance is the file row, cited by phrase."""
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            text = row.get("statement") or row.get("fact") or row.get("text") or ""
            kw = tuple(k.strip() for k in (row.get("keywords") or "").split(";") if k.strip())
            out.append(Fact(row.get("id") or f"row{n}", text,
                            _label(row.get("label") or row.get("tier"), _label_map(labels) or DEFAULT_LABELS),
                            kw, (Provenance(None, db, node, f"{Path(path).name}:{n} {text[:60]}"),)))
    return tuple(out)


def default_path() -> Path:
    return Path(os.environ.get("NOUGEN_XOAH_SCIENCE")
                or Path.home() / ".nougen" / "canon" / "science_ledger.json")


def load_ledger(path: Optional[Path] = None) -> ScienceLedger:
    p = Path(path) if path else default_path()
    return ledger_from_dict(json.loads(p.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- the tool
def _rx(pattern: str, text: str) -> bool:
    try:
        return bool(re.search(pattern, text, re.I))
    except re.error:
        return pattern.lower() in text.lower()


def _matches(facts: Iterable[Fact], claim_words: frozenset, claim: str) -> List[Dict[str, Any]]:
    rows = []
    for f in facts:
        fw = f.words()
        shared = sorted(fw & claim_words)
        if len(shared) >= MIN_OVERLAP:
            coverage = len(shared) / max(len(fw), 1)
            rows.append({"id": f.id, "label": f.label, "statement": f.statement,
                         "matched_tokens": shared, "coverage": round(coverage, 3),
                         "contradicted_by": [c for c in f.contradicts if _rx(c, claim)],
                         "sources": [p.cite() for p in f.provenance]})
    return sorted(rows, key=lambda r: (-len(r["matched_tokens"]), r["id"]))


def science_sandbox(ledger: ScienceLedger, claim: str, scene_context: Optional[str] = None,
                    packet: Optional[CanonPacket] = None) -> ToolReceipt:
    """Layer a claim: real science, extrapolation, contested, canon rulings,
    timeline rows. Precedence: excluded > conflicts-with-ruling > supported >
    partial > contested-only > no match. Never mutates canon."""
    text = claim if not scene_context else f"{claim}\n{scene_context}"
    words = content_words(text)
    inputs = {"claim": claim, "scene_context": scene_context, "ledger_revision": ledger.revision,
              "label_map_source": ledger.label_map()[1]}
    rev = packet or CanonPacket(revision=f"science:{ledger.revision}")

    if not ledger.facts and not ledger.rulings and not ledger.exclusions:
        return receipt("xoah_science_sandbox", rev, inputs, "CANNOT_EVALUATE",
                       [{"missing": "ledger", "detail": "empty science ledger: nothing was measured"}])
    if not content_words(claim):
        return receipt("xoah_science_sandbox", rev, inputs, "CANNOT_EVALUATE",
                       [{"missing": "claim_content", "detail": "claim has no content words to test"}])

    excluded = [e for e in ledger.exclusions if _rx(e.pattern, claim)]
    if excluded:
        return receipt("xoah_science_sandbox", rev, inputs, "EXCLUDED_O1",
                       [{"excluded_by": [{"id": e.id, "reason": e.reason} for e in excluded]}],
                       [p for e in excluded for p in e.provenance], ["ruling"])

    lmap, lmap_source = ledger.label_map()
    matched = _matches(ledger.facts, words, claim)
    layers = {name: [m for m in matched if layer_of(m["label"], lmap) == name] for name in LAYERS}
    low = text.lower()
    relevant_rulings = [r for r in ledger.rulings
                        if any((t.lower() in low) if " " in t else (t.lower() in words) for t in r.topics)]
    contradictions = [{"ruling": r.id, "because": r.statement,
                       "matched": [c for c in r.contradicts if _rx(c, claim)],
                       "sources": [p.cite() for p in r.provenance]}
                      for r in relevant_rulings if any(_rx(c, claim) for c in r.contradicts)]
    timeline_rows = []
    if packet is not None:
        for e in packet.timeline:
            shared = sorted(content_words(e.statement) & words)
            if len(shared) >= MIN_OVERLAP:
                timeline_rows.append({"fact_id": e.fact_id, "route": e.route, "order": e.order,
                                      "matched_tokens": shared})

    science_contradictions = [m for m in matched
                              if m["contradicted_by"] and layer_of(m["label"], lmap) != "speculative"]
    supporting = [m for m in layers["real"] if m["coverage"] >= SUPPORT_COVERAGE]
    if science_contradictions:
        verdict = "CONTRADICTS_REAL_SCIENCE"
    elif contradictions:
        verdict = "CONFLICTS_WITH_CANON_RULING"
    elif supporting:
        verdict = "SUPPORTED_BY_REAL_SCIENCE"
    elif layers["real"] or layers["historical"] or layers["extrapolation"]:
        # real facts that only brush the claim (low coverage) are partial, not support
        verdict = "PARTIAL_MATCH_ONLY"
    elif layers["contested"]:
        verdict = "CONTESTED_ONLY"
    else:
        verdict = "NO_REAL_SCIENCE_MATCH"  # speculative (E-) matches are shown, never load-bearing

    used = [f for f in ledger.facts if f.id in {m["id"] for m in matched}]
    findings = [{
        "layers": {**layers, "canon_rulings": [{"id": r.id, "statement": r.statement}
                                                 for r in relevant_rulings],
                   "timeline_rows": timeline_rows},
        "contradictions": contradictions,
        "science_contradictions": [{"fact": m["id"], "matched": m["contradicted_by"],
                                    "sources": m["sources"]} for m in science_contradictions],
        "support_basis": "topical overlap + coverage; a claim can only be refuted by a fact's own "
                         "contradiction patterns, so SUPPORTED means 'consistent with and about', "
                         "not 'proven by'",
        "claim_tokens": sorted(words),
        "fiction_layer": "whatever the claim asserts beyond the matched facts is fiction, not science",
        "min_overlap": MIN_OVERLAP,
        "label_map": dict(lmap), "label_map_source": lmap_source,
    }]
    sources = [p for f in used for p in f.provenance] + [p for r in relevant_rulings for p in r.provenance]
    kinds = ["fact:" + f.label for f in used] + ["ruling"] * bool(relevant_rulings)
    return receipt("xoah_science_sandbox", rev, inputs, verdict, findings, sources, kinds)
