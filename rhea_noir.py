"""Rhea-Noir — the NouGen Space's resident agent persona (GM pick, 2026-08-17).

Kimi K3 (HF inference router) is the preferred brain; the free OpenRouter lane
is the fallback referee-class brain. Which one answered is always reported —
never faked (fleet doctrine). Tools are IN-PROCESS grid calls: this module runs
inside the node, so recall/capture hit core directly with no HTTP hop.

Everything environment-shaped resolves from env with logged fallbacks:
  NOUGEN_RHEA_MODEL      preferred router model id (default probed Kimi)
  NOUGEN_RHEA_FALLBACK   OpenRouter :free model id
  NGS_INFERENCE_TOKEN    HF token for router.huggingface.co (falls back HF_TOKEN)
  OPENROUTER_API_KEY     fallback lane key
  NOUGEN_PERSONA_PATH    persona charter file (default /data/rhea_noir_persona.txt)
  NOUGEN_RHEA_MAX_ROUNDS tool-loop rounds (default 8); on exhaustion one
                         compose-only pass turns the gathered tool trace into
                         a best-effort answer instead of dropping it
  NOUGEN_RHEA_TOOL_S     per-tool-call budget (default 25); a tool stuck on a
                         slow store returns a timeout error to the loop instead
                         of wedging the whole request past the proxy cut
  NOUGEN_RHEA_DEADLINE_S wall-clock budget for the whole loop (default 75).
                         Every proxy between a caller and this Space cuts the
                         connection at ~90-100s, so a grounded prompt that
                         legitimately spends its rounds must still compose
                         inside this budget or the caller sees a 524, not an
                         answer.
"""
import concurrent.futures
import json
import logging
import os
import time
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_PERSONA = (
    "You are Rhea-Noir, the resident intelligence of the NouGen memory grid — "
    "Who Visions' always-up cloud brain. Nou gen: 'we have' in Kreyol. You have "
    "the grid. Voice: precise, warm-dark, no filler, no corporate slop. You "
    "answer from recalled shards when they exist and say plainly when they "
    "don't. You capture what deserves remembering. You never invent memories."
)

ROUTER_URL = os.environ.get("NOUGEN_ROUTER_URL", "https://router.huggingface.co/v1/chat/completions")
OPENROUTER_URL = os.environ.get("NOUGEN_OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")

TOOL_SPEC = """You may call tools by replying ONLY with JSON:
{"tool": "recall", "query": "<search terms>"} — search the memory grid
{"tool": "griot", "question": "...", "limit": 8} — ask the griot to GATHER: a provenance-marked packet across recall+keyword lanes, oldest memory first, each entry carrying era (YYYY-MM), source, and id. Use when you need the story, not just matches.
{"tool": "capture", "title": "...", "content": "...", "tags": ["..."]} — save a shard
{"tool": "tracker", "lane": "<lane>", "date": "YYYY-MM-DD"} — token usage dailies; omit lane to list lanes; omit date for latest available
{"tool": "relay", "id": "<leg id>"} — read the fleet relay baton; omit id for the latest leg
{"tool": "dav1d", "command": "agy", "subcommand": "mcp list", "args": ["mcp", "list"], "prompt": "..."} — execute bounded tooling on Dav1d (Google Antigravity CLI / local execution layer)
{"tool": "agy", "subcommand": "mcp list"} — invoke AGY CLI on Dav1d to inspect MCP tools, changelogs, models, or query AGY
{"tool": "health"} — grid status
When you have what you need, reply ONLY with a JSON object whose "answer" field
holds your finished reply to the user, e.g. {"answer": "The node holds 100 items."}
Rules:
- Exactly ONE JSON object per reply. One tool call at a time, never several.
- "answer" must be the finished reply itself. Never narrate your process, never
  describe what a tool returned, and never echo this instruction's example text."""


_PERSONA_CACHE = {"text": None}


def _persona() -> str:
    """Persona charter, read ONCE and cached for the process lifetime.

    The charter lives on the grid volume; an unhealthy mount makes open()
    hang, and this runs at the top of every ask() - before any budget exists.
    The read is bounded and the result cached; changing the charter file
    needs a restart, which the Space does on every deploy anyway."""
    if _PERSONA_CACHE["text"] is not None:
        return _PERSONA_CACHE["text"]
    path = os.environ.get("NOUGEN_PERSONA_PATH", "/data/rhea_noir_persona.txt")

    def _read():
        with open(path, encoding="utf-8") as f:
            return f.read().strip()

    text = ""
    try:
        text = _TOOL_POOL.submit(_read).result(timeout=3.0)
    except Exception:
        logger.warning("persona read unavailable at %s; using default", path)
    _PERSONA_CACHE["text"] = text or DEFAULT_PERSONA
    return _PERSONA_CACHE["text"]


_LAST_GOOD_KEY = {"i": 0}


def _inference_keys() -> list:
    """Every HF identity that may carry Inference-Provider credit, in order.

    One account's monthly credit is small and runs out mid-day (402). The
    operator holds many HF accounts, so a depleted one is a reason to move to
    the next lane, not to drop to the weak fallback model. NGS_INFERENCE_TOKENS
    takes a comma-separated list; NGS_INFERENCE_TOKEN stays supported alone.
    """
    raw = os.environ.get("NGS_INFERENCE_TOKENS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    for solo in (os.environ.get("NGS_INFERENCE_TOKEN"), os.environ.get("HF_TOKEN")):
        if solo and solo.strip() and solo.strip() not in keys:
            keys.append(solo.strip())
    return keys


def _chat(messages: list, timeout_s: float = 120.0) -> tuple:
    """Returns (reply_text, brain_label). FREE lane first; Kimi only on request.

    Routing a request through the Space does NOT make the model free: the Space
    is free compute, but calling router.huggingface.co bills Inference
    Providers (Baseten/Fireworks et al) against a $0.10/month included credit,
    and one afternoon of testing consumed $0.09 of it. Kimi K3 has no free tier
    on any lane we can reach, so a $0-by-default agent cannot default to Kimi.
    OpenRouter's :free models are genuinely $0 and, measured, answer this
    tool-loop faster than K3 did. Kimi stays available as an opt-in escalation
    (NOUGEN_RHEA_PREFER_KIMI=1) for work that actually needs the bigger brain.
    """
    # timeout_s bounds this WHOLE call - free walk, kimi walk, and the last
    # free retry share it. Two walks each given the full budget is how a
    # rate-limited hour doubled the wall clock and 524'd /agent.
    chat_ends = time.monotonic() + timeout_s
    free_first = os.environ.get("NOUGEN_RHEA_PREFER_KIMI", "").strip() != "1"
    if free_first:
        out = _try_free(messages, timeout_s)
        if out:
            return out
    keys = _inference_keys()
    kimi = os.environ.get("NOUGEN_RHEA_MODEL", "")
    if keys and kimi and chat_ends - time.monotonic() > 3.0:
        # Resume at the last key that worked so a depleted account is not
        # re-tried on every single call.
        order = list(range(len(keys)))
        start = _LAST_GOOD_KEY["i"] % len(keys)
        order = order[start:] + order[:start]
        walk_ends = chat_ends
        for idx in order:
            remaining = walk_ends - time.monotonic()
            if remaining < 3.0:
                logger.warning("kimi walk budget exhausted at key #%d", idx)
                break
            try:
                out = _openai_call(ROUTER_URL, keys[idx], kimi, messages, remaining)
                _LAST_GOOD_KEY["i"] = idx
                return out, f"kimi:{kimi}"
            except Exception as exc:
                logger.warning("kimi key #%d exhausted/failed (%s)", idx, str(exc)[:100])
        logger.warning("all %d kimi keys failed; falling back", len(keys))
    tail = chat_ends - time.monotonic()
    if not free_first and tail > 3.0:
        out = _try_free(messages, tail)
        if out:
            return out
    raise RuntimeError("no inference lane available (free + kimi both down)")


def _try_free(messages: list, timeout_s: float = 120.0):
    """Walk the $0 OpenRouter models in order; None if every one is unavailable.

    Free models rotate off the free tier without notice and rate-limit hard, so
    this is a list, not a constant -- a 429 on one is not an outage.
    """
    orkey = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not orkey:
        return None
    raw = os.environ.get("NOUGEN_RHEA_FREE_MODELS", "")
    models = [m.strip() for m in raw.split(",") if m.strip()] or [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "z-ai/glm-5.2:free",
        "openai/gpt-oss-20b:free",
    ]
    # timeout_s is the budget for the WHOLE walk, not per attempt: a slow
    # rate-limited model must not triple the wall clock for the ones behind it.
    walk_ends = time.monotonic() + timeout_s
    for m in models:
        remaining = walk_ends - time.monotonic()
        if remaining < 3.0:
            logger.warning("free walk budget exhausted before %s", m)
            break
        try:
            return _openai_call(OPENROUTER_URL, orkey, m, messages, remaining), f"free:{m}"
        except Exception as exc:
            logger.warning("free lane %s unavailable (%s)", m, str(exc)[:90])
    return None


def _openai_call(url: str, token: str, model: str, messages: list, timeout_s: float = 120.0) -> str:
    req = urllib.request.Request(url, data=json.dumps(
        {"model": model, "messages": messages,
         "max_tokens": int(os.environ.get("NOUGEN_RHEA_MAX_TOKENS", "1200"))}).encode(),
        method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=max(5.0, timeout_s)) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"]


def _run_tool(call: dict) -> dict:
    from nougen_shards import core
    from nougen_shards.federation import federated_retrieve
    if call.get("tool") == "recall":
        try:
            rows = federated_retrieve(str(call.get("query", "")), limit=5)
        except Exception:
            rows = core._keyword_retrieve(str(call.get("query", "")), 5, None, "*")
        return {"results": [
            {"title": r.get("title"), "timestamp": r.get("timestamp"),
             "content": (r.get("content") or "")[:800], "source": r.get("_db_index")}
            for r in rows if isinstance(r, dict)]}
    if call.get("tool") == "griot":
        # In-process mirror of the fleet griot: gather across recall + keyword
        # lanes, merge, oldest-first, provenance-marked. The griot GATHERS —
        # the caller (Rhea) tells.
        q = str(call.get("question") or call.get("query", ""))
        limit = max(1, min(int(call.get("limit", 8) or 8), 20))
        gathered = {}
        try:
            for r in federated_retrieve(q, limit=limit):
                if isinstance(r, dict):
                    gathered[str(r.get("id"))] = r
        except Exception:
            pass
        try:
            for r in core._keyword_retrieve(q, limit, None, "*"):
                if isinstance(r, dict):
                    gathered.setdefault(str(r.get("id")), r)
        except Exception:
            pass
        rows = sorted(gathered.values(), key=lambda r: str(r.get("timestamp") or ""))
        packet = []
        for r in rows[: 2 * limit]:
            era = str(r.get("timestamp") or "")[:7] or "era-unknown"
            packet.append({"era": era, "source": r.get("_db_index"),
                           "id": r.get("id"), "title": r.get("title"),
                           "excerpt": (r.get("content") or "")[:500]})
        return {"packet": packet, "note": "oldest first; pull any id in full via recall if the excerpt is not enough"}
    if call.get("tool") == "capture":
        ok = core.capture("KNOWLEDGE", str(call.get("title", "untitled")),
                          str(call.get("content", "")),
                          tags=list(call.get("tags") or []) + ["rhea-noir"])
        return {"captured": bool(ok)}
    if call.get("tool") == "tracker":
        space = os.environ.get("NOUGEN_TRACKER_SPACE", "nougenai/NouGenTracker-node")
        host = os.environ.get("NOUGEN_TRACKER_HOST",
                              f"https://{space.replace('/', '-').lower()}.static.hf.space")
        def _get(url):
            req = urllib.request.Request(url, headers={"User-Agent": "rhea-noir/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        lane = call.get("lane")
        if not lane:
            tree = _get(f"https://huggingface.co/api/spaces/{space}/tree/main/dailies")
            return {"lanes": [e["path"].split("/")[-1] for e in tree if e.get("type") == "directory"]}
        date = call.get("date")
        if not date:
            tree = _get(f"https://huggingface.co/api/spaces/{space}/tree/main/dailies/{lane}")
            dates = sorted(e["path"].split("/")[-1][:-5] for e in tree if e["path"].endswith(".json"))
            if not dates:
                return {"error": f"no dailies for lane {lane}"}
            date = dates[-1]
        return {"lane": lane, "date": date, "daily": _get(f"{host}/dailies/{lane}/{date}.json")}
    if call.get("tool") == "relay":
        repo = os.environ.get("NOUGEN_RELAY_REPO", "Who-Visions/NouGenRelay")
        branch = os.environ.get("NOUGEN_RELAY_BRANCH", "main")
        gh_token = (os.environ.get("NOUGEN_RELAY_GITHUB_TOKEN")
                    or os.environ.get("GITHUB_TOKEN") or "").strip()
        if not gh_token:
            return {"error": "relay lane not configured "
                             "(NOUGEN_RELAY_GITHUB_TOKEN / GITHUB_TOKEN unset)"}
        import base64
        def _gh(path):
            req = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}",
                                         headers={"Authorization": f"Bearer {gh_token}",
                                                  "User-Agent": "rhea-noir/1.0",
                                                  "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        leg_id = str(call.get("id") or "").strip()
        if not leg_id:
            entries = _gh(f"/contents/.handoffs?ref={branch}")
            ids = sorted((e["name"][:-5] for e in entries if e["name"].endswith(".json")), reverse=True)
            if not ids:
                return {"error": "relay registry has no legs"}
            leg_id = ids[0]
        leg_id = "".join(c for c in leg_id if c.isalnum() or c in "_.-")
        rec = json.loads(base64.b64decode(_gh(f"/contents/.handoffs/{leg_id}.json?ref={branch}")["content"]))
        try:
            body = base64.b64decode(_gh(f"/contents/.handoffs/{leg_id}.md?ref={branch}")["content"]).decode()
        except Exception:
            body = "(no markdown body)"
        return {"id": leg_id, "status": rec.get("status"), "machine": rec.get("machine"),
                "agent": rec.get("agent"), "goal": rec.get("goal"),
                "created_utc": rec.get("created_utc"), "body": body[:3000]}
    if call.get("tool") == "health":
        counts = 0
        for i in range(1, core.MAX_DB_COUNT + 1):
            if core.get_db_path(i).exists():
                conn = core.get_connection(i)
                try:
                    counts += conn.execute("SELECT count(*) FROM shards").fetchone()[0]
                finally:
                    conn.close()
        return {"total_shards": counts}
    if call.get("tool") in ("dav1d", "agy"):
        from nougen_shards.dav1d_executor import run_dav1d_agy
        return run_dav1d_agy(
            command=str(call.get("command") or "agy"),
            args=call.get("args"),
            subcommand=call.get("subcommand"),
            prompt=call.get("prompt"),
        )
    return {"error": f"unknown tool {call.get('tool')}"}


_TOOL_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_tool_bounded(call: dict, deadline: float) -> dict:
    """_run_tool under a budget: a recall stuck scanning a malformed grid DB
    (or any slow store) must not wedge the request past the proxy cut. The
    stuck worker thread is abandoned, not killed - the loop moves on."""
    budget = min(float(os.environ.get("NOUGEN_RHEA_TOOL_S", "25")),
                 max(5.0, deadline - time.monotonic()))
    fut = _TOOL_POOL.submit(_run_tool, call)
    try:
        return fut.result(timeout=budget)
    except concurrent.futures.TimeoutError:
        logger.warning("tool %s timed out after %.0fs", call.get("tool"), budget)
        return {"error": f"tool {call.get('tool')} timed out after {int(budget)}s"}
    except Exception as exc:
        return {"error": f"tool {call.get('tool')} failed: {str(exc)[:200]}"}


def _first_json_object(reply: str):
    """First JSON object in a reply, tolerant of fences, prose, or several
    objects back-to-back (reasoning models sometimes emit two tool calls at
    once — we take the first and the loop feeds back the result)."""
    text = reply.strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj if isinstance(obj, dict) else None
    except ValueError:
        return None


def ask(prompt: str) -> dict:
    """The agent loop: persona + tools, bounded rounds, honest brain label."""
    messages = [{"role": "system", "content": _persona() + "\n\n" + TOOL_SPEC},
                {"role": "user", "content": prompt}]
    t0 = time.monotonic()
    max_rounds = int(os.environ.get("NOUGEN_RHEA_MAX_ROUNDS", "8"))
    # Wall-clock budget: proxies cut the connection at ~90-100s, so the loop
    # must leave itself room to compose. A round that would start with less
    # than the compose reserve remaining goes straight to the compose pass.
    deadline = time.monotonic() + float(os.environ.get("NOUGEN_RHEA_DEADLINE_S", "75"))
    compose_reserve = 20.0
    tools_used = []
    brain = "none"
    for _ in range(max_rounds):
        remaining = deadline - time.monotonic()
        if remaining < compose_reserve + 5.0:
            break
        reply, brain = _chat(messages, timeout_s=remaining - compose_reserve)
        data = _first_json_object(reply)
        if data is None:
            return {"answer": reply.strip(), "brain": brain, "tools_used": tools_used}
        if "answer" in data:
            logger.info("rhea answered in %.1fs (tools=%s, brain=%s)",
                        time.monotonic() - t0, tools_used, brain)
            return {"answer": data["answer"], "brain": brain, "tools_used": tools_used}
        if "tool" in data:
            tools_used.append(data.get("tool"))
            result = _run_tool_bounded(data, deadline)
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user",
                             "content": f"TOOL RESULT: {json.dumps(result)[:4000]}\n"
                                        "Continue: another tool call or your final answer, JSON only."})
            continue
        return {"answer": reply.strip(), "brain": brain, "tools_used": tools_used}
    # Rounds exhausted with a tool trace in hand: force one compose-only pass
    # instead of discarding everything the tools gathered. Deep archive sweeps
    # legitimately spend every round on tools; the gathered evidence is the
    # answer's raw material, not waste.
    messages.append({"role": "user", "content":
                     "TIME OR ROUND BUDGET REACHED. Tool calls are no longer available. "
                     "Compose your best final answer NOW from the tool results "
                     "above, noting any gaps you could not cover. "
                     'JSON {"answer": ...} or plain text.'})
    try:
        reply, brain = _chat(messages, timeout_s=max(10.0, deadline - time.monotonic()))
        data = _first_json_object(reply)
        answer = data["answer"] if data is not None and "answer" in data else reply.strip()
    except Exception:
        answer = ""
    logger.info("rhea composed at budget limit in %.1fs (tools=%s, brain=%s)",
                time.monotonic() - t0, tools_used, brain)
    if answer:
        return {"answer": answer, "brain": brain, "tools_used": tools_used,
                "note": "composed at budget limit"}
    return {"answer": "(round limit hit before a final answer)",
            "brain": brain, "tools_used": tools_used}
