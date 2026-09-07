"""Semantic terminal UI layer for the NouGen CLI.

One place decides what a colour means, whether motion is allowed, and how a
payload is rendered. Commands emit structured data; this module decides the
representation (rich TTY, stable plain text, or JSON).

Nothing here is hardcoded to an environment: width, colour, unicode, motion and
verbosity all resolve env -> probe -> logged fallback (see `resolution_report`).
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

# Fallback constants. These are last resorts, never the source of truth: every
# one of them is reported as `source="fallback"` by `resolution_report()`.
FALLBACK_WIDTH = 80
FALLBACK_SPINNER_INTERVAL_S = 0.12
MIN_WIDTH = 20
MAX_WIDTH = 200

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


class Mode(str, Enum):
    """How output should be represented."""

    RICH = "rich"
    PLAIN = "plain"
    JSON = "json"


class Role(str, Enum):
    """Semantic roles. Colour means the same thing everywhere."""

    SUCCESS = "success"
    WARN = "warn"
    ERROR = "error"
    NET = "net"
    MODEL = "model"
    META = "meta"
    CURRENT = "current"
    HEADING = "heading"


# The only place ANSI codes live.
_SGR = {
    Role.SUCCESS: "32",
    Role.WARN: "33",
    Role.ERROR: "31",
    Role.NET: "36",
    Role.MODEL: "35",
    Role.META: "90",
    Role.CURRENT: "97",
    Role.HEADING: "1;97",
}

_GLYPHS_UNICODE = {
    Role.SUCCESS: "✔",
    Role.WARN: "△",
    Role.ERROR: "✘",
    Role.NET: "●",
    Role.MODEL: "◆",
    Role.META: "·",
    Role.CURRENT: "→",
    Role.HEADING: "",
}

_GLYPHS_ASCII = {
    Role.SUCCESS: "OK",
    Role.WARN: "!",
    Role.ERROR: "X",
    Role.NET: "*",
    Role.MODEL: "+",
    Role.META: "-",
    Role.CURRENT: ">",
    Role.HEADING: "",
}

_SPINNER_UNICODE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPINNER_ASCII = "|/-\\"

_BOX_UNICODE = {"h": "─", "v": "│", "tl": "╭", "tr": "╮",
                "bl": "╰", "br": "╯"}
_BOX_ASCII = {"h": "-", "v": "|", "tl": "+", "tr": "+", "bl": "+", "br": "+"}

_TREE_UNICODE = {"tee": "├─ ", "end": "└─ ", "pipe": "│  ", "gap": "   "}
_TREE_ASCII = {"tee": "|- ", "end": "`- ", "pipe": "|  ", "gap": "   "}

# Presentation flags consumed globally, in any argv position.
_GLOBAL_FLAGS = {"--plain", "--no-color", "--no-colour", "--quiet", "--verbose"}


def _env_flag(name: str, env: Mapping[str, str]) -> bool | None:
    """Tri-state env flag: True, False, or None when unset/unparsable."""
    raw = env.get(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    # NO_COLOR is set-means-on regardless of value, per the spec.
    return True if name == "NO_COLOR" and value != "" else None


@dataclass
class Capabilities:
    """Resolved terminal capabilities plus where each value came from."""

    mode: Mode = Mode.PLAIN
    color: bool = False
    unicode: bool = False
    motion: bool = False
    width: int = FALLBACK_WIDTH
    verbose: bool = False
    quiet: bool = False
    sources: dict[str, str] = field(default_factory=dict)


def detect(
    *,
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    stream: Any | None = None,
    as_json: bool | None = None,
) -> Capabilities:
    """Resolve capabilities from flags, env and a live probe of `stream`."""
    env = os.environ if env is None else env
    argv = [] if argv is None else list(argv)
    stream = sys.stdout if stream is None else stream
    src: dict[str, str] = {}

    flag_plain = "--plain" in argv
    flag_no_color = "--no-color" in argv or "--no-colour" in argv
    flag_quiet = "--quiet" in argv
    flag_verbose = "--verbose" in argv
    flag_json = as_json if as_json is not None else ("--json" in argv)

    try:
        tty = bool(stream.isatty())
    except (AttributeError, ValueError):
        tty = False
    src["tty"] = "probe"

    env_plain = _env_flag("NOUGEN_PLAIN", env)
    dumb = env.get("TERM", "").strip().lower() == "dumb"
    ci = _env_flag("CI", env) is True

    if flag_json:
        mode = Mode.JSON
        src["mode"] = "flag:--json"
    elif flag_plain:
        mode = Mode.PLAIN
        src["mode"] = "flag:--plain"
    elif env_plain is True:
        mode = Mode.PLAIN
        src["mode"] = "env:NOUGEN_PLAIN"
    elif dumb:
        mode = Mode.PLAIN
        src["mode"] = "env:TERM=dumb"
    elif tty:
        mode = Mode.RICH
        src["mode"] = "probe:tty"
    else:
        mode = Mode.PLAIN
        src["mode"] = "probe:not-a-tty"

    color_pref = env.get("NOUGEN_COLOR", "auto").strip().lower()
    no_color = _env_flag("NO_COLOR", env) is True
    if flag_no_color:
        color, src["color"] = False, "flag:--no-color"
    elif no_color:
        color, src["color"] = False, "env:NO_COLOR"
    elif color_pref == "never":
        color, src["color"] = False, "env:NOUGEN_COLOR=never"
    elif color_pref == "always":
        color, src["color"] = True, "env:NOUGEN_COLOR=always"
    else:
        color = mode is Mode.RICH
        src["color"] = "derived:mode"

    uni_pref = _env_flag("NOUGEN_UNICODE", env)
    if uni_pref is not None:
        unicode_ok, src["unicode"] = uni_pref, "env:NOUGEN_UNICODE"
    else:
        encoding = (getattr(stream, "encoding", None) or "").lower()
        unicode_ok = mode is Mode.RICH and ("utf" in encoding)
        src["unicode"] = "probe:stream-encoding" if encoding else "fallback"

    # No animation off a TTY, in CI, or in plain/json. Never fake progress.
    motion = mode is Mode.RICH and tty and not ci
    src["motion"] = "env:CI" if ci else "derived:mode+tty"

    raw_width = env.get("NOUGEN_WIDTH", "").strip()
    if raw_width.isdigit():
        width, src["width"] = int(raw_width), "env:NOUGEN_WIDTH"
    else:
        probed = shutil.get_terminal_size(fallback=(0, 0)).columns
        if probed > 0 and tty:
            width, src["width"] = probed, "probe:terminal-size"
        else:
            width, src["width"] = FALLBACK_WIDTH, "fallback"
    width = max(MIN_WIDTH, min(MAX_WIDTH, width))

    level = env.get("NOUGEN_LOG_LEVEL", "").strip().lower()
    verbose = flag_verbose or level == "debug"
    quiet = flag_quiet or level == "quiet"
    src["log_level"] = "flag" if (flag_verbose or flag_quiet) else (
        "env:NOUGEN_LOG_LEVEL" if level else "fallback")

    return Capabilities(mode=mode, color=color, unicode=unicode_ok, motion=motion,
                        width=width, verbose=verbose, quiet=quiet, sources=src)


class UI:
    """Renderer. Every method is safe in every mode."""

    def __init__(self, caps: Capabilities | None = None, stream: Any | None = None):
        self.caps = caps or detect()
        self.stream = stream if stream is not None else sys.stdout

    # -- primitives ---------------------------------------------------------

    def style(self, text: str, role: Role) -> str:
        if not self.caps.color or not text:
            return text
        return f"\033[{_SGR[role]}m{text}\033[0m"

    def glyph(self, role: Role) -> str:
        table = _GLYPHS_UNICODE if self.caps.unicode else _GLYPHS_ASCII
        return table[role]

    def _write(self, text: str, err: bool = False) -> None:
        target = sys.stderr if err else self.stream
        print(text, file=target)

    def line(self, text: str = "", role: Role | None = None, err: bool = False) -> None:
        if self.caps.quiet and role not in (Role.ERROR, Role.WARN):
            return
        self._write(self.style(text, role) if role else text, err=err)

    def _tagged(self, role: Role, text: str, err: bool = False) -> None:
        mark = self.glyph(role)
        body = f"{mark} {text}" if mark else text
        self.line(body, role=role, err=err)

    def success(self, text: str) -> None:
        self._tagged(Role.SUCCESS, text)

    def warn(self, text: str) -> None:
        self._tagged(Role.WARN, text, err=True)

    def error(self, text: str) -> None:
        self._tagged(Role.ERROR, text, err=True)

    def info(self, text: str) -> None:
        self._tagged(Role.NET, text)

    def detail(self, text: str) -> None:
        """Secondary metadata. Suppressed unless verbose."""
        if self.caps.verbose:
            self.line(text, role=Role.META)

    def heading(self, text: str) -> None:
        self.line(text, role=Role.HEADING)

    # -- composites ---------------------------------------------------------

    def render_table(self, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
        cells = [[("" if c is None else str(c)) for c in row] for row in rows]
        widths = [len(str(c)) for c in columns]
        for row in cells:
            for i, cell in enumerate(row[:len(widths)]):
                widths[i] = max(widths[i], len(cell))
        budget = self.caps.width - (3 * (len(widths) - 1))
        # Shrink the widest column repeatedly rather than once: one oversized
        # column must not push the whole row past the terminal.
        floor = 3
        while widths and sum(widths) > budget and max(widths) > floor:
            widest = widths.index(max(widths))
            widths[widest] -= 1

        def fit(text: str, size: int) -> str:
            if len(text) <= size:
                return text
            if self.caps.unicode and size > 1:
                return text[: size - 1] + "…"
            return text[:size]

        head = "   ".join(self.style(fit(str(c), w).ljust(w), Role.HEADING)
                          for c, w in zip(columns, widths))
        rule = "   ".join((_BOX_UNICODE if self.caps.unicode else _BOX_ASCII)["h"] * w for w in widths)
        body = [
            "   ".join(fit(cell, w).ljust(w) for cell, w in zip(row, widths))
            for row in cells
        ]
        return "\n".join([head, self.style(rule, Role.META), *body])

    def table(self, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        self.line(self.render_table(columns, rows))

    def render_panel(self, title: str, lines: Sequence[str]) -> str:
        box = _BOX_UNICODE if self.caps.unicode else _BOX_ASCII
        content = [str(line) for line in lines]
        inner = max([len(title) + 2, *(len(line) for line in content)] or [len(title)])
        inner = min(inner, self.caps.width - 4)
        top = (f"{box['tl']}{box['h']} {title} "
               + box["h"] * max(0, inner - len(title) - 1) + box["tr"])
        mid = [f"{box['v']} {line[:inner].ljust(inner)} {box['v']}" for line in content]
        bottom = box["bl"] + box["h"] * (inner + 2) + box["br"]
        return "\n".join([top, *mid, bottom])

    def panel(self, title: str, lines: Sequence[str]) -> None:
        self.line(self.render_panel(title, lines))

    def render_tree(self, node: Mapping[str, Any] | Sequence[Any], prefix: str = "") -> str:
        """Render {label: children} nesting. Children may be dict, list or leaf."""
        glyphs = _TREE_UNICODE if self.caps.unicode else _TREE_ASCII
        items: list[tuple[str, Any]]
        if isinstance(node, Mapping):
            items = list(node.items())
        else:
            items = [(str(item), None) for item in node]
        out: list[str] = []
        for index, (label, children) in enumerate(items):
            last = index == len(items) - 1
            out.append(prefix + (glyphs["end"] if last else glyphs["tee"]) + str(label))
            if children:
                nested = prefix + (glyphs["gap"] if last else glyphs["pipe"])
                out.append(self.render_tree(children, nested))
        return "\n".join(line for line in out if line)

    def tree(self, node: Mapping[str, Any] | Sequence[Any]) -> None:
        self.line(self.render_tree(node))

    def banner(self, lines: Sequence[str]) -> None:
        """First-run ceremony only. Silent in plain, json and quiet modes."""
        if self.caps.mode is not Mode.RICH or self.caps.quiet:
            return
        for line in lines:
            self.line(line, role=Role.HEADING)

    @contextmanager
    def spinner(self, label: str):
        """Motion for a real phase. A no-op wherever motion is not allowed.

        Never reports progress it cannot observe: this is an indeterminate
        activity indicator, not a progress bar.
        """
        if not self.caps.motion or self.caps.quiet:
            if not self.caps.quiet and self.caps.mode is not Mode.JSON:
                self.line(f"{self.glyph(Role.CURRENT)} {label}", role=Role.META)
            yield
            return

        frames = _SPINNER_UNICODE if self.caps.unicode else _SPINNER_ASCII
        interval = _float_env("NOUGEN_SPINNER_INTERVAL_S", FALLBACK_SPINNER_INTERVAL_S)
        stop = threading.Event()

        def spin() -> None:
            i = 0
            while not stop.is_set():
                frame = self.style(frames[i % len(frames)], Role.NET)
                self.stream.write(f"\r{frame} {label}")
                self.stream.flush()
                i += 1
                stop.wait(interval)

        worker = threading.Thread(target=spin, daemon=True)
        worker.start()
        try:
            yield
        finally:
            stop.set()
            worker.join(timeout=interval * 4)
            self.stream.write("\r" + " " * (len(label) + 4) + "\r")
            self.stream.flush()

    # -- the parity contract ------------------------------------------------

    def emit(
        self,
        data: Mapping[str, Any],
        render: Callable[["UI", Mapping[str, Any]], None] | None = None,
        *,
        as_json: bool | None = None,
    ) -> None:
        """Single exit point for a command's result.

        `data` is the machine contract and is identical in every mode. `render`
        draws the human view and is only called when not emitting JSON.
        """
        want_json = self.caps.mode is Mode.JSON if as_json is None else as_json
        if want_json:
            # Byte-compatible with the CLI's existing --json output.
            print(json.dumps(data, default=str), file=self.stream)
            return
        if render is not None:
            render(self, data)

    def resolution_report(self) -> list[tuple[str, str, str]]:
        """(setting, value, source) for `doctor --verbose`. Nothing is magic."""
        caps = self.caps
        values = {"mode": caps.mode.value, "color": caps.color, "unicode": caps.unicode,
                  "motion": caps.motion, "width": caps.width,
                  "log_level": "verbose" if caps.verbose else ("quiet" if caps.quiet else "normal")}
        return [(k, str(v), caps.sources.get(k, "derived")) for k, v in values.items()]


def _float_env(name: str, fallback: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return fallback


# -- module-level singleton -------------------------------------------------

_ui = UI(Capabilities())
_ui_configured = False


def get_ui() -> UI:
    """The active renderer. Auto-detects once if `configure` was never called."""
    global _ui, _ui_configured
    if not _ui_configured:
        _ui = UI(detect())
        _ui_configured = True
    return _ui


def configure(caps: Capabilities, stream: Any | None = None) -> UI:
    global _ui, _ui_configured
    _ui = UI(caps, stream=stream)
    _ui_configured = True
    return _ui


def configure_from_argv(argv: Sequence[str], env: Mapping[str, str] | None = None) -> list[str]:
    """Resolve presentation from argv, then return argv without global flags.

    Global flags are accepted in any position so `nougen status --plain` and
    `nougen --plain status` behave identically. `--json` is inspected but left
    in place: subcommands still own their own `--json` argument.
    """
    caps = detect(argv=list(argv), env=env)
    configure(caps)
    return [token for token in argv if token not in _GLOBAL_FLAGS]


def add_global_arguments(parser: Any) -> None:
    """Register the presentation flags so they appear in `--help`."""
    group = parser.add_argument_group("presentation")
    group.add_argument("--plain", action="store_true",
                       help="Stable plain text, no colour or motion (also NOUGEN_PLAIN=1)")
    group.add_argument("--no-color", "--no-colour", dest="no_color", action="store_true",
                       help="Disable colour (also NO_COLOR=1)")
    group.add_argument("--quiet", action="store_true", help="Errors and warnings only")
    group.add_argument("--verbose", action="store_true", help="Include diagnostic internals")


def capture(caps: Capabilities, fn: Callable[[UI], None]) -> str:
    """Render into a string. Used by tests to snapshot each mode."""
    buffer = io.StringIO()
    ui = UI(caps, stream=buffer)
    fn(ui)
    return buffer.getvalue()


__all__ = ["Mode", "Role", "Capabilities", "UI", "detect", "configure",
           "configure_from_argv", "add_global_arguments", "get_ui", "capture"]
