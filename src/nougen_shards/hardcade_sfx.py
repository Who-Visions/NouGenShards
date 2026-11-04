"""Hardcade SFX: play the move's sound when a fleet operation lands.

Each fleet operation maps to its Hardcade move (docs/hardcade-lexicon.md):
shard capture is a HADOUKEN, a relay leg sent forward is a SHORYUKEN, a peer
message is a SONIC BOOM, a fetch is a LOOT, a search sweep is a HURRICANE
KICK. A failed command plays LOSE.

Sounds are read from ``~/.nougen/sfx/hardcade/<move>.mp3`` (override with
``NOUGEN_SFX_DIR``). They are never shipped in the repo. Playback is
fire-and-forget through the platform player and can never break or slow the
operation that triggered it: a missing file, missing player or any error is
silently ignored.

Off switch: ``NOUGEN_SFX=0``. It is also off under pytest and in CI.
"""

from __future__ import annotations

import functools
import inspect
import os
import shutil
import subprocess
import sys
from pathlib import Path

# CLI command (and optional first subcommand) -> move.
CLI_MOVES: dict[str, str] = {
    "add": "hadouken",
    "mark": "hadouken",
    "ingest": "loot",
    "tube": "loot",
    "nougentube": "loot",
    "arxiv": "loot",
    "transcribe": "loot",
    "search": "hurricane_kick",
    "msg": "sonic_boom",
    "destiny": "hadouken",
    "dream": "ultra",
    "evolve": "ultra",
    "sweep": "zangief_spd",
    "zombies": "zangief_spd",
    "hi": "fight",
    "bye": "win",
    "claim": "fight",
    "pr": "perfect",
}

# `nougen relay <sub>` and `nougen handoff <sub>` -> move.
SUB_MOVES: dict[tuple[str, str], str] = {
    ("relay", "create"): "shoryuken",
    ("relay", "ack"): "fight",
    ("relay", "close"): "win",
    ("relay", "touchdown"): "perfect",
    ("relay", "open"): "spinning_bird_kick",
    ("relay", "read"): "flash_kick",
    ("handoff", "create"): "new_challenger",
    ("handoff", "checkpoint"): "hadouken",
    ("handoff", "read"): "flash_kick",
    ("msg", "send"): "sonic_boom",
}

# MCP tool name -> move.
TOOL_MOVES: dict[str, str] = {
    "capture_experience": "hadouken",
    "add_shard": "hadouken",
    "promote_context_to_shard": "hadouken",
    "create_destiny": "hadouken",
    "checkpoint_session": "hadouken",
    "recall_memory": "hurricane_kick",
    "recall_layered": "hurricane_kick",
    "recall_related": "hurricane_kick",
    "search_shards": "hurricane_kick",
    "search_context": "hurricane_kick",
    "search_destinies": "hurricane_kick",
    "nougenmsg_search": "hurricane_kick",
    "nougenmsg_send": "sonic_boom",
    "nougenmsg_inbox": "flash_kick",
    "relay_open": "spinning_bird_kick",
    "claim_lane": "fight",
    "release_lane": "win",
    "session_hi": "fight",
    "session_bye": "win",
    "fetch_web_sandboxed": "loot",
    "nougen_web_fetch": "loot",
    "nougen_web_crawl": "loot",
    "transcribe_media": "loot",
    "arxiv_paper": "loot",
    "arxiv_radar": "loot",
    "evolve_skill": "ultra",
    "run_brain_scan": "zangief_spd",
}

_PLAYERS = (
    ("afplay",),
    ("paplay",),
    ("ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"),
    ("mpg123", "-q"),
)


def enabled() -> bool:
    flag = os.environ.get("NOUGEN_SFX", "").strip().lower()
    if flag in {"0", "off", "false", "no"}:
        return False
    if flag in {"1", "on", "true", "yes"}:
        return True
    return not ("pytest" in sys.modules or os.environ.get("CI"))


def sfx_dir() -> Path:
    return Path(os.environ.get("NOUGEN_SFX_DIR") or Path.home() / ".nougen" / "sfx" / "hardcade")


def _player() -> tuple[str, ...] | None:
    for cmd in _PLAYERS:
        if shutil.which(cmd[0]):
            return cmd
    return None


def play(move: str | None) -> bool:
    """Fire the move's sound without waiting. Returns True if a player was spawned."""
    if not move or not enabled():
        return False
    try:
        path = sfx_dir() / f"{move}.mp3"
        player = _player()
        if not path.is_file() or player is None:
            return False
        subprocess.Popen(
            [*player, str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False


def move_for_cli(command: str | None, argv: list[str] | None = None) -> str | None:
    sub = next((a for a in (argv or []) if not a.startswith("-")), None)
    if command and sub and (command, sub) in SUB_MOVES:
        return SUB_MOVES[(command, sub)]
    return CLI_MOVES.get(command or "")


def run_cli(command: str | None, argv: list[str], fn, *args, **kwargs):
    """Run a CLI handler, then play its move (or LOSE if it failed)."""
    try:
        result = fn(*args, **kwargs)
    except SystemExit as exc:
        play(move_for_cli(command, argv) if exc.code in (0, None) else "lose")
        raise
    except BaseException:
        play("lose")
        raise
    play(move_for_cli(command, argv))
    return result


def wrap_tool(fn):
    """Wrap an MCP tool so its move plays after the call returns."""
    move = TOOL_MOVES.get(fn.__name__)
    if move is None:
        return fn

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                play("lose")
                raise
            play(move)
            return result

        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except Exception:
            play("lose")
            raise
        play(move)
        return result

    return wrapper


def install_on(server) -> None:
    """Make every ``@server.tool()`` registration wrap its function with SFX."""
    original = getattr(server, "tool", None)
    if original is None or getattr(original, "_hardcade_sfx", False):
        return

    @functools.wraps(original)
    def tool(*dargs, **dkwargs):
        decorator = original(*dargs, **dkwargs)

        def register(fn):
            return decorator(wrap_tool(fn))

        return register

    tool._hardcade_sfx = True
    try:
        server.tool = tool
    except Exception:
        pass
