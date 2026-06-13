#!/usr/bin/env python
"""
Fleet Test — multi-account parallel test/audit orchestrator for NouGenShards.

The "fleet" is the set of cloud accounts whose API keys live in the Keymaker
vault: every OPENROUTER_* key and every OLLAMA_* (Ollama Cloud) key. This tool
treats each account as a worker-agent, fans tasks across them in parallel, and
aggregates the results for a single audit verdict — so you never have to wire
the keys by hand again.

Usage
-----
  python tools/fleet_test.py probe
        Validate every account key (free: OpenRouter GET /key, Ollama /api/tags).

  python tools/fleet_test.py audit [--modules core,history,...] [--model M] [--workers N]
        Parity-audit each TypeScript module in ts/ against its Python source.
        Each module is reviewed by a different account-agent; findings are merged.

  python tools/fleet_test.py delegate "PROMPT" [--n 13] [--model M] [--provider openrouter|ollama]
        Round-robin an arbitrary prompt across N account-agents and collect answers.

  python tools/fleet_test.py benchmark [--shards 100000]
        Benchmark substrate performance: 100k shard ingestion + concurrent BM25 retrieval.

Reports are written to tools/reports/fleet_<command>_<timestamp>.json.
Keys are read from the DPAPI-encrypted vault via keymaker; values are never printed.
Stdlib-only (urllib, concurrent.futures) — no extra dependencies.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import sqlite3
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# --- Locate the package so we can read keys from the vault ---------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nougen_shards import keymaker, core  # noqa: E402  (after sys.path tweak)

REPORTS_DIR = REPO_ROOT / "tools" / "reports"

# Default OpenRouter model + fallbacks (override with --model). Cheap, code-capable.
DEFAULT_OR_MODEL = "deepseek/deepseek-chat"
OR_FALLBACKS = ["google/gemini-2.0-flash-001", "openai/gpt-4o-mini"]

# Ollama Cloud account -> model map (from the fleet roster). Accounts not listed
# fall back to DEFAULT_OLLAMA_MODEL when used as generic workers.
OLLAMA_CLOUD_MODELS = {
    "OLLAMA_WHOV_OLL_KEY": "nemotron-3-ultra:cloud",
    "OLLAMA_CONTACTWHO": "nemotron-3-nano:cloud",
    "OLLAMA_WHOE": "minimax-m3:cloud",
    "OLLAMA_AIWITHDAV3": "gemma4:31b-cloud",
    "OLLAMA_NOUGEN": "nemotron-3-super:cloud",
}
DEFAULT_OLLAMA_MODEL = "gemma4:31b-cloud"

# TS<->Python module pairs eligible for parity audit.
AUDIT_PAIRS = {
    "core": ("src/nougen_shards/core.py", "ts/src/nougen_shards/core.ts"),
    "history": ("src/nougen_shards/history.py", "ts/src/nougen_shards/history.ts"),
    "federation": ("src/nougen_shards/federation.py", "ts/src/nougen_shards/federation.ts"),
    "keymaker": ("src/nougen_shards/keymaker.py", "ts/src/nougen_shards/keymaker.ts"),
    "models_client": ("src/nougen_shards/models_client.py", "ts/src/nougen_shards/models_client.ts"),
    "structured": ("src/nougen_shards/structured.py", "ts/src/nougen_shards/structured.ts"),
    "router": ("src/nougen_shards/router.py", "ts/src/nougen_shards/router.ts"),
    "billing": ("src/nougen_shards/billing.py", "ts/src/nougen_shards/billing.ts"),
    "connectors_sql": ("src/nougen_shards/connectors/sql.py", "ts/src/nougen_shards/connectors/sql.ts"),
    "connectors_cloud": ("src/nougen_shards/connectors/cloud.py", "ts/src/nougen_shards/connectors/cloud.ts"),
    "nougen_context": ("src/nougen_shards/nougen_context.py", "ts/src/nougen_shards/nougen_context.ts"),
    "nougen_sandbox": ("src/nougen_shards/nougen_sandbox.py", "ts/src/nougen_shards/nougen_sandbox.ts"),
    "dream": ("src/nougen_shards/dream.py", "ts/src/nougen_shards/dream.ts"),
    "evolution": ("src/nougen_shards/evolution.py", "ts/src/nougen_shards/evolution.ts"),
    "brain_scan_scanner": ("src/nougen_shards/brain_scan/scanner.py", "ts/src/nougen_shards/brain_scan/scanner.ts"),
    "brain_scan_parsers": ("src/nougen_shards/brain_scan/parsers.py", "ts/src/nougen_shards/brain_scan/parsers.ts"),
    "brain_scan_redaction": ("src/nougen_shards/brain_scan/redaction.py", "ts/src/nougen_shards/brain_scan/redaction.ts"),
    "handoff": ("src/nougen_shards/handoff.py", "ts/src/nougen_shards/handoff.ts"),
    "cli": ("src/nougen_shards/cli.py", "ts/src/nougen_shards/cli.ts"),
    "mcp": ("src/nougen_shards/mcp.py", "ts/src/nougen_shards/mcp.ts"),
}

AUDIT_SYSTEM = (
    "You are a strict source-porting auditor. You are given a Python source file and its "
    "TypeScript port. Report ONLY real behavioral divergences: logic that would produce a "
    "different result/output, off-by-one, wrong default, missing branch, bad hash/encoding, "
    "an async path not awaited, or SQL differences. Ignore style, naming, and formatting. "
    'Respond ONLY with minified JSON: {"module":str,"parity_ok":bool,'
    '"bugs":[{"severity":"high|med|low","issue":str}],"confidence":0..1}'
)


# --- Vault / key helpers -------------------------------------------------------
def fleet_keys(provider: str) -> list[str]:
    """Return vault key-names for a provider ('openrouter' or 'ollama')."""
    names = keymaker.list_providers()
    if provider == "openrouter":
        return sorted(k for k in names if k.startswith("OPENROUTER_") and k != "OPENROUTER_API_KEY")
    if provider == "ollama":
        return sorted(k for k in names if k.startswith("OLLAMA_"))
    raise ValueError(f"unknown provider {provider!r}")


def _short(key_name: str) -> str:
    return key_name.replace("OPENROUTER_", "").replace("OLLAMA_", "")


def _read(rel: str, limit: int = 14000) -> str:
    try:
        return REPO_ROOT.joinpath(rel).read_text(encoding="utf-8")[:limit]
    except OSError as exc:
        return f"<<missing: {exc}>>"


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# --- Provider call wrappers ----------------------------------------------------
def call_openrouter(key_name: str, system: str, prompt: str, model: str,
                    json_mode: bool = False, timeout: int = 120) -> dict:
    val = keymaker.get_secret(key_name)
    if not val:
        return {"error": "key not found in vault"}
    payload = {
        "model": model,
        "models": OR_FALLBACKS,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 900,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {val}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://whovisions.com",
        "X-Title": "NouGenShards-FleetTest",
    }
    try:
        d = _post_json("https://openrouter.ai/api/v1/chat/completions", payload, headers, timeout)
        return {"model": d.get("model", model), "content": d["choices"][0]["message"]["content"]}
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}: {exc.read().decode()[:120]}"}
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": str(exc)[:120]}


def call_ollama_cloud(key_name: str, system: str, prompt: str, model: Optional[str] = None,
                      timeout: int = 180) -> dict:
    val = keymaker.get_secret(key_name)
    if not val:
        return {"error": "key not found in vault"}
    model = model or OLLAMA_CLOUD_MODELS.get(key_name, DEFAULT_OLLAMA_MODEL)
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {val}", "Content-Type": "application/json"}
    try:
        d = _post_json("https://ollama.com/api/chat", payload, headers, timeout)
        return {"model": model, "content": d.get("message", {}).get("content", "")}
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}: {exc.read().decode()[:120]}"}
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": str(exc)[:120]}


def _parse_json_blob(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _run_parallel(items: list, fn: Callable, workers: int) -> list:
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        return list(ex.map(fn, items))


def _write_report(command: str, data) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"fleet_{command}_{stamp}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# --- Commands ------------------------------------------------------------------
def cmd_probe(_args) -> int:
    or_keys = fleet_keys("openrouter")
    oll_keys = fleet_keys("ollama")
    print(f"Probing {len(or_keys)} OpenRouter + {len(oll_keys)} Ollama-cloud account keys...\n")

    def probe_or(name):
        val = keymaker.get_secret(name)
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                         headers={"Authorization": f"Bearer {val}"})
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode()).get("data", {})
            return (name, True, f"usage=${d.get('usage')} limit={d.get('limit') or 'unlimited'}")
        except urllib.error.HTTPError as exc:
            return (name, False, f"HTTP {exc.code}")
        except Exception as exc:  # pylint: disable=broad-except
            return (name, False, str(exc)[:50])

    def probe_oll(name):
        val = keymaker.get_secret(name)
        try:
            req = urllib.request.Request("https://ollama.com/api/tags",
                                         headers={"Authorization": f"Bearer {val}"})
            with urllib.request.urlopen(req, timeout=15) as r:
                ok = r.getcode() == 200
            return (name, ok, OLLAMA_CLOUD_MODELS.get(name, "(generic worker)"))
        except urllib.error.HTTPError as exc:
            return (name, False, f"HTTP {exc.code}")
        except Exception as exc:  # pylint: disable=broad-except
            return (name, False, str(exc)[:50])

    or_res = _run_parallel(or_keys, probe_or, len(or_keys) or 1)
    oll_res = _run_parallel(oll_keys, probe_oll, len(oll_keys) or 1)
    live = 0
    print("OpenRouter:")
    for name, ok, info in sorted(or_res):
        live += ok
        print(f"  {'OK ' if ok else 'XX '}{_short(name):<16} {info}")
    print("\nOllama Cloud:")
    for name, ok, info in sorted(oll_res):
        live += ok
        print(f"  {'OK ' if ok else 'XX '}{_short(name):<16} {info}")
    total = len(or_keys) + len(oll_keys)
    print(f"\nLive: {live}/{total} account-agents")
    _write_report("probe", {"openrouter": [(n, o, i) for n, o, i in or_res],
                            "ollama": [(n, o, i) for n, o, i in oll_res], "live": live, "total": total})
    return 0 if live == total else 1


def cmd_audit(args) -> int:
    selected = list(AUDIT_PAIRS) if not args.modules else [m.strip() for m in args.modules.split(",")]
    selected = [m for m in selected if m in AUDIT_PAIRS]
    keys = fleet_keys("openrouter")
    if not keys:
        print("No OpenRouter account keys in vault. Run keymaker ingest first.")
        return 2
    model = args.model or DEFAULT_OR_MODEL
    print(f"Auditing {len(selected)} modules across {len(keys)} account-agents (model={model})...\n")

    tasks = []
    for i, mod in enumerate(selected):
        py, ts = AUDIT_PAIRS[mod]
        key = keys[i % len(keys)]  # round-robin across accounts for load distribution
        tasks.append((mod, py, ts, key))

    def worker(task):
        mod, py, ts, key = task
        prompt = f"MODULE: {mod}\n\n=== PYTHON ({py}) ===\n{_read(py)}\n\n=== TYPESCRIPT ({ts}) ===\n{_read(ts)}"
        res = call_openrouter(key, AUDIT_SYSTEM, prompt, model, json_mode=True)
        if "error" in res:
            return {"module": mod, "key": _short(key), "error": res["error"]}
        verdict = _parse_json_blob(res["content"]) or {"parity_ok": None, "bugs": [], "raw": res["content"][:200]}
        return {"module": mod, "key": _short(key), "model": res.get("model"), "verdict": verdict}

    results = _run_parallel(tasks, worker, args.workers or len(tasks))

    findings = []
    for r in sorted(results, key=lambda x: x["module"]):
        if "error" in r:
            print(f"  [ERR] {r['module']:<22} via {r['key']:<12} {r['error']}")
            continue
        v = r["verdict"]
        bugs = v.get("bugs") or []
        ok = v.get("parity_ok")
        tag = "OK parity " if ok and not bugs else ("!! bugs   " if bugs else "?? unclear")
        print(f"  {tag} {r['module']:<22} via {r['key']:<12} [{str(r.get('model','')).split('/')[-1][:16]}] conf={v.get('confidence','?')}")
        for b in bugs:
            sev = b.get("severity", "?")
            iss = b.get("issue", "")
            findings.append({"severity": sev, "module": r["module"], "issue": iss})
            print(f"        - [{sev}] {iss[:160]}")

    high = [f for f in findings if f["severity"] == "high"]
    path = _write_report("audit", {"model": model, "modules": selected, "results": results, "findings": findings})
    print(f"\n==== AUDIT SUMMARY ====  modules={len(selected)}  findings={len(findings)}  HIGH={len(high)}")
    print(f"Report -> {path}")
    return 1 if high else 0


def cmd_delegate(args) -> int:
    provider = args.provider
    keys = fleet_keys(provider)
    if not keys:
        print(f"No {provider} keys in vault.")
        return 2
    n = min(args.n or len(keys), len(keys))
    keys = keys[:n]
    print(f"Delegating prompt to {n} {provider} account-agents...\n")

    def worker(key):
        if provider == "openrouter":
            res = call_openrouter(key, "You are a concise assistant.", args.prompt, args.model or DEFAULT_OR_MODEL)
        else:
            res = call_ollama_cloud(key, "You are a concise assistant.", args.prompt, args.model)
        return {"key": _short(key), **res}

    results = _run_parallel(keys, worker, n)
    for r in sorted(results, key=lambda x: x["key"]):
        if "error" in r:
            print(f"  [ERR] {r['key']:<16} {r['error']}")
        else:
            print(f"  [{r['key']:<16}] ({str(r.get('model','')).split('/')[-1]}): {str(r.get('content','')).strip()[:300]}")
    path = _write_report("delegate", {"prompt": args.prompt, "provider": provider, "results": results})
    print(f"\nReport -> {path}")
    return 0


def cmd_benchmark(args) -> int:
    """Run substrate resilience stress test."""
    count = args.shards
    print(f"Initiating Stress Test: {count} shards ingestion + BM25 retrieval load...")
    
    # 1. Ingestion
    start_ingest = time.time()
    for i in range(count):
        core.capture("STRESS", f"Shard {i}", f"Content for shard {i} " * 10)
    ingest_time = time.time() - start_ingest
    print(f"Ingestion {count} shards: {ingest_time:.2f}s ({count/ingest_time:.1f} shards/s)")

    # 2. Retrieval Load (parallelized via ThreadPoolExecutor)
    def run_query(q):
        core.retrieve(q, limit=5)
        
    start_retrieve = time.time()
    queries = [f"Content {i}" for i in range(100)] # 100 concurrent-ish
    _run_parallel(queries, run_query, 10)
    retrieve_time = time.time() - start_retrieve
    print(f"Concurrent retrieval (100 queries): {retrieve_time:.2f}s ({100/retrieve_time:.1f} queries/s)")
    
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fleet_test", description="Multi-account parallel test/audit orchestrator.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("probe", help="Validate every account key (free).")

    pa = sub.add_parser("audit", help="Parity-audit TS modules vs Python across accounts.")
    pa.add_argument("--modules", help="Comma list (default: all). Names: " + ",".join(AUDIT_PAIRS))
    pa.add_argument("--model", help=f"OpenRouter model (default {DEFAULT_OR_MODEL}).")
    pa.add_argument("--workers", type=int, help="Max parallel workers (default: one per module).")

    pd = sub.add_parser("delegate", help="Round-robin a prompt across accounts.")
    pd.add_argument("prompt", help="The prompt to send.")
    pd.add_argument("--n", type=int, help="How many accounts to use (default: all).")
    pd.add_argument("--provider", choices=["openrouter", "ollama"], default="openrouter")
    pd.add_argument("--model", help="Override model.")
    
    pb = sub.add_parser("benchmark", help="Benchmark resilience: ingestion + retrieval.")
    pb.add_argument("--shards", type=int, default=10000, help="Number of shards to ingest (default: 10000).")
    
    return p


def main() -> int:
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    args = build_parser().parse_args()
    start = time.time()
    rc = {"probe": cmd_probe, "audit": cmd_audit, "delegate": cmd_delegate, "benchmark": cmd_benchmark}[args.command](args)
    print(f"\n[fleet_test {args.command} done in {time.time()-start:.1f}s]")
    return rc


if __name__ == "__main__":
    sys.exit(main())
