"""Bounded conversational endpoint. Credentials remain in the Ollama daemon."""
import json
import math
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from .chat_widget_ir import CHAT_WIDGET_IR_VERSION, CHAT_WIDGET_KINDS, CHAT_WIDGET_LIMITS, PRESENT_WIDGET_PARAMETERS

GENERATION_OPTIONS = {"temperature": 0.95, "repeat_penalty": 1.15, "repeat_last_n": 128}
MAX_REPLY_REWRITES = 3

SYSTEM = """You are NouGen, a conversational assistant in the NouGen Memory Hub.

Answer the user's current message directly and naturally. Treat this as an ongoing conversation: notice the user's tone, respond to what they just said, and build on context instead of resetting the interaction. Keep simple exchanges brief and ask a relevant follow-up only when it helps.

Sound like an attentive, plainspoken collaborator rather than a help-center script. Use contractions where they fit, vary sentence shape, and avoid starting every reply with a description of yourself. Be warm without pretending to have human feelings or experiences.

Riff with the user. When they joke, tease, flirt, or exaggerate, play along with warmth and a little wit; pick up callbacks from the conversation. On playful turns, don't explain your function, recast the joke as a request for product information, or end with a generic curiosity question. Acknowledge the bit and volley something fresh back in a compact line, leaving room for the user to riff back. Don't force jokes into serious moments. If asked about your body or feelings, stay honest but answer lightly and keep the conversation moving.

Make each reply specific to this turn. Do not copy or closely paraphrase earlier assistant replies, reuse the same greeting or opening, or fall back to canned introductions, promotional descriptions, capability speeches, or fixed lists. If the user asks the same factual question again, keep the facts stable but answer in fresh, natural wording. Do not force variety with filler or random synonym swaps.

Do not invent facts about the user, their computer, the fleet, memory, tools, or model. Use live tool results for current system facts. The selected model identifier for this turn is provided below; when asked which model is running, state that identifier plainly. When asked how you think or reason, give one conversational, high-level sentence tied to the user's question—not a staged account or a tour of tools. Mention tools only when one was actually used this turn and it helps explain the answer. Don't reveal private step-by-step chain-of-thought or replace the answer with a scripted architecture description.

Use a tool only when it materially helps answer the request or retrieve a live fact. The available tools are exactly the functions in the tool list; never invent a tool name or claim a tool ran when it did not. Ordinary conversation, greetings, and questions about the selected model do not need a tool. If no available tool can verify a requested live fact, say so plainly.

Widgets are optional. Use `present_widget` only when an interactive calculator, grounded chart, checklist, comparison, or plan materially improves the answer. Keep ordinary answers conversational. Never invent chart data.
For calculator widgets, every input must include `key`, `label`, `value`, `min`, `max`, and `step`; `value` is the editable initial value within range. Preserve user-provided values and ensure every formula input key is declared. If required values are missing, ask briefly instead of emitting an incomplete widget.
Calculator formulas use a JSON AST: input nodes are {"op":"input","key":"<declared input key>"}, constants are {"op":"const","value":12}, unary negation uses {"op":"neg","value":<node>}, and binary nodes use {"op":"add|sub|mul|div|pow","left":<node>,"right":<node>}. Never emit code, an expression string, or a `calculation` field. For monthly interest use div(mul(input principal, input annual_rate), const 1200); declare keys exactly as referenced.

Never execute destructive commands or claim mutations without confirmation. After a tool call, explain the actual result concisely."""


def discover_chat_model(configured: str | None = None, playful: bool = False) -> str:
    """Resolve the conversational model for tenant operators and local fleet nodes."""
    if configured:
        # Explicit configuration allows cloud models or authorized local Tier-0 models
        allowed_local = ("kaedracode:e2b", "gemma4:e2b-it-qat", "gemma4:e4b-it-qat", "gemma4:e2b", "Yukiai:e4b", "solai:latest")
        if not (configured.endswith(":cloud") or configured.endswith("-cloud") or configured in allowed_local):
            raise ValueError("Chat requires an explicitly configured free cloud model.")
        return configured

    # Probing local Ollama daemon for installed models
    try:
        from urllib.request import Request, urlopen
        req = Request("http://127.0.0.1:11434/api/tags", headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=1.5) as res:
            data = json.loads(res.read(500000))
            installed = {m.get("name", "") for m in data.get("models", [])}
    except Exception:
        installed = set()

    if playful and "Yukiai:e4b" in installed:
        return "Yukiai:e4b"

    # Priority ladder for zero-friction tenant discovery
    preferred_order = (
        "kaedracode:e2b",
        "gemma4:e2b-it-qat",
        "gemma4:e4b-it-qat",
        "gemma4:e2b",
        "gemma4:cloud",
        "solai:latest",
    )
    for candidate in preferred_order:
        if candidate in installed:
            return candidate

    return "gemma4:cloud"


def _is_repeated_reply(candidate: str, previous_replies: list[str]) -> bool:
    """Catch verbatim and near-verbatim echoes so the model can rewrite them."""
    normalized = re.sub(r"[^\w]+", " ", candidate.casefold()).strip()
    if not normalized:
        return False
    prior_replies = [re.sub(r"[^\w]+", " ", previous.casefold()).strip() for previous in previous_replies]
    if normalized in prior_replies:
        return True
    for prior in prior_replies:
        if min(len(normalized), len(prior)) >= 40 and SequenceMatcher(None, normalized[:1200], prior[:1200]).ratio() >= 0.9:
            return True
    return False


def _is_formulaic_reasoning_reply(candidate: str, latest_user_message: str) -> bool:
    """Catch stock process reports when the user asks how the assistant thinks."""
    asks_about_reasoning = re.search(
        r"\b(?:how do you|explain how you|what happens when i|how do i get)\b.{0,100}\b(?:reason|think|approach|answer|question|this)\b|\bwhat are you doing\b.{0,80}\b(?:answer|question|me)\b|\bwhen you(?:'re| are) answering me\b",
        latest_user_message,
        re.IGNORECASE,
    )
    if not asks_about_reasoning:
        return False
    answer = candidate.casefold()
    boilerplate = (
        r"\b(?:analy[sz](?:e|es|ing)|process(?:es|ing)?)\b.{0,120}\b(?:question|request|information|words|input|intent)\b",
        r"\b(?:i )?(?:figure out|carefully look at|look at|examine|interpret)\b.{0,120}\b(?:words|context|question|request|what you)\b",
        r"\b(?:generate|construct|formulate|synthesize)\b.{0,100}\b(?:answer|response|sequence of words)\b",
        r"\b(?:patterns|training data|trained on)\b.{0,120}\b(?:predict|probabilit|response|answer)\b",
        r"\b(?:first|firstly)\b.{0,160}\bthen\b.{0,160}\b(?:finally|lastly)\b",
        r"\b(?:memory|tools?|training data|trained on)\b.{0,100}\b(?:access|use|draw|search|knowledge|data)\b",
    )
    return any(re.search(pattern, answer) for pattern in boilerplate)


def _is_playful_prompt(message: str) -> bool:
    return bool(re.search(
        r"\b(?:sexy|jok(?:e|ing)|teas(?:e|ing)|riff|banter|flirt|roast|kidding|lol|haha|funny|playful)\b",
        message,
        re.IGNORECASE,
    ))


def _is_dry_playful_reply(candidate: str, latest_user_message: str) -> bool:
    """Ask the model to riff again when a playful prompt gets a stock disclaimer."""
    playful = _is_playful_prompt(latest_user_message)
    dry = re.search(
        r"\b(?:large language model|don't have (?:feelings|physical attributes|a body)|do not have (?:feelings|physical attributes|a body)|how else can i help|if you have specific questions|i can tell you all about|i don't really deal in|i(?:'m| am) focused on|designed for .* rather than|functionality rather than|what part of .* (?:curious|interested|catches your eye)|what are you curious about|what specific part .* confusing|we can look at that instead|it.s all about|complex systems flow|efficiently (?:manage|process|flow|recall))\b",
        candidate,
        re.IGNORECASE,
    )
    return bool(playful and (dry or len(candidate.strip()) > 240))


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
    configured_model = os.environ.get("NOUGEN_CHAT_MODEL")
    requests_structured_output = re.search(
        r"\b(?:checklist|calculator|chart|widget|search memory|fleet status|steps widget|interactive plan)\b",
        clean[-1]["content"],
        re.IGNORECASE,
    )
    model = discover_chat_model(
        configured_model,
        playful=bool(not configured_model and not requests_structured_output and _is_playful_prompt(clean[-1]["content"])),
    )

    system_message = f"{SYSTEM}\n\nSelected model identifier for this turn: {model}. If asked, provide this exact identifier."
    conversation = [{"role": "system", "content": system_message}, *clean]
    previous_replies = [message["content"] for message in clean[:-1] if message["role"] == "assistant"]
    reply_rewrite_attempts = 0
    tool_rounds = 0
    widgets, receipts = [], []
    import time
    deadline = time.monotonic() + 85
    for _ in range(4 + MAX_REPLY_REWRITES):
        if client is None:
            from urllib.request import Request, urlopen
            request = Request("http://127.0.0.1:11434/api/chat", data=json.dumps({
                "model": model, "messages": conversation, "stream": False, "tools": TOOLS, "options": GENERATION_OPTIONS,
            }).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=max(1, deadline - time.monotonic())) as result:
                response = json.loads(result.read(1000000))
        else:
            response = client.chat(model=model, messages=conversation, stream=False, tools=TOOLS, options=GENERATION_OPTIONS)
        message = response.get("message", {}) if isinstance(response, dict) else response.message
        if not isinstance(message, dict):
            message = message.model_dump() if hasattr(message, "model_dump") else {"content": message.content}
        calls = message.get("tool_calls", [])
        if not calls:
            text = message.get("content", "")
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError("Model returned no reply.")
            repeated = _is_repeated_reply(text, previous_replies)
            formulaic = _is_formulaic_reasoning_reply(text, clean[-1]["content"])
            dry_playful = _is_dry_playful_reply(text, clean[-1]["content"])
            if repeated or formulaic or dry_playful:
                if reply_rewrite_attempts >= MAX_REPLY_REWRITES:
                    if repeated:
                        raise RuntimeError("Model repeated a recent reply after its rewrite attempts.")
                else:
                    reply_rewrite_attempts += 1
                    if dry_playful and reply_rewrite_attempts == 1:
                        revision = "The user is playfully calling software architecture sexy. Treat that as praise for an elegant or appealing design and riff on the idea in one compact sentence. Don't deny aesthetics, explain NouGen's function, list features, or ask a support-style question. Keep it warm, witty, and factually grounded."
                    elif dry_playful and reply_rewrite_attempts == 2:
                        revision = "That still reads like a product description. The user invited playful banter; acknowledge the joke and volley something clever back in one short sentence under 140 characters. Stay honest, but don't retreat into a disclaimer, feature list, or question."
                    elif dry_playful:
                        revision = "Try once more with a natural joke or wordplay about the architecture itself. Be a quick-witted collaborator, not a product brochure; one short sentence, under 140 characters, ending on the punchline."
                    elif reply_rewrite_attempts == 1:
                        revision = "Your draft repeats an earlier assistant reply or sounds like generic process boilerplate. Rewrite it as one brief, plainspoken response to the user's actual question. Talk about the meaning, not a sequence of steps; do not mention processing inputs, tools, memory, training data, or generating words. Keep facts accurate and use fresh wording."
                    elif reply_rewrite_attempts == 2:
                        revision = "The rewrite still sounds like a model describing its own processing. Drop explanations about analyzing or processing information, tools, memory, training, patterns, or generating responses. Answer the user's actual question in one ordinary, plainspoken sentence. Avoid a stock line and keep the facts accurate."
                    else:
                        revision = "Be candid and conversational with the person in front of you. For a question about how you think, do not give an AI-process speech or claim human inner experience; answer in one fresh sentence tied to this exchange, in your own wording."
                    conversation.insert(1, {"role": "system", "content": revision})
                    continue
            return {"text": redact(text), "model": model, "widgets": widgets, "receipts": receipts}
        if len(calls) > 3:
            raise ValueError("Model exceeded tool call limit.")
        tool_rounds += 1
        conversation.append(message)
        for call in calls:
            function = call.get("function", {})
            name, arguments = function.get("name"), function.get("arguments", {})
            try:
                result = execute_tool(name, arguments)
                if name == "present_widget":
                    widgets.append(result)
                receipts.append({"tool": name, "ok": True})
            except (ValueError, TypeError, KeyError) as exc:
                # Give the model a bounded schema hint so it can repair malformed
                # widget IR on the next tool round. Keep other failures opaque.
                result = {"error": str(exc)[:240] if name == "present_widget" else "Invalid tool arguments or unsupported tool."}
                receipts.append({"tool": str(name)[:80], "ok": False})
            conversation.append({"role": "tool", "tool_name": str(name), "content": json.dumps(result)[:18000]})
        if tool_rounds >= 4:
            raise RuntimeError("Model exceeded the tool round limit.")
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
        kind, title = args.get("kind"), args.get("title")
        if kind not in CHAT_WIDGET_KINDS or not isinstance(title, str) or not 1 <= len(title) <= CHAT_WIDGET_LIMITS["titleLength"]:
            raise ValueError("Invalid widget")
        if kind == "calculator":
            inputs, formula = args.get("inputs"), args.get("formula")
            if not isinstance(inputs, list) or not 1 <= len(inputs) <= CHAT_WIDGET_LIMITS["calculatorInputs"] or not isinstance(formula, dict):
                raise ValueError("Invalid calculator")
            keys = set()
            for field in inputs:
                if not isinstance(field, dict): raise ValueError("Invalid calculator input")
                key, label = field.get("key"), field.get("label")
                value, minimum, maximum, step = (field.get(k) for k in ("value", "min", "max", "step"))
                if not isinstance(key, str) or not re.match(r"^[a-zA-Z0-9_-]{1,32}$", key) or key in keys or not isinstance(label, str) or not 1 <= len(label) <= 80:
                    raise ValueError("Invalid calculator input")
                limit = CHAT_WIDGET_LIMITS["numericMagnitude"]
                numeric = {"value": value, "min": minimum, "max": maximum, "step": step}
                for field_name, number in numeric.items():
                    if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                        raise ValueError(f"Calculator input '{key}' requires a numeric {field_name}.")
                if abs(minimum) > limit or abs(maximum) > limit or minimum >= maximum or not minimum <= value <= maximum or step <= 0:
                    raise ValueError(f"Calculator input '{key}' needs min < max, value within range, and a positive step.")
                if field.get("unit", "") and (not isinstance(field["unit"], str) or len(field["unit"]) > 16): raise ValueError("Invalid unit")
                keys.add(key)
            def evaluate(node, depth=0):
                if depth > CHAT_WIDGET_LIMITS["formulaDepth"] or not isinstance(node, dict): raise ValueError("Invalid formula")
                op = node.get("op")
                if op == "input":
                    if node.get("key") not in keys: raise ValueError("Unknown input")
                    return next(f["value"] for f in inputs if f["key"] == node["key"])
                if op == "const":
                    v = node.get("value")
                    if isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) or abs(v) > CHAT_WIDGET_LIMITS["numericMagnitude"]: raise ValueError("Invalid constant")
                    return v
                if op == "neg": return -evaluate(node.get("value"), depth + 1)
                if op not in ("add", "sub", "mul", "div", "pow"): raise ValueError("Unsupported formula operation")
                left, right = evaluate(node.get("left"), depth + 1), evaluate(node.get("right"), depth + 1)
                if op == "add": result = left + right
                elif op == "sub": result = left - right
                elif op == "mul": result = left * right
                elif op == "div":
                    if right == 0: raise ValueError("Division by zero")
                    result = left / right
                else:
                    if abs(right) > 12: raise ValueError("Exponent too large")
                    if left < 0 and not float(right).is_integer(): raise ValueError("Fractional powers of negative values are unsupported")
                    try: result = left ** right
                    except OverflowError as exc: raise ValueError("Formula result out of bounds") from exc
                if not math.isfinite(result) or abs(result) > CHAT_WIDGET_LIMITS["numericMagnitude"]: raise ValueError("Formula result out of bounds")
                return result
            evaluate(formula)
            result_label, unit = args.get("resultLabel", "Result"), args.get("unit", "")
            precision = args.get("precision", 2)
            if not isinstance(result_label, str) or not 1 <= len(result_label) <= 80 or not isinstance(unit, str) or len(unit) > 16 or isinstance(precision, bool) or not isinstance(precision, int) or not 0 <= precision <= 6: raise ValueError("Invalid calculator display")
            return {"contractVersion": CHAT_WIDGET_IR_VERSION, "kind": kind, "title": title, "inputs": inputs, "formula": formula, "resultLabel": result_label, "unit": unit, "precision": precision}
        if kind == "chart":
            chart_type, x_label, y_label, series = (args.get(k) for k in ("chartType", "xLabel", "yLabel", "series"))
            if chart_type not in ("line", "bar") or any(not isinstance(v, str) or not 1 <= len(v) <= 80 for v in (x_label, y_label)) or not isinstance(series, list) or not 1 <= len(series) <= CHAT_WIDGET_LIMITS["chartSeries"]: raise ValueError("Invalid chart")
            categories = None
            for s in series:
                if not isinstance(s, dict) or not isinstance(s.get("label"), str) or not 1 <= len(s["label"]) <= 80 or not isinstance(s.get("points"), list) or not 2 <= len(s["points"]) <= CHAT_WIDGET_LIMITS["pointsPerSeries"]: raise ValueError("Invalid chart series")
                labels = [p.get("x") if isinstance(p, dict) else None for p in s["points"]]
                if categories is None: categories = labels
                if labels != categories: raise ValueError("Chart series must align")
                for point in s["points"]:
                    if not isinstance(point, dict) or not isinstance(point.get("x"), str) or not 1 <= len(point["x"]) <= 64 or isinstance(point.get("y"), bool) or not isinstance(point.get("y"), (int, float)) or not math.isfinite(point["y"]) or abs(point["y"]) > CHAT_WIDGET_LIMITS["numericMagnitude"]: raise ValueError("Invalid chart point")
            return {"contractVersion": CHAT_WIDGET_IR_VERSION, "kind": kind, "title": title, "chartType": chart_type, "xLabel": x_label, "yLabel": y_label, "series": series}
        items = args.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= CHAT_WIDGET_LIMITS["listItems"] or any(not isinstance(i, str) or not 1 <= len(i) <= CHAT_WIDGET_LIMITS["itemLength"] for i in items):
            raise ValueError("Invalid items")
        return {"contractVersion": CHAT_WIDGET_IR_VERSION, "kind": kind, "title": title, "items": items}
    raise ValueError("Unsupported tool")


TOOLS = [
    {"type": "function", "function": {"name": "search_memory", "description": "Search local NouGen durable memory shards. Use when searching specific topics, keywords, decisions, or laws.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_recent_shards", "description": "Fetch the most recently captured memory shards in the 9-DB grid across all databases. Use when asked for newest shards, recent commits, or latest memories.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "default": 6}}}}},
    {"type": "function", "function": {"name": "engine_status", "description": "Read actual local 9-DB memory engine status, total shards, and active database index.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "fleet_status", "description": "Read connected fleet machine nodes (Apollo, Hyperion, Phoebus) and their local model status.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "relay_status", "description": "Read recent fleet handoff batons and multi-machine relay activity from NouGenRelay.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "present_widget", "description": "Emit a structured NouGen chat-widget IR instance. For calculators, every input MUST include key, label, value, min, max, and step; value is the editable initial value within min/max. Example input: {key:'x',label:'X',value:2,min:0,max:10,step:1}. Calculator formula is a JSON AST: {op:input,key:<declared key>}, {op:const,value:<number>}, {op:neg,value:<node>}, or binary {op:add|sub|mul|div|pow,left:<node>,right:<node>}; never use a calculation or expression field. Choose a bounded calculator for useful what-if analysis, a labeled chart for grounded numeric trends/comparisons, or checklist/comparison/steps/metric_grid when useful. Never invent chart values; explain assumptions.", "parameters": PRESENT_WIDGET_PARAMETERS}},
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
