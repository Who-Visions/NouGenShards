"""The NouGenTube panel palettes must match designs/mono-violet/design.json (drift check)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "extensions" / "nougentube-chrome" / "content.js"
DESIGN = ROOT / "designs" / "mono-violet" / "design.json"

# extension short var -> design package token
MAP = {"bg": "--bg", "card": "--surface", "raised": "--raised", "ln": "--border", "lns": "--border-strong",
       "tx": "--text", "mu": "--muted", "ac": "--accent", "ac2": "--extra", "ok": "--good", "warn": "--warn",
       "bad": "--bad", "ink": "--control-ink", "focus": "--focus", "r": "--radius-control",
       "rp": "--radius-panel", "ow": "--outline-width"}


def _norm(v):
    v = v.strip().lower()
    return "0px" if v in ("0", "0px") else v


def _blocks(js):
    out = {}
    for sel, body in re.findall(r"\.p(\[data-theme=\w+\])?\{(--bg:[^}]*)\}", js):
        name = sel[len("[data-theme="):-1] if sel else "dark"
        out[name] = dict(re.findall(r"--([\w-]+):([^;]+)", body))
    return out


def test_extension_palettes_match_mono_violet_package():
    spec = json.loads(DESIGN.read_text(encoding="utf-8"))
    blocks = _blocks(CONTENT.read_text(encoding="utf-8"))
    assert set(blocks) == set(spec["themes"]), blocks.keys()
    for theme, values in blocks.items():
        want = {**spec["tokens"], **spec["themes"][theme]}
        for short, token in MAP.items():
            assert short in values, (theme, short)
            assert _norm(values[short]) == _norm(want[token]), (theme, short, values[short], want[token])


def test_actionable_chips_get_button_semantics():
    js = CONTENT.read_text(encoding="utf-8")
    assert 'a.name.startsWith("data-")' in js and "c.attributes.length > 2" not in js
