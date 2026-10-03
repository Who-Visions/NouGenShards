"""One cross-plane proof contract for every canonical or negative answer.

NouGen keeps four planes: raw witnessed memory, temporal historical state
(``temporal_fabric``), the canonical current projection (``canonical_facts``) and
execution/proof receipts. Each already reports ``status``, ``lanes_queried`` and
``failed_lanes``; none carried the same envelope. ``ProofContext`` is that envelope.
It is read-only: it is built *from* a resolver result and never touches storage.

Verdicts
--------
``present``           a canonical/temporal answer was resolved
``absent_proven``     nothing found AND every expected source answered (absence is provable)
``absent_unproven``   nothing found but a source failed, timed out or never answered, so
                      absence MUST NOT be asserted
``conflicted``        more than one candidate survived resolution

The ``receipt_hash`` is SHA-256 over canonical JSON of every other field, so the same
evidence yields a byte-identical receipt and any edit to a field breaks ``verify()``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping, Optional

CONTRACT_VERSION = "proof-context-1"
PLANES = ("recall", "temporal", "canonical")
VERDICTS = ("present", "absent_proven", "absent_unproven", "conflicted")
_TIMEOUT_MARKERS = ("timeout", "timed out", "timed_out", "deadline")


def _sorted(values: Optional[Iterable[str]]) -> tuple[str, ...]:
    return tuple(sorted({str(v) for v in (values or ())}))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class ProofContext:
    plane: str
    query_intent: str
    valid_time_ms: Optional[int]
    known_time_ms: Optional[int]
    expected_sources: tuple[str, ...]
    succeeded_sources: tuple[str, ...]
    failed_sources: tuple[str, ...]
    timed_out_sources: tuple[str, ...]
    canonical_snapshot_id: Optional[str]
    supporting_shard_hashes: tuple[str, ...]
    conflict_state: str  # none | conflicted
    retraction_state: str  # unchecked | none | retracted
    answered: bool
    verdict: str
    contract_version: str = CONTRACT_VERSION
    receipt_hash: str = ""

    def _body(self) -> dict[str, Any]:
        body = asdict(self)
        body.pop("receipt_hash")
        return body

    def compute_hash(self) -> str:
        return hashlib.sha256(canonical_json(self._body()).encode("utf-8")).hexdigest()

    def verify(self) -> bool:
        return bool(self.receipt_hash) and self.receipt_hash == self.compute_hash()

    @property
    def missing_sources(self) -> tuple[str, ...]:
        seen = set(self.succeeded_sources)
        return tuple(s for s in self.expected_sources if s not in seen)

    @property
    def absence_provable(self) -> bool:
        return self.verdict == "absent_proven"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["missing_sources"] = list(self.missing_sources)
        return out


def build(*, plane: str, query_intent: str, answered: bool,
          expected_sources: Iterable[str], succeeded_sources: Iterable[str],
          failed_sources: Iterable[str] = (), timed_out_sources: Iterable[str] = (),
          valid_time_ms: Optional[int] = None, known_time_ms: Optional[int] = None,
          canonical_snapshot_id: Optional[str] = None,
          supporting_shard_hashes: Iterable[str] = (),
          candidate_count: int = 0, retraction_state: str = "unchecked") -> ProofContext:
    if plane not in PLANES:
        raise ValueError(f"unknown plane: {plane}")
    if retraction_state not in ("unchecked", "none", "retracted"):
        raise ValueError(f"unknown retraction_state: {retraction_state}")
    intent = (query_intent or "").strip()
    if not intent:
        raise ValueError("query_intent must not be empty")
    expected, ok = _sorted(expected_sources), _sorted(succeeded_sources)
    failed, timed_out = _sorted(failed_sources), _sorted(timed_out_sources)
    # a source can only count as having answered if it neither failed nor timed out
    ok = tuple(s for s in ok if s not in set(failed) | set(timed_out))
    conflicted = candidate_count > 1
    full_coverage = not failed and not timed_out and set(expected) <= set(ok)
    if conflicted:
        verdict = "conflicted"
    elif answered:
        verdict = "present"
    else:
        verdict = "absent_proven" if full_coverage else "absent_unproven"
    ctx = ProofContext(
        plane=plane, query_intent=intent, valid_time_ms=valid_time_ms, known_time_ms=known_time_ms,
        expected_sources=expected, succeeded_sources=ok, failed_sources=failed,
        timed_out_sources=timed_out, canonical_snapshot_id=canonical_snapshot_id,
        supporting_shard_hashes=_sorted(supporting_shard_hashes),
        conflict_state="conflicted" if conflicted else "none",
        retraction_state=retraction_state, answered=bool(answered), verdict=verdict,
    )
    return replace(ctx, receipt_hash=ctx.compute_hash())


def _split_failed(failed: Iterable[Any]) -> tuple[list[str], list[str]]:
    """Failed lanes may be plain names or {lane, error|reason}; timeouts are told apart by their text."""
    plain, timed = [], []
    for item in failed or ():
        if isinstance(item, Mapping):
            name = str(item.get("lane") or item.get("source") or item.get("name") or "unknown")
            why = str(item.get("error") or item.get("reason") or "").lower()
        else:
            name, why = str(item), str(item).lower()
        (timed if any(m in why for m in _TIMEOUT_MARKERS) else plain).append(name)
    return plain, timed


def from_canonical_resolve(result: Mapping[str, Any], *, query_intent: str,
                           valid_time_ms: Optional[int] = None,
                           known_time_ms: Optional[int] = None,
                           retraction_state: str = "unchecked") -> ProofContext:
    """Wrap a ``CanonicalFactIndex.resolve``/``resolve_query`` result."""
    coverage = result.get("coverage") or {}
    lanes = list(result.get("lanes_queried") or [])
    failed, timed = _split_failed(result.get("failed_lanes") or [])
    expected = [f"machine:{m}" for m in coverage.get("expected_machines") or []]
    ok = [f"machine:{m}" for m in coverage.get("present_machines") or []]
    expected += [f"lane:{lane}" for lane in lanes]
    ok += [f"lane:{lane}" for lane in lanes]
    snapshot = result.get("snapshot") or {}
    provenance = (snapshot.get("provenance") or {}).get("source_hashes") or {}
    return build(
        plane="canonical", query_intent=query_intent, answered=result.get("status") == "complete",
        expected_sources=expected, succeeded_sources=ok,
        failed_sources=[f"lane:{n}" for n in failed], timed_out_sources=[f"lane:{n}" for n in timed],
        valid_time_ms=valid_time_ms, known_time_ms=known_time_ms,
        canonical_snapshot_id=snapshot.get("snapshot_id"),
        supporting_shard_hashes=provenance.values(),
        candidate_count=len(result.get("candidates") or []), retraction_state=retraction_state,
    )


def from_temporal_resolve(result: Mapping[str, Any], *, query_intent: str,
                          retraction_state: str = "unchecked") -> ProofContext:
    """Wrap a ``TemporalFabric.resolve_as_of`` result."""
    lanes = list(result.get("lanes_queried") or [])
    version = result.get("version") or {}
    payload = version.get("payload") or {}
    hashes = [h for h in (version.get("content_hash"), payload.get("content_hash")) if h]
    return build(
        plane="temporal", query_intent=query_intent, answered=result.get("status") == "complete",
        expected_sources=[f"lane:{lane}" for lane in lanes], succeeded_sources=[f"lane:{lane}" for lane in lanes],
        valid_time_ms=result.get("valid_as_of_ms"), known_time_ms=result.get("known_as_of_ms"),
        canonical_snapshot_id=None, supporting_shard_hashes=hashes, candidate_count=1 if version else 0,
        retraction_state=retraction_state,
    )


def from_recall(body: Mapping[str, Any], *, query_intent: str, expected_sources: Iterable[str],
                shard_hashes: Iterable[str] = ()) -> ProofContext:
    """Wrap a fanout recall body: ``complete`` and ``dropped_lanes`` decide whether absence is provable."""
    dropped = list(body.get("dropped_lanes") or [])
    failed, timed = _split_failed(dropped)
    expected = _sorted(expected_sources)
    succeeded = [s for s in expected if s not in set(failed) | set(timed)] if body.get("complete") is not False else []
    results = body.get("results") or body.get("hits") or []
    return build(
        plane="recall", query_intent=query_intent, answered=bool(results),
        expected_sources=expected, succeeded_sources=succeeded, failed_sources=failed,
        timed_out_sources=timed, supporting_shard_hashes=shard_hashes,
    )
