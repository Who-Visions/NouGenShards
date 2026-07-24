"""Provenance/authority tiers: third-party text must not win on the prior alone.

Every fixture here is synthetic. The SHAPES they reproduce are the ones a
bulk-ingest lane creates in any mixed corpus:

  * feed-ingested abstracts can outnumber curated operational rows.
  * a whole ingest batch can sit pinned at one inflated `utility_score` while
    curated rows sit near the neutral baseline.
  * arXiv frontmatter carries `source: arxiv`; tags carry "arxiv"/"cs.AI"/
    "research-doc".
  * `intelligence_shard_arxiv_*` rows wear a first-party filename convention but
    are arXiv imports.
"""
from datetime import datetime, timezone

import pytest

from nougen_shards import core, provenance


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _arxiv_shard(utility=4.286875, shard_id=101):
    """Third-party: arXiv abstract with the inflated bulk-ingest prior."""
    return {
        "id": shard_id,
        "_db_index": 1,
        "file_hash": "hash_arxiv_101",
        "title": "arxiv_cs_AI_20260722_HijackKV_New_Threat_in_Position-Independent_KV_Cache_Reuse.md",
        "content": "---\ntopic: arxiv_cs_ai_2607.19957\nsource: arxiv\n"
                   "category: TECHNICAL_DEEP_DIVE\n---\nPosition-independent KV cache reuse.",
        "tags": '["arxiv", "cs.AI", "research-doc"]',
        "event_type": "DOCUMENTATION",
        "utility_score": utility,
        "timestamp": _now(),
    }


def _first_party_shard(utility=0.9, shard_id=202):
    """First-party curated doctrine, the exact-match target that was buried."""
    return {
        "id": shard_id,
        "_db_index": 2,
        "file_hash": "hash_fp_202",
        "title": "intelligence_shard_44_logfire_observability_wiring.md",
        "content": "---\ntopic: logfire_wiring\nsource: cli_execution\n---\n"
                   "logfire configuration for the mesh service.",
        "tags": '["doctrine"]',
        "event_type": "DOCTRINE",
        "utility_score": utility,
        "timestamp": _now(),
    }


# --------------------------------------------------------------------------
# Tier derivation
# --------------------------------------------------------------------------

def test_arxiv_shard_classifies_third_party():
    assert provenance.classify(_arxiv_shard()) == provenance.TIER_THIRD_PARTY


def test_curated_doctrine_classifies_first_party_curated():
    assert provenance.classify(_first_party_shard()) == provenance.TIER_CURATED


def test_intelligence_shard_arxiv_prefix_is_not_first_party():
    """The trap: an arXiv import wearing the first-party filename convention.

    Underscore is a word character, so a naive `\\barxiv\\b` never fires here.
    """
    item = {
        "title": "intelligence_shard_arxiv_2607.19957_hijackkv_new_threat.md",
        "content": "---\ntopic: arxiv_cs_ai_2607.19957\nsource: arxiv\n---\n",
        "tags": "[]",
        "event_type": "DOCUMENTATION",
    }
    assert provenance.classify(item) == provenance.TIER_THIRD_PARTY


def test_session_transcript_classifies_first_party_derived():
    item = {
        "title": "handoff_20260724_claude-cli.md",
        "content": "session record",
        "tags": '["handoff-derived"]',
        "event_type": "HANDOFF",
    }
    assert provenance.classify(item) == provenance.TIER_DERIVED


def test_explicit_tier_field_wins_over_pattern_heuristics():
    """Explicit signals still beat the title/tag PATTERN heuristics...

    ...but they are reconciled against the shard's own `source:` line. This
    fixture has no `source:` frontmatter, so the field is uncontradicted and
    wins outright.
    """
    item = _arxiv_shard()
    item["content"] = "abstract text with no frontmatter"
    item["provenance_tier"] = provenance.TIER_CURATED
    assert provenance.classify(item) == provenance.TIER_CURATED


def test_explicit_provenance_tag_wins_over_patterns():
    item = _arxiv_shard()
    item["content"] = "abstract text with no frontmatter"
    item["tags"] = '["provenance:first_party_curated"]'
    assert provenance.classify(item) == provenance.TIER_CURATED


def test_explicit_signal_cannot_override_contradicting_source_frontmatter():
    """CHANGED 2026-07-24. Previously an explicit tier short-circuited before
    the `source:` line was ever read, which let the transcript-ingest lane's
    blanket `provenance:first_party_derived` stamp launder 22 third-party rows.
    `source: arxiv` is the shard describing itself; the tag is an ingest-time
    assertion about it. On conflict, least privilege wins.
    """
    item = _arxiv_shard()
    assert "source: arxiv" in item["content"]
    item["provenance_tier"] = provenance.TIER_CURATED
    assert provenance.classify(item) == provenance.TIER_THIRD_PARTY


def test_legacy_explicit_wins_strategy_remains_available(monkeypatch):
    """The old behaviour is a config choice, not a deleted code path."""
    monkeypatch.setattr(provenance, "CONFLICT_STRATEGY", "explicit_wins")
    item = _arxiv_shard()
    item["provenance_tier"] = provenance.TIER_CURATED
    assert provenance.classify(item) == provenance.TIER_CURATED


def test_unknown_content_falls_back_to_configured_default():
    item = {"title": "some_local_note.md", "content": "no frontmatter",
            "tags": "[]", "event_type": "DOCUMENTATION"}
    assert provenance.classify(item) == provenance.DEFAULT_TIER


def test_classification_never_raises_on_garbage():
    for junk in ({}, {"title": None, "content": None, "tags": None},
                 {"title": 12, "tags": ["a", 3], "content": b"x"}):
        assert provenance.classify(junk) in provenance.TIERS


def test_tier_is_memoized_on_the_item():
    item = _arxiv_shard()
    provenance.tier_of(item)
    assert item["_provenance_tier"] == provenance.TIER_THIRD_PARTY


def test_tier_rank_orders_first_party_above_third_party():
    assert (provenance.tier_rank(provenance.TIER_CURATED)
            < provenance.tier_rank(provenance.TIER_DERIVED)
            < provenance.tier_rank(provenance.TIER_THIRD_PARTY))


# --------------------------------------------------------------------------
# BEFORE / AFTER: the live defect and its reversal
# --------------------------------------------------------------------------

def _fuse():
    """Reproduce the measured shape: each shard is rank-1 in its OWN store's
    lane, so RRF consensus TIES and the utility prior alone decides."""
    arxiv, first_party = _arxiv_shard(), _first_party_shard()
    fused = core.reciprocal_rank_fusion([[arxiv], [first_party]], k=60)
    return [f["file_hash"] for f in fused], fused


def test_before_third_party_outranks_exact_first_party_match(monkeypatch):
    """BEFORE: with the provenance transform disabled, the inflated arXiv prior
    (4.286875 vs 0.9) beats the exact-match first-party shard on a consensus
    tie. This is the shipped defect."""
    monkeypatch.setattr(provenance, "ENABLED", False)
    order, fused = _fuse()
    assert order[0] == "hash_arxiv_101", "expected the defect to reproduce"
    assert fused[0]["final_score"] > fused[1]["final_score"]


def test_after_first_party_outranks_third_party(monkeypatch):
    """AFTER: the same fixture, transform enabled. The order reverses."""
    monkeypatch.setattr(provenance, "ENABLED", True)
    order, fused = _fuse()
    assert order[0] == "hash_fp_202", f"first-party should lead, got {order}"
    assert order[1] == "hash_arxiv_101"


def test_reversal_comes_only_from_the_prior_not_the_evidence(monkeypatch):
    """The consensus term is identical for both shards; only the prior moved."""
    monkeypatch.setattr(provenance, "ENABLED", True)
    arxiv, first_party = _arxiv_shard(), _first_party_shard()
    core.reciprocal_rank_fusion([[arxiv], [first_party]], k=60)
    # Same lane position in their own list -> identical RRF consensus.
    assert provenance.adjust_prior(arxiv, 4.286875) < provenance.adjust_prior(first_party, 0.9)


def test_prior_cap_blocks_unbounded_inflation():
    """No matter how inflated, a third-party prior cannot exceed cap * weight."""
    arxiv = _arxiv_shard(utility=1000.0)
    capped = provenance.adjust_prior(arxiv, 1000.0)
    cap = provenance.CAPS[provenance.TIER_THIRD_PARTY]
    assert capped == pytest.approx(cap * provenance.tier_weight(provenance.TIER_THIRD_PARTY))
    # ... and stays below the LOWEST first-party utility observed in the vault.
    assert capped < provenance.adjust_prior(_first_party_shard(), 0.9)


def test_first_party_prior_is_not_capped():
    fp = _first_party_shard(utility=5.0)
    assert provenance.adjust_prior(fp, 5.0) == pytest.approx(
        5.0 * provenance.tier_weight(provenance.TIER_CURATED))


# --------------------------------------------------------------------------
# Reachability: research queries must still surface arXiv
# --------------------------------------------------------------------------

def test_research_query_still_returns_arxiv_when_evidence_favours_it(monkeypatch):
    """Un-privileged, NOT unreachable.

    When the arXiv shard is the one with real evidence (it appears in BOTH
    lanes, the first-party shard in neither-but-one), it still ranks first even
    with the transform on -- because the transform only touches the prior.
    """
    monkeypatch.setattr(provenance, "ENABLED", True)
    arxiv, first_party = _arxiv_shard(), _first_party_shard()
    fused = core.reciprocal_rank_fusion(
        [[arxiv, first_party], [arxiv]], k=60)
    assert fused[0]["file_hash"] == "hash_arxiv_101"


def test_arxiv_never_filtered_out_of_results(monkeypatch):
    """The policy de-weights; it must never drop a third-party shard."""
    monkeypatch.setattr(provenance, "ENABLED", True)
    arxiv, first_party = _arxiv_shard(), _first_party_shard()
    fused = core.reciprocal_rank_fusion([[arxiv], [first_party]], k=60)
    assert {f["file_hash"] for f in fused} == {"hash_arxiv_101", "hash_fp_202"}


def test_likelihood_terms_are_untouched_by_the_tier():
    """Semantic/BM25 evidence must be identical regardless of tier."""
    arxiv, fp = _arxiv_shard(), _first_party_shard()
    for item in (arxiv, fp):
        item["bm25_score"] = -8.0
        item["embedding"] = None
    a = core._process_fts_result(arxiv, 1, None)
    f = core._process_fts_result(fp, 2, None)
    # Same bm25 -> same likelihood contribution; only the prior term differs.
    assert a["bm25_score"] == f["bm25_score"]
    assert a["final_score"] < f["final_score"]


# --------------------------------------------------------------------------
# Rule 0.2: configurability, no magic numbers
# --------------------------------------------------------------------------

def test_policy_is_env_configurable(monkeypatch):
    monkeypatch.setattr(provenance, "WEIGHTS",
                        {provenance.TIER_THIRD_PARTY: 1.0, provenance.TIER_CURATED: 1.0})
    monkeypatch.setattr(provenance, "CAPS", {})
    # With a neutral policy the transform is a no-op, proving the numbers are
    # policy and not baked into the ranking code.
    assert provenance.adjust_prior(_arxiv_shard(), 4.286875) == pytest.approx(4.286875)


def test_disabled_flag_restores_legacy_behaviour(monkeypatch):
    monkeypatch.setattr(provenance, "ENABLED", False)
    assert provenance.adjust_prior(_arxiv_shard(), 4.286875) == 4.286875


def test_malformed_env_config_degrades_to_fallback():
    assert provenance._parse_float_map("garbage,third_party:nan_x", "T") == {}
    assert provenance._compile_patterns("([unclosed", "T") == []


def test_describe_reports_resolved_policy():
    """describe() is a diagnostics contract: every value it publishes must be
    demonstrated by the engine's actual behaviour, not merely echo a constant.
    A gutted engine that still reports the policy fails here."""
    desc = provenance.describe()

    # The published tier vocabulary IS the ranking order the engine applies.
    assert desc["tiers"] == [t for _, t in
                             sorted((provenance.tier_rank(t), t) for t in desc["tiers"])]
    for expected_rank, tier in enumerate(desc["tiers"]):
        assert provenance.tier_rank(tier) == expected_rank

    # The published third-party weight IS the multiplier adjust_prior applies.
    third_party = _arxiv_shard()
    assert provenance.tier_of(third_party) == provenance.TIER_THIRD_PARTY
    tiny = 0.01  # well under any cap, so only the weight is in play
    observed_weight = provenance.adjust_prior(third_party, tiny) / tiny
    assert observed_weight == pytest.approx(desc["weights"][provenance.TIER_THIRD_PARTY])

    # The published cap IS the ceiling adjust_prior enforces.
    cap = desc["prior_caps"][provenance.TIER_THIRD_PARTY]
    huge = cap * 1000
    assert provenance.adjust_prior(third_party, huge) == pytest.approx(
        cap * desc["weights"][provenance.TIER_THIRD_PARTY])

    # The published default tier IS what an item with no signals classifies as.
    bare = {"title": "some_local_note.md", "content": "no frontmatter",
            "tags": "[]", "event_type": "DOCUMENTATION"}
    assert provenance.classify(bare) == desc["default_tier"]


def test_annotate_stamps_tier_for_downstream_consumers():
    items = [_arxiv_shard(), _first_party_shard()]
    provenance.annotate(items)
    assert items[0]["_provenance_tier"] == provenance.TIER_THIRD_PARTY
    assert items[1]["_provenance_tier"] == provenance.TIER_CURATED


# ---------------------------------------------------------------------------
# Unmapped-source fail-closed behaviour.
#
# Defect: third-party rows were classified as `first_party_derived` because
# their `source:` value was not in the map and unmapped values fell through to
# the permissive terminal default. Two shapes it happens to:
#
#   * a review of an external podcast episode, `source: podcast`
#   * video transcripts whose `source:` is a bare watch URL
#
# Both also carry an ingest-stamped `provenance:first_party_derived` TAG, which
# is why the tag can no longer elevate past contradicting source evidence.
# ---------------------------------------------------------------------------


def _shard_with_source(source, shard_id=900, title="some_operational_note", tags=None):
    return {
        "id": shard_id,
        "_db_index": 1,
        "file_hash": f"hash_{shard_id}",
        "title": title,
        "tags": tags if tags is not None else ["note"],
        "event_type": "DOCUMENTATION",
        "content": f"---\ntopic: t\nsource: {source}\ncategory: X\n---\n\nbody",
        "utility_score": 1.0,
        "timestamp": _now(),
    }


def test_known_third_party_source_classifies_third_party():
    """`podcast` is a real vault value (1 row) and is third-party content."""
    assert provenance.classify(_shard_with_source("podcast")) == provenance.TIER_THIRD_PARTY


def test_unknown_garbage_source_fails_closed_to_least_privileged():
    """The core guarantee: an unrecognized source may NOT gain first-party rank."""
    for bogus in ("wibble_feed_v9", "totally-made-up", "zzz", "New_Vendor_Feed"):
        tier = provenance.classify(_shard_with_source(bogus))
        assert tier == provenance.LEAST_PRIVILEGED_TIER, bogus
        assert tier != provenance.TIER_CURATED
        assert tier != provenance.TIER_DERIVED
    # ...and least-privileged really is the bottom of the ordered vocabulary.
    assert provenance.tier_rank(provenance.LEAST_PRIVILEGED_TIER) == len(provenance.TIERS) - 1


def test_unknown_source_is_demoted_not_merely_defaulted():
    """Distinguishes the fix from the old behaviour: the prior is actually cut."""
    item = _shard_with_source("brand_new_feed_type")
    assert provenance.adjust_prior(item, 4.286875) < 1.0


def test_genuine_first_party_source_still_classifies_first_party():
    """`first_party_interview` is ours (owner is the interviewer, not a viewer)."""
    assert provenance.classify(
        _shard_with_source("first_party_interview")) == provenance.TIER_CURATED
    assert provenance.classify(_shard_with_source("cli_execution")) == provenance.TIER_CURATED
    assert provenance.classify(
        _shard_with_source("session_record")) == provenance.TIER_DERIVED


def test_url_shaped_source_is_external_by_construction():
    """22 live rows use a bare watch URL as their `source:` value."""
    assert provenance.classify(_shard_with_source(
        "https://www.youtube.com/watch?v=HgAQOkG_v8c")) == provenance.TIER_THIRD_PARTY
    assert provenance.classify(_shard_with_source(
        "http://example.com/feed.xml")) == provenance.TIER_THIRD_PARTY


def test_ingest_stamped_tag_cannot_launder_third_party_source():
    """Shard 1295's exact shape: third-party source + first-party tag."""
    item = _shard_with_source(
        "podcast",
        shard_id=1295,
        title="How I AI (Claire Vo) Opus 5 review: hated in chat, won the blind benchmark",
        tags=["opus5", "model-eval", "how-i-ai", "provenance:first_party_derived"],
    )
    assert provenance.classify(item) == provenance.TIER_THIRD_PARTY


def test_explicit_tag_may_still_demote():
    """least_privilege is asymmetric: demotion is always honoured."""
    item = _shard_with_source(
        "cli_execution", tags=["note", "provenance:third_party"])
    assert provenance.classify(item) == provenance.TIER_THIRD_PARTY


def test_no_source_line_at_all_is_not_demoted(monkeypatch):
    """Silence != unrecognized declaration. Most legacy rows have no `source:`."""
    item = {
        "id": 950, "_db_index": 1, "file_hash": "h950",
        "title": "Handoff Registry Workflow", "tags": ["atomic"],
        "event_type": "DOCUMENTATION", "content": "plain operational note, no frontmatter",
        "utility_score": 1.0, "timestamp": _now(),
    }
    assert provenance.classify(item) == provenance.DEFAULT_TIER
    assert provenance.DEFAULT_TIER != provenance.LEAST_PRIVILEGED_TIER


def test_unknown_source_tier_is_env_overridable_and_bad_values_fail_closed():
    """Rule 0.2: the policy is config, not a bare inline literal."""
    assert provenance.source_tier("nonsense_feed") == provenance.UNKNOWN_SOURCE_TIER
    assert provenance.source_tier(None) is None
    assert provenance.source_tier("   ") is None
    # A source map supplied entirely by env is honoured.
    assert provenance.SOURCE_MAP.get("podcast") == provenance.TIER_THIRD_PARTY
    assert len(provenance.SOURCE_PREFIX_MAP) >= 2


def test_describe_exposes_the_failclosed_policy():
    """The advertised fail-closed policy must be the one actually enforced."""
    desc = provenance.describe()

    # Least-privileged means exactly that: the worst rank in the vocabulary.
    least = desc["least_privileged_tier"]
    assert provenance.tier_rank(least) == len(desc["tiers"]) - 1
    assert all(provenance.tier_rank(t) <= provenance.tier_rank(least)
               for t in desc["tiers"])

    # An item whose `source:` is unmapped really DOES land on the advertised
    # unknown-source tier -- fail closed, not fall through to curated.
    unmapped = _shard_with_source("some_vendor_nobody_mapped_yet")
    assert provenance.classify(unmapped) == desc["unknown_source_tier"]
    assert desc["unknown_source_tier"] == least

    # The advertised conflict strategy is the specific shipped default, and it
    # is the rule actually applied when signals disagree.
    assert desc["conflict_strategy"] == "least_privilege"
    conflicted = _arxiv_shard()  # content says `source: arxiv` (third party)
    conflicted["provenance_tier"] = provenance.TIER_CURATED  # tag claims curated
    assert provenance.classify(conflicted) == provenance.TIER_THIRD_PARTY
