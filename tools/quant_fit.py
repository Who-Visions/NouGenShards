#!/usr/bin/env python3
"""quant_fit.py - which locally-pulled models actually fit this GPU's VRAM.

Replaces the one genuinely useful thing an LM Studio GUI offers (a VRAM-usage
readout while picking a quant) with a probe that answers it for the machine you
are actually on, without leaving the ollama lane.

Everything environment-shaped is discovered at runtime (Rule 0.2):
  VRAM        -> nvidia-smi, else NOUGEN_GPU_VRAM_MB, else refuse to guess
  models      -> {OLLAMA_HOST}/api/tags
  per-model   -> {OLLAMA_HOST}/api/show (layers/heads for a real KV-cache figure)
  context     -> NOUGEN_QUANT_FIT_CTX (default: the model's own trained ctx, capped)
  headroom    -> NOUGEN_VRAM_HEADROOM_PCT

Usage:
  python quant_fit.py                 # table, all local models
  python quant_fit.py --ctx 8192      # size the KV cache for an 8k window
  python quant_fit.py --json          # machine-readable
  python quant_fit.py --filter gemma  # substring match on model name
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

# --- fallbacks only; every one of these is overridden by a probe or env ------
DEFAULT_OLLAMA_BIND_CLIENT = "127.0.0.1"
DEFAULT_OLLAMA_PORT = 11434
DEFAULT_OLLAMA_HOST = f"http://{DEFAULT_OLLAMA_BIND_CLIENT}:{DEFAULT_OLLAMA_PORT}"
DEFAULT_HEADROOM_PCT = 10.0      # leave room for the desktop compositor
DEFAULT_CTX_CAP = 8192           # don't size KV for a 128k window nobody asked for
DEFAULT_KV_BYTES_PER_ELEM = 2    # f16 KV cache
DEFAULT_OVERHEAD_PCT = 8.0       # compute buffers, when /api/show can't tell us
DEFAULT_SWA_FULL_RATIO = 1 / 6   # gemma3/4 interleave: 1 full-attention layer per 6
HTTP_TIMEOUT_SEC = 20.0
CLOUD_MARKERS = ("-cloud", ":cloud")


def _env_float(name: str, fallback: float) -> tuple[float, str]:
    raw = os.environ.get(name)
    if raw is None:
        return fallback, "fallback-constant"
    try:
        return float(raw), f"env:{name}"
    except ValueError:
        print(f"[warn] {name}={raw!r} is not a number; using {fallback}", file=sys.stderr)
        return fallback, "fallback-constant"


def _env_int(name: str, fallback: int) -> tuple[int, str]:
    val, src = _env_float(name, float(fallback))
    return int(val), src


def ollama_host() -> str:
    """OLLAMA_HOST is a *bind* address for the server ("0.0.0.0", ":11434") and a
    *client* URL for everyone else. The canonical sanitizer lives in
    nougen_shards.ollama_host; fall back to a local copy when this script runs
    standalone outside the package."""
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
        from nougen_shards.ollama_host import resolve_ollama_url
        return resolve_ollama_url()
    except Exception:
        host = (os.environ.get("NOUGEN_OLLAMA_HOST")
                or os.environ.get("OLLAMA_HOST") or "").strip()
        if not host:
            return DEFAULT_OLLAMA_HOST
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        scheme, _, rest = host.partition("://")
        rest = rest.rstrip("/")
        hostname, sep, port = rest.rpartition(":")
        if not sep or not port.isdigit():          # no explicit port
            hostname, port = rest, str(DEFAULT_OLLAMA_PORT)
        if hostname in ("", "0.0.0.0", "::", "[::]", "*"):
            hostname = DEFAULT_OLLAMA_BIND_CLIENT  # wildcard bind is dialed on loopback
        return f"{scheme}://{hostname}:{port}"


def _get_json(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"} if data else {}
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# --- VRAM discovery ---------------------------------------------------------
def probe_vram_mb() -> tuple[int | None, int | None, str]:
    """Return (total_mb, used_mb, source). Probe first, env second, never a constant."""
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run(
                [smi, "--query-gpu=memory.total,memory.used",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=15, check=True,
            ).stdout.strip().splitlines()
            if out:
                total_s, used_s = (p.strip() for p in out[0].split(","))
                return int(float(total_s)), int(float(used_s)), "probe:nvidia-smi"
        except (subprocess.SubprocessError, ValueError, OSError) as exc:
            print(f"[warn] nvidia-smi probe failed: {exc}", file=sys.stderr)
    forced = os.environ.get("NOUGEN_GPU_VRAM_MB")
    if forced:
        try:
            return int(float(forced)), None, "env:NOUGEN_GPU_VRAM_MB"
        except ValueError:
            print(f"[warn] NOUGEN_GPU_VRAM_MB={forced!r} is not a number", file=sys.stderr)
    return None, None, "unresolved"


# --- model inspection -------------------------------------------------------
def _pick(info: dict, *suffixes: str) -> int | None:
    """model_info keys are arch-prefixed (llama.block_count, gemma3.block_count...)."""
    for key, val in info.items():
        if any(key.endswith(sfx) for sfx in suffixes) and isinstance(val, (int, float)):
            return int(val)
    return None


def kv_cache_bytes(info: dict, ctx: int, bytes_per_elem: int,
                   swa_full_ratio: float) -> tuple[int, list[str]] | None:
    """Bytes of KV cache at `ctx`, plus notes about anything we had to assume.

    Handles the two things a naive 2*layers*heads*dim*ctx formula gets wrong on
    the gemma family: K and V can have different head dims, and sliding-window
    layers only ever hold `sliding_window` tokens no matter how big ctx is.
    """
    layers = _pick(info, ".block_count")
    n_embd = _pick(info, ".embedding_length")
    n_head = _pick(info, ".attention.head_count")
    if not (layers and n_head):
        return None
    notes: list[str] = []
    n_kv = _pick(info, ".attention.head_count_kv")
    if not n_kv:
        n_kv = n_head
        notes.append("head_count_kv not exported; assumed MHA (pessimistic if GQA)")
    head_dim = (n_embd // n_head) if n_embd else None
    k_len = _pick(info, ".attention.key_length") or head_dim
    v_len = _pick(info, ".attention.value_length") or k_len
    if not k_len:
        return None
    per_tok_per_layer = n_kv * (k_len + v_len) * bytes_per_elem

    window = _pick(info, ".attention.sliding_window")
    if window and 0 < swa_full_ratio < 1:
        k_swa = _pick(info, ".attention.key_length_swa") or k_len
        v_swa = _pick(info, ".attention.value_length_swa") or k_swa
        full_layers = max(1, round(layers * swa_full_ratio))
        swa_layers = layers - full_layers
        swa_tokens = min(ctx, window)
        total = (full_layers * ctx * per_tok_per_layer
                 + swa_layers * swa_tokens * n_kv * (k_swa + v_swa) * bytes_per_elem)
        notes.append(f"sliding-window attn: {swa_layers}/{layers} layers capped at "
                     f"{window} tokens (full-layer ratio {swa_full_ratio:.3g})")
        return int(total), notes
    return int(layers * ctx * per_tok_per_layer), notes


def trained_ctx(info: dict) -> int | None:
    return _pick(info, ".context_length")


def human_gb(nbytes: float) -> str:
    return f"{nbytes / (1024 ** 3):.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ctx", type=int, default=None,
                    help="context window to size the KV cache for "
                         "(default: NOUGEN_QUANT_FIT_CTX, else the model's own, capped)")
    ap.add_argument("--filter", default=os.environ.get("NOUGEN_QUANT_FIT_FILTER", ""),
                    help="substring match on model name")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    host = ollama_host()
    headroom_pct, headroom_src = _env_float("NOUGEN_VRAM_HEADROOM_PCT", DEFAULT_HEADROOM_PCT)
    overhead_pct, overhead_src = _env_float("NOUGEN_VRAM_OVERHEAD_PCT", DEFAULT_OVERHEAD_PCT)
    ctx_cap, ctx_cap_src = _env_int("NOUGEN_QUANT_FIT_CTX_CAP", DEFAULT_CTX_CAP)
    kv_elem, kv_elem_src = _env_int("NOUGEN_KV_BYTES_PER_ELEM", DEFAULT_KV_BYTES_PER_ELEM)
    swa_ratio, swa_src = _env_float("NOUGEN_SWA_FULL_LAYER_RATIO", DEFAULT_SWA_FULL_RATIO)
    ctx_override = args.ctx
    ctx_src = "flag:--ctx"
    if ctx_override is None:
        raw_ctx = os.environ.get("NOUGEN_QUANT_FIT_CTX")
        if raw_ctx:
            try:
                ctx_override, ctx_src = int(raw_ctx), "env:NOUGEN_QUANT_FIT_CTX"
            except ValueError:
                print(f"[warn] NOUGEN_QUANT_FIT_CTX={raw_ctx!r} ignored", file=sys.stderr)

    total_mb, used_mb, vram_src = probe_vram_mb()
    if total_mb is None:
        print("[fail] could not resolve GPU VRAM (no nvidia-smi, no NOUGEN_GPU_VRAM_MB). "
              "Refusing to guess.", file=sys.stderr)
        return 2
    total_b = total_mb * 1024 ** 2
    budget_b = total_b * (1.0 - headroom_pct / 100.0)

    try:
        tags = _get_json(f"{host}/api/tags").get("models", [])
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        print(f"[fail] ollama not reachable at {host}: {exc}", file=sys.stderr)
        return 2

    rows = []
    for m in tags:
        name = m.get("name", "")
        if args.filter and args.filter.lower() not in name.lower():
            continue
        details = m.get("details") or {}
        row = {
            "name": name,
            "quant": details.get("quantization_level") or "?",
            "params": details.get("parameter_size") or "?",
            "weights_bytes": int(m.get("size") or 0),
        }
        if any(mk in name for mk in CLOUD_MARKERS):
            row.update(verdict="CLOUD", note="remote lane, no local VRAM cost",
                       ctx=None, kv_bytes=0, total_bytes=0)
            rows.append(row)
            continue

        info, tmpl_ctx = {}, None
        try:
            shown = _get_json(f"{host}/api/show", {"model": name})
            info = shown.get("model_info") or {}
            tmpl_ctx = trained_ctx(info)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            row["note"] = f"/api/show unavailable ({exc.__class__.__name__}); estimated"

        ctx = ctx_override or min(tmpl_ctx or ctx_cap, ctx_cap)
        computed = kv_cache_bytes(info, ctx, kv_elem, swa_ratio)
        if computed is None:
            kv = int(row["weights_bytes"] * overhead_pct / 100.0)
            notes = ["KV estimated from % overhead (no usable model_info)"]
        else:
            kv, notes = computed
        if row.get("note"):
            notes.insert(0, row["note"])
        row["note"] = "; ".join(notes) if notes else None
        total_need = row["weights_bytes"] + kv
        if total_need <= budget_b:
            verdict = "FITS"
        elif row["weights_bytes"] <= budget_b:
            verdict = "TIGHT"      # weights fit, KV at this ctx pushes it over
        else:
            verdict = "SPILLS"     # partial offload -> CPU layers, slow
        row.update(ctx=ctx, kv_bytes=kv, total_bytes=total_need, verdict=verdict)
        rows.append(row)

    order = {"FITS": 0, "TIGHT": 1, "SPILLS": 2, "CLOUD": 3}
    rows.sort(key=lambda r: (order.get(r["verdict"], 9), -r["total_bytes"]))

    result = {
        "host": host,
        "vram_total_mb": total_mb,
        "vram_used_mb": used_mb,
        "vram_source": vram_src,
        "headroom_pct": headroom_pct, "headroom_source": headroom_src,
        "usable_budget_gb": round(budget_b / 1024 ** 3, 2),
        "ctx_source": ctx_src if ctx_override else f"per-model (cap {ctx_cap}, {ctx_cap_src})",
        "kv_bytes_per_elem": kv_elem, "kv_elem_source": kv_elem_src,
        "overhead_pct_source": overhead_src,
        "swa_full_layer_ratio": swa_ratio, "swa_source": swa_src,
        "models_seen": len(tags), "models_reported": len(rows),
        "models": rows,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    used_s = f", {used_mb} MB in use" if used_mb is not None else ""
    print(f"GPU: {total_mb} MB total{used_s} ({vram_src})")
    print(f"Budget: {result['usable_budget_gb']} GB after {headroom_pct:g}% headroom "
          f"({headroom_src})   host: {host}")
    print(f"{'VERDICT':<8} {'MODEL':<34} {'QUANT':<8} {'WEIGHTS':>8} {'KV':>7} "
          f"{'TOTAL':>8} {'CTX':>7}")
    print("-" * 84)
    for r in rows:
        ctx_s = f"{r['ctx']:,}" if r.get("ctx") else "-"
        w = human_gb(r["weights_bytes"]) if r["weights_bytes"] else "-"
        kv = human_gb(r["kv_bytes"]) if r["kv_bytes"] else "-"
        tot = human_gb(r["total_bytes"]) if r["total_bytes"] else "-"
        print(f"{r['verdict']:<8} {r['name'][:34]:<34} {r['quant']:<8} {w:>8} {kv:>7} "
              f"{tot:>8} {ctx_s:>7}")
        if r.get("note"):
            print(f"{'':<8} -- {r['note']}")
    print("\nFITS = fully GPU-resident.  TIGHT = weights fit, KV at this ctx does not "
          "(lower --ctx).  SPILLS = layers land on CPU.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
