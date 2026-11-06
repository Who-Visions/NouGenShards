"""Hardcade SFX: play a sound when a fleet operation lands.

Every fleet operation resolves to a Hardcade move (docs/hardcade-lexicon.md),
and every move resolves to a sound you supply. Nothing is hard-wired here:

* Operation -> move comes from the shipped defaults in ``sfx/moves.json``,
  overlaid by the ``moves`` section of your own map file.
* Move (or operation) -> sound comes from the ``sounds`` section of your map
  file, else from a file named after the move in your sound folder, in any of
  the formats in ``AUDIO_EXTS``.

Operation keys are ``cli:<command>``, ``cli:<command> <subcommand>``,
``tool:<mcp tool name>`` and ``fail``. A user map looks like::

    {"moves":  {"tool:cf_deploy_worker": "shoryuken"},
     "sounds": {"hadouken": "~/sounds/boom.wav", "tool:nougenmsg_send": "~/ping.mp3"}}

Locations, all resolved at call time:
map file ``NOUGEN_SFX_MAP`` else ``$NOUGEN_HOME/sfx/hardcade.json``;
sound folder ``NOUGEN_SFX_DIR`` else ``$NOUGEN_HOME/sfx/hardcade``;
``NOUGEN_HOME`` defaults to ``~/.nougen`` as elsewhere in NouGenShards.

No sounds ship with NouGenShards. With none configured, nothing plays.
Playback is fire-and-forget and can never break or slow the operation: a
missing file, missing player or any error is ignored. Off with
``NOUGEN_SFX=0``, and off by default under pytest and CI.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

AUDIO_EXTS = (".wav", ".mp3", ".aiff", ".aif", ".m4a", ".ogg", ".flac")

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


def _home() -> Path:
    return Path(os.environ.get("NOUGEN_HOME") or Path.home() / ".nougen").expanduser()


def sfx_dir() -> Path:
    return Path(os.environ.get("NOUGEN_SFX_DIR") or _home() / "sfx" / "hardcade").expanduser()


def _map_path() -> Path:
    return Path(os.environ.get("NOUGEN_SFX_MAP") or _home() / "sfx" / "hardcade.json").expanduser()


def _read_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def config() -> dict[str, dict[str, str]]:
    """Shipped default moves overlaid with the user's map file."""
    try:
        defaults = _read_json(resources.files("nougen_shards.sfx").joinpath("moves.json").read_text())
    except Exception:
        defaults = {}
    try:
        user = _read_json(_map_path().read_text())
    except Exception:
        user = {}
    merged: dict[str, dict[str, str]] = {}
    for section in ("moves", "sounds"):
        layer: dict[str, str] = {}
        for source in (defaults, user):
            block = source.get(section)
            if isinstance(block, dict):
                layer.update({str(k).lower(): str(v) for k, v in block.items()})
        merged[section] = layer
    return merged


def cli_key(command: str | None, argv: list[str] | None = None, moves: dict | None = None) -> str | None:
    """``cli:<command> <sub>`` when that is mapped, else ``cli:<command>``."""
    if not command:
        return None
    moves = config()["moves"] if moves is None else moves
    sub = next((a for a in (argv or []) if not a.startswith("-")), None)
    if sub and f"cli:{command} {sub}".lower() in moves:
        return f"cli:{command} {sub}".lower()
    return f"cli:{command}".lower()


def resolve(key: str | None) -> Path | None:
    """The sound file for an operation key, or None when none is configured."""
    if not key:
        return None
    cfg = config()
    key = key.lower()
    move = cfg["moves"].get(key, key if ":" not in key else None)
    for name in (key, move):
        if name and name in cfg["sounds"]:
            path = Path(cfg["sounds"][name]).expanduser()
            return path if path.is_file() else None
    if not move:
        return None
    folder = sfx_dir()
    for ext in AUDIO_EXTS:
        path = folder / f"{move}{ext}"
        if path.is_file():
            return path
    return None


def _player() -> tuple[str, ...] | None:
    for cmd in _PLAYERS:
        if shutil.which(cmd[0]):
            return cmd
    return None


def play(key: str | None) -> bool:
    """Fire the sound for ``key`` without waiting. True if a player was spawned."""
    if not key or not enabled():
        return False
    try:
        path = resolve(key)
        player = _player() if path else None
        if path is None or player is None:
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


def run_cli(command: str | None, argv: list[str], fn, *args, **kwargs):
    """Run a CLI handler, then play its sound (or the ``fail`` sound)."""
    try:
        result = fn(*args, **kwargs)
    except SystemExit as exc:
        code = exc.code
        _safe_play(lambda: cli_key(command, argv) if code in (0, None) else "fail")
        raise
    except BaseException:
        _safe_play(lambda: "fail")
        raise
    _safe_play(lambda: cli_key(command, argv))
    return result


def _safe_play(key_fn) -> None:
    try:
        play(key_fn())
    except Exception:
        pass


def _reports_failure(result) -> bool:
    """True when a tool returned normally but its payload says the call failed."""
    if isinstance(result, dict):
        if result.get("ok") is False or result.get("success") is False or result.get("isError") is True:
            return True
        if str(result.get("status", "")).lower() in ("error", "failed", "failure"):
            return True
        return bool(result.get("error"))
    if isinstance(result, str):
        return result.lstrip().lower().startswith(("error", "failed"))
    return False


def wrap_tool(fn):
    """Wrap an MCP tool so ``tool:<name>`` plays after the call returns."""
    key = f"tool:{fn.__name__}"

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                _safe_play(lambda: "fail")
                raise
            _safe_play(lambda: "fail" if _reports_failure(result) else key)
            return result

        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except Exception:
            _safe_play(lambda: "fail")
            raise
        _safe_play(lambda: "fail" if _reports_failure(result) else key)
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
