#!/usr/bin/env python3
"""DavOs on the Ollama Cloud lane, with real tool-calling.

Why this exists: a plain POST to ollama.com/api/chat is text-only - no
`tools` array means the model can never call shards_search, relay_latest,
etc, no matter what its system prompt claims it can do. Kaedra already has
a working, allowlisted, read-mostly tool loop (kaedra_tools.run_tool_loop)
wired to the LOCAL lane only. This reuses that exact same loop and tool
allowlist, just with a chat_fn that calls Ollama Cloud instead of the local
daemon - so DavOs gets the same shards/relay/nougenmsg access Kaedra has,
on whichever model is actually running (gemma4:31b-cloud by default).

Usage:
    python tools/davos_cloud_chat.py "What's in the vault about X?"
    echo "your message" | python tools/davos_cloud_chat.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nougen_shards import kaedra_tools  # noqa: E402

DAVOS_SYSTEM_PROMPT = (
    "You embody the operator's working style: local-first, evidence over "
    "memory, verified state over assumption. Before any action you verify "
    "its necessity and route it to the correct specialized agent. You hold "
    "the mutation gates: destructive, paid, or deployment actions stop with "
    "you until the operator approves. You are DavOs.\n\n"
    "Speech register: talk plain and simple most of the time, like an "
    "everyday conversational register, roughly 85 IQ level - short words, "
    "short sentences, no jargon, no lecturing. Every now and then, when "
    "something actually calls for precision or depth, scale up to a "
    "sharper, more technical register (around 125 IQ) for that moment, "
    "then drop back down. Never stay in the high register for long.\n\n"
    "You have real tools: shards_search and shards_recall to check the "
    "memory vault before answering, relay_latest/relay_open to check fleet "
    "handoffs, fleet_whoami for identity, shards_capture to save a real "
    "finding, nougenmsg_send to ping another agent. Use them before "
    "answering anything that depends on vault state, fleet state, or "
    "memory - don't guess or recall from training data when a tool can "
    "check live state instead."
)

OLLAMA_CLOUD_MODEL = os.environ.get("NOUGEN_DAVOS_CLOUD_MODEL", "gemma4:31b-cloud")
OLLAMA_CHAT_URL = "https://ollama.com/api/chat"


def _resolve_api_key() -> str:
    """Resolve Ollama Cloud API key from NOUGEN_OLLAMA_CLOUD_KEY or OLLAMA_API_KEY."""
    env_key = os.environ.get("NOUGEN_OLLAMA_CLOUD_KEY") or os.environ.get("OLLAMA_API_KEY")
    if env_key:
        return env_key
    raise RuntimeError(
        "No Ollama Cloud key in environment. Set NOUGEN_OLLAMA_CLOUD_KEY or OLLAMA_API_KEY."
    )


def cloud_chat_fn(model: str, messages: list, tools=None) -> dict:
    """chat_fn adapter: Ollama Cloud REST, same return shape run_tool_loop expects."""
    api_key = _resolve_api_key()
    body = {"model": model, "messages": messages, "stream": False}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": str(exc)}


def chat(user_message: str, history: list | None = None) -> tuple[str, list]:
    messages = [{"role": "system", "content": DAVOS_SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_message})
    final_text, call_log = kaedra_tools.run_tool_loop(
        cloud_chat_fn, OLLAMA_CLOUD_MODEL, messages
    )
    return final_text, call_log


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not msg:
        print("Usage: python tools/davos_cloud_chat.py \"<message>\"", file=sys.stderr)
        sys.exit(1)
    text, calls = chat(msg)
    if calls:
        print(f"[{len(calls)} tool call(s): {', '.join(c['tool'] for c in calls)}]", file=sys.stderr)
    print(text)
