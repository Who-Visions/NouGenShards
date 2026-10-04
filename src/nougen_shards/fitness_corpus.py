"""Fitness corpus: the replayable benchmark that NouGen self-improvement is scored against.

Round-robin leg 20261004T181440Z (turn 5 + synthesis). Every failure the GM catches that the
fleet missed becomes a case here, so the share of "only Dave noticed" shrinks over time.

Design answers the round's challenges:
- Phoebus (REUSE, arXiv 2609.33180): a set the proposing lane has read cannot gate promotion.
  Each epoch splits cases into SEARCH (visible to lanes) and SEALED (evaluator-only) by a keyed
  hash. The key lives outside the repo (``$NOUGEN_FITNESS_KEY_FILE`` or
  ``~/.nougen/state/fitness_epoch_keys.json``, mode 0600), so a lane cannot recompute the split.
- Phoebus: 4 incidents cannot carry a threshold. ``gate_ready`` refuses until the sealed split
  holds ``min_sealed`` cases (env ``NOUGEN_FITNESS_MIN_SEALED``, default 30).
- Codex (turn 4): the ledger's "search-source" label is a trusted-caller assertion.
  ``is_search_case`` is the authoritative membership check a ledger can call instead.

The public API never lists sealed case ids or contents; only ``Evaluator`` (constructed with the
key) can read them.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

DEFAULT_SEALED_FRACTION = 0.4
DEFAULT_MIN_SEALED = 30


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _nougen_home() -> Path:
    return Path(os.environ.get("NOUGEN_STATE_HOME") or (Path.home() / ".nougen"))


def default_corpus_path() -> Path:
    return Path(os.environ.get("NOUGEN_FITNESS_CORPUS") or (_nougen_home() / "fitness" / "cases.jsonl"))


def default_key_path() -> Path:
    return Path(os.environ.get("NOUGEN_FITNESS_KEY_FILE") or (_nougen_home() / "state" / "fitness_epoch_keys.json"))


@dataclass(frozen=True)
class FitnessCase:
    """One replayable failure: what went wrong, and a detector that says whether it recurs.

    ``detector`` is a declarative spec (e.g. {"kind": "proc_count", "name": "node.exe", "max": 150})
    interpreted by the evaluator, never code to exec.
    """
    case_id: str
    title: str
    detector: Dict[str, object]
    source: str  # shard id, relay leg id, or "gm" for a hand report
    caught_by: str = "gm"  # "gm" = the fleet missed it; that is the RSI signal
    created_utc: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @staticmethod
    def make_id(title: str, detector: Dict[str, object]) -> str:
        body = json.dumps({"t": title.strip().lower(), "d": detector}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()[:16]


class FitnessCorpus:
    """Append-only JSONL store of cases. Deduplicates by content-derived ``case_id``."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_corpus_path()

    def _iter_all(self) -> Iterator[FitnessCase]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield FitnessCase(**json.loads(line))

    def add(self, title: str, detector: Dict[str, object], source: str, caught_by: str = "gm") -> FitnessCase:
        case = FitnessCase(FitnessCase.make_id(title, detector), title, detector, source, caught_by)
        if any(c.case_id == case.case_id for c in self._iter_all()):
            return case
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(case), sort_keys=True) + "\n")
        return case

    def count(self) -> int:
        return sum(1 for _ in self._iter_all())


class EpochKeys:
    """Per-epoch HMAC keys, stored outside the repository with owner-only permissions."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_key_path()

    def _load(self) -> Dict[str, str]:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def get(self, epoch: str, *, create: bool = False) -> bytes:
        keys = self._load()
        if epoch not in keys:
            if not create:
                raise KeyError(f"no fitness key for epoch {epoch!r}")
            keys[epoch] = secrets.token_hex(32)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(keys, sort_keys=True), encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            tmp.replace(self.path)
        return bytes.fromhex(keys[epoch])


def _is_sealed(case_id: str, key: bytes, fraction: float) -> bool:
    digest = hmac.new(key, case_id.encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < fraction


class SearchView:
    """What a candidate lane may see: search cases only. No sealed ids, no sealed count."""

    def __init__(self, corpus: FitnessCorpus, key: bytes, fraction: float) -> None:
        self._corpus, self._key, self._fraction = corpus, key, fraction

    def cases(self) -> List[FitnessCase]:
        return [c for c in self._corpus._iter_all() if not _is_sealed(c.case_id, self._key, self._fraction)]

    def is_search_case(self, case_id: str) -> bool:
        """Authoritative search-set membership, for ledgers that must not trust caller labels."""
        known = any(c.case_id == case_id for c in self._corpus._iter_all())
        return known and not _is_sealed(case_id, self._key, self._fraction)


DEFAULT_MIN_ANCHOR_FRACTION = 0.20


class Evaluator:
    """Evaluator-private access to the sealed split. Hold this only inside the evaluator service."""

    def __init__(self, corpus: FitnessCorpus, keys: EpochKeys, epoch: str,
                 fraction: Optional[float] = None, min_sealed: Optional[int] = None,
                 anchor_from: Optional["Evaluator"] = None,
                 min_anchor_overlap: Optional[float] = None) -> None:
        self.corpus, self.epoch = corpus, epoch
        self.fraction = fraction if fraction is not None else _env_float("NOUGEN_FITNESS_SEALED_FRACTION", DEFAULT_SEALED_FRACTION)
        if not 0.0 < self.fraction < 1.0:
            raise ValueError("sealed fraction must be in (0, 1)")
        self.min_sealed = min_sealed if min_sealed is not None else int(_env_float("NOUGEN_FITNESS_MIN_SEALED", DEFAULT_MIN_SEALED))
        self.min_anchor_overlap = (
            min_anchor_overlap
            if min_anchor_overlap is not None
            else _env_float("NOUGEN_FITNESS_MIN_ANCHOR_OVERLAP", DEFAULT_MIN_ANCHOR_FRACTION)
        )
        self._key = keys.get(epoch, create=True)
        self._anchor_case_ids: set[str] = set()

        if anchor_from is not None:
            prior_sealed = {c.case_id for c in anchor_from.sealed_cases()}
            curr_sealed = {c.case_id for c in self.sealed_cases()}
            overlap = prior_sealed & curr_sealed
            self._anchor_case_ids = overlap
            if prior_sealed:
                overlap_ratio = len(overlap) / len(prior_sealed)
                if overlap_ratio < self.min_anchor_overlap:
                    raise ValueError(
                        f"reseal with <{self.min_anchor_overlap*100:.0f}% anchor overlap is refused: "
                        f"got {overlap_ratio*100:.1f}% ({len(overlap)}/{len(prior_sealed)})"
                    )

    def search_view(self) -> SearchView:
        return SearchView(self.corpus, self._key, self.fraction)

    def sealed_cases(self) -> List[FitnessCase]:
        return [c for c in self.corpus._iter_all() if _is_sealed(c.case_id, self._key, self.fraction)]

    def anchor_cases(self) -> List[FitnessCase]:
        """Sealed cases retained from the prior epoch to anchor cross-epoch score calibration."""
        return [c for c in self.sealed_cases() if c.case_id in self._anchor_case_ids]

    def epoch_hash(self) -> str:
        """Commitment to this epoch's sealed membership without revealing it (for the fitness gate's epoch check)."""
        ids = sorted(c.case_id for c in self.sealed_cases())
        return hmac.new(self._key, "\n".join(ids).encode(), hashlib.sha256).hexdigest()

    def gate_ready(self) -> bool:
        """Refuse to gate promotion on too few sealed cases (a threshold on 4 incidents is noise)."""
        return len(self.sealed_cases()) >= self.min_sealed


def seed_from(corpus: FitnessCorpus, incidents: Iterable[Dict[str, object]]) -> int:
    """Add incidents ({title, detector, source, caught_by?}); returns the corpus size afterwards."""
    for inc in incidents:
        corpus.add(str(inc["title"]), dict(inc["detector"]), str(inc["source"]), str(inc.get("caught_by", "gm")))
    return corpus.count()


# Incidents the GM caught on 2026-10-04 that the fleet did not self-detect.
SEED_2026_10_04 = [
    {"title": "leaked npx mcp-remote processes exhaust commit charge",
     "detector": {"kind": "proc_count", "name": "node.exe", "max": 150}, "source": "shard:30744"},
    {"title": "windows commit charge below safe floor",
     "detector": {"kind": "free_commit_gb", "min": 10}, "source": "shard:30744"},
    {"title": "recurring job fires faster than its declared cadence",
     "detector": {"kind": "relay_cadence", "suffix": "-hourly-delta", "min_interval_s": 3000},
     "source": "leg:20261004T181440Z"},
    {"title": "two lanes ship overlapping implementations of one leg",
     "detector": {"kind": "duplicate_pr_topic", "window_h": 24}, "source": "NouGenShards#700/NouGenCode#34"},
    {"title": "peer asserts config entry absent without file:line evidence",
     "detector": {"kind": "claim_requires_evidence", "pattern": "not found|no .* entry"}, "source": "msg:2026-10-04T15:33Z"},
    {"title": "local llm cli hangs silently with no output",
     "detector": {"kind": "cli_timeout_no_output", "cmd": "nougen_open.cli doctor", "max_s": 60}, "source": "NouGenOpen#11"},
]


def gate_config(evaluator: "Evaluator", evaluator_hash: str, budget: int, alpha: float = 0.05):
    """Build the sealed-holdout gate's config (#707) from this epoch's sealed split.

    The gate gets exactly the evaluator-private sealed ids, so lanes never choose or see them.
    Refuses (ValueError) below ``evaluator.min_sealed`` instead of letting a tiny set gate promotion.
    """
    from .fitness_gate import GateConfig

    if not evaluator.gate_ready():
        raise ValueError(f"fitness corpus not gate-ready: {len(evaluator.sealed_cases())} sealed cases "
                         f"< {evaluator.min_sealed} for epoch {evaluator.epoch!r}")
    sealed = tuple(sorted(c.case_id for c in evaluator.sealed_cases()))
    return GateConfig(epoch=evaluator.epoch, evaluator_hash=evaluator_hash,
                      sealed_case_ids=sealed, budget=budget, alpha=alpha)
