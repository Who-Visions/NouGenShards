"""The fixture for the shared credential pattern set.

This file is the reason the module exists. Three nodes each wrote a private
pattern set, each passed its own suite, and each missed about half of what the
others tested for -- so the suite lives next to the patterns from now on, and a
blind spot fails CI instead of becoming a published number.

Every value here is synthetic padding. Never add a real credential.
"""

import re

from nougen_shards import credential_patterns as cp


def test_every_shape_is_redacted():
    """No shape in the fixture may survive redaction."""
    missed = [name for name, sample in cp.SHAPES.items()
              if cp.redact(sample) == sample]
    assert not missed, f"shapes not redacted: {missed}"


def test_every_shape_is_detected():
    """contains_credential must agree with redact on every shape."""
    missed = [name for name, sample in cp.SHAPES.items()
              if not cp.contains_credential(sample)]
    assert not missed, f"shapes not detected: {missed}"


def test_controls_pass_through_untouched():
    """Ordinary text must survive byte-identical.

    A redactor that mangles normal output gets switched off, which protects
    nothing at all -- so false positives are a hard failure here, not a
    tolerable cost of broader coverage.
    """
    damaged = [c for c in cp.CONTROLS if cp.redact(c) != c]
    assert not damaged, f"false positives on ordinary text: {damaged}"


def test_controls_are_not_detected():
    damaged = [c for c in cp.CONTROLS if cp.contains_credential(c)]
    assert not damaged, f"false positives from contains_credential: {damaged}"


def test_credential_names_survive_but_values_do_not():
    """Fleet doctrine: names, fingerprints and paths may travel; values may not.

    A redactor that destroys the name too makes its own output useless for
    diagnosis, which is why the name-directed rule captures a prefix.
    """
    out = cp.redact("NGS_NODE_TOKEN=" + "M" * 40)
    assert out.startswith("NGS_NODE_TOKEN=")
    assert "M" * 40 not in out

    # A DB URI is the deliberate exception: the canonical redactor replaces the
    # whole connection string, host included, rather than just the password.
    # That predates this fixture and is the safer choice for a URI, so the
    # contract asserted here is only that the secret does not survive.
    out = cp.redact("postgres://user:" + "Q" * 24 + "@host:5432/db")
    assert "Q" * 24 not in out


def test_no_competing_pattern_set_is_defined_here():
    """This module must stay a fixture, not a fourth pattern set.

    The whole failure being fixed was three privately-written sets. If someone
    adds patterns here beside the canonical ones in brain_scan.redaction, the
    fleet is back to two sets that drift apart silently.
    """
    assert not hasattr(cp, "PATTERNS")
    from nougen_shards.brain_scan import redaction
    assert cp.redact("ghp_" + "A" * 36) == redaction.redact_content("ghp_" + "A" * 36)


def test_sk_proj_is_not_swallowed_by_the_legacy_sk_rule():
    """Ordering regression guard.

    sk-proj- is the format OpenAI issues today and its hyphens defeat an
    alphanumeric-only class. It defeated blade's set entirely; it must not be
    partially matched here, leaving a live tail in the output.
    """
    sample = "sk-proj-" + "a" * 20 + "-" + "b" * 20 + "-" + "c" * 24
    out = cp.redact(sample)
    assert "a" * 20 not in out and "c" * 24 not in out
    assert "sk-proj-" not in out


def test_redact_is_idempotent():
    for sample in cp.SHAPES.values():
        once = cp.redact(sample)
        assert cp.redact(once) == once


def test_redact_passes_non_strings_through():
    for value in (None, 42, {"a": 1}, ["x"]):
        assert cp.redact(value) is value


def test_version_is_declared():
    """Counts are published against a stated version, so it must exist."""
    assert cp.VERSION
    assert cp.VERSION.count(".") == 2


def test_every_shape_is_structurally_synthetic():
    """No shape may contain material that could be a live key.

    This is what earns credential_patterns.py its place on the
    test_published_surface allowlist. Allowlisting a file on the promise that
    its contents are fake is exactly how a real key eventually lands in one --
    so the promise is checked here instead of trusted.

    Every value must either carry a run of >=16 identical characters (the
    fabricated padding this fixture is built from) or contain no long
    high-entropy token at all (a bare PEM header, a label).
    """
    padding = re.compile(r"(.)\1{15,}")
    entropy = re.compile(r"[A-Za-z0-9_\-+/=.~]{20,}")
    suspicious = [
        name for name, sample in cp.SHAPES.items()
        if not padding.search(sample) and entropy.search(sample)
    ]
    assert not suspicious, f"shapes with no fabricated padding: {suspicious}"


def test_typescript_half_has_parity():
    """The TS pattern table must carry every marker the Python one does.

    They are two halves of one set with no shared source. Nothing but this
    test stops them drifting -- and drift between two pattern sets is the
    exact failure this whole module exists to fix, one layer down. On
    2026-09-07 the TS half was missing all eight of the additions made to the
    Python side.
    """
    from pathlib import Path
    ts = Path(__file__).resolve().parents[1] / "ts/src/nougen_shards/brain_scan/redaction.ts"
    if not ts.exists():                       # TS half not vendored here
        return
    body = ts.read_text(encoding="utf-8")
    for marker in ("sk_live_", "sk_test_", "glpat-", "npm_", "AccountKey",
                   "PRIVATE KEY-----", "SECRET|TOKEN|PASSWORD"):
        assert marker in body, f"TS redaction table is missing {marker!r}"


def test_v2_tiers_score_clean_with_no_false_positives():
    """The headline number, published as counts and never as a ratio."""
    r = cp.score()
    assert r["fn"] == 0, f"missed: {r['fn_names']}"
    assert r["fp"] == 0, f"false positives: {r['fp_cases']}"
    assert r["tp"] == len(cp.SHAPES) + len(cp.EMBEDDED) + len(cp.MARKERS)
    assert r["tn"] == len(cp.CONTROLS_V2)


def test_marker_tier_is_non_empty_and_zero_entropy():
    """Guards the class that gets omitted by construction.

    A fixture assembled from high-entropy strings systematically omits
    marker-only shapes -- there is no random material in them to generate. If
    this tier is ever emptied, the blind spot returns silently.
    """
    assert cp.MARKERS
    padding = re.compile(r"(.)\1{15,}")
    for name, sample in cp.MARKERS.items():
        # The defining property: a marker carries NO fabricated padding,
        # because it carries no secret material at all. Every other tier is
        # built from padding runs. That difference is the whole reason a
        # detector written to match randomness cannot see this class.
        assert not padding.search(sample), (
            f"{name!r} contains padding; it belongs in SHAPES, not MARKERS")


def test_tier_names_are_unique_across_tiers():
    """A duplicate name silently drops a case from the score.

    SHAPES and EMBEDDED both used "bearer header", and score() merged them
    into a dict -- so one case vanished and the headline read 40 against 41
    cases. An undercount that presents as a clean pass is the worst shape a
    security number can take.
    """
    names = [n for tier in (cp.SHAPES, cp.EMBEDDED, cp.MARKERS, cp.LOW_CONFIDENCE)
             for n in tier]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate case names across tiers: {dupes}"
    assert cp.score()["cases"] == len(cp.SHAPES) + len(cp.EMBEDDED) + len(cp.MARKERS)


def test_low_confidence_is_excluded_from_the_headline():
    """A tier whose precision is known to collapse must not inflate the score.

    blade measured a rule broad enough to catch a bare AWS secret matching
    1448 distinct strings on one node, essentially all benign. Scored beside
    the others it would read as coverage; scored apart it reads as the
    trade-off it is.
    """
    r = cp.score()
    assert "low_confidence" in r
    assert r["tp"] + r["fn"] == len(cp.SHAPES) + len(cp.EMBEDDED) + len(cp.MARKERS)
    for name in cp.LOW_CONFIDENCE:
        assert name not in cp.SHAPES and name not in cp.EMBEDDED


def test_embedded_tier_covers_real_world_wrappings():
    """A key in the wild is rarely bare; v1 of this fixture had none of these."""
    for required in ("json value", "url query param", "env assignment",
                     "bearer header", "yaml indented"):
        assert required in cp.EMBEDDED
