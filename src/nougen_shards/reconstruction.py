"""Reconstructive recall prototype: bounded retrieval-angle sweep + envelope.

Process donor: the "retrieval angle" and "partial plate" ideas from popular
accounts of distributed-memory models, used ONLY as an engineering metaphor. Nothing here stores interference patterns or claims any physical,
quantum or paranormal mechanism. It is query reformulation, one-hop association
expansion, multi-feature scoring and honest coverage accounting.

Status: PROTOTYPE. Not wired into ``recall_memory`` / ``federated_retrieve``.
Sources are injected (see :class:`EvidenceSource`), so tests run against a
synthetic fixture vault and never open the live grid.

Every tunable resolves env -> fallback, and the fallback is logged once.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Config (env -> logged fallback)
# --------------------------------------------------------------------------

_DEFAULT_ANGLES = "verbatim,keyword,alias,time_window,association,relay"
_DEFAULT_WEIGHTS = {"lexical": 0.45, "entity": 0.30, "temporal": 0.15, "state": 0.10, "kind": 0.10}
_STATE_FACTOR = {"live": 1.0, "superseded": 0.3, "retracted": 0.0}
_logged_fallbacks: set = set()


def _env_num(name: str, fallback: float, cast=float):
    raw = os.environ.get(name, "").strip()
    if raw:
        try:
            return cast(raw)
        except ValueError:
            log.warning("reconstruction: bad %s=%r, using fallback %r", name, raw, fallback)
    elif name not in _logged_fallbacks:
        _logged_fallbacks.add(name)
        log.info("reconstruction: %s unset, fallback %r", name, fallback)
    return fallback


@dataclass
class SweepConfig:
    angles: List[str]
    max_calls: int
    max_ms: float
    confidence_target: float
    accept_threshold: float
    rival_margin: float
    patience: int
    per_call_limit: int
    weights: Dict[str, float]

    @classmethod
    def from_env(cls) -> "SweepConfig":
        angles_raw = os.environ.get("NOUGEN_RECON_ANGLES", "").strip() or _DEFAULT_ANGLES
        weights = dict(_DEFAULT_WEIGHTS)
        raw_w = os.environ.get("NOUGEN_RECON_WEIGHTS", "").strip()
        if raw_w:
            try:
                weights.update({k: float(v) for k, v in json.loads(raw_w).items()})
            except (ValueError, AttributeError):
                log.warning("reconstruction: bad NOUGEN_RECON_WEIGHTS, using fallback")
        return cls(
            angles=[a.strip() for a in angles_raw.split(",") if a.strip()],
            max_calls=_env_num("NOUGEN_RECON_MAX_CALLS", 18, int),
            max_ms=_env_num("NOUGEN_RECON_MAX_MS", 2000.0),
            confidence_target=_env_num("NOUGEN_RECON_CONFIDENCE_TARGET", 0.80),
            accept_threshold=_env_num("NOUGEN_RECON_ACCEPT", 0.55),
            rival_margin=_env_num("NOUGEN_RECON_MARGIN", 0.05),
            patience=_env_num("NOUGEN_RECON_PATIENCE", 2, int),
            per_call_limit=_env_num("NOUGEN_RECON_PER_CALL_LIMIT", 8, int),
            weights=weights,
        )


# --------------------------------------------------------------------------
# Source protocol
# --------------------------------------------------------------------------

class SourceUnavailable(RuntimeError):
    """A vault/lane did not answer. A hole in coverage, never an empty result."""


class EvidenceSource(Protocol):
    name: str

    def search(self, query: str, limit: int, *, mode: str = "all",
               kinds: Optional[Sequence[str]] = None,
               date_range: Optional[Tuple[str, str]] = None) -> List[dict]:
        """Return evidence dicts: key, title, body, entities, date, kind, state."""

    def neighbours(self, key: str) -> List[Tuple[str, str]]:
        """Return (neighbour_key, relation) edges touching ``key``."""

    def get(self, key: str) -> Optional[dict]:
        """Fetch one evidence dict by key, or None if this source does not hold it."""


# --------------------------------------------------------------------------
# Envelope schema
# --------------------------------------------------------------------------

@dataclass
class AngleRun:
    angle: str
    query: str
    calls: int
    new_candidates: int
    top_score_after: float
    elapsed_ms: float
    skipped_reason: Optional[str] = None


@dataclass
class Candidate:
    key: str
    vault: str
    title: str
    kind: str
    state: str
    score: float
    features: Dict[str, float]
    found_by: List[str] = field(default_factory=list)


@dataclass
class AssociationHop:
    from_key: str
    to_key: str
    relation: str
    vault: str


@dataclass
class Rejection:
    key: str
    reason: str
    score: float


@dataclass
class ReconstructionEnvelope:
    query: str
    query_fingerprint: Dict[str, object]
    retrieval_angles: List[AngleRun]
    candidate_sources: List[Candidate]
    association_hops: List[AssociationHop]
    vault_coverage: Dict[str, object]
    time_coverage: Dict[str, object]
    correction_state: Dict[str, str]
    confidence: float
    reconstruction_summary: str
    unresolved_gaps: List[str]
    # explainability extras (experiment F)
    answer_key: Optional[str] = None
    rival_key: Optional[str] = None
    rival_margin: float = 0.0
    rejected: List[Rejection] = field(default_factory=list)
    stop_reason: str = ""
    calls: int = 0
    elapsed_ms: float = 0.0
    absence_proven: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Query fingerprint
# --------------------------------------------------------------------------

_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or", "is", "was",
    "what", "when", "where", "who", "why", "how", "does", "did", "do", "its", "it",
    "about", "from", "that", "this", "now", "use", "uses", "went", "which", "with",
}
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1]


def _time_window(text: str) -> Optional[Tuple[str, str]]:
    low = text.lower()
    m = re.search(r"\b(20\d\d)-(\d\d)\b", low)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return f"{y:04d}-{mo:02d}-01", f"{y:04d}-{mo:02d}-31"
    year = re.search(r"\b(20\d\d)\b", low)
    for name, mo in _MONTHS.items():
        if re.search(rf"\b{name}\b", low) and year:
            y = int(year.group(1))
            return f"{y:04d}-{mo:02d}-01", f"{y:04d}-{mo:02d}-31"
    if year:
        y = int(year.group(1))
        return f"{y:04d}-01-01", f"{y:04d}-12-31"
    return None


def _apply_aliases(text: str, aliases: Dict[str, List[str]]) -> str:
    low = " " + text.lower() + " "
    for canonical, variants in aliases.items():
        for v in sorted(variants, key=len, reverse=True):
            low = re.sub(rf"(?<![a-z0-9]){re.escape(v.lower())}(?![a-z0-9])", canonical.lower(), low)
    return low.strip()


def fingerprint(query: str, aliases: Dict[str, List[str]], known_entities: Iterable[str]) -> dict:
    canon = _apply_aliases(query, aliases)
    ents = sorted({e for e in known_entities if re.search(rf"(?<![a-z0-9]){re.escape(e.lower())}(?![a-z0-9])", canon)})
    return {
        "tokens": _tokens(query),
        "canonical_tokens": _tokens(canon),
        "canonical_query": canon,
        "entities": ents,
        "time_window": _time_window(query),
        "relay_cue": bool(re.search(r"\b(handoff|relay|leg|instruction)\b", query.lower())),
        "sha": hashlib.sha256(query.encode("utf-8")).hexdigest()[:12],
    }


# --------------------------------------------------------------------------
# Recognition score (experiment E)
# --------------------------------------------------------------------------

def recognition_score(ev: dict, fp: dict, weights: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
    doc_tokens = set(_tokens(ev.get("title", "") + " " + ev.get("body", "")))
    q = set(fp["canonical_tokens"])
    lexical = len(q & doc_tokens) / len(q) if q else 0.0
    q_ents = set(fp["entities"])
    doc_ents = {e.lower() for e in ev.get("entities", [])}
    if q_ents:
        entity = len(q_ents & doc_ents) / len(q_ents)
    else:
        entity = 0.5  # no entity named: neutral, neither rewards nor punishes
    win = fp["time_window"]
    date = ev.get("date", "")
    if win is None or not date:
        temporal = 1.0
    else:
        temporal = 1.0 if win[0] <= date[:10] <= win[1] else 0.0
    state = _STATE_FACTOR.get(ev.get("state", "live"), 0.5)
    # Provenance-kind fit: a query that asks for a handoff should prefer the
    # relay leg over the shard the leg later produced (and the reverse).
    if fp.get("relay_cue"):
        kind = 1.0 if ev.get("kind") == "relay" else 0.0
    else:
        kind = 0.5
    feats = {"lexical": round(lexical, 4), "entity": round(entity, 4),
             "temporal": temporal, "state": state, "kind": kind}
    total_w = sum(weights.values()) or 1.0
    score = sum(weights.get(k, 0.0) * v for k, v in feats.items()) / total_w
    # A retracted row can be shown as provenance, but it can never win.
    if state == 0.0:
        score = min(score, 0.0)
    return round(score, 4), feats


# --------------------------------------------------------------------------
# Sweep
# --------------------------------------------------------------------------

class _Sweep:
    def __init__(self, query, sources, aliases, known_entities, cfg):
        self.query = query
        self.sources = list(sources)
        self.aliases = aliases or {}
        self.cfg = cfg
        self.fp = fingerprint(query, self.aliases, known_entities or [])
        self.cands: Dict[str, Candidate] = {}
        self.raw: Dict[str, dict] = {}
        self.failed: Dict[str, str] = {}
        self.calls = 0
        self.t0 = time.perf_counter()
        self.runs: List[AngleRun] = []
        self.hops: List[AssociationHop] = []

    # -- helpers ---------------------------------------------------------
    def _elapsed_ms(self):
        return (time.perf_counter() - self.t0) * 1000.0

    def _budget_left(self):
        return self.calls < self.cfg.max_calls and self._elapsed_ms() < self.cfg.max_ms

    def _live_sources(self):
        return [s for s in self.sources if s.name not in self.failed]

    def _add(self, ev: dict, vault: str, angle: str) -> bool:
        key = ev["key"]
        if key in self.cands:
            if angle not in self.cands[key].found_by:
                self.cands[key].found_by.append(angle)
            return False
        score, feats = recognition_score(ev, self.fp, self.cfg.weights)
        self.raw[key] = ev
        self.cands[key] = Candidate(key=key, vault=vault, title=ev.get("title", ""),
                                   kind=ev.get("kind", "shard"), state=ev.get("state", "live"),
                                   score=score, features=feats, found_by=[angle])
        return True

    def top(self) -> List[Candidate]:
        return sorted(self.cands.values(), key=lambda c: c.score, reverse=True)

    def _search_all(self, angle, q, **kw) -> int:
        new = 0
        for src in self._live_sources():
            if not self._budget_left():
                break
            self.calls += 1
            try:
                rows = src.search(q, self.cfg.per_call_limit, **kw)
            except SourceUnavailable as exc:
                self.failed[src.name] = str(exc) or "unavailable"
                continue
            for ev in rows:
                new += self._add(ev, src.name, angle)
        return new

    # -- angles ----------------------------------------------------------
    def angle_verbatim(self):
        return self.query, self._search_all("verbatim", self.query, mode="all")

    def angle_keyword(self):
        q = " ".join(self.fp["tokens"])
        return q, self._search_all("keyword", q, mode="any")

    def angle_alias(self):
        q = " ".join(self.fp["canonical_tokens"])
        if q == " ".join(self.fp["tokens"]):
            return q, None  # aliases changed nothing: no new angle, spend nothing
        return q, self._search_all("alias", q, mode="any")

    def angle_time_window(self):
        win = self.fp["time_window"]
        if not win:
            return "", None
        q = " ".join(self.fp["canonical_tokens"])
        return q, self._search_all("time_window", q, mode="any", date_range=win)

    def angle_relay(self):
        if not self.fp["relay_cue"]:
            return "", None
        q = " ".join(self.fp["canonical_tokens"])
        return q, self._search_all("relay", q, mode="any", kinds=["relay"])

    def angle_association(self):
        ranked = self.top()
        if not ranked:
            return "", None
        cue = ranked[0]
        new = 0
        for src in self._live_sources():
            if not self._budget_left():
                break
            self.calls += 1
            try:
                edges = src.neighbours(cue.key)
            except SourceUnavailable as exc:
                self.failed[src.name] = str(exc) or "unavailable"
                continue
            for nkey, rel in edges:
                if any(h.from_key == cue.key and h.to_key == nkey for h in self.hops):
                    continue  # edge already followed via another source
                ev = None
                for holder in self._live_sources():
                    if not self._budget_left():
                        break
                    self.calls += 1
                    try:
                        ev = holder.get(nkey)
                    except SourceUnavailable as exc:
                        self.failed[holder.name] = str(exc) or "unavailable"
                        continue
                    if ev:
                        self.hops.append(AssociationHop(cue.key, nkey, rel, holder.name))
                        new += self._add(ev, holder.name, "association")
                        break
        return f"hop:{cue.key}", new

    # -- driver ----------------------------------------------------------
    def run(self) -> ReconstructionEnvelope:
        stop_reason = "angles_exhausted"
        stale = 0
        for name in self.cfg.angles:
            fn = getattr(self, f"angle_{name}", None)
            if fn is None:
                self.runs.append(AngleRun(name, "", 0, 0, 0.0, 0.0, "unknown_angle"))
                continue
            if not self._budget_left():
                stop_reason = ("budget_calls" if self.calls >= self.cfg.max_calls else "budget_time")
                break
            if not self._live_sources():
                stop_reason = "no_reachable_sources"
                break
            before_top = self.top()[0].score if self.cands else 0.0
            calls_before, t = self.calls, time.perf_counter()
            q, new = fn()
            after = self.top()
            after_top = after[0].score if after else 0.0
            self.runs.append(AngleRun(name, q, self.calls - calls_before, new or 0, after_top,
                                      round((time.perf_counter() - t) * 1000.0, 3),
                                      None if new is not None else "not_applicable"))
            if new is None:
                continue
            stale = stale + 1 if after_top <= before_top else 0
            if len(after) >= 1:
                margin = after_top - (after[1].score if len(after) > 1 else 0.0)
                if after_top >= self.cfg.confidence_target and margin >= self.cfg.rival_margin:
                    stop_reason = "confident"
                    break
            if stale >= self.cfg.patience and self.cands:
                stop_reason = "no_marginal_gain"
                break
        return self._envelope(stop_reason)

    def _envelope(self, stop_reason: str) -> ReconstructionEnvelope:
        ranked = self.top()
        total = len(self.sources)
        reachable = total - len(self.failed)
        frac = reachable / total if total else 0.0
        if reachable == 0:
            cov_state = "no_reachable_evidence"
        elif self.failed:
            cov_state = "reconstructed_from_partial_evidence"
        else:
            cov_state = "complete_federated_recall"
        gaps: List[str] = [f"vault_unavailable:{n}" for n in sorted(self.failed)]
        rejected: List[Rejection] = []
        answer = rival = None
        margin = 0.0
        confidence = 0.0
        for c in ranked:
            if c.state == "retracted":
                rejected.append(Rejection(c.key, "retracted", c.score))
            elif c.state == "superseded":
                rejected.append(Rejection(c.key, "superseded", c.score))
        eligible = [c for c in ranked if c.state == "live"]
        if eligible:
            best = eligible[0]
            margin = best.score - (eligible[1].score if len(eligible) > 1 else 0.0)
            if best.score < self.cfg.accept_threshold:
                gaps.append("below_accept_threshold")
                rejected.append(Rejection(best.key, "below_accept_threshold", best.score))
            elif margin < self.cfg.rival_margin:
                gaps.append("ambiguous_rival")
                rejected.append(Rejection(best.key, "rival_too_close", best.score))
                rival = eligible[1].key
            else:
                answer = best.key
                rival = eligible[1].key if len(eligible) > 1 else None
                confidence = round(best.score * frac, 4)
            for c in eligible[1:]:
                if c.key != rival:
                    rejected.append(Rejection(c.key, "lower_recognition_score", c.score))
        # Proof of absence needs full coverage AND an exhausted sweep with zero
        # evidence. Anything short of that is "not reconstructed", never "absent".
        absence = (cov_state == "complete_federated_recall" and not self.cands
                   and stop_reason == "angles_exhausted")
        if not self.cands and not absence:
            gaps.append("no_candidates_absence_not_proven")
        if answer:
            summary = (f"{answer} ({self.cands[answer].title}) via "
                       f"{'+'.join(self.cands[answer].found_by)}; coverage {cov_state}")
        elif absence:
            summary = "no evidence under complete coverage and exhausted sweep"
        else:
            summary = f"not reconstructed; coverage {cov_state}"
        return ReconstructionEnvelope(
            query=self.query,
            query_fingerprint=self.fp,
            retrieval_angles=self.runs,
            candidate_sources=ranked,
            association_hops=self.hops,
            vault_coverage={"total": total, "reachable": reachable,
                            "failed": dict(self.failed), "state": cov_state,
                            "fraction": round(frac, 4)},
            time_coverage={"window": self.fp["time_window"],
                           "applied": any(r.angle == "time_window" and not r.skipped_reason
                                          for r in self.runs)},
            correction_state={c.key: c.state for c in ranked if c.state != "live"},
            confidence=confidence,
            reconstruction_summary=summary,
            unresolved_gaps=gaps,
            answer_key=answer,
            rival_key=rival,
            rival_margin=round(margin, 4),
            rejected=rejected,
            stop_reason=stop_reason,
            calls=self.calls,
            elapsed_ms=round(self._elapsed_ms(), 3),
            absence_proven=absence,
        )


def load_alias_map(path: Optional[str] = None) -> Dict[str, List[str]]:
    """Opt-in synonym/alias map. Default: none.

    Resolves ``path`` -> ``NOUGEN_RECON_ALIAS_MAP`` (a JSON file mapping a
    canonical term to its variants). Unset, missing or malformed -> ``{}``.
    """
    src = path or os.environ.get("NOUGEN_RECON_ALIAS_MAP", "").strip()
    if not src:
        return {}
    try:
        with open(src, encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): [str(v) for v in vs] for k, vs in data.items() if isinstance(vs, list)}
    except (OSError, ValueError, AttributeError) as exc:
        log.warning("reconstruction: alias map unreadable (%s), using none", type(exc).__name__)
        return {}


_SWEEP_TRIGGERS = ("low_confidence", "zero_hit", "never")


def should_sweep(baseline: "ReconstructionEnvelope", config: Optional[SweepConfig] = None) -> bool:
    """Decide whether a baseline recall earns an angle sweep.

    ``NOUGEN_RECON_SWEEP_TRIGGER``: ``low_confidence`` (default: zero hits OR top
    score below the accept threshold), ``zero_hit`` (zero hits only), ``never``.
    """
    mode = os.environ.get("NOUGEN_RECON_SWEEP_TRIGGER", "").strip().lower() or "low_confidence"
    if mode not in _SWEEP_TRIGGERS:
        log.warning("reconstruction: unknown NOUGEN_RECON_SWEEP_TRIGGER=%r, using low_confidence", mode)
        mode = "low_confidence"
    if mode == "never":
        return False
    if baseline.answer_key is None:
        return True
    if mode == "zero_hit":
        return False
    cfg = config or SweepConfig.from_env()
    top = max((a.top_score_after for a in baseline.retrieval_angles), default=0.0)
    return top < cfg.accept_threshold


def retrieval_angle_sweep(query: str, sources: Sequence[EvidenceSource], *,
                          aliases: Optional[Dict[str, List[str]]] = None,
                          known_entities: Optional[Iterable[str]] = None,
                          config: Optional[SweepConfig] = None) -> ReconstructionEnvelope:
    """Bounded multi-angle reconstruction. Opt-in; never call on every prompt."""
    if aliases is None:
        aliases = load_alias_map()
    return _Sweep(query, sources, aliases, known_entities, config or SweepConfig.from_env()).run()


def single_shot(query: str, sources: Sequence[EvidenceSource], *,
                known_entities: Optional[Iterable[str]] = None,
                config: Optional[SweepConfig] = None) -> ReconstructionEnvelope:
    """Baseline shaped like production keyword recall: AND, then ranked-OR retry,
    top hit returned with no acceptance gate (core._keyword_retrieve semantics)."""
    cfg = config or SweepConfig.from_env()
    sw = _Sweep(query, sources, {}, known_entities, cfg)
    sw.cfg = SweepConfig(**{**asdict(cfg), "angles": ["verbatim"]})
    _, new = sw.angle_verbatim()
    angle = "verbatim"
    if not sw.cands:
        _, new = sw.angle_keyword()
        angle = "keyword"
    env = sw._envelope("single_shot")
    # Production returns the top row whatever its score; mirror that for the baseline.
    ranked = [c for c in sw.top() if c.state != "retracted"]
    env.answer_key = ranked[0].key if ranked else None
    env.retrieval_angles = [AngleRun(angle, query, sw.calls, new or 0,
                                     ranked[0].score if ranked else 0.0, env.elapsed_ms)]
    return env
