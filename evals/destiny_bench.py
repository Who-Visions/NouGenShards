"""Destiny reconciler benchmark: shards-first vs prompt-only vs no-memory (#1085).

Every arm runs the SAME tasks through the SAME reconciler tick
(``nougen_shards.destiny_task_reconciler``) on the SAME local lanes. Only the
memory port differs:

    no_memory    recall returns nothing; the agent sees the task alone.
    prompt_only  recall returns nothing; the agent's prompt carries the whole
                 fact sheet (all 100 facts, 75 of them distractors) every call.
    shards_first facts live in a throwaway NouGen vault; recall is the real
                 ``core.retrieve`` path, cut to the reconciler's bounds
                 (top-k, token cap) and wrapped in a #1084 receipt.

Tasks need a fact about a fictional project ("Project Kestrel") that no model
can know, so success measures memory use, not trivia. Each task asks for a
Python ``answer()`` whose value is derived from one fact.

Measured per arm:
    success   tasks DONE, verified by hidden asserts run in a separate python
              process (verifier id ``hidden-tests``, never the executor).
    cost      prompt + completion tokens reported by the lane, all attempts.
    recovery  of tasks hit by an injected fault (first route times out, or the
              worker crashes mid-task and its lease expires), how many still
              finished DONE via route failover / crash-resume.
    rollback  a task that did not finish DONE must have published nothing
              (no evidence shard, no relay leg); a DONE task exactly one each.
              Any other count is a violation.

Isolation: NOUGEN_VAULT_DIR, NOUGEN_DESTINY_DB, NOUGEN_RECONCILER_DB and
NOUGEN_RECEIPTS_DIR all point into a temp dir that is deleted afterwards.
Nothing touches the real vault, destiny registry or relay board.

This is a measurement of one loop on small local models. It proves nothing
about AGI or recursive self-improvement, and the report says so.

Usage:
    python evals/destiny_bench.py --n 100 --out evals/results/destiny_bench_<date>.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLLAMA = os.environ.get("BENCH_OLLAMA", "http://localhost:11434/v1/chat/completions")
PRIMARY = os.environ.get("BENCH_PRIMARY", "gemma4:e2b-qat")
ALTERNATE = os.environ.get("BENCH_ALTERNATE", "gemma2:2b")

NOUNS = [
    "staging port", "retry ceiling", "release build number", "shard quota", "lease seconds",
    "cache size in megabytes", "worker count", "audit retention days", "relay batch size",
    "embedding dimension", "nightly job hour offset", "alert threshold", "upload chunk kilobytes",
    "session timeout minutes", "max tenants", "queue depth", "backup slot", "gateway shard count",
    "review quorum", "token budget in thousands", "health probe interval", "log rotation count",
    "schema version", "canary percentage", "replica count",
]
PROJECTS = ["Kestrel", "Osprey", "Heron", "Plover"]  # Kestrel is asked about; the rest distract
VARIANTS = [
    ("returns {q}", lambda v: v),
    ("returns {q} plus one", lambda v: v + 1),
    ("returns twice {q}", lambda v: v * 2),
    ("returns {q} as a string", lambda v: str(v)),
]


def build_world(seed: int = 1085):
    rng = random.Random(seed)
    facts, truth = [], {}
    for noun in NOUNS:
        for proj in PROJECTS:
            val = rng.randint(1000, 9899)
            facts.append({"project": proj, "noun": noun, "value": val,
                          "text": f"Project {proj}'s {noun} is {val}."})
            if proj == "Kestrel":
                truth[noun] = val
    tasks = []
    for vi, (tmpl, fn) in enumerate(VARIANTS):
        for noun in NOUNS:
            q = f"Project Kestrel's {noun}"
            goal = f"Write a Python function answer() that {tmpl.format(q=q)}."
            tasks.append({"goal": goal, "expected": fn(truth[noun]), "noun": noun, "variant": vi})
    return facts, tasks


# ---------------------------------------------------------------- lanes
def chat(model: str, system: str, user: str, max_tokens: int = 2048, timeout: float = 180.0) -> dict:
    body = json.dumps({"model": model, "messages": [{"role": "system", "content": system},
                                                    {"role": "user", "content": user}],
                       "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    usage = data.get("usage") or {}
    return {"text": data["choices"][0]["message"].get("content") or "",
            "tokens": int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0)}


SYSTEM = ("You write one small Python function. Reply with only a ```python code block that "
          "defines answer() and nothing else. Use only facts you are given; never invent a value.")


def extract_code(text: str) -> str:
    m = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return (m[-1] if m else text).strip()


_FORBIDDEN_NAMES = frozenset({
    "__import__", "eval", "exec", "compile", "open", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "dir", "input", "breakpoint",
})


def _validate_generated_ast(code: str) -> str | None:
    """Reject imports, dunder attributes, and I/O builtins before execution."""
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "forbidden import"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"forbidden dunder attribute: {node.attr}"
        if isinstance(node, ast.Name) and (
            node.id in _FORBIDDEN_NAMES or node.id.startswith("__")
        ):
            return f"forbidden identifier: {node.id}"
    return None


def hidden_verify(code: str, expected) -> tuple[bool, str]:
    err = _validate_generated_ast(code)
    if err:
        return False, f"sandbox rejected: {err}"
    prog = code + f"\n\nassert answer() == {expected!r}, repr(answer())\nprint('ok')\n"
    try:
        p = subprocess.run([sys.executable, "-I", "-c", prog], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    return p.returncode == 0 and "ok" in p.stdout, (p.stderr or p.stdout)[-300:]


# ---------------------------------------------------------------- one arm
class Crash(BaseException):
    """Simulated worker death: escapes the tick like a killed process would."""


def run_arm(arm: str, facts, tasks, *, max_ticks: int = 40, log=print) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"destiny_bench_{arm}_"))
    env = {"NOUGEN_DESTINY_DB": str(tmp / "destinies.db"), "NOUGEN_RECONCILER_DB": str(tmp / "rec.db"),
           "NOUGEN_RECEIPTS_DIR": str(tmp / "receipts"), "NOUGEN_TENANT": "bench"}
    os.environ.update(env)
    from nougen_shards import destiny, destiny_task_reconciler as dr
    core = None
    if arm == "shards_first":
        from nougen_shards import core  # NOUGEN_VAULT_DIR is a throwaway dir set by main()
        assert "bench_vault_" in str(os.environ.get("NOUGEN_VAULT_DIR")), "refusing to seed a real vault"
        for f in facts:
            core.capture("KNOWLEDGE", f"{f['project']} {f['noun']}", f["text"], tags=["destiny-bench"])

    d = destiny.create_destiny(f"bench {arm}", "answer every Kestrel task correctly",
                               verification="hidden asserts per task", status="dormant", actor="bench")
    did = d.get("id") or d.get("destiny", {}).get("id")
    by_goal = {t["goal"]: t for t in tasks}
    cfg = dr.Config(owner=f"bench-{arm}", max_attempts=3, lease_s=300, max_tasks_per_tick=len(tasks),
                    tick_token_budget=10 ** 7, task_token_budget=60000, auto_fulfill=True)
    # Route timeouts are injected on the first configured route only (see
    # execute): the fault is a property of that route, never of whichever
    # route the reconciler happens to try first.
    fault_route = cfg.routes[0]
    for i, t in enumerate(tasks):
        t["route_fault"] = (i % 5 == 0)
        t["crash_fault"] = (i % 10 == 3)
    fired = {"route": set(), "crash": set()}
    published: dict = {}
    usage = {"tokens": 0, "prompt_tokens": 0, "calls": 0, "errors": 0}
    offset = [0.0]
    sheet = "\n".join(f["text"] for f in facts)

    def clock():
        return time.time() + offset[0]

    def recall(query, limit):
        if arm != "shards_first":
            return {"tier": f"{arm}-arm", "partial": False, "shards": []}
        hits = core.retrieve(query, limit=limit) or []
        return {"tier": "fts+vector", "partial": False,
                "shards": [{"id": h.get("id"), "text": h.get("content") or h.get("text") or ""} for h in hits]}

    def execute(task, agent, route, context, strategy):
        key = task["goal"].replace("Break into the smallest steps, then solve: ", "")
        t = by_goal[key]
        # The injected timeout belongs to the first configured route (the
        # primary lane), not to whichever route the reconciler tries first:
        # which route is tried first is decided by the cooldown table, so
        # firing on attempt order lets the fault leak onto the failover route
        # and knock out the last healthy lane instead of measuring failover.
        # A flagged task attempted while the primary route cools down runs
        # unfaulted on the failover route; only fired faults count as faulted.
        if t["route_fault"] and route == fault_route and key not in fired["route"]:
            fired["route"].add(key)
            raise dr.RouteTimeout(f"injected: {route} timeout")
        if t["crash_fault"] and key not in fired["crash"]:
            fired["crash"].add(key)
            raise Crash("injected: worker killed mid-task")
        facts_txt = ""
        if arm == "prompt_only":
            facts_txt = "Known facts:\n" + sheet
        elif context["shards"]:
            facts_txt = "Known facts:\n" + "\n".join(s["text"] for s in context["shards"])
        user = (facts_txt + "\n\n" if facts_txt else "") + "Task: " + task["goal"]
        model = PRIMARY if agent.id == "e2b-qat" else ALTERNATE
        try:
            r = chat(model, SYSTEM, user)
        except Exception as exc:
            usage["errors"] += 1
            raise RuntimeError(f"lane error: {exc}")
        usage["tokens"] += r["tokens"]
        usage["prompt_tokens"] += r["prompt_tokens"]
        usage["calls"] += 1
        return {"output": extract_code(r["text"]), "tokens": r["tokens"]}

    def verify(task, result):
        ok, detail = hidden_verify(result["output"], by_goal[task["goal"]]["expected"])
        return {"passed": ok, "evidence": detail, "verifier": "hidden-tests"}

    def record_evidence(task, payload):
        published.setdefault(task["goal"], {"evidence": 0, "relay": 0})["evidence"] += 1
        return f"bench-shard-{task['id']}"

    def publish_relay(task, payload):
        published.setdefault(task["goal"], {"evidence": 0, "relay": 0})["relay"] += 1
        return f"bench-leg-{task['id']}"

    ports = dr.store_ports(
        list_destinies=lambda: [destiny.get_destiny(did) | {"verification": None}],  # no goal task; updates still flow
        list_intents=lambda: [{"ref": f"t{i}", "text": t["goal"], "destiny_id": did} for i, t in enumerate(tasks)],
        recall=recall, execute=execute, verify=verify,
        agents=lambda: [dr.Agent("e2b-qat"), dr.Agent("gemma2-2b")],
        record_evidence=record_evidence, publish_relay=publish_relay,
        relay_check=lambda: {"ok": True, "legs": 0}, clock=clock)

    t0 = time.time()
    crashes = ticks = 0
    for ticks in range(1, max_ticks + 1):
        try:
            out = dr.tick(cfg, ports)
        except Crash:
            crashes += 1
            offset[0] += cfg.lease_s + 1  # the dead worker's lease lapses; next tick resumes it
            continue
        st = dr.status()["tasks"]
        log(f"[{arm}] tick {ticks}: {st} tokens={usage['tokens']}")
        if not out["results"] and not st.get("queued"):
            break
    wall = time.time() - t0

    import sqlite3
    con = sqlite3.connect(env["NOUGEN_RECONCILER_DB"])
    con.row_factory = sqlite3.Row
    rows = {r["goal"]: dict(r) for r in con.execute("SELECT goal,state,attempts,strategy_idx FROM tasks")}
    outcomes = {r[0]: r[1] for r in con.execute("SELECT outcome, COUNT(*) FROM attempts GROUP BY outcome")}
    strat = {r[0]: r[1] for r in con.execute("SELECT strategy, COUNT(*) FROM attempts WHERE outcome='passed' GROUP BY strategy")}
    con.close()
    done = [g for g, r in rows.items() if r["state"] == "done"]
    faulted = [t["goal"] for t in tasks if t["goal"] in fired["route"] | fired["crash"]]
    violations = []
    for g, r in rows.items():
        p = published.get(g, {"evidence": 0, "relay": 0})
        want = 1 if r["state"] == "done" else 0
        if p["evidence"] != want or p["relay"] != want:
            violations.append({"goal": g, "state": r["state"], **p})
    final = destiny.get_destiny(did)
    res = {
        "arm": arm, "tasks": len(tasks), "done": len(done), "success_rate": round(len(done) / len(tasks), 3),
        "states": {s: sum(1 for r in rows.values() if r["state"] == s) for s in {r["state"] for r in rows.values()}},
        "first_attempt_passes": strat.get("baseline", 0), "passes_by_strategy": strat,
        "attempt_outcomes": outcomes,
        "tokens_total": usage["tokens"], "prompt_tokens": usage["prompt_tokens"], "lane_calls": usage["calls"],
        "lane_errors": usage["errors"],
        "tokens_per_success": round(usage["tokens"] / len(done)) if done else None,
        "faults_injected": {"route_timeout": len(fired["route"]), "crash": len(fired["crash"]), "crash_ticks": crashes},
        "recovery_rate": round(sum(1 for g in faulted if g in done) / len(faulted), 3) if faulted else None,
        "faulted_tasks": len(faulted), "faulted_done": sum(1 for g in faulted if g in done),
        # compare recovery_rate with this: a fault-tolerant loop matches its own unfaulted rate
        "unfaulted_success_rate": round(sum(1 for t in tasks if t["goal"] not in faulted and t["goal"] in done)
                                        / max(1, len(tasks) - len(faulted)), 3),
        "faulted_tasks_lost": sum(1 for g in faulted if rows.get(g, {}).get("state") not in ("done", "failed")),
        "rollback_violations": len(violations), "violation_samples": violations[:5],
        "destiny_final_status": final.get("status"), "ticks": ticks, "wall_s": round(wall, 1),
    }
    shutil.rmtree(tmp, ignore_errors=True)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--arms", default="no_memory,prompt_only,shards_first")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    facts, tasks = build_world()
    tasks = tasks[: a.n]
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema": "destiny-bench/1", "issue": 1085, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "lanes": {"primary": PRIMARY, "alternate": ALTERNATE, "endpoint": OLLAMA},
              "world": {"facts": len(facts), "distractors": len(facts) - len(NOUNS), "tasks": len(tasks)},
              "claim_limits": "Measures one reconciler loop on small local models. Proves nothing about AGI or RSI.",
              "arms": []}
    for arm in a.arms.split(","):
        # each arm in its own process: the vault and destiny paths resolve at import time
        sub = subprocess.run([sys.executable, __file__, "--_arm", arm, "--n", str(a.n)],
                             capture_output=True, text=True, cwd=ROOT,
                             env={**os.environ, "PYTHONPATH": str(ROOT / "src"),
                                  "NOUGEN_VAULT_DIR": tempfile.mkdtemp(prefix=f"bench_vault_{arm}_")})
        sys.stderr.write(sub.stderr[-4000:])
        line = [l for l in sub.stdout.splitlines() if l.startswith("RESULT ")]
        report["arms"].append(json.loads(line[-1][7:]) if line else {"arm": arm, "error": sub.stderr[-1500:]})
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps([{k: r.get(k) for k in ("arm", "success_rate", "tokens_total", "tokens_per_success",
                                             "recovery_rate", "rollback_violations", "error")} for r in report["arms"]], indent=1))
    return 0


if __name__ == "__main__":
    if "--_arm" in sys.argv:
        i = sys.argv.index("--_arm")
        arm = sys.argv[i + 1]
        n = int(sys.argv[sys.argv.index("--n") + 1])
        vault = os.environ.get("NOUGEN_VAULT_DIR")
        facts, tasks = build_world()
        try:
            res = run_arm(arm, facts, tasks[:n], log=lambda m: print(m, file=sys.stderr, flush=True))
        finally:
            if vault and "bench_vault_" in vault:
                shutil.rmtree(vault, ignore_errors=True)
        print("RESULT " + json.dumps(res, default=str))
        sys.exit(0)
    sys.exit(main())
