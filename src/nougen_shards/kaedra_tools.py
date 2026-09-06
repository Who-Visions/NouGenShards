"""Read-only tool-calling path for the Kaedra agent (war game Move 3).

Six tools, all read-only, all bound to functions that already exist in this
package. Nothing here writes to the vault, the relay registry, or the fleet.
The model is told to cite only ids and names the tools returned and to say
plainly what it could not check.

Every environment-shaped value resolves from env with a logged fallback:

  NOUGEN_KAEDRA_TOOL_ROUNDS   max tool rounds per run_tool_loop (fallback 4)
  NOUGEN_KAEDRA_TOOL_LIMIT    default and ceiling for list limits (fallback 5)
  NOUGEN_KAEDRA_RESULT_CHARS  max chars of a tool result fed back (fallback 4000)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _env_int(name: str, fallback: int) -> int:
    """Resolve an integer from env; log when the fallback is used."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        logger.info("%s unset; using fallback %d", name, fallback)
        return fallback
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int; using fallback %d", name, raw, fallback)
        return fallback


_CITE_RULE = (" Cite only ids and names this tool returns. If it returns nothing"
              " or an error, say what you could not check; never invent values.")

TOOLS: List[Dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "fleet_whoami",
        "description": "Identity of the node running this agent: machine id, host label,"
                       " hostname, platform." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "shards_search",
        "description": "Search the memory vault for shards matching a query. Returns"
                       " id, db_index, title, score." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search text."},
            "limit": {"type": "integer", "description": "Max shards to return."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "shards_recall",
        "description": "Fetch one shard by id and db_index (both from shards_search)."
                       + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "shard_id": {"type": "integer", "description": "Shard id from shards_search."},
            "db_index": {"type": "integer", "description": "db_index from shards_search."},
        }, "required": ["shard_id", "db_index"]},
    }},
    {"type": "function", "function": {
        "name": "relay_latest",
        "description": "Newest relay handoff legs (any status): id, agent, machine, goal,"
                       " live_status." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Max legs to return."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "relay_open",
        "description": "Relay handoff legs whose live status is still open, acknowledged,"
                       " in progress or blocked." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "Max legs to return."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "reach_state",
        "description": "Live reachability matrix of fleet surfaces. May be unavailable on"
                       " this checkout; if so, report that." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
]

TOOL_NAMES = frozenset(t["function"]["name"] for t in TOOLS)


def _limit(args: dict) -> int:
    ceiling = _env_int("NOUGEN_KAEDRA_TOOL_LIMIT", 5)
    try:
        want = int(args.get("limit", ceiling))
    except (TypeError, ValueError):
        want = ceiling
    return max(1, min(want, ceiling))


# ---- backing functions (read-only, resolved lazily so imports stay cheap) ----

def _fleet_whoami(args: dict) -> dict:
    from nougen_shards.machine import machine_identity
    ident = machine_identity()
    return {"machine_id": ident.get("machine_id"), "host": ident.get("host"),
            "hostname": ident.get("hostname"), "platform": ident.get("platform"),
            "os": ident.get("os")}


def _shards_search(args: dict) -> dict:
    from nougen_shards import core
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required"}
    items = core.retrieve(query, limit=_limit(args)) or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append({"id": it.get("id"), "db_index": it.get("db_index"),
                    "title": it.get("title"), "score": it.get("score")})
    return {"query": query, "shards": out}


def _shards_recall(args: dict) -> dict:
    from nougen_shards import core
    try:
        shard_id = int(args["shard_id"])
        db_index = int(args["db_index"])
    except (KeyError, TypeError, ValueError):
        return {"error": "shard_id and db_index (integers) are required"}
    row = core.get_shard_by_id(shard_id, db_index)
    if not row:
        return {"shard": None, "reason": f"no shard {shard_id} in db {db_index}"}
    cap = _env_int("NOUGEN_KAEDRA_RESULT_CHARS", 4000)
    return {"shard": {"id": row.get("id"), "db_index": db_index,
                      "title": row.get("title"),
                      "content": str(row.get("content", ""))[:cap]}}


def _relay_feed(args: dict, only_open: bool) -> dict:
    from nougen_shards import handoff
    limit = _limit(args)
    # Open filtering happens after the read, so fetch a wider window first.
    feed = handoff.handoff_feed(limit=limit * (4 if only_open else 1)) or []
    legs = []
    for leg in feed:
        live = str(leg.get("live_status") or leg.get("status") or "open").lower()
        if only_open and live.replace("_", "-") not in {
                s.replace("_", "-") for s in handoff.OPEN_STATUSES}:
            continue
        legs.append({"id": leg.get("id"), "agent": leg.get("agent"),
                     "machine": leg.get("machine"), "goal": leg.get("goal"),
                     "timestamp": leg.get("timestamp"), "live_status": live})
        if len(legs) >= limit:
            break
    return {"legs": legs}


def _relay_latest(args: dict) -> dict:
    return _relay_feed(args, only_open=False)


def _relay_open(args: dict) -> dict:
    return _relay_feed(args, only_open=True)


def _reach_state(args: dict) -> dict:
    # tools/reach_matrix.py (PR #249) is a script under tools/, not a package
    # module, so it is only importable when tools/ is on sys.path. Import by
    # probe; report unavailable truthfully. main() is never called (argparse,
    # capture side effects); only the read-only run() entry point is bound.
    try:
        import importlib
        mod = importlib.import_module("reach_matrix")
    except ImportError:
        return {"unavailable": True,
                "reason": "reach_matrix module not on this checkout (PR #249)"}
    run = getattr(mod, "run", None)
    load_manifest = getattr(mod, "load_manifest", None)
    if not (callable(run) and callable(load_manifest)):
        return {"unavailable": True, "reason": "reach_matrix present but exposes no run()"}
    try:
        token = getattr(mod, "node_token", lambda: None)()
        return {"state": run(load_manifest(), token)}
    except Exception as exc:  # pylint: disable=broad-except
        return {"unavailable": True, "reason": f"reach_matrix run failed: {exc}"}


_DISPATCH: Dict[str, Callable[[dict], dict]] = {
    "fleet_whoami": _fleet_whoami,
    "shards_search": _shards_search,
    "shards_recall": _shards_recall,
    "relay_latest": _relay_latest,
    "relay_open": _relay_open,
    "reach_state": _reach_state,
}


def dispatch(name: str, args: Optional[dict] = None) -> dict:
    """Route one tool call to its read-only backing function. Never raises."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": "unknown tool"}
    try:
        result = fn(dict(args or {}))
        return result if isinstance(result, dict) else {"result": result}
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("kaedra tool %s failed: %s", name, exc)
        return {"error": str(exc)}


def _parse_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def run_tool_loop(chat_fn: Callable[..., dict], model: str, messages: list,
                  max_rounds: Optional[int] = None,
                  log: Optional[logging.Logger] = None) -> Tuple[str, List[dict]]:
    """Drive an ollama-style tool loop until the model stops calling tools.

    chat_fn(model, messages, tools=TOOLS) must return the ollama chat
    response dict. Returns (final_text, call_log) where call_log holds one
    {tool, args, result_size, ok} entry per attempted call for grant audit.
    """
    lg = log or logger
    rounds = max_rounds if max_rounds is not None else _env_int("NOUGEN_KAEDRA_TOOL_ROUNDS", 4)
    cap = _env_int("NOUGEN_KAEDRA_RESULT_CHARS", 4000)
    msgs = list(messages)
    call_log: List[dict] = []
    final_text = ""

    for rnd in range(rounds + 1):
        resp = chat_fn(model, msgs, tools=TOOLS) or {}
        if not isinstance(resp, dict) or "error" in resp or "message" not in resp:
            # OllamaClient.chat_raw returns {"error": ...} instead of raising
            # (VRAM refusal, HTTP failure). Surface it: an empty answer with an
            # empty call_log reads as success to a scorer.
            if isinstance(resp, dict):
                err = resp.get("error") or "chat returned no message"
            else:
                err = f"chat returned {type(resp).__name__}, not a dict"
            text = str(err)
            lg.warning("kaedra tool loop chat error: %s", text)
            call_log.append({"tool": "_chat", "args": {}, "result_size": len(text),
                             "ok": False, "error": text})
            return f"[chat error] {text}", call_log
        message = resp.get("message") or {}
        final_text = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []
        if not final_text.strip() and not tool_calls:
            # Thinking-capable models can spend the budget before content;
            # mirror OllamaClient.chat() and keep the reasoning as output.
            thinking = message.get("thinking") or ""
            if isinstance(thinking, str) and thinking.strip():
                final_text = "[recovered from reasoning]\n" + thinking
        if not tool_calls:
            return final_text, call_log
        if rnd >= rounds:
            lg.warning("kaedra tool loop hit max rounds (%d); stopping", rounds)
            break
        msgs.append(message)
        for call in tool_calls:
            fn = (call or {}).get("function") or {}
            name = str(fn.get("name", ""))
            args = _parse_args(fn.get("arguments"))
            if name not in TOOL_NAMES:
                lg.warning("kaedra tool loop refused non-allowlisted tool %r", name)
                call_log.append({"tool": name, "args": args, "result_size": 0, "ok": False,
                                 "refused": True})
                msgs.append({"role": "tool", "tool_name": name,
                             "content": json.dumps({"error": "unknown tool"})})
                continue
            result = dispatch(name, args)
            payload = json.dumps(result, default=str)
            ok = "error" not in result
            call_log.append({"tool": name, "args": args, "result_size": len(payload), "ok": ok})
            lg.info("kaedra tool %s ok=%s size=%d", name, ok, len(payload))
            msgs.append({"role": "tool", "tool_name": name, "content": payload[:cap]})

    if not final_text:
        final_text = "[kaedra] tool round limit reached before a final answer."
    return final_text, call_log
