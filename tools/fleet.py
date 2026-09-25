"""
NouGen FLEET — parallel multi-route dispatcher.

"Fleet" means MANY routes at once. Never a single worker.

Honours Rule 0.5 routing priority:
    1. Hugging Face Spaces      (MoE / frontier)
    2. OpenRouter free routes   (frontier fallback)
    3. Arli AI free routes      (frontier fallback)
    4. Local Ollama / LM Studio (tactical, $0)
    5. Ollama Cloud routes      (heavy cloud fallback)

Routes are read from the global MCP registry:
    ~\\.gemini\\antigravity-ide\\mcp_config.json

Usage
-----
    from fleet import Fleet
    f = Fleet()                      # loads + ranks every route
    f.probe()                        # health-check all routes in parallel
    out = f.map(prompts)             # fan N prompts across N routes concurrently
    one = f.ask("question")          # single call, first healthy route by priority

CLI
---
    python fleet.py probe            # show which routes are alive
    python fleet.py ask "question"
"""
from __future__ import annotations
import json, os, re, sys, time, itertools, threading, hashlib, ipaddress
for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; never crash printing model output (9/13/2026)
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request, urllib.error, urllib.parse

MCP_CONFIG = os.path.expanduser(r"~\.gemini\antigravity-ide\mcp_config.json")

# Rule 0.5 priority: lower number = tried first
PRIORITY = [
    ("hf-space",     1),
    ("openrouter",   2),
    ("arliai",       3),
    ("lmstudio",     4),
    ("local",        4),
    ("ollama-cloud", 5),
    ("vertex",       6),   # BILLED — opt-in only, see vertex_lane.py
]
# Fleet boxes run on DHCP, so a literal address here is a route that works
# until the next lease and then fails as "host down". mDNS names track the
# lease; env vars let a caller override without editing code. The same stale
# literal (a hardcoded LAN address) is what broke blade's firewall rule and
# its CLAUDE.md docs, so it is not a hypothetical failure mode.
BLADE_HOST  = os.environ.get("NOUGEN_BLADE_HOST",  "blade1tb.local")
BLADE_MODEL = os.environ.get("NOUGEN_BLADE_MODEL", "gemma4:e2b")
# The route is NAMED for whoart, so it must ADDRESS whoart. Defaulting this
# to localhost meant that whenever Fleet dispatched from any other box, the
# "whoart" lane loaded a ~7GB gemma4 onto THAT machine instead. On phoebus
# (16GB, CPU-only) that evicted the kaedracode:e2b the Kaedra gateway pins
# with keep_alive=-1, so the pin looked broken while whoart's own ollama --
# which actually holds gemma4:e2b-qat -- sat idle.
WHOART_HOST = os.environ.get("NOUGEN_WHOART_HOST", "whoart.local")

LOCAL_ROUTES = [
    {"name": "local-ollama-whoart", "url": f"http://{WHOART_HOST}:11434/v1",
     "model": "gemma4:e2b-qat", "headers": {}, "kind": "local"},
    {"name": "local-ollama-blade", "url": f"http://{BLADE_HOST}:11434/v1",
     "model": BLADE_MODEL, "headers": {}, "kind": "local"},
    {"name": "lmstudio-whoart", "url": f"http://{WHOART_HOST}:1234/v1",
     "model": "local-model", "headers": {}, "kind": "lmstudio"},
]


# Privacy mode (openhuman's local-only switch, clean-room from its README):
# NOUGEN_PRIVACY=1 makes the dispatcher STRUCTURALLY refuse any route that is
# not on this LAN. Rule 0.3 was policy only; this is the enforcement. It is
# checked at load AND at every call, so a route added later (diversify, vertex)
# cannot slip through.
class PrivacyError(RuntimeError):
    pass


def privacy_mode() -> bool:
    return os.environ.get("NOUGEN_PRIVACY", "").strip().lower() in ("1", "true", "yes", "on")


def is_private_url(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or "." not in host or host.endswith((".local", ".lan", ".home.arpa")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


# No-progress circuit breaker (openhuman move, clean-room): a caller re-running
# a prompt that already failed on every lane is a loop, not bad luck. After
# BREAKER_MAX consecutive fully-failed runs of one prompt, dispatch stops and
# hands back a root-cause summary instead of burning more lanes. Counted per
# run, not per lane, so one bad consensus run never cuts off its own lanes.
BREAKER_MAX = int(os.environ.get("NOUGEN_BREAKER_MAX", "3") or 3)
_breaker: dict[str, list[str]] = {}
_breaker_lock = threading.Lock()


def _prompt_key(prompt) -> str:
    return hashlib.sha1(json.dumps(prompt, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _root_cause(fails: list[str]) -> str:
    joined = " ".join(fails).lower()
    if "privacyerror" in joined:
        hint = "privacy mode refused every route; use a local lane or unset NOUGEN_PRIVACY"
    elif " 401" in joined or " 403" in joined:
        hint = "auth refused; a registry key is stale"
    elif " 429" in joined:
        hint = "rate-limited; a 429 is one model's shared pool, so diversify() to other vendors instead of retrying"
    elif "empty" in joined:
        hint = "empty content at HTTP 200; max_tokens is starving a reasoning model, raise it to >= 1400"
    elif "timeout" in joined or "urlerror" in joined:
        hint = "routes unreachable; probe() and check the DHCP/mDNS host names"
    else:
        hint = "no common cause; read the last reason"
    return f"breaker: {len(fails)} identical failed runs; last: {fails[-1][:160]}; cause: {hint}"


def _breaker_open(key: str) -> str | None:
    with _breaker_lock:
        fails = _breaker.get(key, [])
        return _root_cause(fails) if len(fails) >= BREAKER_MAX else None


def _breaker_record(key: str, reason: str | None) -> None:
    with _breaker_lock:
        if reason is None:
            _breaker.pop(key, None)
        else:
            _breaker.setdefault(key, []).append(reason)


def breaker_reset() -> None:
    with _breaker_lock:
        _breaker.clear()

# Free OpenRouter models spanning DIFFERENT LABS. Consensus across one model family
# only reproduces that family's blind spots -- decorrelate by vendor.
# Refreshed 2026-09-25 from GET /api/v1/models (":free" suffix). OpenRouter governs
# free capacity GLOBALLY per model, not per account -- more keys on one slug buy
# nothing; more slugs do. Verify slugs against the live list before adding.
OR_DIVERSE = [
    ("google-31b",   "google/gemma-4-31b-it:free"),
    ("nvidia-super", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("cohere",       "cohere/north-mini-code:free"),
    ("qwen",         "qwen/qwen3.8-27b:free"),
    ("tml-small",    "thinkingmachines/inkling-small:free"),
    ("nvidia-light", "nvidia/nemotron-3.5-lightning:free"),
    ("dots",         "dots-studio/dots-3-note-preview:free"),
    ("google-moe",   "google/gemma-4-26b-a4b-it:free"),
    ("poolside-s",   "poolside/laguna-s-2.1:free"),
    ("nvidia-ultra", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    ("zai",          "z-ai/glm-5.2:free"),
    ("nvidia-omni",  "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"),
    ("tml",          "thinkingmachines/inkling:free"),
    ("poolside-xs",  "poolside/laguna-xs-2.1:free"),
    ("ling-fin",     "inclusionai/ling-3.0-flash-fin:free"),
    ("liquid",       "liquid/lfm-2.5-2.6b:free"),
]
# Server-side fallback chain sent as "models": OpenRouter hops to the next slug on a
# 429/404 inside one request instead of returning the error to us. Hard cap is 3
# entries total, so: primary + one decorrelated vendor + the random free router.
OR_FALLBACK_DEPTH = 1
OR_FREE_ROUTER = "openrouter/free"
OR_FREE_CACHE = os.path.expanduser(r"~\.nougen\fleet_or_free.json")


def refresh_or_diverse(max_age_s: int = 6 * 3600) -> list[tuple[str, str]]:
    """Rebuild OR_DIVERSE from GET /api/v1/models so deprecated ':free' slugs
    never reach a request. Cached on disk; the hardcoded list is the fallback."""
    global OR_DIVERSE
    try:
        if os.path.exists(OR_FREE_CACHE) and time.time() - os.path.getmtime(OR_FREE_CACHE) < max_age_s:
            OR_DIVERSE = [tuple(x) for x in json.load(open(OR_FREE_CACHE, encoding="utf-8"))]
            return OR_DIVERSE
        url = "https://openrouter.ai/api/v1/models?sort=throughput-high-to-low"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nougen-fleet"}), timeout=30) as r:
            data = json.load(r)["data"]
        live = []
        for m in data:
            mid = m.get("id", "")
            if not mid.endswith(":free") or m.get("expiration_date"):
                continue
            if "text" not in (m.get("architecture") or {}).get("output_modalities", ["text"]):
                continue
            if "content-safety" in mid or int(m.get("context_length") or 0) < 32000:
                continue
            tag = re.sub(r"[^a-z0-9]+", "-", mid.split("/", 1)[1].replace(":free", ""))[:24]
            live.append((tag, mid))
        if live:
            OR_DIVERSE = live
            os.makedirs(os.path.dirname(OR_FREE_CACHE), exist_ok=True)
            json.dump(live, open(OR_FREE_CACHE, "w", encoding="utf-8"))
    except Exception:
        pass
    return OR_DIVERSE


def _kind(name: str) -> str:
    for prefix, _ in PRIORITY:
        if name.startswith(prefix):
            return prefix
    return "other"


def _rank(kind: str) -> int:
    return dict(PRIORITY).get(kind, 9)


class Fleet:
    def __init__(self, config_path: str = MCP_CONFIG, include_local: bool = True,
                 include_vertex: bool | None = None, privacy: bool | None = None):
        self.routes: list[dict] = []
        self.privacy = privacy_mode() if privacy is None else privacy
        if self.privacy:
            include_vertex = False
        if os.path.exists(config_path):
            cfg = json.load(open(config_path, encoding="utf-8"))
            servers = cfg.get("mcpServers", cfg)
            for name, e in servers.items():
                if not isinstance(e, dict):
                    continue
                url = e.get("url")
                if not url or e.get("type") != "openai-compatible":
                    continue
                self.routes.append({
                    "name": name,
                    "url": url.rstrip("/"),
                    "model": e.get("model", "gpt-3.5-turbo"),
                    "headers": e.get("headers", {}) or {},
                    "kind": _kind(name),
                    "min_tokens": e.get("min_tokens", 0),
                })
        if include_local:
            self.routes.extend(LOCAL_ROUTES)
        # Vertex bills per token while every other lane is free tier or local
        # GPU, so it never joins the fleet by accident.
        if include_vertex is None:
            include_vertex = os.environ.get("NOUGEN_VERTEX") == "1"
        if include_vertex:
            from vertex_lane import vertex_routes
            self.routes.extend(vertex_routes())
        if self.privacy:
            self.routes = [r for r in self.routes if is_private_url(r["url"])]
        self.routes.sort(key=lambda r: (_rank(r["kind"]), r["name"]))
        self.healthy: list[dict] = []
        self._lock = threading.Lock()

    # ---------- model diversity ----------
    def diversify(self) -> list[dict]:
        """Expand OpenRouter accounts across DIFFERENT model vendors.

        8 accounts all pointed at one model is account diversity, not model
        diversity -- consensus over it just repeats one family's errors.
        Pairs each OpenRouter key with a different vendor's free model.
        """
        or_routes = [r for r in self.routes if r["kind"] == "openrouter"]
        if not or_routes:
            return self.routes
        refresh_or_diverse()
        extra = []
        # Every key becomes a route; keys cycle through vendors so no slug is hit
        # by more keys than necessary (the per-model pool is global anyway).
        for i, base in enumerate(or_routes):
            tag, model = OR_DIVERSE[i % len(OR_DIVERSE)]
            acct = base["name"].replace("openrouter-", "")
            extra.append({**base, "name": f'or-{tag}-{acct}', "model": model, "vendor": tag,
                          "min_tokens": max(base.get("min_tokens", 0), 1024),
                          "fallbacks": [m for _, m in OR_DIVERSE[(i + 1) % len(OR_DIVERSE):][:OR_FALLBACK_DEPTH]]
                                       + [OR_FREE_ROUTER]})
        # keep non-openrouter routes, replace the duplicated openrouter block
        self.routes = [r for r in self.routes if r["kind"] != "openrouter"] + extra
        self.routes.sort(key=lambda r: (_rank(r["kind"]), r["name"]))
        return self.routes

    def by_vendor(self) -> dict:
        """Healthy routes grouped by distinct model, for true consensus sampling."""
        g = {}
        for r in self.healthy:
            g.setdefault(r["model"], []).append(r)
        return g

    # ---------- transport ----------
    def _call(self, route: dict, prompt, timeout: int = 120,
              max_tokens: int = 2048, temperature: float = 0.0) -> str:
        """prompt: a string (sent as one user message) or a ready chat list [{"role", "content"}, ...]."""
        if (getattr(self, "privacy", False) or privacy_mode()) and not is_private_url(route["url"]):
            raise PrivacyError(f"privacy mode: refused cloud route {route['name']} "
                               f"({urllib.parse.urlsplit(route['url']).hostname})")
        # Reasoning models spend a hidden budget before emitting content and
        # return empty at HTTP 200 if starved. A route may declare its floor.
        max_tokens = max(max_tokens, route.get("min_tokens", 0))
        payload = {
            "model": route["model"],
            "messages": prompt if isinstance(prompt, list) else [{"role": "user", "content": str(prompt)}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if route.get("fallbacks"):
            payload["models"] = [route["model"], *route["fallbacks"]]
        body = json.dumps(payload).encode()
        hdrs = {"Content-Type": "application/json", **route["headers"]}
        # Vertex-style routes carry a short-lived token minted per call, not a
        # static key baked into the registry.
        if route.get("token_fn"):
            hdrs["Authorization"] = f'Bearer {route["token_fn"]()}'
        req = urllib.request.Request(route["url"] + "/chat/completions", data=body, headers=hdrs)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.load(r)
        return (j.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""

    # ---------- health ----------
    def probe(self, timeout: int = 25, workers: int = 16, verbose: bool = True) -> list[dict]:
        """Health-check every route in parallel. Populates self.healthy."""
        def check(rt):
            t0 = time.time()
            try:
                # 128 not 8: reasoning models (nemotron, gpt-oss, minimax) spend tokens
                # thinking before content; at 8 they return empty and probe as dead.
                out = self._call(rt, "Reply with the single word: OK", timeout=timeout, max_tokens=128)
                ok = bool(out.strip())
                return rt, ok, round(time.time() - t0, 1), out.strip()[:24]
            except Exception as ex:
                code = getattr(ex, "code", "")
                try:
                    detail = ex.read()[:400].decode("utf-8", "replace") if hasattr(ex, "read") else ""
                    m = re.search(r'"raw":"([^"]{0,60})|"message":"([^"]{0,60})', detail)
                    detail = next((g for g in (m.groups() if m else ()) if g), "")
                except Exception:
                    detail = ""
                return rt, False, round(time.time() - t0, 1), f"{type(ex).__name__} {code} {detail}".strip()
        results = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for rt, ok, dt, note in ex.map(check, self.routes):
                results.append((rt, ok, dt, note))
                if ok:
                    with self._lock:
                        self.healthy.append(rt)
        self.healthy.sort(key=lambda r: (_rank(r["kind"]), r["name"]))
        if verbose:
            for rt, ok, dt, note in sorted(results, key=lambda x: (_rank(x[0]["kind"]), x[0]["name"])):
                print(f'  [{ "UP " if ok else "down" }] {_rank(rt["kind"])} {rt["name"][:38]:<40}'
                      f'{dt:>6.1f}s  {rt["model"][:28]:<30} {note[:22]}')
            print(f'\n  {len(self.healthy)}/{len(self.routes)} routes healthy')
        return self.healthy

    # ---------- work ----------
    def ask(self, prompt: str, **kw) -> str:
        """Single question, first healthy route by Rule 0.5 priority, with fallback."""
        key = _prompt_key(prompt)
        tripped = _breaker_open(key)
        if tripped:
            raise RuntimeError(f"no route answered ({tripped})")
        reasons = []
        for rt in (self.healthy or self.routes):
            try:
                out = self._call(rt, prompt, **kw)
                if out.strip():
                    _breaker_record(key, None)
                    return out
                reasons.append("empty")
            except Exception as ex:
                reasons.append(f"{type(ex).__name__} {getattr(ex, 'code', '')}".strip())
        _breaker_record(key, "; ".join(sorted(set(reasons))) or "no routes")
        raise RuntimeError("no route answered")

    def map(self, prompts: list[str], workers: int | None = None, retries: int = 2, **kw):
        """Fan a list of prompts across ALL healthy routes concurrently.
        Returns list of (index, route_name, output) in completion order."""
        pool = self.healthy or self.routes
        if not pool:
            raise RuntimeError("no routes")
        workers = workers or min(len(pool) * 2, 24)
        cyc = itertools.cycle(pool)
        assign = [(i, p, next(cyc)) for i, p in enumerate(prompts)]

        def run(item):
            i, prompt, rt = item
            tripped = _breaker_open(_prompt_key(prompt))
            if tripped:
                return i, f"FAILED({tripped})", ""
            last = None
            for attempt in range(retries + 1):
                if attempt:  # back off before re-trying; never hammer a failing pool
                    time.sleep(min(4.0, 0.5 * 2 ** (attempt - 1)))
                try:
                    out = self._call(rt, prompt, **kw)
                    if out.strip():
                        return i, rt["name"], out
                    last = "empty"
                except Exception as ex:  # keep the reason: "HTTPError 429 rate limit" beats a bare class name
                    code = getattr(ex, "code", "")
                    try:
                        detail = ex.read()[:120].decode("utf-8", "replace") if hasattr(ex, "read") else str(ex)[:120]
                    except Exception:
                        detail = ""
                    last = f"{type(ex).__name__} {code} {detail}".strip()
                rt = next(cyc)          # rotate to a different route on failure
            return i, f"FAILED({last})", ""
        out = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(run, a) for a in assign]
            for f in as_completed(futs):
                out.append(f.result())
        out.sort()
        runs: dict[str, list] = {}
        for i, name, text in out:
            runs.setdefault(_prompt_key(prompts[i]), []).append((name, text))
        for key, rows in runs.items():
            if any(text for _, text in rows):
                _breaker_record(key, None)
            elif not all(n.startswith("FAILED(breaker") for n, _ in rows):
                _breaker_record(key, "; ".join(sorted({n[7:-1] for n, _ in rows}))[:300])
        return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    f = Fleet()
    print(f"loaded {len(f.routes)} routes "
          f"({sum(1 for r in f.routes if r['kind']=='hf-space')} hf-space, "
          f"{sum(1 for r in f.routes if r['kind']=='openrouter')} openrouter, "
          f"{sum(1 for r in f.routes if r['kind']=='arliai')} arliai, "
          f"{sum(1 for r in f.routes if r['kind'] in ('local','lmstudio'))} local, "
          f"{sum(1 for r in f.routes if r['kind']=='ollama-cloud')} ollama-cloud, "
          f"{sum(1 for r in f.routes if r['kind']=='vertex')} vertex)\n")
    if cmd == "probe":
        f.probe()
    elif cmd == "ask":
        f.probe(verbose=False)
        print(f.ask(" ".join(sys.argv[2:])))
