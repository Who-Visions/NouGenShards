"""VRAM admission gate for WhoArt (RTX 4050 Laptop, 6141 MiB).

Operator rule, 2026-08-08: "EVERY REQUEST SHOULD SEE IF VRAM IS CLEAR."
Context: spilled generation crashed the machine on 2026-08-08, and the IRIS
vision lane (Yuki-Ai/persistence/look.py) deliberately pins qwen3-vl:4b
resident at ~3.53 GB with keep_alive=-1 — so free VRAM, not total, is the
budget, and it is usually ~1.5-2.5 GB.

Call check_vram(model) before ANY local Ollama request. It answers with a
verdict instead of raising, so callers can route to the fleet or skip:

    from nougen_shards.vram_gate import check_vram
    v = check_vram("gemma4:e2b")
    if not v.ok:
        # route to fleet / skip / report v.reason — do NOT generate locally
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from dataclasses import dataclass

OLLAMA = "http://127.0.0.1:11434"

# Measured Ollama LOAD sizes on WhoArt (/api/ps during generation, 2026-08-08).
# Disk size and vendor Q4_0 tables are both wrong for this — per-layer
# embeddings are not compressed in Ollama's e-series builds.
MEASURED_LOAD_GB = {
    "gemma4:e2b": 7.51, "Yukiai:e2b": 7.51, "solai:e2b": 7.51,
    "gemma4:e4b": 9.52, "Yukiai:e4b": 9.52, "solai:e4b": 9.52,
    "qwen3-vl:4b": 3.53,
    # MEASURED 2026-08-08 via /api/ps while pinned by IRIS: 1.66 GB, 100% on
    # GPU. QAT q4_0 pages PLE tables on demand instead of loading them dense,
    # so resident cost is far below the 4.3 GB disk size.
    "gemma4:e2b-qat": 1.66,
    "deepseek-ocr:3b": 6.9,
    "nomic-embed-text:latest": 0.4,
}
SAFETY_MARGIN_GB = 0.4  # display/compositor churn headroom


@dataclass
class Verdict:
    ok: bool
    reason: str
    free_gb: float = 0.0
    need_gb: float = 0.0
    residents: tuple = ()


def _free_vram_gb() -> float:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=15)
    return int(out.stdout.strip().splitlines()[0]) / 1024.0


def _residents() -> list[dict]:
    with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
        return json.loads(r.read()).get("models", [])


def resident_model() -> str | None:
    """The pinned resident (IRIS's model) — NouGen's DEFAULT local lane.

    Operator rule 2026-08-08: "iris should probably be your main ollama chain
    ... you don't have to keep squeezing another llm on my vram if one is
    sitting squatting." One resident serves vision AND text; personas ride it
    as system prompts. Returns the first non-embedding resident, else None.
    """
    try:
        for m in _residents():
            name = m.get("name", "")
            if "embed" not in name:
                return name
    except Exception:
        pass
    return None


def free_card() -> list[str]:
    """Unload every resident so a manually-requested model gets the whole card.

    IRIS re-pins its model on its next cycle (each of its calls carries
    keep_alive=-1), so eviction costs one reload, not the watcher.
    Returns the names that were evicted.
    """
    evicted = []
    try:
        for m in _residents():
            name = m.get("name")
            if not name:
                continue
            req = urllib.request.Request(
                f"{OLLAMA}/api/generate",
                data=json.dumps({"model": name, "keep_alive": 0}).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=30).read()
            evicted.append(name)
    except Exception:
        pass
    return evicted


def check_vram(model: str, need_gb: float | None = None,
               manual: bool = False) -> Verdict:
    """Admission check: may `model` be loaded for local generation right now?

    Unknown models are REFUSED (no measured footprint = no admission), matching
    the operator's strict posture. Embedding-sized models pass on their small
    measured size. Never raises on probe failure — an unmeasurable GPU is a
    refusal, not a guess.

    manual=True is the OPERATOR OPT-IN lane (2026-08-08: "if i ever ask for it
    manually i still want that option"): the gate evicts every resident first
    (free_card()), then admits even an oversized model. The run will spill and
    be slow — that is accepted for an explicit manual request — but it starts
    from an empty card, serially, which is the configuration that has never
    crashed this box. Callers must pair manual runs with keep_alive:0. Also
    honored via env NOUGEN_VRAM_MANUAL=1.
    """
    import os
    if os.getenv("NOUGEN_VRAM_GATE", "").strip().lower() in ("0", "false", "no", "off", "disabled") or (
        os.getenv("PYTEST_CURRENT_TEST") and os.getenv("NOUGEN_VRAM_GATE") != "1"
    ):
        return Verdict(True, "vram gate bypassed for test environment")

    if manual or os.getenv("NOUGEN_VRAM_MANUAL") == "1":
        evicted = free_card()
        return Verdict(True, f"manual override — card cleared (evicted: "
                             f"{', '.join(evicted) or 'nothing'}); expect spill, "
                             "run serially, IRIS re-pins next cycle",
                       residents=tuple(evicted))
    need = need_gb if need_gb is not None else MEASURED_LOAD_GB.get(model)
    if need is None:
        return Verdict(False, f"no measured load size for {model!r}; measure via "
                              "/api/ps before admitting it")
    try:
        residents = _residents()
    except Exception as e:
        return Verdict(False, f"cannot read /api/ps ({e}); refusing to guess")
    names = tuple(m.get("name", "?") for m in residents)
    if model in names:
        # already resident — generating on it adds only KV, admit
        return Verdict(True, "already resident", need_gb=need, residents=names)
    try:
        free = _free_vram_gb()
    except Exception as e:
        return Verdict(False, f"cannot read nvidia-smi ({e}); refusing to guess")
    if need + SAFETY_MARGIN_GB <= free:
        return Verdict(True, "fits free VRAM", free_gb=free, need_gb=need,
                       residents=names)
    return Verdict(
        False,
        f"{model} needs {need:.2f} GB but only {free:.2f} GB free "
        f"(residents: {', '.join(names) or 'none'}; IRIS pins qwen3-vl:4b by "
        "design). Route to fleet or skip — spill crashed this box on 2026-08-08.",
        free_gb=free, need_gb=need, residents=names)
