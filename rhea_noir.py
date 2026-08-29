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
{"tool": "health"} — grid status
When you have what you need, reply ONLY with a JSON object whose "answer" field
holds your finished reply to the user, e.g. {"answer": "Blade holds 202,979 shards."}
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



def _get_secret(name: str):
    val = os.environ.get(name)
    if val and val.strip():
        return val.strip()
    try:
        from nougen_shards import keymaker
        s = keymaker.get_secret(name)
        if s and s.strip():
            return s.strip()
    except Exception:
        pass
    return None


_LAST_GOOD_KEY = {"i": 0}


def _inference_keys() -> list:
    """Every HF identity that may carry Inference-Provider credit, in order."""
    keys = []
    raw = _get_secret("NGS_INFERENCE_TOKENS") or ""
    for k in raw.split(","):
        if k.strip():
            keys.append(k.strip())
    
    # Check all candidate HF token names in env & vault
    candidate_names = (
        "NGS_INFERENCE_TOKEN",
        "HF_TOKEN",
        "HUGGINGFACE_API_KEY",
        "HF_SPACE_API_KEY",
        "HUGGINGFACE_KEY_WHOENTERTAINS_GMAIL_COM",
        "HUGGINGFACE_KEY_DAVE_WHOVISIONS_COM",
        "HUGGINGFACE_KEY_SUPERDAVEWHO_GMAIL_COM",
        "HUGGINGFACE_KEY_NOUGENAI_GMAIL_COM",
        "HUGGINGFACE_KEY_AIWITHDAV3_GMAIL_COM",
    )
    for name in candidate_names:
        solo = _get_secret(name)
        if solo and solo.strip() and solo.strip() not in keys:
            keys.append(solo.strip())
    return keys


def _try_local(messages: list):
    """Attempt local Ollama execution on GPU VRAM at $0 before cloud fallback."""
    local_url = os.environ.get("NOUGEN_OLLAMA_URL", "http://127.0.0.1:11434/v1")
    model = os.environ.get("NOUGEN_RHEA_LOCAL_MODEL", "gemma4:e2b-qat")
    try:
        out = _openai_call(f"{local_url.rstrip('/')}/chat/completions", "ollama", model, messages)
        if out and out.strip():
            return out, f"local:{model}"
    except Exception as exc:
        logger.debug("local ollama lane unavailable (%s)", str(exc)[:80])
    return None


# Verified live against OpenRouter /api/v1/models + a real completion on
# 2026-08-29. The six ids this list used to carry after nemotron were dead —
# five returned HTTP 404 (retired model ids) and gemma-4-31b sits behind a
# shared upstream pool that answers 429 most of the day, so a "rollover" list
# of seven was really a list of one. Keep every entry here completion-tested;
# a 404 entry costs a round trip and buys nothing.
DEFAULT_FREE_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "minimax/minimax-m3:free",
    "nvidia/nemotron-3.5-lightning:free",
    "dots-studio/dots-3-note-preview:free",
    "google/gemma-4-31b-it:free",
]


def _try_free(messages: list, diagnostics: dict | None = None):
    """Walk the $0 OpenRouter models in order; rollover on 429/404/failure."""
    orkey = _get_secret("OPENROUTER_API_KEY")
    if not orkey:
        if diagnostics is not None:
            diagnostics["openrouter"] = "OPENROUTER_API_KEY unset"
        return None
    raw = os.environ.get("NOUGEN_RHEA_FREE_MODELS", "")
    models = [m.strip() for m in raw.split(",") if m.strip()] or DEFAULT_FREE_MODELS
    for m in models:
        try:
            res = _openai_call(OPENROUTER_URL, orkey, m, messages)
            if res and res.strip():
                return res, f"free:{m}"
            if diagnostics is not None:
                diagnostics[f"free:{m}"] = "empty"
        except urllib.error.HTTPError as exc:
            err = f"HTTP {exc.code}"
            logger.warning("free lane %s unavailable (%s)", m, err)
            if diagnostics is not None:
                diagnostics[f"free:{m}"] = err
        except Exception as exc:
            err = type(exc).__name__
            logger.warning("free lane %s failed (%s)", m, err)
            if diagnostics is not None:
                diagnostics[f"free:{m}"] = err
    return None


def _try_ollama_cloud(messages: list, diagnostics: dict | None = None):
    """Ollama Cloud — the tier Rhea never tried.

    A fleet probe on 2026-08-29 found 13 healthy Ollama Cloud routes at the
    same moment Rhea reported brain=none, because her chain only knew local /
    free / kimi. Keys are read as a comma-separated list so one exhausted
    account rolls to the next, same shape as the kimi lane.
    """
    raw = _get_secret("NOUGEN_OLLAMA_CLOUD_KEYS") or _get_secret("NOUGEN_OLLAMA_CLOUD_KEY") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        if diagnostics is not None:
            diagnostics["ollama_cloud"] = "NOUGEN_OLLAMA_CLOUD_KEYS unset"
        return None
    url = os.environ.get("NOUGEN_OLLAMA_CLOUD_URL", "https://ollama.com/v1/chat/completions")
    model = os.environ.get("NOUGEN_OLLAMA_CLOUD_MODEL", "gpt-oss:120b")
    for idx, key in enumerate(keys):
        try:
            out = _openai_call(url, key, model, messages)
            if out and out.strip():
                return out, f"ollama-cloud:{model}"
            if diagnostics is not None:
                diagnostics[f"ollama_cloud:key_{idx}"] = "empty"
        except urllib.error.HTTPError as exc:
            if diagnostics is not None:
                diagnostics[f"ollama_cloud:key_{idx}"] = f"HTTP {exc.code}"
        except Exception as exc:
            if diagnostics is not None:
                diagnostics[f"ollama_cloud:key_{idx}"] = type(exc).__name__
    return None


def _try_kimi(messages: list, diagnostics: dict | None = None):
    """Attempt Kimi K3 via HF Inference Router."""
    keys = _inference_keys()
    kimi = os.environ.get("NOUGEN_RHEA_MODEL") or "moonshotai/Kimi-K3"
    if keys and kimi:
        order = list(range(len(keys)))
        start = _LAST_GOOD_KEY["i"] % len(keys)
        order = order[start:] + order[:start]
        for idx in order:
            try:
                out = _openai_call(ROUTER_URL, keys[idx], kimi, messages)
                _LAST_GOOD_KEY["i"] = idx
                return out, f"kimi:{kimi}"
            except Exception as exc:
                err = str(exc)[:80]
                logger.warning("kimi key #%d exhausted/failed (%s)", idx, err)
                if diagnostics is not None:
                    diagnostics[f"kimi:key_{idx}"] = err
    elif diagnostics is not None:
        diagnostics["kimi"] = f"no keys found (keys={len(keys)})"
    return None


def _chat(messages: list, diagnostics: dict | None = None) -> tuple:
    """Returns (reply_text, brain_label). Free/Local lane first; Kimi only on request/fallback."""
    prefer_kimi = os.environ.get("NOUGEN_RHEA_PREFER_KIMI", "").strip() == "1"
    if prefer_kimi:
        out = _try_kimi(messages, diagnostics)
        if out:
            return out

    # 1. Try local Ollama ($0 GPU VRAM)
    local_out = _try_local(messages)
    if local_out:
        return local_out

    # 2. Try OpenRouter free models with rollover
    free_out = _try_free(messages, diagnostics)
    if free_out:
        return free_out

    # 3. Try Kimi if not preferred
    if not prefer_kimi:
        kimi_out = _try_kimi(messages, diagnostics)
        if kimi_out:
            return kimi_out

    # 4. Ollama Cloud — last paid-adjacent tier before giving up
    cloud_out = _try_ollama_cloud(messages, diagnostics)
    if cloud_out:
        return cloud_out

    # Name every lane that was tried and why it failed. "all down" with no
    # per-route detail is what made the 2026-08-29 outage undiagnosable from
    # the connector side — the caller could not tell a missing key from a 429.
    detail = "; ".join(f"{k}={v}" for k, v in sorted((diagnostics or {}).items()))
    raise RuntimeError(
        "no inference lane available (local, free, kimi, ollama-cloud all down)"
        + (f" — {detail}" if detail else " — no per-route diagnostics captured")
    )


def _openai_call(url: str, token: str, model: str, messages: list) -> str:
    req = urllib.request.Request(url, data=json.dumps(
        {"model": model, "messages": messages,
         # >=1400: Gemma 4 E-series emits a reasoning channel that eats the
         # budget first, so an undersized cap returns empty content with no
         # error. 1200 sat under that floor (fleet doctrine, Rule 0.5.1).
         "max_tokens": int(os.environ.get("NOUGEN_RHEA_MAX_TOKENS", "1400"))}).encode(),
        method="POST")
    if token:
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
    """The agent loop: persona + tools, bounded rounds, honest brain label."""
    messages = [{"role": "system", "content": _persona() + "\n\n" + TOOL_SPEC},
                {"role": "user", "content": prompt}]
    max_rounds = int(os.environ.get("NOUGEN_RHEA_MAX_ROUNDS", "8"))
    tools_used = []
    brain = "none"
    diagnostics = {}
    for _ in range(max_rounds):
        try:
            reply, brain = _chat(messages, diagnostics)
        except Exception as exc:
            logger.error("rhea inference failure: %s", exc)
            diag_str = ", ".join(f"{k}: {v}" for k, v in diagnostics.items()) if diagnostics else str(exc)
            return {
                "status": "degraded",
                "brain": "none",
                "answer": f"All Rhea inference routes unavailable ({diag_str}).",
                "diagnostics": diagnostics,
                "tools_used": tools_used,
            }

        data = _first_json_object(reply)
        if data is None:
            return {"status": "ok", "answer": reply.strip(), "brain": brain, "tools_used": tools_used}
        if "answer" in data:
            return {"status": "ok", "answer": data["answer"], "brain": brain, "tools_used": tools_used}
        if "tool" in data:
            tools_used.append(data.get("tool"))
            result = _run_tool(data)
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user",
                             "content": f"TOOL RESULT: {json.dumps(result)[:4000]}\n"
                                        "Continue: another tool call or your final answer, JSON only."})
            continue
        return {"status": "ok", "answer": reply.strip(), "brain": brain, "tools_used": tools_used}
    # Rounds exhausted with a tool trace in hand: force one compose-only pass
    # instead of discarding everything the tools gathered. Deep archive sweeps
    # legitimately spend every round on tools; the gathered evidence is the
    # answer's raw material, not waste.
    messages.append({"role": "user", "content":
                     "ROUND LIMIT REACHED. Tool calls are no longer available. "
                     "Compose your best final answer NOW from the tool results "
                     "above, noting any gaps you could not cover. "
                     'JSON {"answer": ...} or plain text.'})
    try:
        reply, brain = _chat(messages, diagnostics)
        data = _first_json_object(reply)
        answer = data["answer"] if data is not None and "answer" in data else reply.strip()
    except Exception:
        answer = ""
    if answer:
        return {"status": "ok", "answer": answer, "brain": brain,
                "tools_used": tools_used, "note": "composed at round limit"}
    return {"status": "ok", "answer": "(round limit hit before a final answer)",
            "brain": brain, "tools_used": tools_used}
