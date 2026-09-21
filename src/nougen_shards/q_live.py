"""NouGen Q Live Prompt Loop v1: an autonomous, memory-aware teleprompter core.

Canon (shard 26585@db9): Q is NOT a chat surface. The human speaks; Q listens to the transcript,
models what is being talked about NOW, retrieves memory from NouGenShards, predicts useful next
beats, ranks them, shows ONE cue, observes what was actually said, updates, and repeats.

    transcript -> conversation state -> bounded retrieval -> candidate beats
               -> deterministic ranking -> ONE cue -> observe speech -> update -> next cue

Design rules enforced here:
  * Retrieval is bounded and uses the gateway's fast path: POST /search {"fuzzy": false, "fast": true}, the
    local exact keyword index only (0.83s p50 measured; hybrid+vector had a 29.9s tail, fuzzy a 20s cliff:
    shards 30623@db7, 29289@db6). That path is PARTIAL coverage by construction and is reported as such
    (peer vaults not consulted). The full federated/fuzzy path is used only on explicit escalation.
  * Coverage truth is never faked: a timed-out lane, a FEDERATION_STATUS trailer, a retrieval error or
    a non-GREEN vault marks the turn DEGRADED/UNAVAILABLE and the cue's confidence drops (shard 12169@db6).
  * Memory is never fabricated: a cue may cite only shard refs that were actually returned; specifics
    (numbers, names) that appear in neither the transcript nor the retrieved text are penalised.
  * Neither retrieval nor generation ever blocks the cue: both run in the background, results are carried
    forward by topic and marked stale/pending honestly, and a cue is always shown within `cue_budget_s`.
    (Measured 2026-09-21: gateway /search 4-8s even with fuzzy off, local model ~3.5s + reloads.)
  * Read-only on shards. Session state is execution context, not memory (shard 12435@db4).
  * Deterministic ranking; the model only proposes candidates, it never decides what is shown.

Every tunable resolves from env with a logged fallback (Rule 0.0 item 4).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
import uuid
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("nougen_shards.q_live")

# --------------------------------------------------------------------------------------- config


def _env_num(name: str, default: float, cast=float):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using fallback %r", name, raw, default)
        return default


@dataclass(frozen=True)
class QConfig:
    window_words: int = 120          # rolling transcript tail shown to the model
    retrieve_limit: int = 6          # hits per retrieval (bounded)
    retrieve_timeout_s: float = 12.0  # background bound for one gateway call (off the critical path)
    retrieve_grace_s: float = 0.35    # how long a turn waits on an in-flight retrieval before moving on
    llm_timeout_s: float = 20.0       # background bound for one generation call
    cue_budget_s: float = 3.5         # max a turn waits for candidate generation before using carried/heuristic
    carry_turns: int = 4              # a candidate stays eligible this many turns after it was generated
    keep_alive: str = "30m"           # keep the local model loaded (reloads cost 2-35s per call otherwise)
    num_predict: int = 110
    n_candidates: int = 2
    cue_max_words: int = 20
    stale_after_turns: int = 2       # a cue not used/contradicted/passed this many turns is retired
    cache_ttl_s: float = 60.0
    topic_decay: float = 0.7
    memory_decay: float = 0.85        # slower decay for the memory key: it must not chase every sentence
    memory_overlap: float = 0.25      # min term overlap for cached memory to count as fresh for the topic
    retry_backoff_s: float = 10.0     # after a failed retrieval, do not hammer the gateway
    fast_path: bool = True
    gateway_origin: str = "http://127.0.0.1:4444"

    @classmethod
    def from_env(cls) -> "QConfig":
        d = cls()
        return cls(
            window_words=_env_num("Q_LIVE_WINDOW_WORDS", d.window_words, int),
            retrieve_limit=_env_num("Q_LIVE_RETRIEVE_LIMIT", d.retrieve_limit, int),
            retrieve_timeout_s=_env_num("Q_LIVE_RETRIEVE_TIMEOUT_S", d.retrieve_timeout_s),
            retrieve_grace_s=_env_num("Q_LIVE_RETRIEVE_GRACE_S", d.retrieve_grace_s),
            llm_timeout_s=_env_num("Q_LIVE_LLM_TIMEOUT_S", d.llm_timeout_s),
            cue_budget_s=_env_num("Q_LIVE_CUE_BUDGET_S", d.cue_budget_s),
            carry_turns=_env_num("Q_LIVE_CARRY_TURNS", d.carry_turns, int),
            keep_alive=os.environ.get("Q_LIVE_KEEP_ALIVE") or d.keep_alive,
            num_predict=_env_num("Q_LIVE_NUM_PREDICT", d.num_predict, int),
            n_candidates=_env_num("Q_LIVE_CANDIDATES", d.n_candidates, int),
            cue_max_words=_env_num("Q_LIVE_CUE_MAX_WORDS", d.cue_max_words, int),
            stale_after_turns=_env_num("Q_LIVE_STALE_AFTER_TURNS", d.stale_after_turns, int),
            cache_ttl_s=_env_num("Q_LIVE_CACHE_TTL_S", d.cache_ttl_s),
            topic_decay=_env_num("Q_LIVE_TOPIC_DECAY", d.topic_decay),
            memory_decay=_env_num("Q_LIVE_MEMORY_DECAY", d.memory_decay),
            memory_overlap=_env_num("Q_LIVE_MEMORY_OVERLAP", d.memory_overlap),
            retry_backoff_s=_env_num("Q_LIVE_RETRY_BACKOFF_S", d.retry_backoff_s),
            fast_path=os.environ.get("Q_LIVE_FAST", "1").strip().lower() not in ("0", "false", "no", "off"),
            gateway_origin=(os.environ.get("NOUGEN_NODE_ORIGIN") or d.gateway_origin).rstrip("/"),
        )


# --------------------------------------------------------------------------------------- text utils

_WORD = re.compile(r"[a-z][a-z'\-]{2,}")
_STOP = frozenset(
    "the and for that this with you your are was were have has had not but they them their from there "
    "here what when where which who whom will would could should about into over just like really very "
    "also than then being been because while these those it's i'm i've we're don't can't its our out get "
    "got going one all any some more most such only own same too can did does doing how why yes yeah "
    "okay right well let's thing things kind sort stuff know think mean say said says gonna wanna".split()
)
_NEG_WORDS = frozenset("no not never wrong isn't doesn't don't wasn't nope incorrect false".split())
_CORRECTION = re.compile(r"(let me correct|correct that|that's not (right|true)|that is not (right|true)|"
                         r"scratch that|i take that back|not true)", re.I)


def _negated_near(utt: str, cue_terms: set, cue_text: str, window: int = 4) -> bool:
    """True if the utterance negates something about the cue: a negation word (not already in the cue's own
    wording) within `window` tokens of a cue term, or an explicit correction phrase."""
    if _CORRECTION.search(utt):
        return True
    toks = re.findall(r"[a-z][a-z'\-]*", utt.lower())
    own = set(re.findall(r"[a-z][a-z'\-]*", cue_text.lower()))
    for i, t in enumerate(toks):
        if t in _NEG_WORDS and t not in own:
            near = " ".join(toks[max(0, i - window): i + window + 1])
            if set(_terms(near)) & cue_terms:
                return True
    return False


def _terms(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        if w in _STOP:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def _words(text: str) -> int:
    return len(text.split())


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _specifics(text: str) -> set[str]:
    """Digits and mid-sentence Capitalised words: the tokens a model is most likely to invent."""
    toks = re.findall(r"\b\d[\d,.]*\b|(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z]+\b", text)
    return {t.lower().strip(".,") for t in toks if t.lower() not in {"i", "i'm", "i've"}}


# --------------------------------------------------------------------------------------- data


@dataclass
class Hit:
    ref: str
    title: str
    snippet: str
    score: float = 0.0


@dataclass
class RetrievalResult:
    hits: list[Hit] = field(default_factory=list)
    complete: bool = True
    degraded: bool = False
    lanes: str = ""
    latency_ms: float = 0.0
    error: Optional[str] = None
    from_cache: bool = False
    fuzzy: bool = False
    lanes_skipped: list = field(default_factory=list)   # lanes deliberately not consulted (fast path)


@dataclass
class Candidate:
    text: str
    kind: str = "transition"
    shards: list[str] = field(default_factory=list)
    why: str = ""
    score: float = 0.0
    unsupported: int = 0
    source: str = "llm"   # llm | memory | heuristic
    turn: int = 0         # turn the candidate was generated on (carried candidates are older than the turn shown)


@dataclass
class Cue:
    text: str
    why_now: str
    shards: list[str]
    kind: str
    confidence: str
    mode: str
    issued_turn: int
    age: int = 0
    status: str = "pending"   # pending | used | moved_past | contradicted | skipped


# --------------------------------------------------------------------------------------- transports


def urllib_json(method: str, url: str, headers: dict, body: Optional[bytes], timeout: float):
    """(status, response headers, parsed JSON). Raises on network errors; callers own the budget."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - operator-configured gateway/ollama
        raw = resp.read().decode("utf-8") or "null"
        return resp.status, dict(resp.headers), json.loads(raw)


def _gateway_token() -> Optional[str]:
    tok = os.environ.get("NGS_NODE_TOKEN") or os.environ.get("SHARD_GATEWAY_TOKEN")
    if tok:
        return tok.strip()
    try:
        from nougen_shards import keymaker  # pylint: disable=import-outside-toplevel
        return keymaker.get_secret("NGS_NODE_TOKEN") or keymaker.get_secret("SHARD_GATEWAY_TOKEN")
    except Exception:  # noqa: BLE001 - keymaker unavailable => unauthenticated call fails visibly, not silently
        return None


class GatewayRetriever:
    """Bounded read-only recall over the gateway's /search. Never raises: failure is data."""

    def __init__(self, cfg: QConfig, transport=urllib_json, token: Optional[str] = None,
                 fast: Optional[bool] = None):
        self.cfg, self._t = cfg, transport
        self._token = token
        self._fast = cfg.fast_path if fast is None else fast

    def __call__(self, query: str, limit: int, fuzzy: bool = False) -> RetrievalResult:
        t0 = time.perf_counter()
        token = self._token or _gateway_token()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        # escalation (fuzzy=True) leaves the fast path: full federated recall, accepted latency
        body = json.dumps({"query": query, "limit": limit, "fuzzy": bool(fuzzy),
                           "fast": bool(self._fast and not fuzzy)}).encode()
        try:
            _, hdrs, payload = self._t("POST", self.cfg.gateway_origin + "/search", headers, body,
                                       self.cfg.retrieve_timeout_s + 0.5)
        except Exception as exc:  # noqa: BLE001
            return RetrievalResult(complete=False, degraded=True, error=f"{type(exc).__name__}: {exc}"[:200],
                                   latency_ms=(time.perf_counter() - t0) * 1000, fuzzy=fuzzy)
        lower = {k.lower(): v for k, v in hdrs.items()}
        hits, meta_incomplete = _parse_hits(payload)
        degraded = lower.get("x-nougen-degraded") == "1" or meta_incomplete
        skipped = [x for x in lower.get("x-nougen-lanes-skipped", "").split(",") if x]
        return RetrievalResult(hits=hits, complete=not degraded and not skipped, degraded=degraded,
                               lanes=lower.get("x-nougen-lane-timings", ""),
                               latency_ms=(time.perf_counter() - t0) * 1000, fuzzy=fuzzy, lanes_skipped=skipped)


def _parse_hits(payload) -> tuple[list[Hit], bool]:
    hits: list[Hit] = []
    incomplete = False
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("event_type") == "FEDERATION_STATUS" or str(item.get("id", "")).startswith("federation_"):
            incomplete = True   # a coverage marker, not a memory
            continue
        sid, db = item.get("id"), item.get("_db_index")
        if sid is None:
            continue
        snippet = re.sub(r"\s+", " ", str(item.get("content") or ""))[:240]
        hits.append(Hit(ref=f"shard:{sid}@db{db}", title=str(item.get("title") or "")[:120], snippet=snippet,
                        score=float(item.get("final_score") or item.get("score") or 0.0)))
    return hits, incomplete


# ---- candidate generation -------------------------------------------------------------------

_SYSTEM = (
    "You write live teleprompter cues for a human speaker named Dave. Output JSON only. "
    "Each cue is ONE short spoken line Dave could say NEXT, in first person, plain conversational English. "
    "Use only the numbered MEMORY items and the transcript; never invent facts, names, numbers or stories. "
    "If a cue does not use a memory item, its memory list must be empty."
)


def pick_model(served: list[str], env: Optional[str] = None,
               exclude: Optional[set[str]] = None) -> Optional[str]:
    """Rule 0.4 order: env-preferred (if served) > custom e2b/e4b > gemma4 e2b/e4b > refuse.
    12b/27b/31b-class tags and cloud tags are never picked."""
    banned = re.compile(r"(12b|27b|31b|-cloud)")
    exclude = exclude if exclude is not None else set(
        (os.environ.get("Q_LIVE_EXCLUDE_MODELS") or "kaedra,rhea-noir,iris-ai,griot,mrs-b").split(","))
    if env and env in served and not banned.search(env):
        return env
    small = [m for m in served if re.search(r":e[24]b", m.lower()) and not banned.search(m.lower())
             and not any(x and x in m.lower() for x in exclude) and "pre" not in m.lower().split(":")[-1]]
    custom = [m for m in small if not m.lower().startswith(("gemma", "hf.co"))]
    base = [m for m in small if m.lower().startswith("gemma4")]
    for pool in (custom, base):
        for size in (":e2b", ":e4b"):   # e2b first: latency matters more than polish here
            for m in pool:
                if size in m.lower():
                    return m
    return None


class OllamaCandidateGenerator:
    """Proposes candidate beats with a small local model. It has no authority over what is displayed."""

    def __init__(self, cfg: QConfig, transport=urllib_json, base_url: Optional[str] = None,
                 model: Optional[str] = None):
        self.cfg, self._t = cfg, transport
        self._base = (base_url or self._resolve_base()).rstrip("/")
        self.model = model or self._discover_model()

    @staticmethod
    def _resolve_base() -> str:
        try:
            from nougen_shards import ollama_host  # pylint: disable=import-outside-toplevel
            return ollama_host.resolve_ollama_url(log=False)
        except Exception:  # noqa: BLE001
            return os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"

    def _discover_model(self) -> str:
        _, _, tags = self._t("GET", self._base + "/api/tags", {}, None, 5.0)
        served = [m["name"] for m in (tags or {}).get("models", [])]
        model = pick_model(served, os.environ.get("Q_LIVE_MODEL"))
        if not model:
            raise RuntimeError("no e2b/e4b model served; refusing to pick a larger tag (Rule 0.4)")
        return model

    def warm(self) -> float:
        """Load the model into memory once, before the session, so the first cue does not pay 15-35s."""
        t0 = time.perf_counter()
        body = json.dumps({"model": self.model, "stream": False, "keep_alive": self.cfg.keep_alive,
                           "messages": [{"role": "user", "content": "ok"}], "think": False,
                           "options": {"num_predict": 1, "num_ctx": 2048}}).encode()   # same num_ctx as real calls (else reload)
        self._t("POST", self._base + "/api/chat", {"Content-Type": "application/json"}, body, 120.0)
        return (time.perf_counter() - t0) * 1000

    def __call__(self, tail: str, topic: str, hits: list[Hit], n: int) -> list[dict]:
        memory = "\n".join(f"[{i + 1}] {h.title}: {h.snippet[:120]}" for i, h in enumerate(hits[:5])) or "(none)"
        user = (f"TRANSCRIPT (latest last):\n{tail}\n\nTOPIC NOW: {topic}\n\nMEMORY:\n{memory}\n\n"
                f"Give {n} different candidate next lines, each at most {self.cfg.cue_max_words} words. "
                'JSON: {"candidates":[{"text":"...","kind":"callback|fact|story|transition|joke|question|example",'
                '"memory":[1],"why":"..."}]}')
        body = json.dumps({"model": self.model, "stream": False, "think": False, "format": "json",
                           "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
                           "keep_alive": self.cfg.keep_alive,
                           "options": {"temperature": 0.6, "num_predict": self.cfg.num_predict, "num_ctx": 2048}}).encode()
        _, _, data = self._t("POST", self._base + "/api/chat", {"Content-Type": "application/json"}, body,
                             self.cfg.llm_timeout_s)
        parsed = json.loads(data["message"]["content"])
        cands = parsed.get("candidates") if isinstance(parsed, dict) else None
        return [c for c in (cands or []) if isinstance(c, dict)]


def _trim(text: str, max_words: int) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip().strip('"')
    words = text.split()
    return text if len(words) <= max_words else " ".join(words[:max_words]).rstrip(",;:") + "..."


def validate_candidates(raw: list[dict], hits: list[Hit], tail: str, cfg: QConfig) -> list[Candidate]:
    """Turn model output into candidates. Memory indices are checked against real hits; anything the
    model cites that was not retrieved is dropped, so a cue can never point at a shard that was not returned."""
    support = (tail + " " + " ".join(h.title + " " + h.snippet for h in hits)).lower()
    out: list[Candidate] = []
    for c in raw:
        text = _trim(c.get("text", ""), cfg.cue_max_words)
        if not text:
            continue
        refs, seen = [], set()
        for idx in c.get("memory") or []:
            if isinstance(idx, int) and 1 <= idx <= len(hits) and idx not in seen:
                seen.add(idx)
                refs.append(hits[idx - 1].ref)
        bad = sum(1 for s in _specifics(text) if s not in support)
        out.append(Candidate(text=text, kind=str(c.get("kind") or "transition")[:16], shards=refs,
                             why=_trim(c.get("why", ""), 16), unsupported=bad, source="llm"))
    return out


def heuristic_candidates(topic_terms: list[str], hits: list[Hit], cfg: QConfig) -> list[Candidate]:
    """No-model fallback: honest, low-confidence, never claims memory it did not retrieve."""
    out = [Candidate(text=_trim(f"Callback to: {h.title}", cfg.cue_max_words), kind="callback",
                     shards=[h.ref], why="retrieved memory title, verbatim", source="memory") for h in hits[:3]]
    topic = " ".join(topic_terms[:2]) or "this"
    out += [Candidate(text=f"Give one concrete example of {topic}.", kind="example", why="context-only template",
                      source="heuristic"),
            Candidate(text=f"Bring it back: why does {topic} matter to the people listening?", kind="transition",
                      why="context-only template", source="heuristic")]
    return out


# --------------------------------------------------------------------------------------- state


class LiveState:
    def __init__(self, cfg: QConfig):
        self.cfg = cfg
        self.utterances: deque[str] = deque(maxlen=200)
        self.shown: deque[set] = deque(maxlen=12)
        self.kind_weight: dict[str, float] = {}
        self.suppressed: set[str] = set()

    def add(self, text: str) -> None:
        self.utterances.append(text.strip())

    def tail(self) -> str:
        words = " ".join(self.utterances).split()
        return " ".join(words[-self.cfg.window_words:])

    def term_weights(self, decay: Optional[float] = None) -> Counter:
        decay = self.cfg.topic_decay if decay is None else decay
        w: Counter = Counter()
        for age, utt in enumerate(reversed(self.utterances)):
            if age > 12:
                break
            for t in _terms(utt):
                if t not in self.suppressed:
                    w[t] += decay ** age
        return w

    def top_terms(self, n: int, decay: Optional[float] = None) -> list[str]:
        return [t for t, _ in self.term_weights(decay).most_common(n)]


# --------------------------------------------------------------------------------------- engine


class QLive:
    """The loop. Call `on_utterance(text)` with each new chunk of live transcript; get back the state
    dict (session_id, topic_now, transcript_tail, candidate_prompts, display_prompt, latency_ms, ...).

    Pipelined: each turn (1) observes what was said about the standing cue, (2) reads whatever memory the
    background retrieval has produced so far, (3) reads whatever candidates the background generator has
    produced so far, (4) ranks deterministically, (5) shows ONE cue. Slow parts land for the NEXT turn."""

    def __init__(self, retriever: Callable = None, generator: Optional[Callable] = None,
                 cfg: Optional[QConfig] = None, fleet_vaults: Optional[dict] = None,
                 trace_path: Optional[str] = None, clock: Callable[[], float] = time.monotonic):
        self.cfg = cfg or QConfig.from_env()
        self.retriever = retriever or GatewayRetriever(self.cfg)
        self.generator = generator
        self.fleet_vaults = dict(fleet_vaults or {})
        self.trace_path = trace_path
        self._clock = clock
        self.state = LiveState(self.cfg)
        self.session_id = "q_live_" + uuid.uuid4().hex[:10]
        self.turn = 0
        self.cue: Optional[Cue] = None
        # 4 workers: a straggler must never starve the next turn's submission
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="q_live")
        self._mem: Optional[tuple] = None        # (terms:set, RetrievalResult, taken_at)
        self._ret: Optional[tuple] = None        # in-flight retrieval: (terms:set, future, submitted_turn)
        self._ret_error: Optional[RetrievalResult] = None
        self._ret_error_at: float = -1e9
        self._gen: Optional[tuple] = None        # in-flight generation: (future, hits, tail, submitted_turn)
        self._gen_waited = False                 # a stalled call may cost ONE wait, not one per turn
        self._cands: list[Candidate] = []        # carried candidates
        self._last_topic: set[str] = set()
        self._shown_counts: Counter = Counter()
        self._last_call_ms = {"retrieval": 0.0, "generation": 0.0}

    # -- observe what was actually said about the standing cue
    def _observe(self, utt: str) -> Optional[str]:
        cue = self.cue
        if cue is None or cue.status != "pending":
            return None
        cue_terms, utt_terms = set(_terms(cue.text)), set(_terms(utt))
        overlap = len(cue_terms & utt_terms) / len(cue_terms) if cue_terms else 0.0
        topic_now = set(self.state.top_terms(5))
        shifted = _jaccard(self._last_topic, topic_now) < 0.3 if self._last_topic else False
        cue.age += 1
        # contradiction needs a negation near the cue's own terms (or a correction phrase); a "not" in an
        # unrelated clause, or one that is part of the cue's own wording, is not a contradiction
        negated = _negated_near(utt, cue_terms, cue.text)
        if overlap >= 0.35 and not negated:
            status = "used"
        elif overlap >= 0.2 and negated:
            status = "contradicted"
        elif overlap < 0.1 and shifted:
            status = "moved_past"
        elif cue.age >= self.cfg.stale_after_turns:
            status = "skipped"
        else:
            return None   # still pending; it stays displayed one more turn
        cue.status = status
        k = self.state.kind_weight.get(cue.kind, 1.0)
        delta = {"used": 0.1, "skipped": -0.08, "contradicted": -0.15, "moved_past": -0.03}[status]
        self.state.kind_weight[cue.kind] = min(1.4, max(0.6, k + delta))
        if status == "contradicted":
            self.state.suppressed |= cue_terms & utt_terms
        self._shown_counts[cue.text.lower()] = 10 ** 6   # retired for good: never offered again
        self.cue = None   # retired: a stale cue never stays on screen
        return status

    # -- memory: background retrieval, carried by topic, never blocking the cue
    def _harvest_retrieval(self) -> None:
        if self._ret is None or not self._ret[1].done():
            return
        terms, fut, _ = self._ret
        self._ret = None
        try:
            res = fut.result()
        except Exception as exc:  # noqa: BLE001
            res = RetrievalResult(complete=False, degraded=True, error=f"{type(exc).__name__}: {exc}"[:200])
        self._last_call_ms["retrieval"] = res.latency_ms
        if res.error is None:
            self._mem, self._ret_error = (terms, res, self._clock()), None
        else:
            self._ret_error, self._ret_error_at = res, self._clock()

    def _retrieve(self, terms: list[str], escalate: bool) -> tuple[RetrievalResult, str, float]:
        """(result, memory_state, wait_ms). memory_state: fresh | stale | pending | none.
        `terms` is the slow-decay memory key, so a new sentence does not invalidate the memory view."""
        t0 = time.perf_counter()
        cur = set(terms[:8])
        if not cur:
            return RetrievalResult(), "none", 0.0
        self._harvest_retrieval()
        now = self._clock()
        mem = self._mem

        def relevant(m) -> bool:
            return m is not None and _jaccard(m[0], cur) >= self.cfg.memory_overlap

        if mem and not escalate and relevant(mem) and now - mem[2] <= self.cfg.cache_ttl_s:
            return self._copy(mem[1]), "fresh", (time.perf_counter() - t0) * 1000
        backing_off = self._ret_error is not None and now - self._ret_error_at < self.cfg.retry_backoff_s
        if self._ret is None and not backing_off:   # topic moved or memory aged out: refresh in the background
            fut = self._pool.submit(self.retriever, " ".join(terms[:8]), self.cfg.retrieve_limit, escalate)
            self._ret = (cur, fut, self.turn)
        if self._ret is not None and mem is None:
            try:   # nothing to show yet: a short grace for the in-flight call, then move on without it
                self._ret[1].result(timeout=self.cfg.retrieve_grace_s)
            except FutureTimeout:
                pass
            except Exception:  # noqa: BLE001 - surfaced by _harvest_retrieval as an error result
                pass
            self._harvest_retrieval()
            mem = self._mem
        wait_ms = (time.perf_counter() - t0) * 1000
        if mem:
            state = "fresh" if relevant(mem) and now - mem[2] <= self.cfg.cache_ttl_s else "stale"
            return self._copy(mem[1]), state, wait_ms
        if self._ret_error is not None:
            return self._ret_error, "none", wait_ms
        return RetrievalResult(complete=False, degraded=True), "pending", wait_ms

    @staticmethod
    def _copy(r: RetrievalResult) -> RetrievalResult:
        return RetrievalResult(hits=list(r.hits), complete=r.complete, degraded=r.degraded, lanes=r.lanes,
                               latency_ms=r.latency_ms, from_cache=True, fuzzy=r.fuzzy,
                               lanes_skipped=list(r.lanes_skipped))

    # -- candidates: background generation, carried forward, heuristic floor
    def _timed_generate(self, tail: str, topic: str, hits: list[Hit], n: int):
        t0 = time.perf_counter()
        raw = self.generator(tail, topic, hits, n)
        return raw, (time.perf_counter() - t0) * 1000

    def _harvest_generation(self) -> None:
        if self._gen is None or not self._gen[0].done():
            return
        fut, hits, tail, turn = self._gen
        self._gen = None
        try:
            raw, ms = fut.result()
        except Exception as exc:  # noqa: BLE001 - model down/bad JSON: visible via generator="heuristic"
            logger.info("candidate generator failed (%s)", type(exc).__name__)
            return
        self._last_call_ms["generation"] = ms
        for c in validate_candidates(raw, hits, tail, self.cfg):
            c.turn = turn
            self._cands.append(c)
        self._cands = self._cands[-12:]

    def _candidates(self, hits: list[Hit], terms: list[str]) -> tuple[list[Candidate], float, str]:
        t0 = time.perf_counter()
        self._harvest_generation()
        if self.generator is not None and self._gen is None:
            fut = self._pool.submit(self._timed_generate, self.state.tail(), " ".join(terms[:3]), list(hits),
                                    self.cfg.n_candidates)
            self._gen = (fut, list(hits), self.state.tail(), self.turn)
            self._gen_waited = False
        has_live = any(self.turn - c.turn <= self.cfg.carry_turns for c in self._cands)
        if self._gen is not None and not has_live and not self._gen_waited:
            self._gen_waited = True   # block only when there is nothing to show, and only once per in-flight call
            try:
                self._gen[0].result(timeout=self.cfg.cue_budget_s)
            except FutureTimeout:
                pass
            except Exception:  # noqa: BLE001 - handled in harvest
                pass
            self._harvest_generation()
        # copies, so filtering a carried candidate's citations never rewrites the stored original
        live = [Candidate(**asdict(c)) for c in self._cands if self.turn - c.turn <= self.cfg.carry_turns
                and self._shown_counts[c.text.lower()] < self.cfg.stale_after_turns]
        # a carried candidate may only cite shards that are in the CURRENT memory view (provenance stays true)
        cur_refs = {h.ref for h in hits}
        for c in live:
            c.shards = [r for r in c.shards if r in cur_refs]
        wait_ms = (time.perf_counter() - t0) * 1000
        if live:
            return live, wait_ms, "llm"
        fallback = heuristic_candidates(terms, hits, self.cfg)
        for c in fallback:
            c.turn = self.turn
        return fallback, wait_ms, "heuristic"

    def _score(self, c: Candidate, terms: list[str], last_utt: str, hits: list[Hit]) -> float:
        cterms, topic = set(_terms(c.text)), set(terms[:6])
        relevance = min(1.0, len(cterms & topic) / max(1, min(3, len(topic))))
        continuity = min(1.0, 0.6 * _jaccard(cterms, set(_terms(last_utt))) * 4 + (0.4 if c.shards else 0.0))
        recent = set().union(*self.state.shown) if self.state.shown else set()
        spoken = set(_terms(" ".join(list(self.state.utterances)[-3:])))
        novelty = 1.0 - max(_jaccard(cterms, recent), _jaccard(cterms, spoken))
        length = _words(c.text) / self.cfg.cue_max_words
        timing = max(0.0, 1.0 - 0.6 * length)
        usefulness = (0.6 if c.shards else 0.25) - 0.5 * min(2, c.unsupported)
        freshness = 1.0 - 0.12 * max(0, self.turn - c.turn)   # carried candidates fade
        base = 0.30 * relevance + 0.20 * continuity + 0.20 * novelty + 0.10 * timing + 0.20 * max(0.0, usefulness)
        return round(max(0.0, min(1.0, base * freshness * self.state.kind_weight.get(c.kind, 1.0))), 3)

    def _coverage(self, res: RetrievalResult, mem_state: str) -> dict:
        missing = sorted(v for v, st in self.fleet_vaults.items() if str(st).upper() != "GREEN")
        not_consulted = list(res.lanes_skipped)
        if res.error:
            state = "UNAVAILABLE"
        elif mem_state in ("pending", "stale") or res.degraded or not res.complete or missing or not_consulted:
            state = "DEGRADED"
        else:
            state = "GREEN"
        notes = {"pending": "memory retrieval in flight; no memory yet, cue is context-only",
                 "stale": "showing memory from an earlier topic while a refresh is in flight",
                 "none": "no memory retrieved"}
        if not_consulted and mem_state in ("fresh", "stale"):
            notes = {**notes, mem_state: "fast local index only; peer vaults and remote lanes were not consulted"}
        refresh_err = (self._ret_error.error if self._ret_error is not None and mem_state in ("stale", "fresh")
                       else None)
        note = notes.get(mem_state) if state != "GREEN" and mem_state in notes else (
            "absence in these results is NOT evidence of absence in the substrate"
            if state != "GREEN" else "reachable vaults answered")
        return {"state": state, "complete": res.complete and not missing and not not_consulted
                and mem_state == "fresh", "missing_vaults": missing, "lanes_not_consulted": not_consulted,
                "memory": mem_state, "lane_timings": res.lanes, "retrieval_error": res.error,
                "refresh_error": refresh_err, "note": note}

    def on_utterance(self, text: str, escalate: bool = False) -> dict:
        t_turn = time.perf_counter()
        self.turn += 1
        self.state.add(text)
        outcome = self._observe(text)
        terms = self.state.top_terms(6)

        mem_terms = self.state.top_terms(8, self.cfg.memory_decay)
        res, mem_state, ret_wait = self._retrieve(mem_terms, escalate)
        cands, gen_wait, gen_mode = self._candidates(res.hits, terms)
        for c in cands:
            c.score = self._score(c, terms, text, res.hits)
        cands.sort(key=lambda c: c.score, reverse=True)

        cov = self._coverage(res, mem_state)
        best = cands[0] if cands else None
        if best is not None:
            if best.shards:
                conf = "high" if cov["state"] == "GREEN" and best.unsupported == 0 else "medium"
                mode = "memory"
            else:
                conf = "medium" if gen_mode == "llm" and best.unsupported == 0 else "low"
                mode = "context_only"
            if res.error or (not res.hits and gen_mode != "llm"):
                conf = "low"
            self.cue = Cue(text=best.text, why_now=best.why or f"follows topic: {' '.join(terms[:3])}",
                           shards=best.shards, kind=best.kind, confidence=conf, mode=mode, issued_turn=self.turn)
            self.state.shown.append(set(_terms(best.text)))
            self._shown_counts[best.text.lower()] += 1
        else:
            self.cue = None

        self._last_topic = set(self.state.top_terms(5))
        total_ms = (time.perf_counter() - t_turn) * 1000
        out = {
            "session_id": self.session_id, "turn": self.turn, "topic_now": " ".join(terms[:3]),
            "transcript_tail": self.state.tail()[-240:],
            "candidate_prompts": [{"text": c.text, "score": c.score, "shards": c.shards, "kind": c.kind,
                                   "age_turns": self.turn - c.turn} for c in cands[:self.cfg.n_candidates]],
            "display_prompt": ({"text": self.cue.text, "why_now": self.cue.why_now, "shards": self.cue.shards,
                                "kind": self.cue.kind, "confidence": self.cue.confidence, "mode": self.cue.mode,
                                "age_turns": self.turn - best.turn}
                               if self.cue else None),
            "previous_cue_outcome": outcome, "coverage": cov,
            "latency_ms": round(total_ms, 1),
            "timings_ms": {"retrieval_wait": round(ret_wait, 1), "generation_wait": round(gen_wait, 1),
                           "retrieval_call": round(self._last_call_ms["retrieval"], 1),
                           "generation_call": round(self._last_call_ms["generation"], 1)},
            "retrieval": {"hits": len(res.hits), "memory": mem_state, "fuzzy": res.fuzzy,
                          "refs": [h.ref for h in res.hits]},
            "generator": gen_mode,
        }
        if self.trace_path:
            with open(self.trace_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(out, ensure_ascii=False) + "\n")
        return out

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


# --------------------------------------------------------------------------------------- rendering


def render_cue(out: dict, width: int = 72) -> str:
    """ASCII teleprompter frame: one big cue, why-now, coverage badge. Nothing else competes for the eye."""
    cov = out["coverage"]["state"]
    badge = {"GREEN": "[MEMORY OK]", "DEGRADED": "[DEGRADED]", "UNAVAILABLE": "[NO MEMORY]"}.get(cov, "[?]")
    dp = out.get("display_prompt")
    bar = "=" * width
    if not dp:
        return f"{bar}\n  (no cue)  {badge}\n{bar}"
    src = "memory " + ", ".join(dp["shards"][:2]) if dp["shards"] else "context only (no memory cited)"
    miss = out["coverage"]["missing_vaults"]
    extra = f" missing: {','.join(miss)}" if miss else ""
    return (f"{bar}\n  NEXT >  {dp['text']}\n{bar}\n  why now: {dp['why_now']}\n"
            f"  {badge} conf={dp['confidence']} | {src}{extra} | {out['latency_ms']:.0f} ms")


__all__ = ["QConfig", "QLive", "GatewayRetriever", "OllamaCandidateGenerator", "Hit", "RetrievalResult",
           "Candidate", "Cue", "pick_model", "validate_candidates", "heuristic_candidates", "render_cue",
           "asdict"]
