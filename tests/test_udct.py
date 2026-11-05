from nougen_shards.udct import MODULES, Part, Runtime, compose, validate


def grammar(module, rt, prior, attempt, feedback):
    """Deterministic grammar generator: words come from values, not stored lines."""
    name, story = rt.identity["name"], rt.context["story"]
    picks = {
        "identity": [f"{name} here.", f"It's {name}.", f"{name}, on the desk."],
        "situation": [f"Tonight: {story}."],
        "intent": ["Here is the short version."],
        "expression": [""],
        "handoff": [rt.context.get("next", "")],
    }[module]
    text = picks[(rt.seed + attempt) % len(picks)]
    kind = "gesture" if module == "expression" else "words"
    return Part(module, kind, text, 0.4 if kind == "gesture" else 0.0)


def rt(**kw):
    base = dict(identity={"name": "Noo"}, context={"story": "chips get cheaper"}, seed=0,
                model_version="grammar-1")
    base.update(kw)
    return Runtime(**base)


def test_five_modules_and_deterministic_hash():
    a, b = compose(rt(), grammar), compose(rt(), grammar)
    assert a["ok"] and a["hash"] == b["hash"]
    assert [s["module"] for s in a["timeline"]] == list(MODULES)
    assert compose(rt(seed=1), grammar)["hash"] != a["hash"]


def test_retry_dodges_repeated_opener():
    out = compose(rt(history=["Noo here. Tonight: rates went up."]), grammar)
    assert out["ok"] and out["attempts"] == 2 and not out["text"].startswith("Noo here")


def test_prohibited_and_brand_keep():
    errs = validate([Part("intent", text="Here is what matters today")],
                    rt(policy={"prohibited": ["here is what matters"]}))
    assert any("prohibited" in e for e in errs)
    brand = "the Noo-ghen A.I. newsroom tonight"
    pol = {"keep": [brand]}
    errs = validate([Part("identity", text=brand + " and more")], rt(history=[brand], policy=pol))
    assert not [e for e in errs if "repeat" in e]


def test_sequence_and_in_take_repeat():
    parts = [Part(m, text="same line") for m in MODULES]
    errs = validate(parts, rt())
    assert "repeated module dialogue" in errs
    assert "bad module sequence" in validate(parts[::-1], rt())


def test_max_seconds():
    errs = validate([Part("intent", text="word " * 40)], rt(policy={"max_seconds": 5}))
    assert any("too long" in e for e in errs)


def test_unicode_and_branded_opener():
    parts = [Part(m, text=t) for m, t in zip(MODULES, ["你好", "今天下雨", "带一把伞", "注意安全", "明天见"])]
    assert validate(parts, rt()) == []
    brand = "Noo-ghen A.I. News"
    errs = validate([Part("identity", text=brand + ", rates fell.")],
                    rt(history=[brand + ", chips rose."], policy={"keep": [brand]}))
    assert not [e for e in errs if "opener" in e]
