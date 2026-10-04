"""tools/voice: WhoArt-favorites voice resolver and speak() fallbacks. No SSH, audio or model is touched."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

VOICE = Path(__file__).resolve().parents[1] / "tools" / "voice"


def _load(name):
    sys.path.insert(0, str(VOICE))
    spec = importlib.util.spec_from_file_location(name, VOICE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sync(monkeypatch):
    monkeypatch.delenv("NOUGEN_VOICE", raising=False)
    monkeypatch.delenv("NOUGEN_VOICE_SPEED", raising=False)
    mod = _load("whoart_voice_sync")
    monkeypatch.setattr(mod, "get_voice_favorites", lambda force_refresh=False: {})
    return mod


def test_default_without_favorites_is_river(sync):
    assert sync.resolve_dynamic_voice() == ("af_river", 1.05)


@pytest.mark.parametrize("alias", ["river", "Kokoro River", "af_river"])
def test_river_aliases(sync, alias):
    assert sync.resolve_dynamic_voice(alias) == ("af_river", 1.05)


def test_stale_emma_env_falls_through_to_favorites(sync, monkeypatch):
    monkeypatch.setenv("NOUGEN_VOICE", "bf_emma")
    monkeypatch.setattr(sync, "get_voice_favorites",
                        lambda force_refresh=False: {"female": [{"voice_id": "af_nova", "speed": 0.96}]})
    assert sync.resolve_dynamic_voice() == ("af_nova", 0.96)


def test_explicit_voice_beats_favorites(sync, monkeypatch):
    monkeypatch.setattr(sync, "get_voice_favorites",
                        lambda force_refresh=False: {"female": [{"voice_id": "af_nova", "speed": 0.96}]})
    assert sync.resolve_dynamic_voice("adam") == ("am_adam", 0.98)


def test_env_override_wins(sync, monkeypatch):
    monkeypatch.setenv("NOUGEN_VOICE", "river")
    assert sync.resolve_dynamic_voice()[0] == "af_river"


def test_unknown_voice_passes_through_with_env_speed(sync, monkeypatch):
    monkeypatch.setenv("NOUGEN_VOICE_SPEED", "0.9")
    assert sync.resolve_dynamic_voice("bm_george") == ("bm_george", 0.9)


def test_unreachable_whoart_uses_cache_then_empty(monkeypatch, tmp_path):
    mod = _load("whoart_voice_sync")
    monkeypatch.setattr(mod, "CACHE_FILE", tmp_path / "fav.json")
    monkeypatch.setattr(mod, "fetch_whoart_favorites", lambda: {})
    assert mod.get_voice_favorites() == {}                       # no cache, no remote
    (tmp_path / "fav.json").write_text('{"updated_at": 0, "favorites": {"female": [{"voice_id": "af_heart"}]}}')
    assert mod.get_voice_favorites()["female"][0]["voice_id"] == "af_heart"   # stale cache beats nothing


def test_fetch_uses_accept_new_not_no_host_check(monkeypatch, tmp_path):
    mod = _load("whoart_voice_sync")
    key = tmp_path / "k"; key.write_text("x")
    monkeypatch.setattr(mod, "SSH_KEY", key)
    monkeypatch.setenv("NOUGEN_WHOART_SSH", "user@host.invalid"); monkeypatch.setenv("NOUGEN_WHOART_BIN", "remote-bin")
    seen = {}
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: seen.setdefault("cmd", cmd) and subprocess.CompletedProcess(cmd, 1, "", ""))
    mod.fetch_whoart_favorites()
    assert "StrictHostKeyChecking=accept-new" in seen["cmd"] and "StrictHostKeyChecking=no" not in seen["cmd"]


def test_speak_without_args_reaches_native_say_fallback(monkeypatch):
    sp = _load("speak")
    monkeypatch.setattr(sp, "get_dynamic_voice_and_speed", lambda v=None, s=None: ("bf_emma", 1.0))
    monkeypatch.setattr(sp, "VOICE_VENV", Path("/nonexistent"))
    calls = []
    monkeypatch.setattr(sp.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    sp.speak("hello")                                            # no voice/speed args, no neural runner: falls through to say
    assert any(c[0] == "say" for c in calls)


def test_speak_ignores_empty_text(monkeypatch):
    sp = _load("speak")
    monkeypatch.setattr(sp.subprocess, "run", lambda *a, **k: pytest.fail("must not run"))
    sp.speak("   ")


def test_no_remote_configured_means_no_ssh(monkeypatch, tmp_path):
    mod = _load("whoart_voice_sync")
    key = tmp_path / "k"; key.write_text("x")
    monkeypatch.setattr(mod, "SSH_KEY", key)
    monkeypatch.setattr(mod, "REMOTE_FILE", tmp_path / "missing.json")
    monkeypatch.delenv("NOUGEN_WHOART_SSH", raising=False); monkeypatch.delenv("NOUGEN_WHOART_BIN", raising=False)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: pytest.fail("must not ssh"))
    assert mod.fetch_whoart_favorites() == {}


def test_remote_read_from_state_file(monkeypatch, tmp_path):
    mod = _load("whoart_voice_sync")
    f = tmp_path / "r.json"; f.write_text('{"ssh": "u@h.invalid", "bin": "rb"}')
    monkeypatch.setattr(mod, "REMOTE_FILE", f)
    monkeypatch.delenv("NOUGEN_WHOART_SSH", raising=False); monkeypatch.delenv("NOUGEN_WHOART_BIN", raising=False)
    assert mod._remote() == ("u@h.invalid", "rb")
