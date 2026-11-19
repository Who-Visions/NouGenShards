from nougen_shards import nougen_morph_atoms as m

BASE = {"benchmark_score": 0.5, "truth": 0.9, "safety": 0.9}


def test_gate_promotes_clean_gain():
    d = m.HolisticPromotionGate.evaluate_promotion("c", BASE, {**BASE, "benchmark_score": 0.6})
    assert d.promoted and d.regressions == []


def test_gate_blocks_gain_with_regression():
    d = m.HolisticPromotionGate.evaluate_promotion(
        "c", BASE, {**BASE, "benchmark_score": 0.9, "truth": 0.8}
    )
    assert not d.promoted and d.regressions == ["truth"]
    assert d.to_dict()["candidate_id"] == "c"


def test_gate_blocks_no_gain():
    assert not m.HolisticPromotionGate.evaluate_promotion("c", BASE, dict(BASE)).promoted


def test_catalog_maps_rows(monkeypatch):
    row = {"source": "arXiv:1", "claim": "x", "confidence": 1.0, "evidence_type": "paper_body"}
    monkeypatch.setattr(m, "run_morph_atom_catalog", lambda limit: {"result": {"atoms": [row]}})
    atoms = m.NouGenMorphCatalog.get_all_atoms()
    assert atoms["arXiv:1::x"].to_dict() == row
