"""turn_compounder: state must persist and the advertised turn_compound tool must resolve."""
from nougen_shards import core, turn_compounder as tc


def test_record_turn_persists_count(tmp_path, monkeypatch):
    monkeypatch.setattr(tc, "STATE_FILE", tmp_path / "state" / "s.json")
    assert tc.record_turn("a")["turn_count"] == 1
    r = tc.record_turn("b")
    assert r["turn_count"] == 2 and r["history_len"] == 2 and not r["is_4th_turn"]


def test_history_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(tc, "STATE_FILE", tmp_path / "s.json")
    for i in range(12):
        r = tc.record_turn(str(i))
    assert r["history_len"] == 8


def test_compound_trajectory_captures_on_4th_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(tc, "STATE_FILE", tmp_path / "s.json")
    calls = []
    monkeypatch.setattr(core, "capture", lambda *a, **k: calls.append((a, k)) or True)
    for i in range(3):
        assert tc.compound_trajectory(f"t{i}", "n")["captured"] is False
    r = tc.compound_trajectory("t3", "ship it")
    assert r["is_4th_turn"] and r["captured"] is True and len(calls) == 1
    (etype, title, content), kw = calls[0]
    assert "t0" in content and "t3" in content and "ship it" in content
    assert kw["tags"] == ["turn-compound"]