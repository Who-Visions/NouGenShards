"""Rhea's $0 lane must find its OpenRouter key in the keymaker when the
launcher did not export it, and must still prefer the environment."""
import rhea_noir
from nougen_shards import keymaker


def test_env_key_wins(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    monkeypatch.setattr(keymaker, "get_secret", lambda k: "vault-key")
    assert rhea_noir._free_lane_key() == "env-key"


def test_keymaker_used_when_env_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(keymaker, "get_secret", lambda k: "vault-key" if k == "OPENROUTER_API_KEY" else None)
    assert rhea_noir._free_lane_key() == "vault-key"


def test_free_walk_uses_keymaker_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("NOUGEN_RHEA_FREE_MODELS", "m1:free")
    monkeypatch.setattr(keymaker, "get_secret", lambda k: "vault-key")
    seen = {}

    def fake_call(url, token, model, messages, timeout_s=120.0):
        seen.update(token=token, model=model)
        return "hi"

    monkeypatch.setattr(rhea_noir, "_openai_call", fake_call)
    assert rhea_noir._try_free([{"role": "user", "content": "x"}], 30) == ("hi", "free:m1:free")
    assert seen == {"token": "vault-key", "model": "m1:free"}


def test_no_key_anywhere_skips_free_lane(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(keymaker, "get_secret", lambda k: None)
    assert rhea_noir._try_free([{"role": "user", "content": "x"}], 30) is None
