"""Hardcade SFX: moves map to the right sound and never break the operation."""

import asyncio

import pytest

from nougen_shards import hardcade_sfx as sfx


@pytest.fixture
def spawned(monkeypatch, tmp_path):
    calls = []
    for move in ("hadouken", "shoryuken", "sonic_boom", "lose", "fight"):
        (tmp_path / f"{move}.mp3").write_bytes(b"x")
    monkeypatch.setenv("NOUGEN_SFX", "1")
    monkeypatch.setenv("NOUGEN_SFX_DIR", str(tmp_path))
    monkeypatch.setattr(sfx, "_player", lambda: ("afplay",))
    monkeypatch.setattr(sfx.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    return calls


def test_off_under_pytest_by_default(monkeypatch):
    monkeypatch.delenv("NOUGEN_SFX", raising=False)
    assert sfx.enabled() is False


def test_off_switch_wins(monkeypatch):
    monkeypatch.setenv("NOUGEN_SFX", "0")
    assert sfx.play("hadouken") is False


def test_cli_subcommand_moves():
    assert sfx.move_for_cli("relay", ["create", "-t", "x"]) == "shoryuken"
    assert sfx.move_for_cli("relay", ["--json", "ack", "id"]) == "fight"
    assert sfx.move_for_cli("handoff", ["create"]) == "new_challenger"
    assert sfx.move_for_cli("add", ["text"]) == "hadouken"
    assert sfx.move_for_cli("search", ["q"]) == "hurricane_kick"
    assert sfx.move_for_cli("status", []) is None


def test_play_spawns_player(spawned):
    assert sfx.play("hadouken") is True
    assert spawned[0][0] == "afplay" and spawned[0][1].endswith("hadouken.mp3")


def test_missing_sound_is_silent(spawned):
    assert sfx.play("perfect") is False
    assert spawned == []


def test_run_cli_plays_move_then_lose_on_failure(spawned):
    assert sfx.run_cli("relay", ["create"], lambda: "ok") == "ok"
    with pytest.raises(SystemExit):
        sfx.run_cli("relay", ["create"], lambda: (_ for _ in ()).throw(SystemExit(2)))
    assert [c[1].rsplit("/", 1)[1] for c in spawned] == ["shoryuken.mp3", "lose.mp3"]


def test_player_error_never_breaks_operation(monkeypatch, tmp_path):
    (tmp_path / "hadouken.mp3").write_bytes(b"x")
    monkeypatch.setenv("NOUGEN_SFX", "1")
    monkeypatch.setenv("NOUGEN_SFX_DIR", str(tmp_path))
    monkeypatch.setattr(sfx, "_player", lambda: ("afplay",))

    def boom(*a, **k):
        raise OSError("no audio device")

    monkeypatch.setattr(sfx.subprocess, "Popen", boom)
    assert sfx.run_cli("add", [], lambda: 7) == 7


def test_wrap_tool_sync_async_and_signature(spawned):
    def nougenmsg_send(target: str, body: str = "") -> str:
        return f"{target}:{body}"

    async def add_shard(text: str) -> str:
        return text

    wrapped = sfx.wrap_tool(nougenmsg_send)
    assert wrapped("blade", body="hi") == "blade:hi"
    assert list(sfx.inspect.signature(wrapped).parameters) == ["target", "body"]
    assert asyncio.run(sfx.wrap_tool(add_shard)("t")) == "t"
    assert [c[1].rsplit("/", 1)[1] for c in spawned] == ["sonic_boom.mp3", "hadouken.mp3"]


def test_unmapped_tool_is_untouched():
    def cf_status():
        return 1

    assert sfx.wrap_tool(cf_status) is cf_status


def test_install_on_wraps_registered_tools(spawned):
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
    assert [c[1].rsplit("/", 1)[1] for c in spawned] == ["hadouken.mp3"]
