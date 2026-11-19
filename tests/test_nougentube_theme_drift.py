"""The NouGenTube panel palettes come from the generated mono-violet package, never inline copies (drift check)."""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extensions" / "nougentube-chrome"
CONTENT = EXT / "content.js"
TOKENS_JS = EXT / "design-tokens.js"
DESIGN = ROOT / "designs" / "mono-violet"


def test_generated_tokens_js_matches_design_json():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "nougendesigns.py"), "check", str(DESIGN / "design.json"),
                        str(DESIGN), "--tokens-js", str(TOKENS_JS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_content_script_has_no_inline_palettes():
    js = CONTENT.read_text(encoding="utf-8")
    assert "${PALETTES}" in js and "NGT_TOKENS.themes" in js
    assert not re.search(r"--(bg|ac|tx):#[0-9a-fA-F]{3,6}", js), "inline colorway values found in content.js"


def test_manifest_loads_tokens_before_content():
    m = (EXT / "manifest.json").read_text(encoding="utf-8")
    assert m.index('"design-tokens.js"') < m.index('"content.js"')


def test_actionable_chips_are_native_buttons():
    js = CONTENT.read_text(encoding="utf-8")
    for m in re.finditer(r'<span class="chip[^>]*>', js):
        assert not re.search(r'(id|data-[\w-]+)=', m.group(0)), m.group(0)
    assert 'role", "button"' not in js
