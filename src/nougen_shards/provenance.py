"""Provenance / authority tiers for shards.

WHY THIS EXISTS
---------------
The vault mixes two very different kinds of memory in ONE ranked pool:

  * first-party material we authored or executed (doctrine, milestones,
    corrections, handoffs, session records), and
  * third-party material ingested from external feeds -- e.g. paper abstracts
    pulled from an RSS lane. That is UNVETTED INTERNET TEXT, and wherever a
    bulk-ingest lane runs unattended it can quietly become the MAJORITY of the
    pool it is ranked against.

Both carry a `utility_score` prior, and bulk-ingest lanes characteristically
stamp an entire batch at one high default while ordinary curated rows sit near
the neutral baseline -- an inflated prior nothing earned. Because every ranking
blend multiplies the prior in, an ingested abstract can outrank an exact-term
first-party match on the PRIOR ALONE.

Two papers name this risk directly:

  * `Is Deep Research Reliable? Misleading Knowledge Induces False Conclusions`
    (arXiv 2607.20891) -- misleading third-party knowledge with a controllable
    *authority level* survives focused verification and still gets adopted in
    long-horizon workflows. Its lesson: authority must be a PERSISTENT TAG
    carried through to synthesis, not a check performed once at retrieval time.
  * `HijackKV` (arXiv 2607.19957) -- reused state must be gated by the trust
    domain it was computed in, not by surface token match.

THE RULE
--------
A third-party shard must never outrank a first-party shard on the utility prior
alone. Enforced as a two-part transform applied to the PRIOR ONLY:

    effective_prior = tier_weight * min(utility, tier_cap)

The likelihood terms (BM25 / semantic / RRF consensus) are NOT touched, so a
query genuinely about research still surfaces arXiv shards on merit. They are
un-privileged, never unreachable.

RULE 0.2
--------
Every tier name, weight, cap, and pattern resolves env -> parsed config ->
logged constant fallback. No bare magic numbers ship in a ranking line. A
malformed override is logged and the fallback is used; recall never crashes on
a bad env var.

DERIVATION WITHOUT RE-INDEXING
------------------------------
Tiers are COMPUTED at rank time from fields already stored on every row
(`event_type`, `title`, `tags`, and the leading frontmatter of `content`), so
every pre-existing row is classified without a single UPDATE. New writes may
additionally carry an explicit `provenance_tier`, which always wins.

A trap worth stating: `intelligence_shard_arxiv_*` rows LOOK first-party by
filename convention but are external imports carrying the bulk-ingest prior.
Filename prefix is therefore the WEAKEST signal and is checked only after the
external-feed patterns have had their say.
"""
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Tier vocabulary -------------------------------------------------------
# Ordered most-authoritative first. Overridable so a deployment can add tiers
# (e.g. a "partner_verified" lane) without editing code.
_DEFAULT_TIERS = "first_party_curated,first_party_derived,third_party"
# Prior weight per tier.
#
# BOTH first-party tiers default to 1.0 -- i.e. NEUTRAL, a no-op. The defect
# being corrected is third-party inflation, and nothing else; demoting
# first-party derived content by default would rescale every existing score for
# a problem nobody has. The tiers stay distinct in `tier_rank()` and the weight is
# there for a deployment that wants to prefer curated over derived, but the
# shipped default changes ranking ONLY for third-party rows.
#
# third_party at 0.25 is deliberately well below the neutral prior an ordinary
# curated row carries, so the guarantee holds against real data and not merely
# on paper.
_DEFAULT_WEIGHTS = "first_party_curated:1.0,first_party_derived:1.0,third_party:0.25"
# Hard ceiling on the raw utility a tier may contribute. Unlisted tiers are
# uncapped. Capping third_party at the neutral default (1.0) means an inflated
# bulk-ingest prior can never be *earned* rank -- it sits at neutral at best.
_DEFAULT_CAPS = "third_party:1.0"
# Terminal fallback for a shard that declares NO provenance at all -- no
# explicit tier, no tag, no `source:` line, no matching pattern, no event type.
# In a working vault a large share of rows carry no `source:` frontmatter at
# all, and those are overwhelmingly operational first-party memory (handoffs,
# doctrine, commit notes) written before any provenance field existed. Choosing
# `third_party` HERE would demote all of them to fix a defect that only affects
# declared external feeds, so silence stays ours-until-shown-external.
#
# This is a DIFFERENT knob from `_DEFAULT_UNKNOWN_SOURCE_TIER` below, and the
# distinction is the whole fix: *silence* is not evidence, but an *unrecognized
# declaration* is. See that constant for the fail-closed half.
_DEFAULT_TIER = "first_party_derived"

# A shard that WRITES a `source:` line has declared its provenance; if we do not
# recognize the value we do not get to assume it is ours. Defaults to the
# least-privileged tier so a brand-new feed type can never silently arrive with
# first-party ranking. Resolved to TIERS[-1] at config time rather than a
# literal, so re-ordering the tier vocabulary moves this with it.
#
# Defect this closes: rows whose `source:` is a bare video watch URL, or an
# unmapped external value such as `podcast`, previously fell through to
# `_DEFAULT_TIER` and were ranked as first-party -- external content wearing a
# first-party badge purely because nobody had enumerated its source value yet.
_DEFAULT_UNKNOWN_SOURCE_TIER = ""  # "" -> resolve to least-privileged tier

# The `source:` values this map recognizes: arxiv, rss, web, youtube, podcast,
# official_docs and external on the third-party side; constitution, internal,
# cli_execution, user_upload and first_party_interview as curated first-party;
# pipeline_execution, session_record and database_query as first-party derived.
# Bare video watch URLs are handled by the PREFIX map below, not this one, and
# rows with no `source:` line at all fall to `_DEFAULT_TIER`.
#
# `first_party_interview` is genuinely ours despite looking external: its own
# frontmatter says `tier: FIRST_PARTY / provenance: owner_is_interviewer_not_
# viewer`. It is mapped explicitly BECAUSE the new fail-closed default would
# otherwise (correctly, given no other evidence) demote it.
_DEFAULT_SOURCE_MAP = (
    "arxiv:third_party,"
    "rss:third_party,"
    "web:third_party,"
    "youtube:third_party,"
    "podcast:third_party,"
    "official_docs:third_party,"
    "external:third_party,"
    "constitution:first_party_curated,"
    "internal:first_party_curated,"
    "cli_execution:first_party_curated,"
    "user_upload:first_party_curated,"
    "first_party_interview:first_party_curated,"
    "pipeline_execution:first_party_derived,"
    "session_record:first_party_derived,"
    "database_query:first_party_derived"
)

# Prefix rules applied when the exact `source:` value misses. A source that is
# a URL is external BY CONSTRUCTION -- it names a host that is not us -- and
# enumerating every watch URL in an exact map is impossible. Longest prefix
# wins, so a deployment can add `https://intranet.example/:first_party_curated`
# ahead of the generic scheme rule.
_DEFAULT_SOURCE_PREFIX_MAP = "http://:third_party,https://:third_party"

# How to resolve CONFLICTING signals: an explicit `provenance_tier` field or
# `provenance:<tier>` tag versus the shard's own `source:` frontmatter.
#
#   least_privilege (default) -- the least-privileged of the two wins. An
#       explicit tag may DEMOTE freely but may not ELEVATE past contradicting
#       source evidence.
#   explicit_wins             -- legacy: the tag always wins.
#
# Default is least_privilege because the elevating direction is measurably
# unreliable: a transcript-ingest lane will stamp `provenance:first_party_derived`
# onto rows whose own `source:` is a third-party video URL, simply because the
# lane is ours. A tag is an ingest-time assertion; `source:` is what the content
# says about itself. When they disagree, fail closed.
_DEFAULT_CONFLICT_STRATEGY = "least_privilege"

# Regexes matched against "<title>\n<tags>". These identify EXTERNAL FEEDS and
# are checked before any first-party filename convention.
#
# NOTE the token guard `(?<![a-z0-9])arxiv(?![a-z0-9])` instead of `\barxiv\b`:
# shard titles separate tokens with underscores, and `_` is a word character,
# so `\b` does NOT fire inside `intelligence_shard_arxiv_2607...` -- exactly the
# rows that most need catching. Treating `_` as a separator is the whole point.
_DEFAULT_THIRD_PARTY_PATTERNS = (
    r"(?<![a-z0-9])arxiv(?![a-z0-9]);"
    r"research-doc;"
    r"\bcs\.[a-z]{2}\b;"
    r"arxiv-[a-z]+;"
    r"(?<![a-z0-9])rss(?![a-z0-9])"
)
# First-party curated filename conventions. The negative lookahead is load
# bearing: `intelligence_shard_arxiv_*` is an arXiv import wearing a
# first-party filename.
_DEFAULT_CURATED_PATTERNS = r"^intelligence_shard_(?!arxiv);^milestone;^doctrine;^correction"
_DEFAULT_DERIVED_PATTERNS = r"handoff;session;transcript;vault-sweep;handoff-derived"

# event_type -> tier. DOCUMENTATION is deliberately UNMAPPED: it covers 9,576
# rows spanning both arXiv abstracts and genuine first-party docs, so it carries
# no tier information and must not be allowed to vote.
_DEFAULT_EVENT_TIERS = (
    "DOCTRINE:first_party_curated,"
    "MILESTONE:first_party_curated,"
    "CORRECTION:first_party_curated,"
    "PROJECT:first_party_curated,"
    "KNOWLEDGE:first_party_curated,"
    "HANDOFF:first_party_derived,"
    "SYNC:first_party_derived,"
    "INGEST:first_party_derived"
)

# Only the leading slice of content is scanned for frontmatter, so
# classification stays O(1) per item and cannot regress recall latency.
_DEFAULT_FRONTMATTER_CHARS = 512


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        logger.warning("provenance: bad int for %s, using fallback %s", name, default)
        return default


def _parse_list(raw: str) -> List[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def _parse_map(raw: str, name: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key, sep, val = entry.partition(":")
        if not sep or not val.strip():
            logger.warning("provenance: skipping malformed entry %r in %s", entry, name)
            continue
        out[key.strip().lower()] = val.strip()
    return out


def _parse_float_map(raw: str, name: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, val in _parse_map(raw, name).items():
        try:
            out[key] = float(val)
        except (ValueError, TypeError):
            logger.warning("provenance: non-numeric value for %r in %s", key, name)
    return out


def _compile_patterns(raw: str, name: str) -> List[re.Pattern]:
    """Semicolon-separated regexes (commas appear inside tag lists)."""
    pats = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            pats.append(re.compile(chunk, re.IGNORECASE))
        except re.error as exc:
            logger.warning("provenance: bad regex %r in %s (%s), skipped", chunk, name, exc)
    return pats


# --- Resolved configuration (env -> parsed -> logged fallback) --------------
TIERS: List[str] = _parse_list(_env_str("NOUGEN_PROVENANCE_TIERS", _DEFAULT_TIERS))
DEFAULT_TIER: str = _env_str("NOUGEN_PROVENANCE_DEFAULT_TIER", _DEFAULT_TIER)
if DEFAULT_TIER not in TIERS:
    logger.warning("provenance: default tier %r not in %s; using %s",
                   DEFAULT_TIER, TIERS, TIERS[-1] if TIERS else _DEFAULT_TIER)
    DEFAULT_TIER = TIERS[-1] if TIERS else _DEFAULT_TIER

WEIGHTS: Dict[str, float] = _parse_float_map(
    _env_str("NOUGEN_PROVENANCE_WEIGHTS", _DEFAULT_WEIGHTS), "NOUGEN_PROVENANCE_WEIGHTS")
CAPS: Dict[str, float] = _parse_float_map(
    _env_str("NOUGEN_PROVENANCE_PRIOR_CAPS", _DEFAULT_CAPS), "NOUGEN_PROVENANCE_PRIOR_CAPS")
SOURCE_MAP: Dict[str, str] = _parse_map(
    _env_str("NOUGEN_PROVENANCE_SOURCE_MAP", _DEFAULT_SOURCE_MAP), "NOUGEN_PROVENANCE_SOURCE_MAP")

# Prefix rules are stored longest-first so lookup is a plain ordered scan and
# the most specific rule always wins regardless of config order.
SOURCE_PREFIX_MAP: List[Tuple[str, str]] = sorted(
    _parse_map(
        _env_str("NOUGEN_PROVENANCE_SOURCE_PREFIX_MAP", _DEFAULT_SOURCE_PREFIX_MAP),
        "NOUGEN_PROVENANCE_SOURCE_PREFIX_MAP",
    ).items(),
    key=lambda kv: -len(kv[0]),
)
EVENT_TIERS: Dict[str, str] = _parse_map(
    _env_str("NOUGEN_PROVENANCE_EVENT_TIERS", _DEFAULT_EVENT_TIERS), "NOUGEN_PROVENANCE_EVENT_TIERS")

THIRD_PARTY_PATTERNS = _compile_patterns(
    _env_str("NOUGEN_PROVENANCE_THIRD_PARTY_PATTERNS", _DEFAULT_THIRD_PARTY_PATTERNS),
    "NOUGEN_PROVENANCE_THIRD_PARTY_PATTERNS")
CURATED_PATTERNS = _compile_patterns(
    _env_str("NOUGEN_PROVENANCE_CURATED_PATTERNS", _DEFAULT_CURATED_PATTERNS),
    "NOUGEN_PROVENANCE_CURATED_PATTERNS")
DERIVED_PATTERNS = _compile_patterns(
    _env_str("NOUGEN_PROVENANCE_DERIVED_PATTERNS", _DEFAULT_DERIVED_PATTERNS),
    "NOUGEN_PROVENANCE_DERIVED_PATTERNS")

FRONTMATTER_CHARS = _env_int("NOUGEN_PROVENANCE_FRONTMATTER_CHARS", _DEFAULT_FRONTMATTER_CHARS)

# Master switch. Default ON: leaving unvetted third-party text privileged is the
# defect being fixed, so the safe state is enforcement.
ENABLED = os.environ.get("NOUGEN_PROVENANCE_RANKING", "1") == "1"

# Tier names resolved from the ordered list so downstream code never hardcodes
# a string literal either.
TIER_CURATED = TIERS[0] if TIERS else "first_party_curated"
TIER_DERIVED = TIERS[1] if len(TIERS) > 1 else TIER_CURATED
TIER_THIRD_PARTY = TIERS[-1] if TIERS else "third_party"

# The least-privileged tier IS the last entry of the ordered vocabulary; naming
# it separately keeps the fail-closed intent readable at the call site.
LEAST_PRIVILEGED_TIER = TIER_THIRD_PARTY

_unknown_src = _env_str("NOUGEN_PROVENANCE_UNKNOWN_SOURCE_TIER",
                        _DEFAULT_UNKNOWN_SOURCE_TIER).strip().lower()
if _unknown_src and _unknown_src not in TIERS:
    logger.warning("provenance: unknown-source tier %r not in %s; failing closed to %s",
                   _unknown_src, TIERS, LEAST_PRIVILEGED_TIER)
    _unknown_src = ""
# Empty OR invalid both resolve to the least-privileged tier: the fail-closed
# state is the default state AND the error state.
UNKNOWN_SOURCE_TIER: str = _unknown_src or LEAST_PRIVILEGED_TIER

_CONFLICT_STRATEGIES = ("least_privilege", "explicit_wins")
CONFLICT_STRATEGY: str = _env_str(
    "NOUGEN_PROVENANCE_CONFLICT_STRATEGY", _DEFAULT_CONFLICT_STRATEGY).lower()
if CONFLICT_STRATEGY not in _CONFLICT_STRATEGIES:
    logger.warning("provenance: unknown conflict strategy %r; using %s",
                   CONFLICT_STRATEGY, _DEFAULT_CONFLICT_STRATEGY)
    CONFLICT_STRATEGY = _DEFAULT_CONFLICT_STRATEGY

_SOURCE_RE = re.compile(r"^source:\s*([^\s#]+)", re.MULTILINE | re.IGNORECASE)
_TAG_TIER_RE = re.compile(r"provenance[:=]([a-z_]+)", re.IGNORECASE)


def _normalize_tier(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    val = str(value).strip().lower()
    return val if val in TIERS else None


def _haystack(item: dict) -> str:
    title = item.get("title") or ""
    tags = item.get("tags")
    if isinstance(tags, (list, tuple)):
        tags = ",".join(str(t) for t in tags)
    return f"{title}\n{tags or ''}"


def source_tier(source_value: Optional[str]) -> Optional[str]:
    """Tier for a raw `source:` value, or None if there was no value at all.

    A PRESENT but unrecognized value never returns None -- it returns
    `UNKNOWN_SOURCE_TIER` (least-privileged by default). That is the fail-closed
    guarantee: adding a new feed type upstream cannot grant it first-party rank
    by omission, only by an explicit map entry.
    """
    if not source_value:
        return None
    val = str(source_value).strip().lower()
    if not val:
        return None
    mapped = _normalize_tier(SOURCE_MAP.get(val))
    if mapped:
        return mapped
    for prefix, tier in SOURCE_PREFIX_MAP:
        if val.startswith(prefix):
            normalized = _normalize_tier(tier)
            if normalized:
                return normalized
    logger.debug("provenance: unmapped source %r -> %s", val, UNKNOWN_SOURCE_TIER)
    return UNKNOWN_SOURCE_TIER


def _least_privileged(*tiers: Optional[str]) -> Optional[str]:
    """The lowest-authority tier among the arguments (None values ignored)."""
    present = [t for t in tiers if t]
    if not present:
        return None
    return max(present, key=tier_rank)


def _declared_source(item: dict) -> Optional[str]:
    content = item.get("content") or ""
    if not content:
        return None
    hit = _SOURCE_RE.search(content[:FRONTMATTER_CHARS])
    return hit.group(1).strip() if hit else None


def classify(item: dict) -> str:
    """Derive the provenance tier for one shard row. Never raises.

    Precedence, strongest evidence first:
      1. explicit `provenance_tier` field / `provenance:<tier>` tag, RECONCILED
         against the shard's own `source:` line per CONFLICT_STRATEGY
      2. frontmatter `source:` value  (author-written, survives re-titling);
         a present-but-unmapped value fails closed to UNKNOWN_SOURCE_TIER
      3. external-feed patterns on title/tags
      4. first-party curated filename conventions
      5. first-party derived filename conventions
      6. event_type map
      7. configured default tier (silence only -- no `source:` line at all)

    Step 1 is a reconciliation rather than a short-circuit because the ingest
    lane demonstrably mis-stamps: 22 measured rows carry
    `provenance:first_party_derived` while their own `source:` is a third-party
    YouTube URL. Under `least_privilege` the tag can still demote, it just
    cannot launder third-party text into first-party rank.
    """
    try:
        declared = _declared_source(item)
        from_source = source_tier(declared)

        explicit = _normalize_tier(item.get("provenance_tier"))
        hay = _haystack(item)
        if not explicit:
            tag_hit = _TAG_TIER_RE.search(hay)
            if tag_hit:
                explicit = _normalize_tier(tag_hit.group(1))

        if explicit:
            if CONFLICT_STRATEGY == "explicit_wins":
                return explicit
            return _least_privileged(explicit, from_source) or explicit

        if from_source:
            return from_source

        for pat in THIRD_PARTY_PATTERNS:
            if pat.search(hay):
                return TIER_THIRD_PARTY
        for pat in CURATED_PATTERNS:
            if pat.search(hay):
                return TIER_CURATED
        for pat in DERIVED_PATTERNS:
            if pat.search(hay):
                return TIER_DERIVED

        mapped = _normalize_tier(EVENT_TIERS.get(str(item.get("event_type") or "").strip().lower()))
        if mapped:
            return mapped
    except Exception:  # noqa: BLE001 - classification must never break recall
        logger.debug("provenance: classification failed, using default tier", exc_info=True)
    return DEFAULT_TIER


def tier_of(item: dict) -> str:
    """Classify once and memoize on the item so repeated ranking stages are free."""
    cached = item.get("_provenance_tier")
    if cached:
        return cached
    tier = classify(item)
    item["_provenance_tier"] = tier
    return tier


def tier_rank(tier: str) -> int:
    """0 == most authoritative. Unknown tiers sort last."""
    try:
        return TIERS.index(tier)
    except ValueError:
        return len(TIERS)


def is_third_party(item: dict) -> bool:
    return tier_of(item) == TIER_THIRD_PARTY


def tier_weight(tier: str) -> float:
    return WEIGHTS.get(tier, 1.0)


def adjust_prior(item: dict, utility: float) -> float:
    """Apply the tier transform to a UTILITY PRIOR ONLY.

        effective = tier_weight * min(utility, tier_cap)

    Never touches BM25/semantic/RRF-consensus evidence, which is what keeps
    arXiv shards reachable for queries genuinely about research.
    """
    if not ENABLED:
        return utility
    try:
        value = float(utility)
    except (TypeError, ValueError):
        return utility
    tier = tier_of(item)
    cap = CAPS.get(tier)
    if cap is not None and value > cap:
        value = cap
    return value * tier_weight(tier)


def annotate(items: List[dict]) -> List[dict]:
    """Stamp the derived tier on results so callers/UI can see authority."""
    for item in items:
        tier_of(item)
    return items


def describe() -> Dict[str, object]:
    """Resolved configuration, for diagnostics and the lane-health probe."""
    return {
        "enabled": ENABLED,
        "tiers": list(TIERS),
        "default_tier": DEFAULT_TIER,
        "unknown_source_tier": UNKNOWN_SOURCE_TIER,
        "least_privileged_tier": LEAST_PRIVILEGED_TIER,
        "conflict_strategy": CONFLICT_STRATEGY,
        "source_prefix_entries": len(SOURCE_PREFIX_MAP),
        "weights": dict(WEIGHTS),
        "prior_caps": dict(CAPS),
        "frontmatter_chars": FRONTMATTER_CHARS,
        "source_map_entries": len(SOURCE_MAP),
        "event_tier_entries": len(EVENT_TIERS),
    }


def sort_key(item: dict) -> Tuple[int, float]:
    """Authority-then-score key for callers that need an explicit tier sort."""
    return (tier_rank(tier_of(item)), -float(item.get("final_score") or 0.0))
