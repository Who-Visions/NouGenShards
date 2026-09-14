"""persona.py: deterministic, dynamic, no owner hardcodes."""
from pathlib import Path

from nougen_shards import persona as P

OPERATOR = [
    "leg it on the relay",
    "relaunch the distill A/B on the fixed code in background with ollama",
    "so i ask again what has 50 billion tokens taught us",
    "hit this one with a hadouken",
    "fleet probe then shard it",
    "stop talking to me like a bot",
]
CANON = [
    "Xoah is the protagonist of volume one, the arc bends at chapter nine.",
    "Lock this in canon: Kenji was raised by his grandfather in the universe's first era.",
    "The film needs a scene where the character earns the audience before the trailer beat.",
]
KREYOL = ["mwen konnen sa ou vle", "mesi anpil, nou pral fe sa", "ki kote li ye"]


def test_deterministic_same_signals_same_fingerprint():
    a = P.resolve(P.Signals.from_texts(OPERATOR, surfaces=["claude-app", "relay"], tz="America/New_York"))
    b = P.resolve(P.Signals.from_texts(OPERATOR, surfaces=["claude-app", "relay"], tz="America/New_York"))
    assert a.fingerprint() == b.fingerprint()
    assert a == b


def test_operator_signals_resolve_to_fleet_operator():
    p = P.resolve(P.Signals.from_texts(OPERATOR, surfaces=["claude-app", "relay"], tz="America/New_York"))
    assert p.audience == "fleet-operator" and p.market == "agent-fleet-operators"
    assert p.register == "terse" and p.directive and p.repeats_self
    assert p.tz == "America/New_York"
    assert "AM/PM" in p.system_prompt()


def test_canon_signals_resolve_to_canon_keeper():
    p = P.resolve(P.Signals.from_texts(CANON, surfaces=["chatgpt-app"]))
    assert p.audience == "canon-keeper" and p.market == "story-canon-keepers"
    assert p.register != "terse"


def test_kreyol_detected_and_rendered():
    p = P.resolve(P.Signals.from_texts(KREYOL + OPERATOR[:2]))
    assert "ht" in p.languages
    assert "Haitian Creole" in p.system_prompt()


def test_segment_test_one_member_is_not_a_market():
    sig = P.Signals.from_texts(OPERATOR, surfaces=["claude-app"], audience_size=1, stable_days=365)
    p = P.resolve(sig)
    assert p.segment.measurable and p.segment.reachable and p.segment.stable
    assert not p.segment.large_enough and not p.segment.is_market
    sig.audience_size = 50
    assert P.resolve(sig).segment.is_market


def test_registry_is_data(tmp_path: Path):
    reg = tmp_path / "reg.json"
    reg.write_text('{"markets":[{"key":"m","problem":"p","decides":["x"]}],'
                   '"audiences":[{"key":"only","market":"m","affinities":["streaming"],'
                   '"channels":["twitch"],"values":["v"],"pains":["q"],"support":"s"}]}', encoding="utf-8")
    p = P.resolve(P.Signals.from_texts(["stream overlay for twitch chat"]), reg)
    assert p.audience == "only" and p.market == "m" and p.support == "s"


def test_no_owner_hardcodes():
    src = Path(P.__file__).read_text(encoding="utf-8").lower()
    for word in ("dave", "meralus", "whoentertains", "who visions", "blade", "phoebus", "whoart"):
        assert word not in src, word


def test_empty_signals_still_resolve():
    p = P.resolve(P.Signals())
    assert p.audience and p.market and p.fingerprint()


def test_merge_is_order_independent():
    a = P.Signals.from_texts(OPERATOR[:3], surfaces=["claude-app"])
    b = P.Signals.from_texts(CANON, surfaces=["chatgpt-app"])
    ab = P.Signals.from_texts(OPERATOR[:3], surfaces=["claude-app"]).merge_from(P.Signals.from_texts(CANON, surfaces=["chatgpt-app"]))
    ba = P.Signals.from_texts(CANON, surfaces=["chatgpt-app"]).merge_from(P.Signals.from_texts(OPERATOR[:3], surfaces=["claude-app"]))
    assert P.resolve(ab).fingerprint() == P.resolve(ba).fingerprint()
    assert ab.lexicon == a.lexicon + b.lexicon


def test_parallel_shard_build_and_cache(tmp_path: Path):
    import sqlite3, json as _j
    vault = tmp_path / "vault"; vault.mkdir()
    for i, texts in enumerate((OPERATOR, CANON), 1):
        con = sqlite3.connect(vault / f"nougen_shards_{i}.db")
        con.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT, event_type TEXT, title TEXT, content TEXT, tags TEXT)")
        for t in texts:
            con.execute("INSERT INTO shards (timestamp,event_type,title,content,tags) VALUES (?,?,?,?,?)",
                        ("2026-09-14T04:00:00Z", "KNOWLEDGE", "t", t, _j.dumps(["via:claude-app/u", "x"])))
        con.commit(); con.close()
    sig = P.signals_from_shards("via:claude-app/u", vault=vault, tz="America/New_York")
    assert sig.surfaces["claude-app"] == len(OPERATOR) + len(CANON)
    assert sig.lexicon["fleet-ops"] > 0 and sig.lexicon["canon"] > 0
    store = P.PersonaStore(tmp_path / "personas.json")
    assert store.load("via:claude-app/u") is None
    p1 = store.get_or_build("via:claude-app/u", vault=vault, tz="America/New_York")
    p2 = store.load("via:claude-app/u")
    assert p2 is not None and p2.fingerprint() == p1.fingerprint()


def test_register_ignores_long_captures_when_capped():
    long = ["word " * 300]
    sig = P.Signals.from_texts(OPERATOR + long, message_max_words=60)
    assert sig.median_words <= 12 and P.resolve(sig).register == "terse"
    assert "never mention" in P.resolve(sig).system_prompt().lower()


def test_register_standard_when_only_captures():
    sig = P.Signals.from_texts(["word " * 300, "shard " * 200], message_max_words=60)
    p = P.resolve(sig)
    assert sig.register_evidence == "none" and p.register == "standard"
