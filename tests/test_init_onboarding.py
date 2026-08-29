"""Adaptive onboarding: questions follow discovery (leg 20260829T050012Z)."""
import json

from nougen_shards import init_onboarding as ob


def caps(local_models=(), env=None):
    """Build a capability picture without touching the network."""
    env = env or {}
    return {
        "local_runtime": {"url": "http://x", "reachable": bool(local_models),
                          "models": list(local_models),
                          "sizes": {m: i for i, m in enumerate(local_models)}},
        "credentials_present": sorted(k for k in ob.CREDENTIAL_NAMES if env.get(k)),
        "credentials_absent": sorted(k for k in ob.CREDENTIAL_NAMES if not env.get(k)),
        "has_local_lane": bool(local_models),
        "has_free_lane": bool(env.get("OPENROUTER_API_KEY")),
        "has_paid_lane": bool(env.get("NGS_INFERENCE_TOKENS") or env.get("HF_TOKEN")),
    }


def test_bank_stays_between_three_and_five():
    for c in (caps(), caps(["a"]), caps(["a", "b"], {"OPENROUTER_API_KEY": "x", "HF_TOKEN": "y"})):
        assert 3 <= len(ob.question_bank(c)) <= 5


def test_no_local_models_means_no_model_choice_question():
    """Asking which local model to prefer on a machine with none is noise."""
    ids = {q["id"] for q in ob.question_bank(caps())}
    assert "local_model" not in ids
    assert "local_runtime_wanted" in ids


def test_local_models_produce_a_model_choice_defaulting_to_smallest():
    """Smallest resident model is the one that reliably fits the card."""
    c = caps(["big", "small"])
    c["local_runtime"]["sizes"] = {"big": 9_000_000_000, "small": 1_000_000_000}
    q = next(q for q in ob.question_bank(c) if q["id"] == "local_model")
    assert q["default"] == "small"


def test_metered_tier_is_never_offered_without_a_credential():
    """Offering a paid lane with nothing behind it invites a silent bill."""
    q = next(q for q in ob.question_bank(caps(["a"])) if q["id"] == "cost_ceiling")
    assert "metered" not in q["options"]

    q2 = next(q for q in ob.question_bank(caps(["a"], {"HF_TOKEN": "t"}))
              if q["id"] == "cost_ceiling")
    assert "metered" in q2["options"]


def test_tiebreak_question_only_when_both_lanes_exist():
    assert "prefer_local_over_free" not in {q["id"] for q in ob.question_bank(caps(["a"]))}
    ids = {q["id"] for q in ob.question_bank(caps(["a"], {"OPENROUTER_API_KEY": "k"}))}
    assert "prefer_local_over_free" in ids


def test_profile_route_order_respects_cost_ceiling():
    c = caps(["a"], {"OPENROUTER_API_KEY": "k", "HF_TOKEN": "t"})
    assert ob.compile_profile(c, {"cost_ceiling": "local-only"})["route_order"] == ["local"]
    assert ob.compile_profile(c, {"cost_ceiling": "free-lanes"})["route_order"] == ["local", "free"]
    assert ob.compile_profile(c, {"cost_ceiling": "metered"})["route_order"] == [
        "local", "free", "metered"]


def test_profile_never_silently_escalates():
    p = ob.compile_profile(caps(), {"cost_ceiling": "local-only"})
    assert p["on_all_lanes_down"] == "report"
    assert p["route_order"] == [], "nothing routable must be visible, not papered over"


def test_prefer_local_no_demotes_local_below_free():
    c = caps(["a"], {"OPENROUTER_API_KEY": "k"})
    p = ob.compile_profile(c, {"cost_ceiling": "free-lanes", "prefer_local_over_free": "no"})
    assert p["route_order"] == ["free", "local"]


def test_discovery_records_credential_names_never_values(monkeypatch):
    secret = "sk-do-not-leak-this-value"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    monkeypatch.setattr(ob, "_probe_ollama", lambda base, timeout=3.0: {
        "reachable": False, "models": [], "sizes": {}})
    c = ob.discover_capabilities()
    assert "OPENROUTER_API_KEY" in c["credentials_present"]
    assert secret not in json.dumps(c), "a secret value must never enter the profile"


def test_unreachable_runtime_is_not_an_error(monkeypatch):
    """A clean clone with no runtime and no keys must still onboard."""
    monkeypatch.setattr(ob, "_probe_ollama", lambda base, timeout=3.0: {
        "reachable": False, "models": [], "sizes": {}})
    for name in ob.CREDENTIAL_NAMES:
        monkeypatch.delenv(name, raising=False)
    c = ob.discover_capabilities()
    profile = ob.compile_profile(c, ob.default_answers(ob.question_bank(c)))
    assert profile["profile_version"] == ob.PROFILE_VERSION
    assert profile["route_order"] == []


def test_run_writes_a_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "_probe_ollama", lambda base, timeout=3.0: {
        "reachable": True, "models": ["m1"], "sizes": {"m1": 1}})
    profile = ob.run(root=tmp_path, assume_defaults=True)
    written = json.loads((tmp_path / ".nougen" / "profile.json").read_text(encoding="utf-8"))
    assert written["route_order"] == profile["route_order"] == ["local"]
    assert written["default_local_model"] == "m1"


def test_embedding_models_are_not_offered_as_a_chat_lane():
    """Ranking by size alone picked nomic-embed-text, which cannot chat."""
    assert ob._is_generative({"name": "gemma4:e2b-qat", "capabilities": ["completion"]})
    assert not ob._is_generative({"name": "nomic-embed-text:latest",
                                  "capabilities": ["embedding"]})
    # Daemons that omit capabilities fall back to the naming convention.
    assert not ob._is_generative({"name": "nomic-embed-text:latest"})
    assert ob._is_generative({"name": "gemma2:2b"})


def test_probe_excludes_embedding_models_from_the_bank(monkeypatch):
    import json as _json

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _json.dumps({"models": [
                {"name": "nomic-embed-text:latest", "size": 1, "capabilities": ["embedding"]},
                {"name": "gemma4:e2b-qat", "size": 9, "capabilities": ["completion"]},
            ]}).encode()

    monkeypatch.setattr(ob.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    probed = ob._probe_ollama("http://x")
    assert probed["models"] == ["gemma4:e2b-qat"]
    assert probed["excluded_non_generative"] == ["nomic-embed-text:latest"]
