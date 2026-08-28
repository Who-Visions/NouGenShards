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
  NOUGEN_RHEA_MAX_ROUNDS tool-loop rounds (default 4)
"""
import json
import logging
import os
import urllib.request
import datetime
import hashlib
from pathlib import Path

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
{"tool": "relay_create", "goal": "<objective>", "message": "<markdown body>", "status": "open", "idempotency_key": "..."} — publish a new relay leg / handoff to the fleet registry
{"tool": "dav1d", "command": "agy", "subcommand": "mcp list", "args": ["mcp", "list"], "prompt": "..."} — execute bounded tooling on Dav1d (Google Antigravity CLI / local execution layer)
{"tool": "agy", "subcommand": "mcp list"} — invoke AGY CLI on Dav1d to inspect MCP tools, changelogs, models, or query AGY
{"tool": "health"} — grid status
When you have what you need, reply ONLY with a JSON object whose "answer" field
holds your finished reply to the user, e.g. {"answer": "The node holds 100 items."}
Rules:
- Exactly ONE JSON object per reply. One tool call at a time, never several.
- "answer" must be the finished reply itself. Never narrate your process, never
  describe what a tool returned, and never echo this instruction's example text."""


def _persona() -> str:
    path = os.environ.get("NOUGEN_PERSONA_PATH", "/data/rhea_noir_persona.txt")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
            if text:
                return text
    except OSError:
        pass
    return DEFAULT_PERSONA


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


def _chat(messages: list) -> tuple:
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
    free_first = os.environ.get("NOUGEN_RHEA_PREFER_KIMI", "").strip() != "1"
    if free_first:
        out = _try_free(messages)
        if out:
            return out
        # Free Space tunnel outranks billed kimi: the Space owner's inference
        # credit pays, not ours. Fails through silently-but-logged.
        out = _try_kimi_space(messages)
        if out:
            return out
    keys = _inference_keys()
    kimi = os.environ.get("NOUGEN_RHEA_MODEL", "")
    if keys and kimi:
        # Resume at the last key that worked so a depleted account is not
        # re-tried on every single call.
        order = list(range(len(keys)))
        start = _LAST_GOOD_KEY["i"] % len(keys)
        order = order[start:] + order[:start]
        for idx in order:
            try:
                out = _openai_call(ROUTER_URL, keys[idx], kimi, messages)
                _LAST_GOOD_KEY["i"] = idx
                return out, f"kimi:{kimi}"
            except Exception as exc:
                logger.warning("kimi key #%d exhausted/failed (%s)", idx, str(exc)[:100])
        logger.warning("all %d kimi keys failed; falling back", len(keys))
    out = _try_free(messages)
    if out:
        return out
    out = _try_kimi_space(messages)
    if out:
        return out
    raise RuntimeError("no inference lane available (free + kimi-space + kimi all down)")


def _try_free(messages: list):
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
    for m in models:
        try:
            return _openai_call(OPENROUTER_URL, orkey, m, messages), f"free:{m}"
        except Exception as exc:
            logger.warning("free lane %s unavailable (%s)", m, str(exc)[:90])
    return None


def _space_pluck(node):
    """Deepest useful text in a gradio output blob; raises on embedded errors.

    Space endpoints return anything from a bare string to a full chat history
    (list of role dicts) to nested content blocks, so this walks tolerantly
    instead of hardcoding one Space's shape.
    """
    if isinstance(node, str):
        text = node.strip()
        if text.startswith("Error"):
            raise RuntimeError(text[:200])
        return text or None
    if isinstance(node, dict):
        if node.get("error"):
            raise RuntimeError(str(node["error"])[:200])
        for key in ("text", "content", "value", "answer"):
            if key in node:
                got = _space_pluck(node[key])
                if got:
                    return got
        return None
    if isinstance(node, list):
        for item in reversed(node):
            got = _space_pluck(item)
            if got:
                return got
    return None


def _try_kimi_space(messages: list):
    """FREE Kimi via a public HF Space's gradio API; None on any failure.

    The Space is somebody's free compute + inference credit, so it outranks
    the billed kimi-router lane (free-first doctrine). Endpoint shape is
    discovered live from /gradio_api/info (Rule 0.2: probe, don't assume) --
    the first named endpoint whose leading parameter is `message` wins, and
    the message is sent as dict or str to match what the Space declares.
    Verified 2026-08-27: tunnel pattern works hub-wide, but every public Kimi
    Space was OAuth-gated or credit-depleted (402) that day -- so this lane
    arms the route and falls through silently-but-logged until
    NOUGEN_KIMI_SPACE points at a Space that answers anonymously.
    """
    space = (os.environ.get("NOUGEN_KIMI_SPACE") or "").strip() or "akhaliq/Kimi-K3"
    try:
        timeout = int(os.environ.get("NOUGEN_KIMI_SPACE_TIMEOUT", "90"))
    except ValueError:
        timeout = 90
        logger.warning("NOUGEN_KIMI_SPACE_TIMEOUT not an int; using fallback %d", timeout)
    host = space.replace("/", "-").replace("_", "-").replace(".", "-").lower()
    base = f"https://{host}.hf.space/gradio_api"
    try:
        with urllib.request.urlopen(f"{base}/info", timeout=min(timeout, 30)) as r:
            info = json.loads(r.read().decode())
        ep_name, wants_dict, extras = None, False, []
        for name, ep in (info.get("named_endpoints") or {}).items():
            params = ep.get("parameters") or []
            if params and params[0].get("parameter_name") == "message":
                ep_name = name.lstrip("/")
                wants_dict = (params[0].get("type") or {}).get("type") == "object"
                # A required param with no default (history) must still be
                # sent concretely: None makes the app iterate NoneType.
                extras = [p.get("parameter_default")
                          if p.get("parameter_default") is not None else []
                          for p in params[1:]]
                break
        if not ep_name:
            raise RuntimeError("no message-led endpoint in /info")
        prompt = "\n\n".join(
            f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in messages)
        msg = {"text": prompt, "files": []} if wants_dict else prompt
        call_url = f"{base}/call/{ep_name}"
        req = urllib.request.Request(
            call_url, data=json.dumps({"data": [msg] + extras}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=min(timeout, 30)) as r:
            event_id = json.loads(r.read().decode())["event_id"]
        payload = None
        with urllib.request.urlopen(f"{call_url}/{event_id}", timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    payload = line[5:].strip()
        if not payload:
            raise RuntimeError("stream ended with no data event")
        text = _space_pluck(json.loads(payload))
        if not text:
            raise RuntimeError("no text in space output")
        return text, f"kimi-space:{space}"
    except Exception as exc:
        logger.warning("kimi-space %s unavailable (%s)", space, str(exc)[:120])
        return None


def _openai_call(url: str, token: str, model: str, messages: list) -> str:
    req = urllib.request.Request(url, data=json.dumps(
        {"model": model, "messages": messages,
         "max_tokens": int(os.environ.get("NOUGEN_RHEA_MAX_TOKENS", "1200"))}).encode(),
        method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
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
        since = call.get("since")
        until = call.get("until")
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

        def _get_eff_ts(r: dict) -> str:
            tm = r.get("temporal_meta")
            if isinstance(tm, dict) and tm.get("event_time_original"):
                return str(tm["event_time_original"])
            if isinstance(tm, str) and tm.strip():
                try:
                    tmd = json.loads(tm)
                    if isinstance(tmd, dict) and tmd.get("event_time_original"):
                        return str(tmd["event_time_original"])
                except Exception:
                    pass
            if r.get("event_time_original"):
                return str(r["event_time_original"])
            if r.get("original_timestamp"):
                return str(r["original_timestamp"])
            return str(r.get("effective_timestamp") or r.get("timestamp") or "")

        all_rows = list(gathered.values())
        if since or until:
            filtered = []
            for r in all_rows:
                ts = _get_eff_ts(r)
                if not ts:
                    continue
                if since and ts < since:
                    continue
                if until and ts > until + "\ufffd":
                    continue
                filtered.append(r)
            all_rows = filtered

        rows = sorted(all_rows, key=lambda r: _get_eff_ts(r))
        packet = []
        for r in rows[: 2 * limit]:
            eff_ts = _get_eff_ts(r)
            era = str(eff_ts)[:7] or "era-unknown"
            packet.append({"era": era, "source": r.get("_db_index"),
                           "id": r.get("id"), "title": r.get("title"),
                           "excerpt": (r.get("content") or "")[:500],
                           "temporal_meta": r.get("temporal_meta"),
                           "event_time_original": eff_ts if eff_ts else None})
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
        gh_token = (os.environ.get("NOUGEN_RELAY_GITHUB_TOKEN") or "").strip()
        if not gh_token:
            return {"error": "relay lane not configured (NOUGEN_RELAY_GITHUB_TOKEN unset)"}
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
    if call.get("tool") == "relay_create":
        goal = str(call.get("goal") or "").strip()
        message = str(call.get("message") or call.get("content") or "").strip()
        if not goal:
            return {"error": "validation_error: 'goal' is required for relay_create"}
        if not message:
            return {"error": "validation_error: 'message' is required for relay_create"}

        status = str(call.get("status") or "open").strip()
        idempotency_key = str(call.get("idempotency_key") or "").strip()

        repo = os.environ.get("NOUGEN_RELAY_REPO", "Who-Visions/NouGenRelay")
        branch = os.environ.get("NOUGEN_RELAY_BRANCH", "main")
        gh_token = (os.environ.get("NOUGEN_RELAY_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()

        now = datetime.datetime.now(datetime.timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        created_utc = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        machine = os.environ.get("NOUGEN_MACHINE") or "space-rhea"
        agent = "rhea-noir"

        leg_id = f"{stamp}__{machine}__{agent}"
        meta = {
            "id": leg_id,
            "machine": machine,
            "agent": agent,
            "goal": goal,
            "branch": branch,
            "sha": "space",
            "remote": "origin",
            "created_utc": created_utc,
            "stack": {"manifests": [], "frameworks": []},
            "dirty": False,
            "status": status,
        }
        if idempotency_key:
            meta["idempotency_key"] = idempotency_key

        md_body = (
            f"# 🤝 Git Handoff — {machine} / {agent}\n\n"
            f"**Goal**: {goal}\n"
            f"**Branch**: `{branch}`\n"
            f"**When**: {created_utc}\n\n"
            f"---\n{message}\n"
        )

        if gh_token:
            import base64
            def _gh_put(path, content_bytes, commit_msg):
                b64 = base64.b64encode(content_bytes).decode("ascii")
                payload = {"message": commit_msg, "content": b64, "branch": branch}
                req = urllib.request.Request(
                    f"https://api.github.com/repos/{repo}/contents/{path}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Authorization": f"Bearer {gh_token}",
                             "User-Agent": "rhea-noir/1.0",
                             "Accept": "application/vnd.github+json",
                             "Content-Type": "application/json"},
                    method="PUT"
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode())
            try:
                _gh_put(f".handoffs/{leg_id}.json", json.dumps(meta, indent=2).encode("utf-8"), f"relay({machine}): {goal[:50]}")
                _gh_put(f".handoffs/{leg_id}.md", md_body.encode("utf-8"), f"relay({machine}): {goal[:50]} [body]")
                return {"created": True, "id": leg_id, "goal": goal, "machine": machine, "agent": agent, "created_utc": created_utc}
            except urllib.error.HTTPError as exc:
                return {"error": f"github_api_error: HTTP {exc.code} {exc.reason}"}
            except Exception as exc:
                return {"error": f"relay_write_error: {type(exc).__name__}: {exc}"}

        # Env-first (Rule 0.2); the constant is a logged fallback for the
        # machine this first shipped on, not a portable truth.
        local_handoffs = Path(os.environ.get(
            "NOUGEN_RELAY_LOCAL_DIR",
            "c:/Users/super/Watchtower/NouGen/NouGenRelay/.handoffs"))
        if local_handoffs.is_dir():
            try:
                (local_handoffs / f"{leg_id}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
                (local_handoffs / f"{leg_id}.md").write_text(md_body, encoding="utf-8")
                return {"created": True, "id": leg_id, "goal": goal, "machine": machine, "agent": agent, "created_utc": created_utc, "storage": "local_filesystem"}
            except Exception as exc:
                return {"error": f"local_relay_write_error: {exc}"}

        return {"error": "auth_error: NOUGEN_RELAY_GITHUB_TOKEN not configured and local registry not found"}

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
    """The agent loop: persona + tools, guaranteed final synthesis, honest brain label."""
    messages = [{"role": "system", "content": _persona() + "\n\n" + TOOL_SPEC},
                {"role": "user", "content": prompt}]
    max_tool_rounds = int(os.environ.get("NOUGEN_RHEA_MAX_TOOL_ROUNDS", os.environ.get("NOUGEN_RHEA_MAX_ROUNDS", "4")))
    tools_used = []
    brain = "none"
    final_synthesis_forced = False

    # 1. Tool execution loop (bounded by max_tool_rounds)
    for _ in range(max_tool_rounds):
        try:
            reply, brain = _chat(messages)
        except RuntimeError as exc:
            # All inference lanes down is an operational state, not a server
            # fault: report it as a payload instead of letting it 500 the tool.
            return {
                "answer": f"Rhea is temporarily without an inference lane: {exc}",
                "brain": "none",
                "tools_used": tools_used,
                "tool_calls_count": len(tools_used),
                "final_synthesis_forced": False,
                "status": "degraded",
            }
        data = _first_json_object(reply)
        if data is None:
            return {
                "answer": reply.strip(),
                "brain": brain,
                "tools_used": tools_used,
                "tool_calls_count": len(tools_used),
                "final_synthesis_forced": False,
                "status": "completed",
            }
        if "answer" in data:
            return {
                "answer": str(data["answer"]),
                "brain": brain,
                "tools_used": tools_used,
                "tool_calls_count": len(tools_used),
                "final_synthesis_forced": False,
                "status": "completed",
            }
        if "tool" in data:
            tool_name = str(data.get("tool"))
            tools_used.append(tool_name)
            result = _run_tool(data)
            messages.append({"role": "assistant", "content": reply})

            result_str = json.dumps(result)
            if len(result_str) > 3000:
                result_str = result_str[:3000] + "... [truncated observation]"

            messages.append({
                "role": "user",
                "content": f"TOOL RESULT: {result_str}\nContinue: another tool call or your final answer, JSON only."
            })
            continue

        return {
            "answer": reply.strip(),
            "brain": brain,
            "tools_used": tools_used,
            "tool_calls_count": len(tools_used),
            "final_synthesis_forced": False,
            "status": "completed",
        }

    # 2. Guaranteed Final Synthesis Pass (Tools disabled)
    final_synthesis_forced = True
    messages.append({
        "role": "user",
        "content": (
            "Tool budget reached. Synthesize all observations into your final answer now. "
            "Reply ONLY with a JSON object: {\"answer\": \"<your finished response>\"}. "
            "Do not request any further tools."
        )
    })

    try:
        final_reply, brain = _chat(messages)
        final_data = _first_json_object(final_reply)
        if final_data and "answer" in final_data:
            answer_text = str(final_data["answer"])
        else:
            answer_text = final_reply.strip()
    except Exception as exc:
        logger.warning("final synthesis chat failed (%s); emitting digest", exc)
        answer_text = f"Observations gathered from tools ({', '.join(tools_used)}), but final synthesis encountered an error: {exc}"

    return {
        "answer": answer_text,
        "brain": brain,
        "tools_used": tools_used,
        "tool_calls_count": len(tools_used),
        "final_synthesis_forced": final_synthesis_forced,
        "status": "completed",
    }
