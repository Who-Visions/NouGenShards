from nougen_shards.consolidate import consolidate

PIZZA = [{"id": "1", "text": "Likes pizza", "status": "candidate"},
         {"id": "2", "text": "Name is Dave", "status": "candidate"}]
LOCKED = [{"id": "L", "text": "Veil is a dark matter sea", "status": "locked"}]


def dec(action, target=None):
    return lambda fact, n: {"action": action, "target_id": target, "reason": "stub"}


def test_mem0_pizza_pasta_add_is_escalated_to_supersede():
    r = consolidate("I had pizza yesterday but I don't like pizza anymore, I like pasta now", PIZZA, dec("ADD"))
    assert r["action"] == "SUPERSEDE" and r["supersedes"] == "1"
    assert "add_despite_retraction_cue" in r["guards"]


def test_plain_add_stays_add():
    r = consolidate("Likes building automations", PIZZA, dec("ADD"))
    assert r["action"] == "ADD" and r["supersedes"] is None


def test_hallucinated_target_goes_to_review_not_supersede():
    r = consolidate("Likes pasta now", PIZZA, dec("SUPERSEDE", "999"))
    assert r["action"] == "REVIEW" and r["supersedes"] is None


def test_none_with_retraction_cue_is_not_a_duplicate():
    r = consolidate("No longer likes pizza", PIZZA, dec("NONE"))
    assert r["action"] == "REVIEW"


def test_locked_neighbour_yields_conflict_never_supersede():
    r = consolidate("The Veil is no longer dark matter", LOCKED, dec("SUPERSEDE", "L"))
    assert r["action"] == "CONFLICT" and r["supersedes"] is None


def test_locked_can_supersede_locked():
    r = consolidate("Veil is not dark matter", LOCKED, dec("SUPERSEDE", "L"), new_status="locked")
    assert r["action"] == "SUPERSEDE" and r["supersedes"] == "L"


def test_dead_decider_never_drops_the_fact():
    def boom(fact, n):
        raise RuntimeError("ollama down")
    r = consolidate("Likes sushi", PIZZA, boom)
    assert r["action"] == "ADD" and "decider_failed" in r["guards"]


def test_supersede_of_identical_restatement_becomes_none():
    nb = [{"id": "2", "text": "Name is Dave", "status": "candidate"}]
    r = consolidate("Name is Dave", nb, dec("SUPERSEDE", "2"))
    assert r["action"] == "NONE" and "supersede_of_identical_fact" in r["guards"]


# ---- capture wiring ----
from nougen_shards import consolidate as C


def _hits():
    return [{"id": 7, "_db_index": 3, "title": "pref", "content": "Likes pizza", "tags": '["x"]'},
            {"id": 9, "_db_index": 1, "title": "lock", "content": "Veil is a dark matter sea", "tags": ["canon-lock"]}]


def test_tags_supersede_marker_uses_id_at_db():
    tags = C.consolidation_tags("pref", "I no longer like pizza, pasta now", [], lambda q, limit=5: _hits(),
                                decide=lambda f, n: {"action": "ADD", "target_id": None, "reason": ""})
    assert tags == ["supersedes:7@db3"]


def test_tags_conflict_against_canon_lock():
    tags = C.consolidation_tags("veil", "The Veil is not dark matter", ["draft"], lambda q, limit=5: _hits(),
                                decide=lambda f, n: {"action": "SUPERSEDE", "target_id": "9@db1", "reason": ""})
    assert tags == ["consolidate:conflict", "consolidate-target:9@db1"]


def test_tags_never_raise_and_skip_documents():
    def boom(q, limit=5):
        raise RuntimeError("retrieve down")
    assert C.consolidation_tags("t", "c", [], boom) == []
    assert C.consolidation_tags("t", "x" * 5000, [], lambda q, limit=5: _hits()) == []
    assert C.consolidation_tags("t", "c", [], lambda q, limit=5: []) == []


def test_enabled_flag_and_env(monkeypatch):
    monkeypatch.delenv("NOUGEN_CONSOLIDATE", raising=False)
    assert C.enabled() is False and C.enabled(True) is True
    monkeypatch.setenv("NOUGEN_CONSOLIDATE", "1")
    assert C.enabled() is True and C.enabled(False) is False


def test_capture_stamps_tags_and_still_writes(tmp_path, monkeypatch):
    import sqlite3
    from nougen_shards import core
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)   # vault path binds at import; env is too late
    monkeypatch.setattr(C, "consolidation_tags", lambda *a, **k: ["supersedes:7@db3"])
    assert core.capture("KNOWLEDGE", "wired-capture-test", "I no longer like pizza", tags=["t"], consolidate=True)
    found = []
    for db in tmp_path.glob("nougen_shards_*.db"):
        found += sqlite3.connect(db).execute("select tags from shards where title='wired-capture-test'").fetchall()
    assert list(tmp_path.glob("nougen_shards_*.db")), "write must land in tmp_path, not the real vault"
    assert found and "supersedes:7@db3" in found[0][0]
