"""xoah_science_sandbox engine. Fixture = generic public physics statements and
invented rulings; no Xoah lore (this repo is public)."""
import json

import pytest

from nougen_shards.xoah_toolbelt.science import (VERDICTS, facts_from_csv, ledger_from_dict,
                                                 load_ledger, science_sandbox)
from nougen_shards.xoah_toolbelt.types import CanonPacket, Provenance, TimelineEntry


def P(phrase):
    return [{"shard_id": None, "db": "ledger", "node": "fixture", "phrase": phrase}]


LEDGER = ledger_from_dict({
    "revision": "sci-fixture-1",
    "facts": [
        {"id": "f-fusion", "label": "R", "statement": "The solar core fuses hydrogen into helium.",
         "provenance": P("fact: solar fusion")},
        {"id": "f-seismo", "label": "E", "statement": "Helioseismology infers solar interior structure from surface oscillations.",
         "provenance": P("fact: helioseismology")},
        {"id": "f-dark", "label": "R~", "statement": "Dark matter may interact through a hidden dark sector force.",
         "provenance": P("fact: dark sector")},
        {"id": "f-eclipse", "label": "H", "statement": "Ancient astronomers recorded a total solar eclipse over the river delta.",
         "provenance": P("fact: recorded eclipse")},
        {"id": "f-song", "label": "E-", "statement": "Perhaps neutron stars sing through gravitational chords.",
         "provenance": P("fact: star song color")},
        {"id": "f-wind", "label": "R/R~", "statement": "Coronal heating drives the solar wind acceleration mechanism.",
         "provenance": P("fact: coronal heating")},
    ],
    "rulings": [
        {"id": "rule-no-ftl", "statement": "Nothing in the fiction carries signal faster than light.",
         "topics": ["light", "signal"], "contradicts": [r"faster than light", r"\bftl\b"],
         "provenance": P("ruling: no FTL")},
        {"id": "rule-entropy", "statement": "Entropy never runs backward in the fiction.",
         "topics": ["entropy"], "contradicts": [r"\brevers\w*"],
         "provenance": P("ruling: entropy forward")},
    ],
    "exclusions": [
        {"id": "o1-magic", "pattern": r"\bmagic\b", "reason": "magic claims are not science-testable",
         "provenance": P("O1: magic excluded")},
    ],
})


@pytest.mark.parametrize("claim,verdict", [
    ("The Veil draws power from the solar core as it fuses hydrogen.", "SUPPORTED_BY_REAL_SCIENCE"),
    ("Veil tremors show up as surface oscillations of the solar interior.", "PARTIAL_MATCH_ONLY"),
    ("The Veil is made of dark matter bound by a hidden dark sector force.", "CONTESTED_ONLY"),
    ("The Veil sends a signal faster than light between worlds.", "CONFLICTS_WITH_CANON_RULING"),
    ("The Veil is pure magic woven from starlight.", "EXCLUDED_O1"),
    ("Xoah hums a lullaby to the rain.", "NO_REAL_SCIENCE_MATCH"),
])
def test_every_verdict_is_reachable(claim, verdict):
    assert science_sandbox(LEDGER, claim).verdict == verdict


def test_verdict_names_match_the_lore_side_tool():
    assert set(VERDICTS) == {"SUPPORTED_BY_REAL_SCIENCE", "PARTIAL_MATCH_ONLY", "CONTESTED_ONLY",
                             "CONFLICTS_WITH_CANON_RULING", "EXCLUDED_O1", "NO_REAL_SCIENCE_MATCH"}


def test_layers_show_matched_tokens_and_cite_sources():
    r = science_sandbox(LEDGER, "The Veil draws power from the solar core as it fuses hydrogen.")
    real = r.findings[0]["layers"]["real"][0]
    assert real["id"] == "f-fusion" and {"solar", "core", "hydrogen"} <= set(real["matched_tokens"])
    assert any("solar fusion" in s.cite() for s in r.sources)


def test_single_shared_word_is_not_a_match():
    # "solar" alone must not pull in the fusion fact (min overlap = 2)
    assert science_sandbox(LEDGER, "A solar grief settles in her chest.").verdict == "NO_REAL_SCIENCE_MATCH"


def test_ruling_only_fires_on_its_topic():
    # the entropy ruling's pattern is a common word; without its topic it must not fire
    assert science_sandbox(LEDGER, "She reverses her decision at dawn.").verdict == "NO_REAL_SCIENCE_MATCH"
    assert science_sandbox(LEDGER, "Inside the Veil entropy reverses.").verdict == "CONFLICTS_WITH_CANON_RULING"


def test_timeline_rows_are_layered_when_a_packet_is_given():
    pkt = CanonPacket("pkt-1", timeline=(TimelineEntry(
        "t1", "prime", 4, "She first sees the solar core burn through the Veil", (),
        (Provenance(None, "db", "fixture", "timeline: solar core seen"),)),))
    r = science_sandbox(LEDGER, "The Veil draws power from the solar core.", packet=pkt)
    assert r.findings[0]["layers"]["timeline_rows"][0]["fact_id"] == "t1"


def test_deterministic_and_sealed():
    a = science_sandbox(LEDGER, "The Veil draws power from the solar core as it fuses hydrogen.")
    b = science_sandbox(LEDGER, "The Veil draws power from the solar core as it fuses hydrogen.")
    assert a.receipt_id == b.receipt_id and len(a.receipt_id) == 64


def test_loaders_refuse_unprovenanced_or_unlabelled_rows(tmp_path):
    with pytest.raises(ValueError):
        ledger_from_dict({"revision": "x", "facts": [{"id": "f", "label": "R", "statement": "s"}]})
    with pytest.raises(ValueError):
        ledger_from_dict({"revision": "x", "facts": [{"id": "f", "label": "Q", "statement": "s",
                                                      "provenance": P("p")}]})
    p = tmp_path / "l.json"
    p.write_text(json.dumps({"revision": "r2", "facts": []}))
    assert load_ledger(p).revision == "r2"


def test_facts_csv_loader_accepts_blade_style_columns(tmp_path):
    p = tmp_path / "hard_facts.csv"
    p.write_text("id,fact,tier,keywords\nh1,The solar core fuses hydrogen.,R,sun;fusion\n")
    [f] = facts_from_csv(p, node="fixture")
    assert f.label == "R" and "fusion" in f.words() and "hard_facts.csv:2" in f.provenance[0].phrase


def test_default_map_is_blades_legend_and_a_ledger_map_overrides_it():
    r = science_sandbox(LEDGER, "The Veil draws power from the solar core as it fuses hydrogen.")
    assert r.findings[0]["label_map_source"].startswith("default:blade_legend")
    custom = ledger_from_dict({"revision": "x", "labels": {"E": "contested"},
                               "facts": [{"id": "f", "label": "E", "provenance": P("p"),
                                          "statement": "Helioseismology infers solar interior structure from surface oscillations."}]})
    r2 = science_sandbox(custom, "Veil tremors show up as surface oscillations of the solar interior.")
    assert r2.verdict == "CONTESTED_ONLY" and r2.findings[0]["label_map_source"] == "ledger"


def test_historical_record_is_partial_not_support():
    r = science_sandbox(LEDGER, "The Veil opened during a total solar eclipse over the river delta.")
    assert r.verdict == "PARTIAL_MATCH_ONLY" and r.findings[0]["layers"]["historical"][0]["id"] == "f-eclipse"


def test_speculative_color_is_shown_but_never_load_bearing():
    r = science_sandbox(LEDGER, "The Veil hums because neutron stars sing gravitational chords.")
    assert r.verdict == "NO_REAL_SCIENCE_MATCH"
    assert r.findings[0]["layers"]["speculative"][0]["id"] == "f-song"


def test_joined_label_takes_its_weakest_part():
    # R/R~ must not count as settled science
    r = science_sandbox(LEDGER, "Veil friction drives solar wind acceleration via coronal heating.")
    assert r.verdict == "CONTESTED_ONLY" and r.findings[0]["layers"]["contested"][0]["label"] == "R/R~"


def test_label_map_to_unknown_layer_is_refused():
    with pytest.raises(ValueError):
        ledger_from_dict({"revision": "x", "labels": {"R": "gospel"}, "facts": []})
