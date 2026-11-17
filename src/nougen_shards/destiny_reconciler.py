"""Destiny reconciler: one durable loop from prospective memory to verified work.

    GM-intent shards + unfinished destinies
        -> task discovery (idempotent, keyed)
        -> single claim (lease, fenced by owner)
        -> bounded, tenant-scoped recall receipt (context_receipt, #1084)
        -> safety + budget gates
        -> eligible agent on a healthy route (Blade timeout -> Phoebus)
        -> INDEPENDENT verification (verifier id != executor id)
        -> evidence shard + relay leg
        -> destiny link / update, utility marks
        -> next task

This is a tick function, not a daemon. Run it from the scheduler that already
exists (``python -m nougen_shards.destiny_reconciler tick``); a lock file keeps
a second invocation from running beside the first. State lives in SQLite so a
killed tick resumes: a task whose lease expired goes back to the queue.

Every side effect is an injected port (``Ports``) so the loop is testable and
the benchmark can drive it with real or scripted lanes. Nothing here merges,
deploys, edits secrets or deletes data: the safety gate parks such tasks as
``blocked`` until a human authorizes them.

This module makes no claim that the loop is AGI or recursive self-improvement.
Whether shards-first beats its baselines is a measurement (evals/destiny_bench),
and Destiny 10 stays open until that measurement exceeds its own seed band.
"""
from __future__ import annotations

import contextlib
import uuid
import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

QUEUED, CLAIMED, RECALLED, RUNNING, VERIFYING = "queued", "claimed", "recalled", "running", "verifying"
DONE, FAILED, BLOCKED = "done", "failed", "blocked"
OPEN_STATES = (QUEUED, CLAIMED, RECALLED, RUNNING, VERIFYING)

#: Retry strategies, in order. A retry never repeats the previous one.
STRATEGIES = ("baseline", "wider_recall", "decompose", "alternate_agent")

_PROTECTED = re.compile(
    r"(\bmerge\b|\bdeploy\b|\bpublish\b|\bforce[- ]push\b|\bdrop\s+table\b|\brm\s+-rf\b|"
    r"\bforget\b|\bretract\b|\bsecret\b|\bapi[_ -]?key\b|\bcredential|\btoken\b|\bdelete\b)", re.I)


class LeaseLost(Exception):
    """This worker no longer owns the task (lease expired and was re-claimed)."""


class RouteTimeout(Exception):
    """Raised by an executor when a route (e.g. the Blade gateway) times out."""


def _now() -> float:
    return time.time()


def db_path() -> Path:
    """Tenant requests always resolve inside their own vault; the env override
    never applies to them (same rule as destiny.db_path)."""
    from . import core
    raw = os.environ.get("NOUGEN_RECONCILER_DB", "").strip()
    if raw and not core.is_tenant_context():
        return Path(raw)
    return Path(core.active_vault_dir()) / "reconciler.db"


@contextlib.contextmanager
def _connect(path: Optional[Path] = None):
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              key TEXT NOT NULL UNIQUE,
              destiny_id INTEGER,
              intent_ref TEXT,
              goal TEXT NOT NULL,
              state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              strategy_idx INTEGER NOT NULL DEFAULT 0,
              lease_owner TEXT,
              lease_expires REAL,
              tokens_spent INTEGER NOT NULL DEFAULT 0,
              last_agent TEXT,
              blocked_reason TEXT,
              created REAL NOT NULL,
              updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attempts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id INTEGER NOT NULL,
              n INTEGER NOT NULL,
              strategy TEXT NOT NULL,
              agent TEXT, route TEXT,
              outcome TEXT NOT NULL,
              tokens INTEGER NOT NULL DEFAULT 0,
              detail TEXT,
              ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS route_health (
              route TEXT PRIMARY KEY, cooldown_until REAL NOT NULL, last_error TEXT
            );
            """)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@dataclass
class Agent:
    id: str
    skills: Tuple[str, ...] = ()
    max_tokens: int = 4000
    healthy: bool = True


@dataclass
class Config:
    owner: str = "reconciler"
    lease_s: float = 300.0
    max_attempts: int = 4
    task_token_budget: int = 20000
    tick_token_budget: int = 100000
    max_tasks_per_tick: int = 10
    recall_limit: int = 5
    recall_token_cap: int = 1500
    route_cooldown_s: float = 120.0
    routes: Sequence[str] = ("blade", "phoebus")
    auto_fulfill: bool = False
    session_prefix: str = "destiny"


@dataclass
class Ports:
    """Everything the loop touches outside its own SQLite file."""
    list_destinies: Callable[[], List[dict]]
    list_intents: Callable[[], List[dict]]
    recall: Callable[[str, int], dict]                     # (query, limit) -> {tier, partial, shards[]}
    execute: Callable[[dict, Agent, str, dict, str], dict]  # (task, agent, route, context, strategy) -> {output, tokens}
    verify: Callable[[dict, dict], dict]                   # (task, result) -> {passed, evidence, verifier}
    agents: Callable[[], List[Agent]]
    record_evidence: Callable[[dict, dict], str]           # -> shard ref
    publish_relay: Callable[[dict, dict], str]             # -> leg id
    link_destiny: Callable[[int, str, str, str], Any]      # (destiny_id, kind, ref, role)
    update_destiny: Callable[[int, str, str, str], Any]    # (destiny_id, status, actor, evidence)
    mark_utility: Callable[[List[str], bool], Any] = lambda refs, helped: None
    relay_check: Optional[Callable[[], dict]] = None
    safety_gate: Optional[Callable[[dict, str], Tuple[bool, str]]] = None
    clock: Callable[[], float] = _now


def task_key(destiny_id: Optional[int], text: str) -> str:
    h = hashlib.sha1((text or "").strip().lower().encode()).hexdigest()[:12]
    return f"d{destiny_id if destiny_id is not None else 'x'}:{h}"


def default_safety_gate(task: dict, strategy: str) -> Tuple[bool, str]:
    m = _PROTECTED.search(task.get("goal") or "")
    if m:
        return False, f"protected action {m.group(0)!r} needs separate human authorization"
    return True, ""


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------
def discover(ports: Ports, *, path: Optional[Path] = None) -> Dict[str, int]:
    """Turn unfinished destinies and GM-intent shards into queued tasks.

    Idempotent: a task key is derived from (destiny, text), so re-running adds
    nothing. A destiny becomes one task per required event, or one task for its
    goal when it lists none. A destiny with no verification procedure is skipped
    (a goal that cannot be checked is a wish). Intents attach to a destiny only
    if the intent names one; the reconciler never invents a destiny, because
    Destiny 13 forbids duplicates.
    """
    added = skipped = 0
    now = ports.clock()
    items: List[Tuple[Optional[int], Optional[str], str]] = []
    for d in ports.list_destinies():
        if d.get("status") not in ("active", "dormant"):
            continue
        if not d.get("verification"):
            skipped += 1
            continue
        events = d.get("required_events") or []
        texts = events or [d.get("goal") or d.get("title") or ""]
        for t in texts:
            if t:
                items.append((d["id"], None, f"{d.get('title')}: {t}" if events else t))
    for it in ports.list_intents():
        if it.get("text"):
            items.append((it.get("destiny_id"), str(it.get("ref") or ""), it["text"]))
    with _connect(path) as conn:
        for did, ref, text in items:
            cur = conn.execute(
                "INSERT OR IGNORE INTO tasks (key,destiny_id,intent_ref,goal,state,created,updated) VALUES (?,?,?,?,?,?,?)",
                (task_key(did, text), did, ref, text, QUEUED, now, now))
            added += cur.rowcount
    return {"added": added, "skipped_no_verification": skipped}


# --------------------------------------------------------------------------
# claim / resume
# --------------------------------------------------------------------------
def resume_expired(cfg: Config, ports: Ports, *, path: Optional[Path] = None) -> int:
    """Crash-resume: a task whose lease lapsed mid-flight returns to the queue.

    The interrupted attempt is recorded as ``crashed`` and counts against the
    retry bound, so a task that keeps killing its worker cannot loop forever.
    """
    now = ports.clock()
    n = 0
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE state IN (?,?,?,?) AND lease_expires IS NOT NULL AND lease_expires < ?",
            (CLAIMED, RECALLED, RUNNING, VERIFYING, now)).fetchall()
        for r in rows:
            attempts = r["attempts"] + 1
            conn.execute("INSERT INTO attempts (task_id,n,strategy,agent,route,outcome,detail,ts) VALUES (?,?,?,?,?,?,?,?)",
                         (r["id"], attempts, STRATEGIES[min(r["strategy_idx"], len(STRATEGIES) - 1)], r["last_agent"], None,
                          "crashed", f"lease of {r['lease_owner']} expired in {r['state']}", now))
            state = FAILED if attempts >= cfg.max_attempts else QUEUED
            conn.execute("UPDATE tasks SET state=?, attempts=?, lease_owner=NULL, lease_expires=NULL, updated=? WHERE id=?",
                         (state, attempts, now, r["id"]))
            n += 1
    return n


def claim_next(cfg: Config, ports: Ports, *, path: Optional[Path] = None,
               exclude: Sequence[int] = ()) -> Optional[dict]:
    """Atomically take the oldest queued task. One owner per task, enforced by
    the conditional UPDATE; a lost race returns None rather than double-claiming."""
    now = ports.clock()
    with _connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        skip = ",".join("?" * len(exclude))
        row = conn.execute(
            f"SELECT * FROM tasks WHERE state=?{f' AND id NOT IN ({skip})' if exclude else ''} ORDER BY id LIMIT 1",
            (QUEUED, *exclude)).fetchone()
        if row is None:
            return None
        cur = conn.execute(
            "UPDATE tasks SET state=?, lease_owner=?, lease_expires=?, updated=? WHERE id=? AND state=?",
            (CLAIMED, f"{cfg.owner}:{uuid.uuid4().hex[:8]}", now + cfg.lease_s, now, row["id"], QUEUED))
        if cur.rowcount != 1:
            return None
        return dict(conn.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone())


def _set(task_id: int, path: Optional[Path], ports: Ports, cfg: Config, *, fence: Optional[str] = None, **cols) -> None:
    """Update a task. With ``fence`` (the claim token) the write only lands while
    this worker still owns the lease; otherwise LeaseLost is raised."""
    cols["updated"] = ports.clock()
    if cols.get("state") in OPEN_STATES and "lease_expires" not in cols:
        cols["lease_expires"] = ports.clock() + cfg.lease_s
    if cols.get("state") in (DONE, FAILED, BLOCKED, QUEUED):
        cols.setdefault("lease_owner", None)
        cols.setdefault("lease_expires", None)
    sets = ", ".join(f"{k}=?" for k in cols)
    with _connect(path) as conn:
        if fence is None:
            conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*cols.values(), task_id))
        else:
            cur = conn.execute(f"UPDATE tasks SET {sets} WHERE id=? AND lease_owner=?", (*cols.values(), task_id, fence))
            if cur.rowcount != 1:
                raise LeaseLost(f"task {task_id} is no longer leased to {fence}")


def _log_attempt(task: dict, n: int, strategy: str, agent: Optional[str], route: Optional[str],
                 outcome: str, tokens: int, detail: Any, path: Optional[Path], ports: Ports) -> None:
    with _connect(path) as conn:
        conn.execute("INSERT INTO attempts (task_id,n,strategy,agent,route,outcome,tokens,detail,ts) VALUES (?,?,?,?,?,?,?,?,?)",
                     (task["id"], n, strategy, agent, route, outcome, tokens,
                      detail if isinstance(detail, str) else json.dumps(detail, default=str)[:2000], ports.clock()))


# --------------------------------------------------------------------------
# recall receipt, routing, agent choice
# --------------------------------------------------------------------------
def bounded_recall(task: dict, cfg: Config, ports: Ports, *, widen: bool = False) -> Tuple[dict, dict]:
    """Recall with hard bounds, then a #1084 receipt that must validate.

    Returns (context, receipt). The context carries at most ``recall_limit``
    shards and ``recall_token_cap`` tokens (chars/4), cut in rank order.
    ``widen`` doubles both bounds for the wider_recall retry strategy only.
    """
    from . import context_receipt
    limit = cfg.recall_limit * (2 if widen else 1)
    cap = cfg.recall_token_cap * (2 if widen else 1)
    raw = ports.recall(task["goal"], limit) or {}
    kept, used = [], 0
    for s in (raw.get("shards") or [])[:limit]:
        text = str(s.get("text") or s.get("content") or "")
        toks = max(1, len(text) // 4)
        if used + toks > cap:
            break
        kept.append({**s, "text": text})
        used += toks
    raw = {**raw, "shards": kept}
    session = f"{cfg.session_prefix}-{task['key']}"
    relay = ports.relay_check() if ports.relay_check else {"ok": False, "error": "relay check port not supplied"}
    receipt = context_receipt.build(session, task["goal"], raw, relay=relay, agent=cfg.owner)
    receipt["recall"]["tokens"] = used
    receipt["recall"]["bounded"] = {"limit": limit, "token_cap": cap}
    context_receipt.save(receipt)
    ok, why = context_receipt.validate(receipt, session)
    if not ok and context_receipt.degraded_mode() != "reviewed":
        raise PermissionError(f"recall receipt not usable: {why}")
    return {"shards": kept, "tokens": used, "degraded": not ok}, receipt


def _routes_available(cfg: Config, ports: Ports, path: Optional[Path]) -> List[str]:
    now = ports.clock()
    with _connect(path) as conn:
        cool = {r["route"] for r in conn.execute("SELECT route FROM route_health WHERE cooldown_until > ?", (now,))}
    return [r for r in cfg.routes if r not in cool]


def _mark_route(route: str, err: str, cfg: Config, ports: Ports, path: Optional[Path]) -> None:
    with _connect(path) as conn:
        conn.execute("INSERT OR REPLACE INTO route_health (route,cooldown_until,last_error) VALUES (?,?,?)",
                     (route, ports.clock() + cfg.route_cooldown_s, err[:200]))


def choose_agent(task: dict, agents: Sequence[Agent], *, strategy: str, exclude: Sequence[str] = ()) -> Optional[Agent]:
    pool = [a for a in agents if a.healthy and a.id not in exclude]
    if strategy == "alternate_agent" and task.get("last_agent"):
        alt = [a for a in pool if a.id != task["last_agent"]]
        pool = alt or pool
    return pool[0] if pool else None


# --------------------------------------------------------------------------
# one task
# --------------------------------------------------------------------------
def run_task(task: dict, cfg: Config, ports: Ports, *, tick_budget_left: int,
             path: Optional[Path] = None) -> dict:
    """Drive one claimed task through exactly one attempt. Returns an outcome dict.

    Every task write is fenced by the claim token, so a worker that outlived its
    lease cannot overwrite the new owner's state or publish evidence.
    """
    try:
        return _run_task(task, cfg, ports, tick_budget_left=tick_budget_left, path=path)
    except LeaseLost as exc:
        return {"task": task["key"], "outcome": "lease_lost", "reason": str(exc)}


def _run_task(task: dict, cfg: Config, ports: Ports, *, tick_budget_left: int,
              path: Optional[Path] = None) -> dict:
    def S(**cols):
        _set(task["id"], path, ports, cfg, fence=task["lease_owner"], **cols)

    attempt = task["attempts"] + 1
    sidx = min(task["strategy_idx"], len(STRATEGIES) - 1)
    strategy = STRATEGIES[sidx]
    gate = ports.safety_gate or default_safety_gate
    ok, why = gate(task, strategy)
    if not ok:
        S(state=BLOCKED, blocked_reason=why)
        return {"task": task["key"], "outcome": "blocked", "reason": why}
    remaining = min(cfg.task_token_budget - task["tokens_spent"], tick_budget_left)
    if remaining <= 0:
        S(state=BLOCKED, blocked_reason="token budget exhausted")
        return {"task": task["key"], "outcome": "blocked", "reason": "budget"}
    try:
        context, receipt = bounded_recall(task, cfg, ports, widen=(strategy == "wider_recall"))
    except PermissionError as exc:
        _log_attempt(task, attempt, strategy, None, None, "recall_refused", 0, str(exc), path, ports)
        S(state=FAILED if attempt >= cfg.max_attempts else QUEUED, attempts=attempt,
          strategy_idx=min(sidx + 1, len(STRATEGIES) - 1))
        return {"task": task["key"], "outcome": "recall_refused", "reason": str(exc), "attempts": attempt}
    S(state=RECALLED)
    agent = choose_agent(task, ports.agents(), strategy=strategy)
    if agent is None:
        S(state=QUEUED)
        return {"task": task["key"], "outcome": "no_eligible_agent"}
    context["budget_tokens"] = remaining
    goal_for_agent = task if strategy != "decompose" else {**task, "goal": "Break into the smallest steps, then solve: " + task["goal"]}
    result, route_used, tokens = None, None, 0
    S(state=RUNNING, last_agent=agent.id)
    for route in _routes_available(cfg, ports, path):
        try:
            result = ports.execute(goal_for_agent, agent, route, context, strategy)
            route_used = route
            break
        except RouteTimeout as exc:
            _mark_route(route, str(exc), cfg, ports, path)
            _log_attempt(task, attempt, strategy, agent.id, route, "route_timeout", 0, str(exc), path, ports)
        except Exception as exc:  # executor fault: this attempt fails, loop continues
            result = {"error": f"{type(exc).__name__}: {exc}", "tokens": 0}
            route_used = route
            break
    if result is None:
        S(state=QUEUED)
        return {"task": task["key"], "outcome": "all_routes_down"}
    tokens = min(int(result.get("tokens") or 0), 10 ** 9)
    spent = task["tokens_spent"] + tokens
    if tokens > remaining:
        # The executor overran the allowance it was handed: its output is not trusted or published.
        _log_attempt(task, attempt, strategy, agent.id, route_used, "over_budget", tokens,
                     f"used {tokens} of {remaining} allowed", path, ports)
        S(state=BLOCKED, tokens_spent=spent, attempts=attempt, blocked_reason=f"executor exceeded token budget ({tokens}>{remaining})")
        return {"task": task["key"], "outcome": "blocked", "reason": "executor over budget", "tokens": tokens}
    S(state=VERIFYING, tokens_spent=spent)
    verdict = {"passed": False, "evidence": result.get("error", "no output"), "verifier": None}
    if "error" not in result:
        verdict = ports.verify(task, result)
        if verdict.get("verifier") == agent.id or not verdict.get("verifier"):
            verdict = {"passed": False, "verifier": verdict.get("verifier"),
                       "evidence": "verification rejected: verifier must be identified and independent of the executor"}
    S(state=VERIFYING)  # fence check + lease renewal before anything is published
    refs = [str(s.get("id") or s.get("ref")) for s in context["shards"] if s.get("id") or s.get("ref")]
    if verdict.get("passed"):
        shard = ports.record_evidence(task, {"result": result, "verdict": verdict, "receipt": receipt, "agent": agent.id, "route": route_used})
        leg = ports.publish_relay(task, {"shard": shard, "verdict": verdict, "agent": agent.id, "attempt": attempt})
        if task.get("destiny_id") is not None:
            ports.link_destiny(task["destiny_id"], "shard", str(shard), "evidence")
            ports.link_destiny(task["destiny_id"], "relay", str(leg), "outcome")
            ports.link_destiny(task["destiny_id"], "agent", agent.id, "actor")
        ports.mark_utility(refs, True)
        _log_attempt(task, attempt, strategy, agent.id, route_used, "passed", tokens, verdict, path, ports)
        S(state=DONE, attempts=attempt)
        _maybe_fulfill(task, cfg, ports, path)
        return {"task": task["key"], "outcome": "done", "attempts": attempt, "tokens": tokens, "agent": agent.id,
                "route": route_used, "shard": shard, "relay": leg}
    ports.mark_utility(refs, False)
    _log_attempt(task, attempt, strategy, agent.id, route_used, "failed_verification", tokens, verdict, path, ports)
    exhausted = attempt >= cfg.max_attempts or spent >= cfg.task_token_budget
    S(state=FAILED if exhausted else QUEUED, attempts=attempt,
         strategy_idx=min(sidx + 1, len(STRATEGIES) - 1))
    return {"task": task["key"], "outcome": "failed" if exhausted else "retry", "attempts": attempt,
            "next_strategy": STRATEGIES[min(sidx + 1, len(STRATEGIES) - 1)], "tokens": tokens}


def _maybe_fulfill(task: dict, cfg: Config, ports: Ports, path: Optional[Path]) -> None:
    """Fulfil a destiny only when asked to (auto_fulfill) and every task is done.

    Default is conservative: evidence is linked, the destiny stays open, and a
    human or the destiny's own verification decides. Moving dormant -> active
    happens on first success so the registry shows work in flight.
    """
    did = task.get("destiny_id")
    if did is None:
        return
    with _connect(path) as conn:
        total, done = conn.execute("SELECT COUNT(*), SUM(state=?) FROM tasks WHERE destiny_id=?", (DONE, did)).fetchone()
    current = next((d for d in ports.list_destinies() if d.get("id") == did), None)
    if current is not None and current.get("status") == "dormant":
        ports.update_destiny(did, "active", cfg.owner, "reconciler: first verified task")
    if cfg.auto_fulfill and total and done == total:
        ports.update_destiny(did, "fulfilled", cfg.owner, f"{done}/{total} tasks verified independently")


# --------------------------------------------------------------------------
# tick + lock
# --------------------------------------------------------------------------
@contextlib.contextmanager
def single_instance(lock_path: Path, stale_s: float = 900.0):
    """O_EXCL lock so a second reconciler cannot run beside the first."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if lock_path.exists() and time.time() - lock_path.stat().st_mtime > stale_s:
            lock_path.unlink()
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f"another reconciler holds {lock_path}")
    try:
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            lock_path.unlink()


def tick(cfg: Config, ports: Ports, *, path: Optional[Path] = None) -> dict:
    """One reconciliation pass: resume, discover, then work tasks until a bound is hit."""
    out: Dict[str, Any] = {"resumed": resume_expired(cfg, ports, path=path)}
    out["discovered"] = discover(ports, path=path)
    results: List[dict] = []
    tried: List[int] = []  # a task re-queued by an attempt waits for the next tick
    left = cfg.tick_token_budget
    for _ in range(cfg.max_tasks_per_tick):
        if left <= 0:
            break
        task = claim_next(cfg, ports, path=path, exclude=tried)
        if task is None:
            break
        tried.append(task["id"])
        res = run_task(task, cfg, ports, tick_budget_left=left, path=path)
        left -= int(res.get("tokens") or 0)
        results.append(res)
        if left <= 0:
            break
    out["results"] = results
    out["tokens_left"] = left
    return out


def status(*, path: Optional[Path] = None) -> dict:
    with _connect(path) as conn:
        counts = {r["state"]: r["n"] for r in conn.execute("SELECT state, COUNT(*) n FROM tasks GROUP BY state")}
        oc = {r["outcome"]: r["n"] for r in conn.execute("SELECT outcome, COUNT(*) n FROM attempts GROUP BY outcome")}
    return {"tasks": counts, "attempt_outcomes": oc}


# --------------------------------------------------------------------------
# default store-backed ports + CLI
# --------------------------------------------------------------------------
def store_ports(**overrides: Any) -> Ports:
    """Ports backed by the real destiny store. ``execute``, ``verify``, ``agents``,
    ``record_evidence`` and ``publish_relay`` have no safe default (they spend
    budget or publish), so they must come from the caller via ``overrides``."""
    from . import destiny

    def _no(name):
        def f(*a, **k):
            raise NotImplementedError(f"port {name!r} must be supplied by the caller")
        return f

    def _list():
        out = destiny.unfinished_destinies(limit=200)
        return [destiny.get_destiny(d["id"]) | {"required_events": d.get("required_events")}
                for d in out.get("destinies", [])]

    base = dict(
        list_destinies=_list,
        list_intents=lambda: [],
        recall=lambda q, n: {"tier": "none", "reason": "no recall port supplied", "shards": []},
        execute=_no("execute"), verify=_no("verify"), agents=lambda: [],
        record_evidence=_no("record_evidence"), publish_relay=_no("publish_relay"),
        link_destiny=lambda did, kind, ref, role: destiny.link(did, kind, ref, role),
        update_destiny=lambda did, st, actor, ev: destiny.update_status(did, st, actor=actor, evidence=ev),
    )
    base.update(overrides)
    return Ports(**base)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="destiny_reconciler")
    ap.add_argument("cmd", choices=["status", "discover", "tick"])
    ap.add_argument("--ports", help="module:factory returning a Ports (required for tick)")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if a.cmd == "discover":
        print(json.dumps(discover(store_ports()), indent=2))
        return 0
    if not a.ports:
        print("tick needs --ports module:factory (executor/verifier have no safe default)")
        return 2
    import importlib
    mod, _, fn = a.ports.partition(":")
    ports = getattr(importlib.import_module(mod), fn)()
    lock = db_path().with_suffix(".lock")
    with single_instance(lock):
        print(json.dumps(tick(Config(), ports), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
