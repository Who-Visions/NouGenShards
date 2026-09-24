"""The war-game catalog (docs/wargame-catalog) is data the fleet acts on, so it
is gated like code: every record validates, ids are unique, priorities are
derived rather than typed, and the rendered markdown matches the NDJSON.
"""
import json
from pathlib import Path

import pytest

import tools.wargame_catalog as wc

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "docs" / "wargame-catalog" / "catalog.ndjson"


def _item(**over):
    base = {
        "id": "WG-0001",
        "title": "Survive the day blade's :4444 node is launched from a console again",
        "repo": "NouGenShards",
        "kind": "defend",
        "blast_radius": "fleet",
        "likelihood": "observed",
        "effort": "M",
        "failure_surface": "A paused console freezes the asyncio loop; /health hangs and every gateway fanout times out.",
        "first_fork": "if you observe CLOSE_WAIT sockets piling on :4444 -> route A (kill console, start hidden task), else route B (check tunnel).",
        "evidence": ["tools/ngs_node_serve.py"],
        "verdict": "CONFIRMED",
    }
    base.update(over)
    base["priority"] = wc.derive_priority(base)
    return base


def test_priority_is_derived_from_blast_likelihood_and_verdict():
    assert wc.derive_priority({"blast_radius": "fleet", "likelihood": "observed", "verdict": "CONFIRMED"}) == "P0"
    assert wc.derive_priority({"blast_radius": "fleet", "likelihood": "observed", "verdict": "PLAUSIBLE"}) == "P1"
    assert wc.derive_priority({"blast_radius": "repo", "likelihood": "likely", "verdict": "CONFIRMED"}) == "P1"
    assert wc.derive_priority({"blast_radius": "repo", "likelihood": "likely", "verdict": "PLAUSIBLE"}) == "P2"
    assert wc.derive_priority({"blast_radius": "module", "likelihood": "speculative", "verdict": "PLAUSIBLE"}) == "P3"


def test_validate_accepts_a_well_formed_record():
    assert wc.validate_items([_item()]) == []


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "WG-1"},
        {"title": ""},
        {"title": "x" * 200},
        {"kind": "maybe"},
        {"blast_radius": "planet"},
        {"likelihood": "certain"},
        {"effort": "XL"},
        {"verdict": "REFUTED"},
        {"evidence": []},
        {"evidence": [""]},
        {"first_fork": ""},
        {"status": "abandoned"},
        {"unexpected": 1},
        {"families": [0]},
        {"families": [101]},
        {"families": [3, 3]},
        {"families": ["3"]},
        {"families": [True]},
        {"families": 3},
    ],
)
def test_validate_rejects_bad_fields(bad):
    it = _item()
    it.update(bad)
    assert wc.validate_items([it]), bad


def test_validate_accepts_families_and_index_reports_coverage(tmp_path, monkeypatch):
    it = _item(families=[6, 100])
    assert wc.validate_items([it]) == []
    (tmp_path / "families.json").write_text(
        json.dumps({"source": "x#550", "families": {"6": "Corrupt DB reports false empty", "7": "Vector cache stale signature", "100": "War-game claims success without a receipt"}}),
        encoding="utf-8",
    )
    (tmp_path / "catalog.ndjson").write_text(json.dumps(it) + "\n", encoding="utf-8")
    monkeypatch.setattr(wc, "CATALOG_DIR", tmp_path)
    assert wc.main(["render"]) == 0
    index = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert "| 6 | Corrupt DB reports false empty | 1 |" in index
    assert "| 7 | Vector cache stale signature | 0 |" in index
    assert "1 families have no catalog entry yet: 7." in index
    assert "#550 families: 6, 100" in (tmp_path / "nougenshards.md").read_text(encoding="utf-8")


def test_validate_rejects_duplicate_ids_and_hand_typed_priority():
    a, b = _item(), _item()
    assert any("duplicate id" in p for p in wc.validate_items([a, b]))
    c = _item(id="WG-0002")
    c["priority"] = "P3"
    assert any("disagrees with derived" in p for p in wc.validate_items([c]))


def test_render_is_deterministic_and_check_detects_drift(tmp_path, monkeypatch):
    items = [_item(), _item(id="WG-0002", repo="NouGenRelay", likelihood="likely", verdict="PLAUSIBLE")]
    cat = tmp_path / "catalog.ndjson"
    cat.write_text("".join(json.dumps(it) + "\n" for it in items), encoding="utf-8")
    monkeypatch.setattr(wc, "CATALOG_DIR", tmp_path)
    assert wc.main(["render"]) == 0
    assert (tmp_path / "INDEX.md").exists()
    assert (tmp_path / "nougenshards.md").exists()
    assert (tmp_path / "nougenrelay.md").exists()
    assert wc.main(["render", "--check"]) == 0
    (tmp_path / "nougenrelay.md").write_text("edited by hand\n", encoding="utf-8")
    assert wc.main(["render", "--check"]) == 1


@pytest.mark.skipif(not CATALOG.exists(), reason="catalog not present in this checkout")
def test_shipped_catalog_is_valid_and_complete():
    items = wc.load_ndjson(CATALOG)
    assert wc.validate_items(items) == []
    assert len(items) >= 1000
    assert {it["id"] for it in items} == {f"WG-{n:04d}" for n in range(1, len(items) + 1)}
    assert any(it["kind"] == "elevate" for it in items)
    assert any(it["priority"] == "P0" for it in items)


@pytest.mark.skipif(not CATALOG.exists(), reason="catalog not present in this checkout")
def test_shipped_markdown_is_rendered_from_the_catalog():
    assert wc.main(["render", "--check"]) == 0
