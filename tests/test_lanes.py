"""nougen_shards.lanes: dynamic, deterministic, offline-testable lane resolution."""
from nougen_shards import lanes

EMPTY = {}


def fake_prober(served_by_url):
    def probe(url):
        return served_by_url.get(url, [])
    return probe


# ---- pick_model -------------------------------------------------------------------------

def test_custom_small_model_beats_stock():
    assert lanes.pick_model(["gemma4:e4b", "dav1d:e2b", "sol-ai:e4b", "llama3:8b"], exclude=[]) == "dav1d:e2b"


def test_banned_local_sizes_never_returned():
    assert lanes.pick_model(["gemma4:12b", "gemma4:27b", "qwen3:31b"], exclude=[]) is None


def test_cloud_only_when_allowed():
    tags = ["gemma4:31b-cloud", "gpt-oss:120b-cloud"]
    assert lanes.pick_model(tags, exclude=[]) is None
    assert lanes.pick_model(tags, allow_cloud=True, exclude=[]) == "gemma4:31b-cloud"


def test_env_preferred_wins_only_if_served_and_allowed():
    tags = ["dav1d:e2b", "gemma4:e4b"]
    assert lanes.pick_model(tags, preferred="gemma4:e4b", exclude=[]) == "gemma4:e4b"
    assert lanes.pick_model(tags, preferred="gemma4:12b", exclude=[]) == "dav1d:e2b"
    assert lanes.pick_model(tags, preferred="not-served:e2b", exclude=[]) == "dav1d:e2b"


def test_colon_cloud_convention_is_gated_like_dash_cloud():
    # review P2 (1): `gemma4:cloud` must not leak past allow_cloud=False
    tags = ["gemma4:cloud", "qwen3:cloud"]
    assert lanes.is_cloud("gemma4:cloud") and lanes.is_cloud("gemma4:31b-cloud")
    assert lanes.pick_model(tags, exclude=[]) is None
    assert lanes.pick_model(tags, allow_cloud=True, exclude=[]) == "gemma4:cloud"


def test_preferred_model_on_a_later_host_beats_small_model_on_an_earlier_host():
    # review P2 (2): env-preferred > custom e2b/e4b must hold ACROSS hosts, not per host
    probe = fake_prober({"http://a:11434": ["dav1d:e2b"], "http://b:11434": ["sol-ai:e4b", "gemma4:e4b"]})
    env = {"NOUGEN_OLLAMA_HOSTS": "http://a:11434,http://b:11434", "NOUGEN_LANE_MODEL": "sol-ai:e4b"}
    lane = lanes.resolve_lane(env=env, prober=probe, exclude=[])
    assert (lane["host"], lane["model"]) == ("http://b:11434", "sol-ai:e4b")
    # and a preferred tag that is banned or unserved falls back to the earlier host
    env["NOUGEN_LANE_MODEL"] = "gemma4:12b"
    lane = lanes.resolve_lane(env=env, prober=probe, exclude=[])
    assert (lane["host"], lane["model"]) == ("http://a:11434", "dav1d:e2b")


def test_embedding_models_and_excluded_personas_are_skipped():
    tags = ["nomic-embed-text:latest", "kaedra:e4b", "dav1d:e2b"]
    assert lanes.pick_model(tags, exclude=["kaedra"]) == "dav1d:e2b"


# ---- hosts ------------------------------------------------------------------------------

def test_bind_address_in_env_is_sanitized_to_a_dialable_host():
    hosts = lanes.candidate_hosts({"OLLAMA_HOST": "0.0.0.0"})
    assert hosts[0]["source"] == "env"
    assert "0.0.0.0" not in hosts[0]["url"]
    assert hosts[-1]["source"] == "fallback"


def test_explicit_host_list_comes_first_in_order():
    env = {"NOUGEN_OLLAMA_HOSTS": "http://ollama-a.example.test:11434, http://ollama-b.example.test:11436"}
    urls = [h["url"] for h in lanes.candidate_hosts(env)]
    assert urls[:2] == ["http://ollama-a.example.test:11434", "http://ollama-b.example.test:11436"]


def test_fallback_host_is_used_only_after_probe_confirms():
    fb = [h["url"] for h in lanes.candidate_hosts(EMPTY) if h["source"] == "fallback"][0]
    lane = lanes.resolve_lane(env=EMPTY, prober=fake_prober({fb: ["dav1d:e2b"]}), exclude=[])
    assert lane["status"] == "ready" and lane["host_source"] == "fallback" and lane["model"] == "dav1d:e2b"


def test_nothing_served_degrades_to_deterministic_only():
    lane = lanes.resolve_lane(env={"OLLAMA_HOST": "http://dead:11434"}, prober=fake_prober({}), exclude=[])
    assert lane["status"] == "deterministic_only" and lane["model"] is None
    assert lane["tried"][0]["url"] == "http://dead:11434"


def test_first_host_serving_an_allowed_model_wins():
    probe = fake_prober({"http://a:11434": ["gemma4:12b"], "http://b:11434": ["gemma4:e2b"]})
    lane = lanes.resolve_lane(env={"NOUGEN_OLLAMA_HOSTS": "http://a:11434,http://b:11434"}, prober=probe, exclude=[])
    assert (lane["host"], lane["model"]) == ("http://b:11434", "gemma4:e2b")


def test_resolution_is_deterministic():
    fb = [h["url"] for h in lanes.candidate_hosts(EMPTY) if h["source"] == "fallback"][0]
    served = {fb: ["sol-ai:e4b", "dav1d:e2b"]}
    a = lanes.resolve_lane(env=EMPTY, prober=fake_prober(served), exclude=[])
    b = lanes.resolve_lane(env=EMPTY, prober=fake_prober(served), exclude=[])
    assert a == b


# ---- secrets ----------------------------------------------------------------------------

def test_env_secret_is_fingerprinted_never_echoed():
    res = lanes.resolve_secret("EXA_API_KEY", env={"EXA_API_KEY": "x" * 36})
    assert res["source"] == "env" and len(res["fp"]) == 12 and "x" * 36 not in res["fp"]


def test_validator_rejects_dead_env_value():
    res = lanes.resolve_secret("SOME_KEY", env={"SOME_KEY": "x" * 36}, validator=lambda v: False)
    assert res["source"] in ("keymaker", "unresolved")
    assert res["value"] != "x" * 36


def test_unresolved_secret_is_explicit():
    res = lanes.resolve_secret("DEFINITELY_NOT_A_REAL_KEY_NAME_XYZ", env=EMPTY, slots=1)
    assert res["source"] in ("unresolved", "keymaker")
    if res["source"] == "unresolved":
        assert res["value"] is None and res["fp"] is None
