"""Dream must not turn JSON keys into knowledge.

2026-10-01: after the FTS trigger fix let `dream wake` finish, 6,516 of the
9,452 semantic_knowledge rows it touched were JSON fragments (subject '"object"',
predicate '"block",') from Notion-mirror shards, and the skill synthesizer named
skills after them (evolved-name, evolved-notion_id). The samples below are real.
"""
import sqlite3

import pytest

from nougen_shards import dream

GOOD = ("Data Access Pattern", "All data access events must be indexed and traceable using a unique 'source_key'.")
JUNK = [
    ('"object"', '"block",'),
    ('"parent"', '{'),
    ('"type"', '"page_id",'),
    ('"id"', '"2b1d872b-594c-81ef-86f6-0002a"'),
    ('"entities"', '['),
    ('"columns"', '['),
    ('"name"', '"Shadow Dweller",'),
]
NOTION_DUMP = ('{"object": "block", "id": "2b1d872b", "parent": {"type": "page_id", "page_id": "x"}, '
               '"created_by": {"object": "user", "id": "y"}, "has_children": false, "type": "paragraph", '
               '"paragraph": {"rich_text": [{"type": "text", "text": {"content": "hello"}}]}}') * 6


# --- the validator ----------------------------------------------------------

def test_real_junk_fragments_are_rejected():
    for subject, predicate in JUNK:
        assert not dream.is_plausible_invariant(subject, predicate), (subject, predicate)


def test_real_knowledge_is_accepted():
    assert dream.is_plausible_invariant(*GOOD)
    assert dream.is_plausible_invariant("Database File 'veillore.db'", "The designated data store lives on the system path.")


def test_short_plain_pairs_are_accepted():
    # test_dream_transactions saves ('good', 'candidate'); the validator is about
    # structure, not length, so that stays valid.
    assert dream.is_plausible_invariant("good", "candidate")


@pytest.mark.parametrize("subject,predicate", [
    (None, "p"), ("s", None), ("", "p"), ("s", ""), ("  ", "p"), ("123", "p"), ("s", "{}"), ("s", ",")])
def test_degenerate_pairs_are_rejected(subject, predicate):
    assert not dream.is_plausible_invariant(subject, predicate)


def test_json_dump_is_detected_and_prose_is_not():
    assert dream.is_structured_dump(NOTION_DUMP)
    assert dream.is_structured_dump("[" + '{"a": 1, "b": [1, 2, 3]}, ' * 40 + "]")
    assert not dream.is_structured_dump("The relay refuses a leg with no task. See {the docs} for details.")
    assert not dream.is_structured_dump("")
    assert not dream.is_structured_dump(None)
    # A short JSON snippet that opens a document of ordinary prose is still prose.
    assert not dream.is_structured_dump('{"just": "a tiny object"} ' + "followed by a long paragraph of ordinary prose. " * 80)


# --- consolidation ----------------------------------------------------------

@pytest.fixture
def grid(tmp_path, monkeypatch):
    def path(index):
        return tmp_path / f"db{index}.sqlite"

    def connection(index):
        conn = sqlite3.connect(path(index))
        conn.row_factory = sqlite3.Row
        return conn

    with connection(1) as conn:
        conn.executescript("""
            CREATE TABLE shards (id INTEGER PRIMARY KEY, content TEXT,
                domain_key TEXT DEFAULT 'global', utility_score REAL DEFAULT 1,
                consolidated INTEGER DEFAULT 0);
            CREATE TABLE semantic_knowledge (subject TEXT, predicate TEXT,
                domain_key TEXT, updated_at TEXT, confidence_score REAL DEFAULT 1,
                UNIQUE(subject, predicate));
        """)
    monkeypatch.setattr(dream.core, "MAX_DB_COUNT", 1)
    monkeypatch.setattr(dream.core, "get_db_path", path)
    monkeypatch.setattr(dream.core, "get_connection", connection)
    return connection


def _shard(grid, sid, content, utility=5):
    with grid(1) as conn:
        conn.execute("INSERT INTO shards (id, content, utility_score) VALUES (?, ?, ?)", (sid, content, utility))


def _state(grid):
    with grid(1) as conn:
        flags = {r["id"]: r["consolidated"] for r in conn.execute("SELECT id, consolidated FROM shards")}
        rows = [(r["subject"], r["predicate"]) for r in conn.execute("SELECT subject, predicate FROM semantic_knowledge")]
    return flags, rows


def test_json_dump_shard_never_reaches_the_llm_and_is_retired(grid, monkeypatch):
    _shard(grid, 1, NOTION_DUMP)
    calls = []
    monkeypatch.setattr(dream, "extract_semantic_invariants_via_llm", lambda c: calls.append(c) or [])
    result = dream.consolidate_episodic_data(limit=5)
    flags, rows = _state(grid)
    assert calls == []                      # no LLM time spent on data
    assert flags == {1: 1} and rows == []   # retired, so it is not re-picked every cycle
    assert result["structured_skipped"] == 1 and result["complete"]


def test_mixed_extraction_keeps_the_good_and_drops_the_junk(grid, monkeypatch):
    _shard(grid, 1, "Plain prose about the data access layer.")
    monkeypatch.setattr(dream, "extract_semantic_invariants_via_llm", lambda c: [
        {"subject": GOOD[0], "predicate": GOOD[1]},
        {"subject": '"object"', "predicate": '"block",'},
        {"subject": '"parent"', "predicate": "{"},
    ])
    result = dream.consolidate_episodic_data(limit=5)
    flags, rows = _state(grid)
    assert rows == [GOOD] and flags == {1: 1}
    assert result["new_invariants_extracted"] == 1 and result["invariants_rejected"] == 2
    assert result["rules"] == [{"subject": GOOD[0], "predicate": GOOD[1]}]


def test_all_junk_extraction_retires_the_shard_with_no_rows(grid, monkeypatch):
    _shard(grid, 1, "Prose that the model mangled into fragments.")
    monkeypatch.setattr(dream, "extract_semantic_invariants_via_llm",
                        lambda c: [{"subject": s, "predicate": p} for s, p in JUNK])
    result = dream.consolidate_episodic_data(limit=5)
    flags, rows = _state(grid)
    assert rows == [] and flags == {1: 1}
    assert result["shards_rejected"] == 1 and result["invariants_rejected"] == len(JUNK)
    assert result["rules"] == []


def test_retired_shard_is_not_picked_again(grid, monkeypatch):
    _shard(grid, 1, NOTION_DUMP)
    _shard(grid, 2, "Real prose with a real fact about retries.", utility=1)
    monkeypatch.setattr(dream, "extract_semantic_invariants_via_llm",
                        lambda c: [{"subject": "Retries", "predicate": "must be idempotent and fencing-aware"}])
    first = dream.consolidate_episodic_data(limit=1)       # budget of 1: the dump (higher utility) takes it
    assert first["structured_skipped"] == 1 and first["shards_consolidated"] == 0
    second = dream.consolidate_episodic_data(limit=1)      # now the real shard gets the budget
    assert second["shards_consolidated"] == 1
    assert _state(grid)[1] == [("Retries", "must be idempotent and fencing-aware")]


# --- skill synthesis --------------------------------------------------------

class _Skill:
    tier = type("T", (), {"value": "CANDIDATE"})()

    def __init__(self, name):
        self.name = name


class _Manager:
    def __init__(self, tmp):
        self.skills_dir = tmp
        self.registered = []

    def register_candidate(self, name, **_kw):
        self.registered.append(name)
        return _Skill(name)

    def verify_candidate_sandbox(self, _name):
        return True


def test_skills_are_not_named_after_json_keys(tmp_path, monkeypatch):
    import nougen_shards.progressive_skills as ps
    mgr = _Manager(tmp_path)
    monkeypatch.setattr(ps, "get_progressive_skill_manager", lambda: mgr)
    out = dream.synthesize_skills_from_invariants([
        {"subject": '"name"', "predicate": '"Shadow Dweller",'},
        {"subject": '"entities"', "predicate": "["},
        {"subject": "Relay Dispatch", "predicate": "A leg with no task must be refused before it is sent."},
    ], limit=3)
    assert mgr.registered == ["evolved-relay-dispatch"]
    assert [s["name"] for s in out] == ["evolved-relay-dispatch"]
