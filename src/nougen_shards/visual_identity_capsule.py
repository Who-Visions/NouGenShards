"""Read-only validation, centroid calculation, and deterministic selection for visual identity capsules.

This module never loads or mutates image assets. It validates references and
metrics supplied by an upstream renderer/evaluator; scores are diagnostics,
not proof of identity or permission to promote generated material to canon.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION_V1 = "nougen.visual-identity/1.0"
SCHEMA_VERSION_V2 = "nougen.visual-identity/2.0"
SUPPORTED_SCHEMA_VERSIONS = {SCHEMA_VERSION_V1, SCHEMA_VERSION_V2}

_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
_ROOT_KEYS = {
    "schema_version",
    "tenant_id",
    "character_id",
    "capsule_id",
    "parent_capsule_id",
    "revision",
    "supersedes",
    "state",
    "retraction_reason",
    "references",
    "identity",
    "mutation_budget",
    "provenance",
    "negative_constraints",
    "extensions",
}
_REFERENCE_KEYS = {
    "asset_id",
    "sha256",
    "uri",
    "view",
    "pose",
    "expression",
    "quality",
    "source_role",
}


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


@dataclass(frozen=True)
class CandidateScore:
    accepted: bool
    score: float | None
    failures: tuple[str, ...]


@dataclass(frozen=True)
class IdentityRoot:
    tenant_id: str
    character_id: str
    capsule_id: str
    embedding: Mapping[str, Any]
    geometry: Mapping[str, Any]
    marks: Mapping[str, Any]
    hair: Mapping[str, Any]
    body: Mapping[str, Any]
    wardrobe: Mapping[str, Any]


@dataclass(frozen=True)
class IdentityVariant:
    variant_id: str
    parent_id: str
    age_delta: Mapping[str, Any] | None = None
    hair_delta: Mapping[str, Any] | None = None
    mark_delta: Mapping[str, Any] | None = None
    body_delta: Mapping[str, Any] | None = None
    wardrobe_delta: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CausalIdentityState:
    root_identity: Mapping[str, Any]
    temporal_state: Mapping[str, Any] = field(default_factory=dict)
    route_state: Mapping[str, Any] = field(default_factory=dict)
    scene_state: Mapping[str, Any] = field(default_factory=dict)
    mutation_budget: Mapping[str, float] = field(default_factory=dict)


def compute_weighted_centroid(
    embeddings: Sequence[Sequence[float]],
    qualities: Sequence[float],
    redundancies: Sequence[float] | None = None,
) -> list[float]:
    """Calculate multi-reference centroid mu_X = sum(w_i * e_i_hat) / ||sum(w_i * e_i_hat)||.
    
    Weights are defined as w_i = (q_i * (1 - r_i)) / sum(q_j * (1 - r_j)).
    """
    if not embeddings:
        raise ValueError("embeddings cannot be empty")
    k = len(embeddings)
    if len(qualities) != k:
        raise ValueError("qualities length must match embeddings length")
    if redundancies is not None and len(redundancies) != k:
        raise ValueError("redundancies length must match embeddings length")

    dim = len(embeddings[0])
    if any(len(e) != dim for e in embeddings):
        raise ValueError("all embeddings must have the same dimension")

    reds = redundancies if redundancies is not None else [0.0] * k
    raw_weights = []
    for q, r in zip(qualities, reds):
        w = max(0.0, float(q)) * max(0.0, 1.0 - min(1.0, float(r)))
        raw_weights.append(w)

    denom = sum(raw_weights)
    if denom <= 0:
        raise ValueError("at least one reference must have positive quality and non-redundancy weight")
    norm_weights = [w / denom for w in raw_weights]

    accum = [0.0] * dim
    for e, w in zip(embeddings, norm_weights):
        mag = math.sqrt(sum(float(x) ** 2 for x in e))
        if mag <= 0:
            continue
        for d in range(dim):
            accum[d] += w * (float(e[d]) / mag)

    res_mag = math.sqrt(sum(x ** 2 for x in accum))
    if res_mag <= 0:
        raise ValueError("cannot compute an identity centroid from zero or cancelling embeddings")
    return [x / res_mag for x in accum]


def calculate_identity_confidence(
    reference_count: int,
    angle_coverage: float,
    expression_coverage: float,
    geometry_confidence: float,
) -> Mapping[str, Any]:
    """Compute bounded identity confidence score and categorical level."""
    angle = max(0.0, min(1.0, float(angle_coverage)))
    expr = max(0.0, min(1.0, float(expression_coverage)))
    geom = max(0.0, min(1.0, float(geometry_confidence)))
    count_factor = min(1.0, float(reference_count) / 10.0)

    score = 0.35 * count_factor + 0.25 * angle + 0.20 * expr + 0.20 * geom

    if score >= 0.80 and reference_count >= 5:
        level = "strong"
    elif score >= 0.50 and reference_count >= 2:
        level = "moderate"
    else:
        level = "limited"

    return {
        "confidence_score": round(score, 4),
        "confidence_level": level,
        "reference_count": reference_count,
        "angle_coverage": angle,
        "expression_coverage": expr,
        "geometry_confidence": geom,
    }


def find_pareto_frontier(
    candidates: Sequence[Mapping[str, Any]],
    metric_keys: Sequence[str] = ("identity_distance", "geometry_error", "mark_displacement"),
) -> list[Mapping[str, Any]]:
    """Identify non-dominated candidates on Pareto frontier (minimizing distance metrics)."""
    valid = []
    for c in candidates:
        if all(k in c and _unit_interval(c[k]) for k in metric_keys):
            valid.append(c)

    frontier = []
    for i, c1 in enumerate(valid):
        dominated = False
        for j, c2 in enumerate(valid):
            if i == j:
                continue
            better_or_equal = all(c2[k] <= c1[k] for k in metric_keys)
            strictly_better = any(c2[k] < c1[k] for k in metric_keys)
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(c1)
    return frontier


def validate_capsule(
    capsule: Mapping[str, Any],
    *,
    known_assets: Mapping[str, str] | None = None,
    compatible_embedding_models: set[tuple[str, str, int]] | None = None,
) -> list[ValidationIssue]:
    """Validate the capsule's structural and cross-record invariants, read-only."""
    issues: list[ValidationIssue] = []

    def issue(path: str, message: str) -> None:
        issues.append(ValidationIssue(path, message))

    for key in set(capsule) - _ROOT_KEYS:
        issue(key, "unknown field")
    required = ("schema_version", "tenant_id", "character_id", "capsule_id", "revision", "references", "identity", "provenance")
    for key in required:
        if key not in capsule:
            issue(key, "required field is missing")
    if capsule.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        issue("schema_version", f"expected one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    for key in ("tenant_id", "character_id", "capsule_id"):
        if not isinstance(capsule.get(key), str) or not capsule[key].strip():
            issue(key, "must be a non-empty string")
    if "parent_capsule_id" in capsule and capsule.get("parent_capsule_id") is not None:
        if not isinstance(capsule.get("parent_capsule_id"), str) or not capsule["parent_capsule_id"].strip():
            issue("parent_capsule_id", "must be a non-empty string if provided")
    if not isinstance(capsule.get("revision"), int) or isinstance(capsule.get("revision"), bool) or capsule.get("revision", 0) < 1:
        issue("revision", "must be a positive integer")
    if capsule.get("state", "active") not in {"active", "retracted"}:
        issue("state", "must be active or retracted")
    if capsule.get("state") == "retracted" and not capsule.get("retraction_reason"):
        issue("retraction_reason", "retracted capsules require a reason")

    refs = capsule.get("references")
    asset_ids: set[str] = set()
    if not isinstance(refs, list) or not refs:
        issue("references", "must contain at least one canonical reference")
        refs = []
    for i, ref in enumerate(refs):
        path = f"references[{i}]"
        if not isinstance(ref, Mapping):
            issue(path, "must be an object")
            continue
        for key in set(ref) - _REFERENCE_KEYS:
            issue(f"{path}.{key}", "unknown field")
        asset_id, digest = ref.get("asset_id"), ref.get("sha256")
        if not isinstance(asset_id, str) or not asset_id:
            issue(f"{path}.asset_id", "must be a non-empty string")
            continue
        if asset_id in asset_ids:
            issue(f"{path}.asset_id", "duplicate reference asset_id")
        asset_ids.add(asset_id)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            issue(f"{path}.sha256", "must be a 64-character SHA-256 hex digest")
        if not isinstance(ref.get("uri"), str) or not ref["uri"]:
            issue(f"{path}.uri", "must be a non-empty durable asset URI")
        if ref.get("view") not in {"front", "three_quarter", "profile", "full_body", "detail", "other"}:
            issue(f"{path}.view", "must be a supported view label")
        if ref.get("source_role", "supporting") not in {"canonical", "supporting"}:
            issue(f"{path}.source_role", "must be canonical or supporting")
        quality = ref.get("quality")
        if not _unit_interval(quality):
            issue(f"{path}.quality", "must be a finite number in [0, 1]")
        if known_assets is not None:
            known = known_assets.get(asset_id)
            if known is None:
                issue(f"{path}.asset_id", "asset is absent from the supplied read-only asset index")
            elif not isinstance(known, str):
                issue(f"{path}.asset_id", "indexed asset digest must be a string")
            elif isinstance(digest, str) and known.lower() != digest.lower():
                issue(f"{path}.sha256", "does not match the indexed asset digest")

    identity = capsule.get("identity")
    if not isinstance(identity, Mapping):
        issue("identity", "must be an object")
        identity = {}
    for key in set(identity) - {"claims", "invariants", "embedding", "face_geometry", "mark_topology", "hair", "body", "wardrobe"}:
        issue(f"identity.{key}", "unknown field")
    for key in ("claims", "invariants"):
        if key not in identity:
            issue(f"identity.{key}", "required field is missing")
    claims = identity.get("claims", [])
    if not isinstance(claims, list):
        issue("identity.claims", "must be an array")
        claims = []
    for i, claim in enumerate(claims):
        path = f"identity.claims[{i}]"
        if not isinstance(claim, Mapping):
            issue(path, "must be an object")
            continue
        for key in set(claim) - {"key", "value", "evidence_class", "source_ids", "confidence"}:
            issue(f"{path}.{key}", "unknown field")
        if claim.get("evidence_class") not in {"reference_observation", "narrative_canon", "generated_interpretation"}:
            issue(f"{path}.evidence_class", "must preserve the evidence class")
        if not isinstance(claim.get("source_ids"), list) or not claim.get("source_ids") or any(not isinstance(source_id, str) or not source_id for source_id in claim.get("source_ids", [])):
            issue(f"{path}.source_ids", "claims require explicit provenance")

    invariants = identity.get("invariants", [])
    if not isinstance(invariants, list):
        issue("identity.invariants", "must be an array")
    else:
        for i, invariant in enumerate(invariants):
            path = f"identity.invariants[{i}]"
            if not isinstance(invariant, Mapping):
                issue(path, "must be an object")
                continue
            for key in set(invariant) - {"key", "value", "hard", "source_ids"}:
                issue(f"{path}.{key}", "unknown field")
            if not isinstance(invariant.get("key"), str) or not invariant.get("key"):
                issue(f"{path}.key", "must be a non-empty string")
            if not isinstance(invariant.get("hard"), bool):
                issue(f"{path}.hard", "must be boolean")
            if not isinstance(invariant.get("source_ids"), list):
                issue(f"{path}.source_ids", "must be an array")

    embedding = identity.get("embedding")
    if embedding is not None:
        if not isinstance(embedding, Mapping):
            issue("identity.embedding", "must be an object")
        else:
            for key in set(embedding) - {"model", "version", "dimension", "centroid", "reference_asset_ids"}:
                issue(f"identity.embedding.{key}", "unknown field")
            vector = embedding.get("centroid")
            dimension = embedding.get("dimension")
            if not isinstance(vector, list) or not vector or any(not _finite_number(x) for x in vector):
                issue("identity.embedding.centroid", "must be a non-empty finite numeric vector")
            elif dimension != len(vector):
                issue("identity.embedding.dimension", "must equal centroid length")
            elif abs(math.sqrt(sum(float(x) ** 2 for x in vector)) - 1.0) > 1e-3:
                issue("identity.embedding.centroid", "centroid must be L2-normalized within 1e-3")
            if compatible_embedding_models is not None and (embedding.get("model"), embedding.get("version"), dimension) not in compatible_embedding_models:
                issue("identity.embedding", "embedding model/version/dimension is not allowlisted for this consumer")
            embedding_sources = embedding.get("reference_asset_ids", [])
            if not isinstance(embedding_sources, list) or any(not isinstance(x, str) for x in embedding_sources) or not set(embedding_sources) <= asset_ids:
                issue("identity.embedding.reference_asset_ids", "all embedding sources must be listed reference assets")

    mutation_budget = capsule.get("mutation_budget")
    if mutation_budget is not None:
        if not isinstance(mutation_budget, Mapping):
            issue("mutation_budget", "must be an object")
        else:
            for prop, val in mutation_budget.items():
                if not _unit_interval(val):
                    issue(f"mutation_budget.{prop}", "must be a finite number in [0, 1]")

    provenance = capsule.get("provenance")
    if not isinstance(provenance, Mapping) or not isinstance(provenance.get("source_records"), list) or not provenance.get("source_records"):
        issue("provenance.source_records", "at least one source record is required")
    else:
        for key in set(provenance) - {"created_at", "created_by", "source_records", "model_family", "model_version", "prompt_policy"}:
            issue(f"provenance.{key}", "unknown field")
        for key in ("created_at", "created_by", "source_records"):
            if key not in provenance:
                issue(f"provenance.{key}", "required field is missing")
        created_at = provenance.get("created_at")
        if isinstance(created_at, str):
            try:
                parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    issue("provenance.created_at", "must include a timezone")
            except ValueError:
                issue("provenance.created_at", "must be an ISO-8601 date-time")
        else:
            issue("provenance.created_at", "must be an ISO-8601 date-time")
        if not isinstance(provenance.get("created_by"), str) or not provenance.get("created_by"):
            issue("provenance.created_by", "must be a non-empty string")
        if any(not isinstance(source_id, str) or not source_id for source_id in provenance.get("source_records", [])):
            issue("provenance.source_records", "source record IDs must be non-empty strings")
    return issues


def select_capsule(capsules: Iterable[Mapping[str, Any]], *, tenant_id: str, character_id: str) -> Mapping[str, Any] | None:
    """Select latest non-retracted revision for exact tenant + character IDs only."""
    matches = [
        c for c in capsules
        if c.get("tenant_id") == tenant_id
        and c.get("character_id") == character_id
        and c.get("state", "active") != "retracted"
        and isinstance(c.get("revision"), int)
        and not isinstance(c.get("revision"), bool)
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda c: (
            c["revision"],
            str(c.get("provenance", {}).get("created_at", "") if isinstance(c.get("provenance"), Mapping) else ""),
            str(c.get("capsule_id", "")),
        ),
    )


_DEFAULT_WEIGHTS = {
    "identity": 0.30,
    "geometry": 0.20,
    "marks": 0.15,
    "hair": 0.10,
    "body": 0.10,
    "wardrobe": 0.05,
    "prompt": 0.05,
    "artifact": 0.05,
}


def score_candidate(
    metrics: Mapping[str, float | None],
    *,
    hard_invariants: Mapping[str, bool],
    weights: Mapping[str, float] | None = None,
) -> CandidateScore:
    """Weighted 0..1 diagnostic score; any failed hard invariant rejects candidate."""
    failures = tuple(sorted(k for k, passed in hard_invariants.items() if passed is not True))
    chosen = dict(weights or _DEFAULT_WEIGHTS)
    if any(not _finite_number(w) or float(w) < 0 for w in chosen.values()) or sum(float(w) for w in chosen.values()) <= 0:
        return CandidateScore(False, None, failures + ("invalid score weights",))
    present = [
        (name, float(value), float(chosen.get(name, 0)))
        for name, value in metrics.items()
        if name in chosen and value is not None and _finite_number(value)
    ]
    invalid_values = any(name in chosen and value is not None and not _finite_number(value) for name, value in metrics.items())
    if invalid_values or not present or any(not _unit_interval(value) for _, value, _ in present):
        return CandidateScore(False, None, failures + ("metrics must include finite 0..1 distances",))
    denom = sum(weight for _, _, weight in present)
    if denom <= 0:
        return CandidateScore(False, None, failures + ("no positive weight for supplied metrics",))
    distance = sum(value * weight for _, value, weight in present) / denom
    return CandidateScore(not failures, 1.0 - distance, failures)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _unit_interval(value: Any) -> bool:
    return _finite_number(value) and 0.0 <= float(value) <= 1.0
