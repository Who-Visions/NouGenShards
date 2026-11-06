"""Hardcade SFX: config-driven resolution, user sounds, never breaks the operation."""

import asyncio
import json

import pytest

from nougen_shards import hardcade_sfx as sfx


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_HOME", str(tmp_path))
    monkeypatch.delenv("NOUGEN_SFX_DIR", raising=False)
    monkeypatch.delenv("NOUGEN_SFX_MAP", raising=False)
    (tmp_path / "sfx" / "hardcade").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def spawned(monkeypatch, home):
    calls = []
    monkeypatch.setenv("NOUGEN_SFX", "1")
    monkeypatch.setattr(sfx, "_player", lambda: ("afplay",))
    monkeypatch.setattr(sfx.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    return calls


def _sound(home, name):
    path = home / "sfx" / "hardcade" / name
    path.write_bytes(b"x")
    return path


def _names(calls):
    return [c[1].rsplit("/", 1)[1] for c in calls]


def test_off_under_pytest_by_default(monkeypatch):
    monkeypatch.delenv("NOUGEN_SFX", raising=False)
    assert sfx.enabled() is False


def test_off_switch_wins(monkeypatch, home):
    _sound(home, "hadouken.wav")
    monkeypatch.setenv("NOUGEN_SFX", "0")
    assert sfx.play("cli:add") is False


def test_defaults_ship_as_data(home):
    moves = sfx.config()["moves"]
    assert moves["cli:relay create"] == "shoryuken"
    assert moves["tool:nougenmsg_send"] == "sonic_boom"
    assert moves["fail"] == "lose"
    assert sfx.config()["sounds"] == {}


def test_cli_key_prefers_mapped_subcommand(home):
    assert sfx.cli_key("relay", ["--json", "create", "x"]) == "cli:relay create"
    assert sfx.cli_key("relay", ["frobnicate"]) == "cli:relay"
    assert sfx.cli_key("add", ["text"]) == "cli:add"


def test_nothing_plays_without_user_sounds(spawned):
    assert sfx.play("cli:relay create") is False
    assert spawned == []


def test_move_file_in_any_format(spawned, home):
    _sound(home, "shoryuken.aiff")
    assert sfx.play("cli:relay create") is True
    assert _names(spawned) == ["shoryuken.aiff"]


def test_user_map_remaps_and_points_anywhere(spawned, home, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("mine") / "ping.ogg"
    elsewhere.write_bytes(b"x")
    _sound(home, "hadouken.wav")
    (home / "sfx" / "hardcade.json").write_text(json.dumps({
        "moves": {"tool:cf_status": "hadouken"},
        "sounds": {"tool:nougenmsg_send": str(elsewhere)},
    }))
    assert sfx.play("tool:cf_status") is True          # new mapping from user data
    assert sfx.play("tool:nougenmsg_send") is True     # per-operation sound beats move
    assert _names(spawned) == ["hadouken.wav", "ping.ogg"]


def test_env_overrides_locations(spawned, monkeypatch, tmp_path_factory):
    folder = tmp_path_factory.mktemp("snd")
    (folder / "lose.mp3").write_bytes(b"x")
    monkeypatch.setenv("NOUGEN_SFX_DIR", str(folder))
    assert sfx.play("fail") is True


def test_broken_map_is_ignored(spawned, home):
    (home / "sfx" / "hardcade.json").write_text("{not json")
    _sound(home, "hadouken.mp3")
    assert sfx.play("cli:add") is True


def test_run_cli_plays_then_fail_sound(spawned, home):
    _sound(home, "shoryuken.wav")
    _sound(home, "lose.wav")
    assert sfx.run_cli("relay", ["create"], lambda: "ok") == "ok"
    with pytest.raises(SystemExit):
        sfx.run_cli("relay", ["create"], lambda: (_ for _ in ()).throw(SystemExit(2)))
    assert _names(spawned) == ["shoryuken.wav", "lose.wav"]


def test_player_error_never_breaks_operation(monkeypatch, home):
    _sound(home, "hadouken.wav")
    monkeypatch.setenv("NOUGEN_SFX", "1")
    monkeypatch.setattr(sfx, "_player", lambda: ("afplay",))

    def boom(*a, **k):
        raise OSError("no audio device")

    monkeypatch.setattr(sfx.subprocess, "Popen", boom)
    assert sfx.run_cli("add", [], lambda: 7) == 7


def test_wrap_tool_sync_async_and_signature(spawned, home):
    _sound(home, "sonic_boom.wav")
    _sound(home, "hadouken.wav")

    def nougenmsg_send(target: str, body: str = "") -> str:
        return f"{target}:{body}"

    async def add_shard(text: str) -> str:
        return text

    wrapped = sfx.wrap_tool(nougenmsg_send)
    assert wrapped("blade", body="hi") == "blade:hi"
    assert list(sfx.inspect.signature(wrapped).parameters) == ["target", "body"]
    assert asyncio.run(sfx.wrap_tool(add_shard)("t")) == "t"
    assert _names(spawned) == ["sonic_boom.wav", "hadouken.wav"]


def test_install_on_wraps_registered_tools(spawned, home):
    _sound(home, "hadouken.wav")
    registered = {}

    class Server:
        def tool(self, *a, **k):
            def deco(fn):
                registered[fn.__name__] = fn
                return fn
            return deco

    server = Server()
    sfx.install_on(server)
    sfx.install_on(server)  # idempotent

    @server.tool()
    def capture_experience(text: str) -> str:
        return text

    assert registered["capture_experience"]("x") == "x"
    assert _names(spawned) == ["hadouken.wav"]


def test_tool_failure_payload_plays_fail(monkeypatch):
    from nougen_shards import hardcade_sfx as sfx

    played = []
    monkeypatch.setattr(sfx, "play", lambda key: played.append(key) or True)

    def ok_tool():
        return {"ok": True}

    def bad_tool():
        return {"ok": False, "error": "nope"}

    def err_text_tool():
        return "Error: node unreachable"

    sfx.wrap_tool(ok_tool)()
    sfx.wrap_tool(bad_tool)()
    sfx.wrap_tool(err_text_tool)()
    assert played == ["tool:ok_tool", "fail", "fail"]
