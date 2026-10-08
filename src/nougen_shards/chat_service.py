"""Bounded conversational endpoint. Credentials remain in the Ollama daemon."""
import json
import os
import sys

SYSTEM = """You are NouGen, Dave's high-caliber technical collaborator and local intelligence engine.
You are running directly on Dave's local hardware (WhoArt / Hyperion PX13) connected to the 9-DB persistent memory grid (C:\\Users\\super\\.nougen\\shards) and the fleet mesh (Apollo, Hyperion, Phoebus).

Respond directly, intelligently, and naturally without artificial AI hedges, apologies, or generic chatbot disclaimers.
Think like an architect: verify live facts before making claims.
When asked about relays, handoffs, fleet nodes, engine health, or memory shards:
ALWAYS proactively call the appropriate tools (`relay_status`, `fleet_status`, `engine_status`, `search_memory`) to retrieve live verified facts instead of guessing or saying you lack tools.
When presenting multi-item comparisons, plans, or checklists, use `present_widget`.
Never execute destructive commands or claim mutations without confirmation. After tool calls, synthesize the actual live findings with clarity and precision."""


def chat(payload, client=None):
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list) or not messages or len(messages) > 80:
        raise ValueError("Send between 1 and 80 conversation messages.")
    from .credential_patterns import redact
    clean = []
    total = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
            raise ValueError("Invalid conversation role.")
        content = message.get("content")
        if not isinstance(content, str) or len(content) > 24000:
            raise ValueError("Invalid message content.")
        total += len(content)
        clean.append({"role": message["role"], "content": redact(content)})
    if total > 100000 or clean[-1]["role"] != "user":
        raise ValueError("Conversation too large or missing latest user message.")
    model = os.environ.get("NOUGEN_CHAT_MODEL", "gemma4:cloud")
    if not (model.endswith(":cloud") or model.endswith("-cloud")):
        raise ValueError("Chat requires an explicitly configured free cloud model.")
    conversation = [{"role": "system", "content": SYSTEM}, *clean]
    widgets, receipts = [], []
    import time
    deadline = time.monotonic() + 85
    for _ in range(4):
        if client is None:
            from urllib.request import Request, urlopen
            request = Request("http://127.0.0.1:11434/api/chat", data=json.dumps({
                "model": model, "messages": conversation, "stream": False, "tools": TOOLS,
            }).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=max(1, deadline - time.monotonic())) as result:
                response = json.loads(result.read(1000000))
        else:
            response = client.chat(model=model, messages=conversation, stream=False, tools=TOOLS)
        message = response.get("message", {}) if isinstance(response, dict) else response.message
        if not isinstance(message, dict):
            message = message.model_dump() if hasattr(message, "model_dump") else {"content": message.content}
        calls = message.get("tool_calls", [])
        if not calls:
            text = message.get("content", "")
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError("Model returned no reply.")
            return {"text": redact(text), "model": model, "widgets": widgets, "receipts": receipts}
        if len(calls) > 3:
            raise ValueError("Model exceeded tool call limit.")
        conversation.append(message)
        for call in calls:
            function = call.get("function", {})
            name, arguments = function.get("name"), function.get("arguments", {})
            try:
                result = execute_tool(name, arguments)
                if name == "present_widget":
                    widgets.append(result)
                receipts.append({"tool": name, "ok": True})
            except (ValueError, TypeError, KeyError):
                result = {"error": "Invalid tool arguments or unsupported tool."}
                receipts.append({"tool": str(name)[:80], "ok": False})
            conversation.append({"role": "tool", "tool_name": str(name), "content": json.dumps(result)[:18000]})
        if time.monotonic() >= deadline:
            break
    raise RuntimeError("Model exceeded the bounded tool round limit.")


def execute_tool(name, args):
    if not isinstance(args, dict):
        raise ValueError("Invalid arguments")
    if name == "search_memory":
        query = args.get("query", "")
        if not isinstance(query, str) or len(query) > 300:
            raise ValueError("Invalid query")
        from .dynamic_api import search_shards
        rows = search_shards(query, limit=5)
        from .credential_patterns import redact
        return [{"id": row.get("id"), "_db_index": row.get("_db_index"), "title": row.get("title"), "tags": row.get("tags"), "timestamp": row.get("timestamp"), "content": redact(str(row.get("content", "")))[:2000]} for row in rows[:5]]
    if name == "get_recent_shards":
        limit = min(args.get("limit", 6), 10)
        from .dynamic_api import search_shards
        rows = search_shards("", limit=limit)
        from .credential_patterns import redact
        return [{"id": row.get("id"), "_db_index": row.get("_db_index"), "title": row.get("title"), "tags": row.get("tags"), "timestamp": row.get("timestamp"), "content": redact(str(row.get("content", "")))[:1500]} for row in rows[:limit]]
    if name == "engine_status":
        from .dynamic_api import get_engine_status
        return get_engine_status()
    if name == "fleet_status":
        from .dashboard_live import read_json
        nodes = read_json(Path.home() / ".nougen/nodes.json", {})
        return {
            "nodes_count": len(nodes),
            "nodes": [
                {"name": n.get("name", k), "ip": n.get("ip"), "machine": n.get("machine"), "stadium": n.get("stadium")}
                for k, n in list(nodes.items())[:6]
            ],
        }
    if name == "relay_status":
        from .dashboard_live import relay_feed
        feed = relay_feed()
        return {
            "recent_count": len(feed),
            "handoffs": [
                {
                    "id": h.get("id"),
                    "machine": h.get("machine"),
                    "agent": h.get("agent"),
                    "goal": h.get("goal"),
                    "status": h.get("status"),
                    "timestamp": h.get("timestamp"),
                }
                for h in feed[:5]
            ],
        }
    if name == "present_widget":
        kind, title, items = args.get("kind"), args.get("title"), args.get("items")
        if kind not in ("checklist", "comparison", "steps", "metric_grid") or not isinstance(title, str) or not 1 <= len(title) <= 160:
            raise ValueError("Invalid widget")
        if not isinstance(items, list) or not 1 <= len(items) <= 12 or any(not isinstance(i, str) or not 1 <= len(i) <= 500 for i in items):
            raise ValueError("Invalid items")
        return {"kind": kind, "title": title, "items": items}
    raise ValueError("Unsupported tool")


TOOLS = [
    {"type": "function", "function": {"name": "search_memory", "description": "Search local NouGen durable memory shards. Use when searching specific topics, keywords, decisions, or laws.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_recent_shards", "description": "Fetch the most recently captured memory shards in the 9-DB grid across all databases. Use when asked for newest shards, recent commits, or latest memories.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "default": 6}}}}},
    {"type": "function", "function": {"name": "engine_status", "description": "Read actual local 9-DB memory engine status, total shards, and active database index.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "fleet_status", "description": "Read connected fleet machine nodes (Apollo, Hyperion, Phoebus) and their local model status.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "relay_status", "description": "Read recent fleet handoff batons and multi-machine relay activity from NouGenRelay.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "present_widget", "description": "Present a useful interactive checklist, side-by-side comparison, ordered steps, or metric grid in the chat UI.", "parameters": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["checklist", "comparison", "steps", "metric_grid"]}, "title": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}}, "required": ["kind", "title", "items"]}}},
]


def main():
    try:
        raw = sys.stdin.read(420001)
        if len(raw) > 420000:
            raise ValueError("Request too large.")
        result = chat(json.loads(raw))
    except ValueError as exc:
        result = {"error": str(exc), "code": "invalid_request"}
    except Exception:
        result = {"error": "The conversational model is unavailable. Check Ollama cloud sign-in and retry.", "code": "model_unavailable"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
