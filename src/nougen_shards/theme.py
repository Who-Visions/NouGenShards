"""Terminal colour for the NouGenShards CLI.

The CLI speaks in semantic glyphs already ("✅ saved", "❌ no such trigger",
"🔍 Found 12 records"). This module gives those glyphs colour without asking
259 call sites to re-declare intent they have already expressed: `paint()`
reads the leading glyph and applies the matching style.

Rule 0.2 (dynamic over hardcode): nothing here is a bare literal on the wire.
Colour *mode* resolves env -> tty probe -> constant, and every slot in the
palette resolves env -> config -> constant. The constants are logged fallbacks,
not the source of truth, so a terminal with an unreadable purple can be fixed
with an env var instead of a patch.

Honoured, in precedence order:
    NO_COLOR         any non-empty value disables colour (no-color.org)
    FORCE_COLOR      any non-empty value forces it on, even when piped
    NOUGEN_COLOR     auto (default) | always | never
    NOUGEN_COLOR_<SLOT>  override one slot, e.g. NOUGEN_COLOR_ACCENT="38;5;99"
"""
from __future__ import annotations

import os
import sys
from typing import Mapping, Optional

# --- Palette ----------------------------------------------------------------
# SGR parameter strings, not full escapes, so overrides compose the same way.
# 256-colour indices degrade gracefully on 16-colour terminals.
#
#   accent   purple  brand lines, headings, section titles
#   ok       green   completed work, affirmative results
#   info     cyan    counts, lookups, neutral reporting
#   warn     yellow  recoverable problems, skips, overrides
#   err      red     failures and refusals
#   dim      grey    secondary detail that should not compete
_DEFAULT_PALETTE = {
    "accent": "38;5;141",
    "ok": "38;5;114",
    "info": "38;5;80",
    "warn": "38;5;179",
    "err": "38;5;203",
    "dim": "38;5;245",
}

_RESET = "\033[0m"

# Leading glyph -> palette slot. A line that opens with none of these is left
# unstyled: silence is the correct default for machine-readable output.
_GLYPH_STYLES = {
    "✅": "ok",
    "✔": "ok",
    "🎉": "ok",
    "❌": "err",
    "🚫": "err",
    "💥": "err",
    "⚠️": "warn",
    "⚠": "warn",
    "🔓": "warn",
    "🤏": "warn",
    "ℹ️": "info",
    "ℹ": "info",
    "🔍": "info",
    "📊": "info",
    "📈": "info",
    "🔐": "info",
    "🏥": "info",
    "👨‍⚕️": "info",
    "🗑️": "dim",
    "🗑": "dim",
    "🪩": "accent",
    "🌌": "accent",
    "🚀": "accent",
    "🧠": "accent",
    "🤝": "accent",
}


def _env(env: Optional[Mapping[str, str]] = None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _env_flag(name: str, env: Optional[Mapping[str, str]] = None) -> bool:
    """True when the variable is set to any non-empty value."""
    return bool(_env(env).get(name, "").strip())


def colour_enabled(stream=None, env: Optional[Mapping[str, str]] = None) -> bool:
    """Resolve colour mode: explicit env first, live tty probe as the fallback.

    Probing beats assuming — a piped or redirected run must stay clean so that
    `nougen shard search ... | jq` and CI log capture are not poisoned with
    escape sequences.
    """
    e = _env(env)
    if _env_flag("NO_COLOR", e):
        return False
    if _env_flag("FORCE_COLOR", e):
        return True

    mode = e.get("NOUGEN_COLOR", "auto").strip().lower()
    if mode == "always":
        return True
    if mode == "never":
        return False

    if e.get("TERM", "").strip().lower() == "dumb":
        return False

    stream = sys.stdout if stream is None else stream
    try:
        return bool(stream.isatty())
    except Exception:
        # A stream without isatty() is not a terminal we can reason about.
        return False


def palette(env: Optional[Mapping[str, str]] = None) -> dict:
    """Resolve the palette: env override per slot, constant as logged fallback."""
    e = _env(env)
    resolved = {}
    for slot, fallback in _DEFAULT_PALETTE.items():
        override = e.get(f"NOUGEN_COLOR_{slot.upper()}", "").strip()
        resolved[slot] = override or fallback
    return resolved


def style(text: str, slot: str, *, stream=None, env: Optional[Mapping[str, str]] = None) -> str:
    """Wrap `text` in the SGR sequence for `slot`, or return it untouched."""
    if not text or not colour_enabled(stream, env):
        return text
    code = palette(env).get(slot)
    if not code:
        return text
    return f"\033[{code}m{text}{_RESET}"


def _slot_for(text: str) -> Optional[str]:
    stripped = text.lstrip()
    for glyph, slot in _GLYPH_STYLES.items():
        if stripped.startswith(glyph):
            return slot
    return None


def paint(text: str, *, stream=None, env: Optional[Mapping[str, str]] = None) -> str:
    """Colour a line according to the glyph it already leads with."""
    slot = _slot_for(text)
    return text if slot is None else style(text, slot, stream=stream, env=env)


def styled_print(*args, **kwargs) -> None:
    """Drop-in `print` that paints glyph-led lines.

    Imported as `print` at the top of cli.py so existing call sites keep their
    shape. Multi-argument calls are joined by `sep` first, then painted as one
    line, so the leading glyph still governs the whole message.
    """
    stream = kwargs.get("file")
    if stream is None:
        stream = sys.stdout
    sep = kwargs.get("sep", " ")
    rendered = sep.join(str(a) for a in args)
    slot = _slot_for(rendered)
    if slot is not None:
        rendered = style(rendered, slot, stream=stream)
    kwargs.pop("sep", None)
    _builtin_print(rendered, **kwargs)


# Bound once so the shim cannot recurse if a module rebinds the global name.
_builtin_print = print


# --- Explicit helpers for new code ------------------------------------------
# Prefer these when writing new output; they say what they mean instead of
# relying on the glyph table.
def accent(text: str, **kw) -> str:
    return style(text, "accent", **kw)


def ok(text: str, **kw) -> str:
    return style(text, "ok", **kw)


def info(text: str, **kw) -> str:
    return style(text, "info", **kw)


def warn(text: str, **kw) -> str:
    return style(text, "warn", **kw)


def err(text: str, **kw) -> str:
    return style(text, "err", **kw)


def dim(text: str, **kw) -> str:
    return style(text, "dim", **kw)


def heading(text: str, **kw) -> str:
    """Bold accent, for section titles and the banner."""
    if not colour_enabled(kw.get("stream"), kw.get("env")):
        return text
    return f"\033[1m{accent(text, **kw)}"


def enable_windows_ansi() -> None:
    """Turn on ANSI handling on legacy Windows consoles.

    Windows Terminal and PowerShell 7 need nothing; conhost on older builds
    does. colorama is already a declared dependency, so this is free when it is
    present and a no-op when it is not.
    """
    try:
        import colorama
    except Exception:
        return
    fix = getattr(colorama, "just_fix_windows_console", None)
    if fix is not None:
        fix()
    else:  # colorama < 0.4.6
        colorama.init()
