"""
Persist Recursive Learning Shards into ~/.nougen/shards.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from nougen_shards import core as shards

LEARNING_SHARDS = [
    {
        "content": (
            "# Recursive Learning: PEP 562 Dynamic Submodule Resolution in Package __init__.py\n\n"
            "## Problem Context\n"
            "In complex packages (e.g. `nougen_shards`, `nougen_relay`), tests or external scripts "
            "frequently import submodules directly as `from <package> import <submodule>`. "
            "If `<submodule>` is not explicitly defined in `__all__` or imported in `__init__.py`, "
            "Python raises `ImportError: cannot import name '<submodule>' from '<package>'`. "
            "However, eagerly importing every submodule in `__init__.py` causes severe circular import loops, "
            "slows module startup, and breaks when optional heavy dependencies are not yet initialized.\n\n"
            "## Invariant Solution (PEP 562)\n"
            "Implement a dynamic `__getattr__(name: str)` in the root `__init__.py` of the package:\n"
            "```python\n"
            "import importlib\n"
            "def __getattr__(name: str):\n"
            "    if name in _KNOWN_SUBMODULES:\n"
            "        mod = importlib.import_module(f'{__name__}.{name}')\n"
            "        globals()[name] = mod\n"
            "        return mod\n"
            "    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')\n"
            "```\n"
            "This provides zero-cost lazy imports, completely prevents missing submodule import errors, "
            "and decouples module dependency graphs."
        ),
        "tags": "python,architecture,pep562,import-resolution,hardening,recursive-learning",
        "domain": "nougen_core",
    },
    {
        "content": (
            "# Recursive Learning: FastMCP Native Prompts & Subprocess Isolation Invariants\n\n"
            "## Architecture\n"
            "FastMCP servers (`mcp_server.py`) exposed to IDEs (Antigravity, Claude Code, Cursor) "
            "can register native interactive prompts via the `@mcp.prompt()` decorator:\n"
            "- `/research [topic]` -> Automated query expansion and multi-db shard synthesis.\n"
            "- `/lore [query]` -> Narrative worldbuilding and canon retrieval.\n"
            "- `/fleet_sync [node]` -> Cross-node handoff and replication inspection.\n"
            "- `/shot_card [scene_desc]` -> 26-field HyperReality camera prompt generation.\n\n"
            "## Subprocess Isolation Invariant\n"
            "When an MCP tool spawns a subprocess (`subprocess.run`), the spawned process runs in the parent's "
            "arbitrary working directory without the repository `src/` directory in `sys.path`. "
            "This causes `ModuleNotFoundError` or 120s timeouts.\n"
            "Rule: Always explicitly inject `PYTHONPATH=str(SRC_DIR)` and set `cwd=REPO_ROOT` in the subprocess env:\n"
            "```python\n"
            "env = os.environ.copy()\n"
            "env['PYTHONPATH'] = str(SRC_DIR)\n"
            "result = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=30)\n"
            "```"
        ),
        "tags": "mcp,fastmcp,prompts,subprocess,pythonpath,isolation,recursive-learning",
        "domain": "nougen_relay",
    },
    {
        "content": (
            "# Recursive Learning: Windows UTF-8 Console & Byte-Order Mark (BOM) Stripping Protocol\n\n"
            "## Problem Context\n"
            "1. On Windows environments, stdout defaults to `cp1252` encoding. Attempting to print UTF-8 "
            "status emojis (e.g. 🚀, ⚡, 🛡️, ❌) results in `UnicodeEncodeError`.\n"
            "2. Text editors on Windows occasionally save files with a UTF-8 Byte-Order Mark (BOM: `\\xef\\xbb\\xbf`), "
            "which causes AST parsers, linters, and pytest loaders to fail on line 1.\n\n"
            "## Enforcement Protocol\n"
            "- At the entry point of all CLI tools and MCP wrappers:\n"
            "  `if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')`\n"
            "- In automated AST/syntax audit scripts, inspect the first 3 bytes of all `.py` files and strip "
            "`\\xef\\xbb\\xbf` automatically to guarantee pure UTF-8 compatibility across the fleet."
        ),
        "tags": "windows,utf8,encoding,bom,unicode,cli,recursive-learning",
        "domain": "nougen_telemetry",
    },
    {
        "content": (
            "# Recursive Learning: HyperReality 26-Field Camera Coherence Engine\n\n"
            "## Technical Specification\n"
            "To achieve cinematic visual consistency across multiple rendering backends (Veo 3.1, Sora, Midjourney v7, "
            "Flux Pro, Kling), prompts must adhere to a standardized 26-field optical specification:\n"
            "- **Camera Rig**: body (`ARRI ALEXA 35`, `RED V-RAPTOR XL`), lens (`Cooke Anamorphic /i Full Frame Plus`), "
            "focal length (`35mm`, `50mm`, `85mm`), aperture (`f/1.4`, `f/2.0`, `f/2.8`), ISO, shutter angle (`180.0deg`).\n"
            "- **Spatial Choreography**: camera movement (`dolly_in`, `orbit_cw`, `tracking_pan`), speed (`cinematic_slow`, `whip`), "
            "subject distance (`2.5m`), camera height (`1.6m eye level`), tilt/pan angle.\n"
            "- **Lighting & Color**: key light (`tungsten 3200k key`), fill ratio (`4:1`), rim light (`cool 5600k cyan rim`), "
            "color grade LUT (`Kodak 5219 500T Vision3`), atmospheric haze/volumetric density.\n\n"
            "## CameraCoherenceValidator\n"
            "The `CameraCoherenceValidator` enforces physical optical laws: wide-angle lenses (>24mm) cannot have ultra-shallow "
            "depth-of-field without explicit focal distance clamping; anamorphic lenses must specify horizontal squeeze ratio "
            "(e.g. 1.8x or 2.0x) and oval bokeh characteristics."
        ),
        "tags": "cinematics,hyperreality,shotcard,camera-coherence,optics,prompts,recursive-learning",
        "domain": "nougen_cinematics",
    },
    {
        "content": (
            "# Recursive Learning: Fleet Reach Matrix & DNS Tailscale Reachability Invariants\n\n"
            "## Invariant Topology\n"
            "The NouGen fleet operates across a multi-node compute grid:\n"
            "- **Apollo** (Razer Blade 2020 / RTX 2080 Super Max-Q): `192.168.1.16` | `blade.nougenai.com`\n"
            "- **Hyperion** (ASUS ProArt PX13 / RTX 4050): `192.168.1.187` | `hyperion.nougenai.com`\n"
            "- **Phoebus** (Mac Mini / M-series Backbone): `192.168.1.78` | `phoebus.nougenai.com`\n\n"
            "## Diagnostic Verification Protocol\n"
            "The reach matrix (`tools/reach_matrix.py`) executes concurrent TCP socket ping and HTTP health probes across "
            "both local LAN IPs and Tailscale DNS names with a 2.0s connection timeout. A node is classified `GREEN` only "
            "when both network socket handshake and application JSON heartbeat succeed."
        ),
        "tags": "fleet,reach-matrix,dns,tailscale,telemetry,apollo,hyperion,phoebus,recursive-learning",
        "domain": "nougen_telemetry",
    }
]

def main():
    print("=" * 70)
    print("INGESTING RECURSIVE LEARNING SHARDS INTO ~/.nougen/shards")
    print("=" * 70)

    for i, shard_data in enumerate(LEARNING_SHARDS, 1):
        content = shard_data["content"]
        tags_list = [t.strip() for t in shard_data["tags"].split(",") if t.strip()]
        domain = shard_data["domain"]
        first_line = content.splitlines()[0].replace("#", "").strip()
        title = first_line[:40]

        ok = shards.capture(
            event_type="KNOWLEDGE",
            title=title,
            content=content,
            tags=tags_list,
            domain_key=domain
        )
        status_icon = "✅ Captured" if ok else "ℹ️ Existing"
        print(f"[{i}/{len(LEARNING_SHARDS)}] {status_icon}: {title} | Domain: {domain}")

    print("=" * 70)
    print(f"✅ Ingestion cycle complete across {len(LEARNING_SHARDS)} recursive learning shards!")
    print("=" * 70)

if __name__ == "__main__":
    main()
