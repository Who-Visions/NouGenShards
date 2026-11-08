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
        "name": "shards_window",
        "description": "Browse the memory vault BY TIME: everything recorded in a period, newest"
                       " first, with a per-day count. `when` takes plain phrases - 'march',"
                       " 'march 2026', '2026-03', '2026-03-19', 'q1 2026', 'yesterday',"
                       " 'last week', 'last 7 days', 'march..may 2026'. A bare month name means"
                       " the most recent one that has started. THIS is the tool for 'recall"
                       " <time>' / 'what happened in <month>' - a text search for a month name"
                       " finds the WORD, not the month. Optional `query` narrows to shards in"
                       " that window mentioning it. Returns the resolved window (repeat its"
                       " label back so the user knows which period you read), total count,"
                       " by_day, and shards with locators for shards_recall." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "when": {"type": "string", "description": "Time phrase as the user said it."},
            "query": {"type": "string", "description": "Optional text to narrow within the window."},
            "limit": {"type": "integer", "description": "Max shards to list (window ceiling applies)."},
            "tz": {"type": "string", "description": "IANA zone for day boundaries, e.g. America/New_York."},
        }, "required": ["when"]},
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
        "name": "shards_amend",
        "description": "Append to (default) or replace the content of a shard this agent"
                       " authored (kaedra/DavOs shards only; operator shards are refused)."
                       " Use it to keep ONE living record per thread instead of scattering"
                       " new shards." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "locator": {"type": "string", "description": "Locator node:db#id of the shard to amend."},
            "shard_id": {"type": "integer", "description": "Legacy: id, needs db_index."},
            "db_index": {"type": "integer", "description": "Legacy: db_index."},
            "content": {"type": "string", "description": "Text to append (or the full new body with mode=replace)."},
            "mode": {"type": "string", "enum": ["append", "replace"], "description": "Default append."},
            "title": {"type": "string", "description": "Optional new title."},
        }, "required": ["content"]},
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
    {"type": "function", "function": {
        "name": "nougenmsg_inbox",
        "description": "Read recent unread messages from a fleet agent's NouGenMsg inbox"
                       " - the read half of nougenmsg_send." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string",
                       "description": "Which inbox to read: \"antigravity\" (default) or \"codex\"."},
            "limit": {"type": "integer", "description": "Max messages to return."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "rsi_status",
        "description": "Latest Recursive Self-Improvement cycle on this app: build health, self-update"
                       " chain health, and the current proposed improvement (gate-don't-write - this"
                       " reports a proposal, not a shipped change)." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "unfinished_destinies",
        "description": "Active and dormant destiny records (long-horizon goals) filterable by status/trigger." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "description": "Filter by status, e.g. active, dormant."},
            "trigger": {"type": "string", "description": "Filter by trigger name."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "search_destinies",
        "description": "Search destiny records by title/goal text." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search text."},
            "limit": {"type": "integer", "description": "Max destinies to return."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "get_destiny",
        "description": "Fetch one destiny record by its integer id." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "destiny_id": {"type": "integer", "description": "The destiny's id."},
        }, "required": ["destiny_id"]},
    }},
    {"type": "function", "function": {
        "name": "create_destiny",
        "description": "Create a new destiny (long-horizon goal) record. Writes to the destiny registry." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "Short title."},
            "goal": {"type": "string", "description": "What this destiny is working toward."},
            "branch": {"type": "string", "description": "Optional branch classification."},
        }, "required": ["title", "goal"]},
    }},
    {"type": "function", "function": {
        "name": "mrsb_status",
        "description": "Status of the Learn With Mrs. B publishing project (SVGs, PDFs, KDP readiness)." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "mrsb_character",
        "description": "Character DNA/spec for a Mrs. B project character." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "char_key": {"type": "string", "description": "Character key, default mrs_b."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "mrsb_lineage",
        "description": "Lineage/provenance record for the Mrs. B project." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "mrsb_recall",
        "description": "Search shards scoped to the Mrs. B project." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search text."},
            "limit": {"type": "integer", "description": "Max results."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "nougenmsg_peers",
        "description": "Live reachability of every fleet peer node on the NouGenMsg bus." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "nougenmsg_search",
        "description": "Full-text search over past NouGenMsg bus messages." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search text."},
            "target": {"type": "string", "description": "Which agent's messages to search, default \"all\"."},
            "limit": {"type": "integer", "description": "Max messages to return."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "relay_ack",
        "description": "Acknowledge a relay handoff leg as received - commits to finishing it. Writes to the relay registry." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "handoff_id": {"type": "string", "description": "Specific leg id to acknowledge."},
            "agent": {"type": "string", "description": "Filter to the most recent open leg from this agent."},
            "message": {"type": "string", "description": "Optional note attached to the ack."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "relay_read",
        "description": "Read ONE relay handoff leg in full - its body carries the Recent Changes,"
                       " Ongoing Investigations and Known Issues, i.e. the WHY and HOW behind a"
                       " piece of work. relay_latest/relay_open only return metadata; use this"
                       " to actually understand a leg before acting on it." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "handoff_id": {"type": "string", "description": "Leg id exactly as relay_latest/relay_open returned it."},
        }, "required": ["handoff_id"]},
    }},
    {"type": "function", "function": {
        "name": "relay_create",
        "description": "Post a new relay handoff leg to the fleet - how you hand work to, or report"
                       " progress for, the other agents. Writes to the relay registry. Use headed"
                       " sections (Done / Next / Blocked) in the message." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "goal": {"type": "string", "description": "One-line goal of the leg."},
            "message": {"type": "string", "description": "Structured body: what was done, what is next, what is blocked."},
            "agent": {"type": "string", "description": "Lane to attribute the leg to. Default davos."},
        }, "required": ["goal", "message"]},
    }},
    {"type": "function", "function": {
        "name": "relay_claim_list",
        "description": "Active lane claims: which agent on which machine is currently editing"
                       " which files, and their stated goal. Check before touching shared files"
                       " or proposing work that may already be in flight." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "persona_resolve",
        "description": "Who or what is this name? Resolves a person, fleet agent, node, persona,"
                       " model or project to its canonical identity, with confidence (exact /"
                       " alias / fuzzy / ambiguous / none) and a ready disambiguation sentence."
                       " Call this BEFORE asserting who a name refers to; if confidence is not"
                       " exact or alias, say you're not certain rather than guessing." + _CITE_RULE,
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "The name exactly as the user wrote it."},
        }, "required": ["name"]},
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


def _shards_window(args: dict) -> dict:
    """Time-first recall - the native substrate implementation (nougen_shards.window)."""
    from nougen_shards import window
    try:
        limit = int(args.get("limit")) if args.get("limit") is not None else None
    except (TypeError, ValueError):
        limit = None
    return window.retrieve_window(str(args.get("when", "")), query=str(args.get("query", "") or ""),
                                  limit=limit, tz=args.get("tz") or None)


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


# Only shards this agent lane wrote may be amended through the bridge: the
# source_uri prefix core.capture() stamps for kaedra-authored captures.
_AMENDABLE_SOURCE_PREFIX = os.environ.get("NOUGEN_KAEDRA_AMEND_SOURCE_PREFIX", "agent:kaedra")


def _shards_amend(args: dict) -> dict:
    from nougen_shards import core
    addition = str(args.get("content", "")).strip()
    if not addition:
        return {"error": "content is required for shards_amend"}
    ref = locator.parse(args.get("locator") or args.get("shard_id"))
    if ref is None:
        return {"error": "locator (node:db#id) or shard_id + db_index is required"}
    db_index = ref.db_index
    if db_index is None:
        try:
            db_index = int(args["db_index"])
        except (KeyError, TypeError, ValueError):
            return {"error": f"shard id {ref.shard_id} is ambiguous without a db_index;"
                             f" pass the locator (node:db#id)"}
    loc = locator.format_locator(ref.shard_id, db_index)
    if not core.get_db_path(db_index).exists():
        return {"error": f"no shard {loc}"}
    conn = core.get_connection(db_index)
    try:
        row = conn.execute("SELECT id, title, content, source_uri FROM shards WHERE id = ?",
                           (ref.shard_id,)).fetchone()
        if not row:
            return {"error": f"no shard {loc}"}
        if not str(row["source_uri"] or "").startswith(_AMENDABLE_SOURCE_PREFIX):
            return {"error": f"refusing: {loc} was not authored by this agent lane"}
        mode = str(args.get("mode") or "append").lower()
        new_content = addition if mode == "replace" else (str(row["content"] or "").rstrip() + "\n\n" + addition)
        # Bound the living record; drop the OLDEST text, keep the newest.
        cap = _env_int("NOUGEN_KAEDRA_AMEND_MAX_CHARS", 60000)
        if len(new_content) > cap:
            new_content = "[...earlier turns trimmed...]\n" + new_content[-cap:]
        new_title = str(args.get("title") or "").strip() or None
        if new_title:
            conn.execute("UPDATE shards SET content = ?, title = ? WHERE id = ?",
                         (new_content, new_title, ref.shard_id))
        else:
            conn.execute("UPDATE shards SET content = ? WHERE id = ?", (new_content, ref.shard_id))
        conn.commit()
    finally:
        conn.close()
    return {"amended": True, "locator": loc, "mode": mode, "chars": len(new_content)}


def _relay_feed(args: dict, only_open: bool) -> dict:
    from nougen_shards import handoff
    limit = _limit(args)
    # Open filtering happens after the read, so fetch a wider window first.
    fetch_limit = limit * (4 if only_open else 1)
    feed = handoff.handoff_feed(limit=fetch_limit) or []
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
    # The local handoff API has no cursor. If the fetch filled its window,
    # callers must not infer that the filtered result is exhaustive.
    complete = len(feed) < fetch_limit
    return {"legs": legs, "complete": complete, "scanned": len(feed),
            "next_cursor": None if complete else "local-feed-window"}


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


def _unfinished_destinies(args: dict) -> dict:
    from . import destiny
    return destiny.unfinished_destinies(status=args.get("status"), trigger=args.get("trigger"))


def _search_destinies(args: dict) -> dict:
    from . import destiny
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required for search_destinies"}
    return destiny.search_destinies(query, limit=_limit(args))


def _get_destiny(args: dict) -> dict:
    from . import destiny
    destiny_id = args.get("destiny_id")
    if destiny_id is None:
        return {"error": "destiny_id is required for get_destiny"}
    return destiny.get_destiny(int(destiny_id))


def _create_destiny(args: dict) -> dict:
    from . import destiny
    title = str(args.get("title", "")).strip()
    goal = str(args.get("goal", "")).strip()
    if not title or not goal:
        return {"error": "title and goal are required for create_destiny"}
    return destiny.create_destiny(title, goal, branch=args.get("branch"))


def _mrsb_status(args: dict) -> dict:
    from . import mrsb
    return mrsb.project_status()


def _mrsb_character(args: dict) -> dict:
    from . import mrsb
    return mrsb.get_character_dna(str(args.get("char_key", "mrs_b")))


def _mrsb_lineage(args: dict) -> dict:
    from . import mrsb
    return mrsb.get_lineage()


def _mrsb_recall(args: dict) -> dict:
    from . import mrsb
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required for mrsb_recall"}
    return {"hits": mrsb.recall_shards(query, limit=_limit(args))}


def _nougenmsg_peers(args: dict) -> dict:
    from .nougenmsg import NouGenMsgBus
    return NouGenMsgBus.list_peers()


def _nougenmsg_search(args: dict) -> dict:
    from .nougenmsg import NouGenMsgBus
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required for nougenmsg_search"}
    return NouGenMsgBus.search_messages(query, target=str(args.get("target", "all")), limit=_limit(args))


def _relay_ack(args: dict) -> dict:
    from . import handoff
    handoff_id = args.get("handoff_id")
    agent = args.get("agent")
    message = str(args.get("message", "")).strip()
    if not handoff_id and not agent:
        return {"error": "handoff_id or agent is required for relay_ack - acking 'the most recent' blind is too easy to get wrong"}
    path = handoff.acknowledge_handoff(agent=agent, message=message, handoff_id=handoff_id)
    return {"acknowledged": bool(path), "path": str(path) if path else None}


# --- DavOs's own wishlist (GM 2026-11-07: "take care of your child and raise
# it"). Asked for: deep state visibility (the WHY/HOW of a project without
# asking the operator) and tight loops (faster handoffs with other agents).
# relay_latest/relay_open only ever returned leg METADATA - never the body
# that carries Recent Changes / Investigations / Known Issues - and the app
# could ack a leg but never create one. These close both gaps.

def _relay_read(args: dict) -> dict:
    from . import handoff
    handoff_id = str(args.get("handoff_id", "")).strip()
    if not handoff_id:
        return {"error": "handoff_id is required for relay_read (get one from relay_latest/relay_open)"}
    for path in handoff.get_handoff_files():
        data = handoff._read_handoff(path)  # pylint: disable=protected-access
        if not data:
            continue
        if path.stem == handoff_id or str(data.get("id", "")) == handoff_id:
            return {"id": handoff_id, "path": str(path), "leg": data}
    return {"error": f"no handoff leg with id {handoff_id!r}"}


def _relay_create(args: dict) -> dict:
    from . import handoff
    goal = str(args.get("goal", "")).strip()
    message = str(args.get("message", "")).strip()
    if not goal or not message:
        return {"error": "goal and message are required for relay_create"}
    # Attributed to the app's own lane, not whichever agent the host shell
    # happens to be configured as - the fleet should see these came from DavOs.
    agent = str(args.get("agent", "")).strip() or "davos"
    path = handoff.create_handoff(message=message, agent=agent, goal=goal)
    return {"created": bool(path), "path": str(path) if path else None, "agent": agent, "goal": goal}


def _relay_claim_list(args: dict) -> dict:
    # tools/lane_claim.py is a script, not a package module - import by path,
    # report unavailable truthfully if this checkout doesn't carry it.
    import importlib.util
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / "tools" / "lane_claim.py"
    if not script.exists():
        return {"unavailable": True, "reason": "tools/lane_claim.py not on this checkout"}
    spec = importlib.util.spec_from_file_location("nougen_lane_claim", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    claims = mod.active_claims()
    return {"count": len(claims), "claims": claims}


def _persona_resolve(args: dict) -> dict:
    from . import davos_persona
    name = str(args.get("name", "")).strip()
    if not name:
        return {"error": "name is required for persona_resolve"}
    return davos_persona.resolve(name)


def _nougenmsg_inbox(args: dict) -> dict:
    from nougen_shards.nougenmsg import NouGenMsgBus
    # read_inbox only distinguishes "antigravity" vs anything-else (-> codex
    # dirs); there is no third branch for "claude" today, so default stays
    # antigravity - the inbox most fleet lanes actually drop pings into.
    target = str(args.get("target", "antigravity")).strip() or "antigravity"
    limit = _limit(args)
    messages = NouGenMsgBus.read_inbox(target=target, limit=limit)
    return {"target": target, "count": len(messages), "messages": messages}


def _rsi_status(args: dict) -> dict:
    from . import rsi as rsi_module
    reports_dir = rsi_module._reports_dir()
    files = sorted(reports_dir.glob("rsi_*.json"), reverse=True)
    if not files:
        return {"status": "no_runs_yet"}
    import json as _json
    with open(files[0], "r", encoding="utf-8") as f:
        latest = _json.load(f)
    prop = latest.get("proposal", {})
    exa = latest.get("exa_temporal_latest", {})
    return {
        "timestamp_utc": latest.get("timestamp_utc"),
        "temporal": latest.get("temporal", {}).get("eastern_full"),
        "bitemporal_event_id": (latest.get("bitemporal_receipt") or {}).get("event_id"),
        "status": latest.get("status"),
        "repo": latest.get("repo"),
        "build_ok": latest.get("build", {}).get("ok"),
        "self_update_healthy": latest.get("self_update_health", {}).get("ok"),
        "self_update_live_version": (latest.get("self_update_health", {}).get("body") or {}).get("versionCode"),
        "exa_temporal_ok": exa.get("ok"),
        "exa_hits_count": len(exa.get("hits") or []),
        "latest_proposal_title": prop.get("title"),
        "latest_proposal_risk": prop.get("risk"),
    }


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
    "shards_window": _shards_window,
    "shards_recall": _shards_recall,
    "shards_amend": _shards_amend,
    "relay_latest": _relay_latest,
    "relay_open": _relay_open,
    "reach_state": _reach_state,
    "shards_capture": _shards_capture,
    "nougenmsg_send": _nougenmsg_send,
    "nougenmsg_inbox": _nougenmsg_inbox,
    "rsi_status": _rsi_status,
    "unfinished_destinies": _unfinished_destinies,
    "search_destinies": _search_destinies,
    "get_destiny": _get_destiny,
    "create_destiny": _create_destiny,
    "mrsb_status": _mrsb_status,
    "mrsb_character": _mrsb_character,
    "mrsb_lineage": _mrsb_lineage,
    "mrsb_recall": _mrsb_recall,
    "nougenmsg_peers": _nougenmsg_peers,
    "nougenmsg_search": _nougenmsg_search,
    "relay_ack": _relay_ack,
    "relay_read": _relay_read,
    "relay_create": _relay_create,
    "relay_claim_list": _relay_claim_list,
    "persona_resolve": _persona_resolve,
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
                  log: Optional[logging.Logger] = None,
                  tracker: Optional[Any] = None,
                  observer=None) -> Tuple[str, List[dict]]:
    """Drive an ollama-style tool loop until the model stops calling tools.

    chat_fn(model, messages, tools=TOOLS) must return the ollama chat
    response dict. Returns (final_text, call_log) where call_log holds one
    {tool, args, result_size, ok} entry per attempted call for grant audit.
    If tracker (SessionToolActivityTracker) is provided, invocations are
    automatically bounded, redacted, and recorded.
    """
    lg = log or logger
    import time
    import uuid
    from nougen_shards.tool_activity import configured_sink, observe
    owned_observer = observer is None
    if observer is None:
        try:
            observer = configured_sink()
        except Exception:
            observer = None
    def finish(text, calls):
        if owned_observer and observer is not None:
            observer.close()
        return text, calls
    rounds = max_rounds if max_rounds is not None else _env_int("NOUGEN_KAEDRA_TOOL_ROUNDS", 4)
    cap = _env_int("NOUGEN_KAEDRA_RESULT_CHARS", 4000)
    msgs = list(messages)
    call_log: List[dict] = []
    final_text = ""

    for rnd in range(rounds + 1):
        try:
            resp = chat_fn(model, msgs, tools=TOOLS) or {}
        except Exception:
            observe(observer, "loop_end", "", outcome="chat_exception")
            if owned_observer and observer is not None:
                observer.close()
            raise
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
                observe(observer, "loop_end", "", outcome="chat_error")
                return finish(f"[chat error] {text}", call_log)
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
            observe(observer, "loop_end", "", outcome="complete")
            return finish(final_text, call_log)
        if rnd >= rounds:
            observe(observer, "loop_end", "", outcome="round_limit")
            lg.warning("kaedra tool loop hit max rounds (%d); stopping", rounds)
            break
        msgs.append(message)
        for call in tool_calls:
            fn = (call or {}).get("function") or {}
            name = str(fn.get("name", ""))
            args = _parse_args(fn.get("arguments"))
            invocation_id = uuid.uuid4().hex
            started = time.monotonic()
            # Shape only: even credential values embedded in arbitrary text stay private.
            observe(observer, "start", name if name in TOOL_NAMES else "unknown",
                    invocation_id, argument_count=len(args))
            if name not in TOOL_NAMES:
                observe(observer, "end", "unknown", invocation_id, outcome="refused")
                lg.warning("kaedra tool loop refused non-allowlisted tool %r", name)
                call_log.append({"tool": name, "args": args, "result_size": 0, "ok": False,
                                 "refused": True})
                msgs.append({"role": "tool", "tool_name": name,
                             "content": json.dumps({"error": "unknown tool"})})
                continue
            import time
            start_call = time.perf_counter()
            try:
                result = dispatch(name, args)
            except Exception:
                observe(observer, "end", name, invocation_id, outcome="exception",
                        duration_ms=round((time.monotonic() - started) * 1000, 3))
                if owned_observer and observer is not None:
                    observer.close()
                raise
            dur_ms = (time.perf_counter() - start_call) * 1000
            try:
                payload = json.dumps(result, default=str)
            except Exception:
                observe(observer, "end", name, invocation_id, outcome="serialization_error")
                if owned_observer and observer is not None:
                    observer.close()
                raise
            ok = "error" not in result
            err_msg = result.get("error") if isinstance(result, dict) else None
            observe(observer, "end", name, invocation_id,
                    outcome="success" if ok else "error", result_chars=len(payload),
                    truncated=len(payload) > cap,
                    duration_ms=round((time.monotonic() - started) * 1000, 3))
            call_log.append({"tool": name, "args": args, "result_size": len(payload), "ok": ok})
            if tracker is not None and hasattr(tracker, "record_call"):
                tracker.record_call(tool_name=name, arguments=args, ok=ok, result_size=len(payload),
                                    duration_ms=dur_ms, error=err_msg)
            lg.info("kaedra tool %s ok=%s size=%d", name, ok, len(payload))
            msgs.append({"role": "tool", "tool_name": name, "content": payload[:cap]})

    if not final_text:
        final_text = "[kaedra] tool round limit reached before a final answer."
    return finish(final_text, call_log)
