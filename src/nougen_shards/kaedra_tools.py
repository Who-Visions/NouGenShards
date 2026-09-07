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

from nougen_shards import locator

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
                       " locator (node:db#id), id, db_index, title, score. Cite the"
                       " locator, never the bare id: ids are per-DB and collide." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search text."},
            "limit": {"type": "integer", "description": "Max shards to return."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "shards_recall",
        "description": "Fetch one shard by its locator from shards_search."
                       " A bare id is rejected as ambiguous." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "locator": {"type": "string",
                        "description": "Locator from shards_search, e.g. blade:2#29825."},
            "shard_id": {"type": "integer", "description": "Legacy: id, needs db_index."},
            "db_index": {"type": "integer", "description": "Legacy: db_index."},
        }, "required": []},
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
    {"type": "function", "function": {
        "name": "shards_capture",
        "description": "Capture an insight, finding, or experience directly into the memory vault."
                       " Automatically stamped with kaedra-authored tag and provenance." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "Short title describing the finding."},
            "content": {"type": "string", "description": "The detailed content to persist in the vault."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional search tags."},
        }, "required": ["title", "content"]},
    }},
    {"type": "function", "function": {
        "name": "nougenmsg_send",
        "description": "Send an inter-agent or fleet message over the NouGenMsg bus."
                       " Lane-scoped and echo-guarded (cannot target self/kaedra)." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string", "description": "Destination: e.g. @blade, @phoebus, @claude, @all, @antigravity, @codex."},
            "message": {"type": "string", "description": "Message text to deliver."},
        }, "required": ["target", "message"]},
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
    model = os.getenv("NOUGEN_KAEDRA_MODEL", "kaedra:e4b")
    gateway = os.getenv("NOUGEN_KAEDRA_GATEWAY", "http://127.0.0.1:4455")
    return {
        "agent": "Kaedra",
        "machine_id": ident.get("machine_id"),
        "host": ident.get("host"),
        "hostname": ident.get("hostname"),
        "platform": ident.get("platform"),
        "os": ident.get("os"),
        "serving_node": ident.get("host"),
        "model_tag": model,
        "gateway": gateway,
        "grant_scope": sorted(list(TOOL_NAMES)),
        "identity_source": "tool:fleet_whoami",
    }


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
        # core.retrieve tags rows with the private _db_index; reading "db_index"
        # here returned None for every row, so shards_search advertised a db_index
        # it never supplied and callers fell back to citing bare, colliding ids.
        db = it.get("_db_index", it.get("db_index"))
        out.append({"id": it.get("id"), "db_index": db,
                    "locator": locator.format_locator(it.get("id"), db),
                    "title": it.get("title"), "score": it.get("score")})
    return {"query": query, "shards": out}


def _shards_recall(args: dict) -> dict:
    from nougen_shards import core
    ref = locator.parse(args.get("locator") or args.get("shard_id"))
    if ref is None:
        return {"error": "locator (node:db#id) or shard_id + db_index is required"}
    db_index = ref.db_index
    if db_index is None:
        try:
            db_index = int(args["db_index"])
        except (KeyError, TypeError, ValueError):
            # Refuse to guess. A bare id names a different shard in every DB, so
            # defaulting here would return a confidently wrong row.
            return {"error": f"shard id {ref.shard_id} is ambiguous without a db_index;"
                             f" pass the locator from shards_search (node:db#id)"}
    row = core.get_shard_by_id(ref.shard_id, db_index)
    loc = locator.format_locator(ref.shard_id, db_index)
    if not row:
        return {"shard": None, "reason": f"no shard {loc}"}
    cap = _env_int("NOUGEN_KAEDRA_RESULT_CHARS", 4000)
    return {"shard": {"id": row.get("id"), "db_index": db_index, "locator": loc,
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


def _shards_capture(args: dict) -> dict:
    from nougen_shards import core
    title = str(args.get("title", "")).strip()
    content = str(args.get("content", "")).strip()
    if not title or not content:
        return {"error": "title and content are required for shards_capture"}

    raw_tags = args.get("tags") or []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    else:
        tags = []

    if "kaedra-authored" not in tags:
        tags.append("kaedra-authored")

    res = core.capture(
        event_type="kaedra_insight",
        title=title,
        content=content,
        tags=tags,
        source_uri="agent:kaedra:move3"
    )
    if isinstance(res, dict):
        return {
            "captured": bool(res.get("captured")),
            "shard_id": res.get("shard_id"),
            "db_index": res.get("db_index"),
            "reason": res.get("reason"),
            "tags": tags,
        }
    return {"captured": bool(res), "tags": tags}


def _nougenmsg_send(args: dict) -> dict:
    from nougen_shards.nougenmsg import NouGenMsgBus, get_current_node
    target = str(args.get("target", "")).strip()
    message = str(args.get("message", "")).strip()
    if not target or not message:
        return {"error": "target and message are required for nougenmsg_send"}

    # Echo guard: do not allow messaging herself or creating recursive wakeup loops
    clean = target.lower().lstrip("@")
    if "kaedra" in clean or "self" in clean:
        return {"error": "refused: echo guard prevented targeting self/kaedra"}

    node, agent = NouGenMsgBus.parse_destination(target)
    if agent == "kaedra":
        return {"error": "refused: echo guard prevented targeting agent kaedra"}

    origin = {
        "original_sender": "kaedra",
        "machine": get_current_node(),
        "lane": "kaedra-autonomous",
        "provenance_state": "asserted",
    }
    res = NouGenMsgBus.live_ping(agent, message, node=node, origin=origin)
    return {"delivered": True, "target": target, "result": res}


_DISPATCH: Dict[str, Callable[[dict], dict]] = {
    "fleet_whoami": _fleet_whoami,
    "shards_search": _shards_search,
    "shards_recall": _shards_recall,
    "relay_latest": _relay_latest,
    "relay_open": _relay_open,
    "reach_state": _reach_state,
    "shards_capture": _shards_capture,
    "nougenmsg_send": _nougenmsg_send,
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
            # (VRAM refusal, HTTP failure). Attempt cloud fallback before giving up.
            if isinstance(resp, dict):
                err = resp.get("error") or "chat returned no message"
            else:
                err = f"chat returned {type(resp).__name__}, not a dict"
            text = str(err)

            if _env_int("NOUGEN_KAEDRA_FALLBACK", 1):
                try:
                    from nougen_shards.workers_ai_client import kaedra_cloud_fallback
                    lg.info("kaedra tool loop local chat error (%s); trying workers-ai fallback", text)
                    fb_resp = kaedra_cloud_fallback(messages=msgs, tools=TOOLS)
                    if isinstance(fb_resp, dict) and "message" in fb_resp and "error" not in fb_resp:
                        call_log.append({"tool": "_workers_ai_fallback", "args": {"original_error": text},
                                         "result_size": len(json.dumps(fb_resp.get("usage", {}))), "ok": True})
                        resp = fb_resp
                    else:
                        fb_err = fb_resp.get("error") if isinstance(fb_resp, dict) else str(fb_resp)
                        lg.warning("workers-ai cloud fallback also failed: %s", fb_err)
                except Exception as fb_exc:  # pylint: disable=broad-except
                    lg.warning("workers-ai fallback raised: %s", fb_exc)

            if not isinstance(resp, dict) or "error" in resp or "message" not in resp:
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
