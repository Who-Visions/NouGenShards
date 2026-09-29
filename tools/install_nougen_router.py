"""Propagate the /nougen router (Claude command) to agy, codex, ollama and the nougen CLI.

Source of truth: tools/nougen_router.md (bundled here); falls back to ~/.claude/commands/nougen.md.
Writes: ~/.claude/commands/nougen.md (if absent), $NOUGEN_ROOT/router/nougen_router.md,
agy + codex skills/nougen/SKILL.md, and ollama model nougen-router (skip: --no-ollama).
Per-node base model: set NOUGEN_ROUTER_BASE (e.g. whoart: Yukiai:e2b); else custom e4b/e2b, then gemma4.
"""
import json, os, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path

HOME = Path.home()
CLAUDE_CMD = HOME / ".claude" / "commands" / "nougen.md"
BUNDLED = Path(__file__).with_name("nougen_router.md")
SRC = BUNDLED if BUNDLED.exists() else CLAUDE_CMD
NOUGEN_ROOT = Path(os.environ.get("NOUGEN_ROOT", HOME / ".nougen"))
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
OLLAMA = OLLAMA.replace("0.0.0.0", "127.0.0.1")  # bind addr, not a dial addr
if not re.search(r":\d+$", OLLAMA):
    OLLAMA += ":" + os.environ.get("OLLAMA_PORT", "11434")  # ollama's documented default
ROUTER_MODEL = os.environ.get("NOUGEN_ROUTER_MODEL", "nougen-router")
CUSTOM = ("sol-ai", "dav1d", "kaedra", "iris-ai", "rhea-noir", "griot", "davos", "mrs-b", "yukiai")
NOWIN = 0x08000000 if os.name == "nt" else 0


def body() -> tuple[str, str]:
    text = SRC.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    desc = "NouGen root dispatcher over every NouGen MCP tool"
    if m:
        d = re.search(r"^description:\s*(.+)$", m.group(1), re.M)
        desc = d.group(1).strip() if d else desc
        text = text[m.end():]
    # Claude-only arg placeholder -> neutral wording for other CLIs
    return desc, text.replace("`$ARGUMENTS`", "the user's arguments")


def write_skill(root: Path, desc: str, text: str) -> str:
    d = root / "nougen"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: nougen\ndescription: {desc}\n---\n\n{text}", encoding="utf-8")
    return str(d / "SKILL.md")


def pick_base() -> str | None:
    pref = os.environ.get("NOUGEN_ROUTER_BASE")
    tags = [m["name"] for m in json.load(urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=10))["models"]]
    if pref and pref in tags:
        return pref
    ok = lambda t: re.search(r":e[24]b$", t) and "prev" not in t and "pre-" not in t
    for fam in CUSTOM:  # custom e2b/e4b first (Rule 0.4), prefer e4b
        for size in ("e4b", "e2b"):
            for t in tags:
                if t.lower().startswith(fam + ":") and t.endswith(size) and ok(t):
                    return t
    return next((t for t in tags if t.startswith("gemma4:") and ok(t)), None)


def ollama_model(text: str) -> str:
    base = pick_base()
    if not base:
        return "SKIP: no custom/gemma4 e2b/e4b served"
    mf = Path(tempfile.gettempdir()) / "nougen_router.Modelfile"
    sys_prompt = ("You are the NouGen router. Map the user's intent to the right NouGen MCP tool(s) "
                  "from this atlas and answer with the tool call plan only.\n\n" + text).replace('"""', "'''")
    mf.write_text(f'FROM {base}\nSYSTEM """{sys_prompt}"""\n', encoding="utf-8")
    r = subprocess.run(["ollama", "create", ROUTER_MODEL, "-f", str(mf)], capture_output=True,
                       text=True, creationflags=NOWIN)
    return f"{ROUTER_MODEL} <- {base}: " + ("ok" if r.returncode == 0 else r.stderr.strip()[-200:])


def main():
    if not CLAUDE_CMD.exists() and SRC != CLAUDE_CMD:
        CLAUDE_CMD.parent.mkdir(parents=True, exist_ok=True)
        CLAUDE_CMD.write_text(SRC.read_text(encoding="utf-8"), encoding="utf-8")
        print("claude:", CLAUDE_CMD)
    desc, text = body()
    atlas = NOUGEN_ROOT / "router" / "nougen_router.md"
    atlas.parent.mkdir(parents=True, exist_ok=True)
    atlas.write_text(text, encoding="utf-8")
    print("nougen cli atlas:", atlas)
    print("agy:", write_skill(HOME / ".gemini" / "antigravity" / "skills", desc, text))
    print("codex:", write_skill(HOME / ".codex" / "skills", desc, text))
    if "--no-ollama" not in sys.argv:
        print("ollama:", ollama_model(text))


if __name__ == "__main__":
    main()
