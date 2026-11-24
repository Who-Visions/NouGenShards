"""Tests for space_orchestration.py and davos_persona.py (previously untested)."""
import json
import urllib.error

import pytest

from nougen_shards import davos_persona as dp
from nougen_shards import space_orchestration as so


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("NOUGEN_HF_SPACE_ID", "NOUGEN_HF_TOKEN_KEY", *so.DEFAULT_TOKEN_KEYS, "my_key"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(so.keymaker, "get_secret", lambda key: None)


# ---- space_orchestration ----

def test_normalize_space_id_strips_prefixes_and_slashes():
    assert so.normalize_space_id("https://huggingface.co/spaces/a/b/") == "a/b"
    assert so.normalize_space_id("https://huggingface.co/api/spaces/a/b") == "a/b"
    assert so.normalize_space_id("  a/b  ") == "a/b"


def test_normalize_space_id_default_and_env(monkeypatch):
    assert so.normalize_space_id() == so.DEFAULT_SPACE_ID
    monkeypatch.setenv("NOUGEN_HF_SPACE_ID", "x/y")
    assert so.normalize_space_id() == "x/y"
    assert so.normalize_space_id("p/q") == "p/q"


def test_space_log_url_and_invalid_kind():
    assert so.space_log_url("build", "a/b") == "https://huggingface.co/api/spaces/a/b/logs/build"
    with pytest.raises(ValueError):
        so.space_log_url("nope")


def test_resolve_credential_missing():
    cred = so.resolve_hf_credential()
    assert not cred.present and cred.key is None
    assert cred.redacted_header() == {}


def test_resolve_credential_order(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "tok-env")
    monkeypatch.setattr(so.keymaker, "get_secret",
                        lambda key: "tok-km" if key == "HUGGINGFACE_API_KEY" else None)
    # HUGGINGFACE_API_KEY precedes HF_TOKEN in DEFAULT_TOKEN_KEYS
    assert so.resolve_hf_credential().key == "HUGGINGFACE_API_KEY"
    # explicit key wins
    monkeypatch.setenv("my_key", "tok-mine")
    cred = so.resolve_hf_credential("my_key")
    assert (cred.key, cred.token) == ("my_key", "tok-mine")
    assert cred.redacted_header() == {"Authorization": "Bearer <redacted:my_key>"}


def test_build_log_request_never_leaks_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "secret-value")
    req = so.build_log_request("run", "a/b")
    assert req["token_present"] is True
    assert "secret-value" not in json.dumps(req)
    assert "secret-value" not in so.snapshot_json(kind="run", space_id="a/b")


class _Res:
    def __init__(self, data):
        self.data = data

    def read(self, n):
        return self.data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_log_snapshot_redacts_and_bounds(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "secret-value")
    seen = {}

    def fake_urlopen(req, timeout):
        seen["auth"] = req.get_header("Authorization")
        return _Res(b"log secret-value end")

    monkeypatch.setattr(so.urllib.request, "urlopen", fake_urlopen)
    out = so.fetch_log_snapshot("run", "a/b")
    assert seen["auth"] == "Bearer secret-value"
    assert out["status"] == "ok"
    assert "secret-value" not in out["body"]
    assert "<redacted:HF_TOKEN>" in out["body"]
    assert so.fetch_log_snapshot("run", "a/b", max_bytes=3)["body"] == "log"


def test_fetch_log_snapshot_error(monkeypatch):
    def boom(req, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(so.urllib.request, "urlopen", boom)
    out = so.fetch_log_snapshot("build", "a/b")
    assert out["status"] == "error"
    assert "URLError" in out["error"]
    assert out["token_present"] is False


def test_anchor_truncates(monkeypatch):
    from nougen_shards import agent_hooks
    monkeypatch.setattr(agent_hooks, "latest_handoff_text", lambda limit=None: "X" * 5000)
    anchor = so.get_space_orchestration_anchor(max_chars=400, space_id="a/b")
    assert len(anchor) <= 400
    assert anchor.endswith("[SPACE_ANCHOR_TRUNCATED]")
    short = so.get_space_orchestration_anchor(max_chars=100000, space_id="a/b")
    assert "[HF_SPACE_ORCHESTRATION]" in short and "Space: a/b" in short
    assert "key=missing; present=false" in short


# ---- davos_persona ----

@pytest.fixture
def no_vault(monkeypatch):
    monkeypatch.setattr(dp, "_vault_hits", lambda name, limit=3: [])
    monkeypatch.setattr(dp, "builtin_identities", lambda: [
        dp.self_identity(),
        dp.Identity("Sol-Ai", "model", ("sol ai", "sol")),
        dp.Identity("Iris-Ai", "model", ("iris",)),
    ])


def test_norm():
    assert dp._norm("  Sol_Ai-X ") == "sol ai x"
    assert dp._norm(None) == ""


def test_self_lane_env(monkeypatch):
    monkeypatch.setenv("NOUGEN_DAVOS_LANE", "lane-7")
    assert dp.self_identity().home == "lane-7"


def test_resolve_empty_and_self(no_vault):
    assert dp.resolve("  ")["confidence"] == "none"
    r = dp.resolve("yourself")
    assert r["confidence"] == "exact" and r["match"]["canonical"] == "DavOs"


def test_resolve_exact_alias_and_normalization(no_vault, tmp_path):
    reg = tmp_path / "none.json"
    assert dp.resolve("sol_ai", registry=reg)["confidence"] == "exact"
    assert dp.resolve("SOL-AI", registry=reg)["confidence"] == "exact"
    r = dp.resolve("Sol", registry=reg)
    assert r["confidence"] == "alias" and r["match"]["canonical"] == "Sol-Ai"


def test_resolve_fuzzy_and_none(no_vault, tmp_path):
    reg = tmp_path / "none.json"
    r = dp.resolve("irris", registry=reg)
    assert r["confidence"] == "fuzzy" and r["match"]["canonical"] == "Iris-Ai"
    r = dp.resolve("zzzzzz", registry=reg)
    assert r["confidence"] == "none" and r["match"] is None
    assert "guess" in r["disambiguation"]


def test_resolve_vault_makes_fuzzy_ambiguous(monkeypatch, tmp_path):
    monkeypatch.setattr(dp, "builtin_identities", lambda: [dp.Identity("Iris-Ai", "model", ("iris",))])
    monkeypatch.setattr(dp, "_vault_hits", lambda name, limit=3: [{"title": "t", "id": 1, "db_index": 0}])
    r = dp.resolve("irris", registry=tmp_path / "none.json")
    assert r["confidence"] == "ambiguous" and r["match"] is None
    assert len(r["vault_hits"]) == 1


def test_vault_fallback_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(dp, "builtin_identities", lambda: [])
    monkeypatch.setattr(dp, "_vault_hits", lambda *a, **k: pytest.fail("vault queried"))
    assert dp.resolve("x", vault_fallback=False, registry=tmp_path / "n.json")["confidence"] == "none"


def test_registry_load_and_override(monkeypatch, tmp_path):
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({"identities": [
        {"canonical": "sol-ai", "kind": "persona", "aliases": ["solly"], "role": "override"},
        {"canonical": "Zed"}, {"nocanonical": 1}, "junk"]}), encoding="utf-8")
    ids = dp.registry_identities(reg)
    assert [i.canonical for i in ids] == ["sol-ai", "Zed"]
    assert ids[1].kind == "persona" and ids[1].source == "registry"
    monkeypatch.setattr(dp, "builtin_identities", lambda: [dp.Identity("Sol-Ai", "model")])
    merged = {dp._norm(i.canonical): i for i in dp.all_identities(reg)}
    assert merged["sol ai"].source == "registry"
    assert dp.resolve("solly", vault_fallback=False, registry=reg)["match"]["role"] == "override"


def test_registry_bad_file_and_list_shape(tmp_path):
    assert dp.registry_identities(tmp_path / "missing.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert dp.registry_identities(bad) == []
    lst = tmp_path / "l.json"
    lst.write_text('[{"canonical": "A", "aliases": null}]', encoding="utf-8")
    assert dp.registry_identities(lst)[0].aliases == ()


def test_registry_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_PERSONA_REGISTRY", str(tmp_path / "x.json"))
    assert dp.registry_path() == tmp_path / "x.json"


def test_anchor_uses_real_handoff_reader(monkeypatch, tmp_path):
    """Regression: the anchor called a nonexistent hooks.get_latest_anchor."""
    from nougen_shards import handoff
    monkeypatch.setattr(handoff, "HANDOFF_DIR", tmp_path)
    (tmp_path / "handoff_1.md").write_text("HELLO-HANDOFF", encoding="utf-8")
    assert "HELLO-HANDOFF" in so.get_space_orchestration_anchor(space_id="a/b")
