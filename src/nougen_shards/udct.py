"""Universal Dynamic Composition Template (UDCT).

Value-driven, not phrase-driven: no module stores a sentence. Each of the five
modules is a semantic responsibility that an injected generator fills from
runtime values. Same runtime (incl. seed + model_version) + same generator
=> same validated output, fingerprinted with SHA-256.

    Values -> M1..M5 -> validate -> timeline -> (speech/animation) -> shard/relay

Used first by NOU (nougenai-next ai_news); meant for every agent voice.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Protocol

MODULES = ("identity", "situation", "intent", "expression", "handoff")
WPS = 2.6  # spoken words per second, for duration estimates
N = 5      # shingle size for cross-history repeat checks
OPENER = 3


@dataclass
class Runtime:
    identity: dict
    context: dict
    audience: dict = field(default_factory=dict)
    policy: dict = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    seed: int = 0
    model_version: str = "unset"


@dataclass
class Part:
    module: str
    kind: str = "words"  # words | gesture | silence | transition
    text: str = ""
    seconds: float = 0.0


class Generator(Protocol):
    def __call__(self, module: str, runtime: Runtime, prior: list[Part],
                 attempt: int, feedback: list[str]) -> Part: ...


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s]+", " ", s.casefold()).split())


def _shingles(s: str) -> set[str]:
    w = _norm(s).split()
    return {" ".join(w[i:i + N]) for i in range(len(w) - N + 1)}


def _opener(s: str) -> str:
    return " ".join(_norm(s).split()[:OPENER])


def _seconds(p: Part) -> float:
    return p.seconds or (len(p.text.split()) / WPS if p.kind == "words" else 0.0)


def validate(parts: list[Part], runtime: Runtime) -> list[str]:
    """Policy + uniqueness checks. Returns errors; empty means valid."""
    errs: list[str] = []
    pol = runtime.policy
    if tuple(p.module for p in parts) != MODULES:
        errs.append("bad module sequence")
    spoken = [_norm(p.text) for p in parts if p.kind == "words" and p.text.strip()]
    if len(spoken) != len(set(spoken)):
        errs.append("repeated module dialogue")
    text = " ".join(p.text for p in parts if p.kind == "words")
    low = _norm(text)
    for ph in pol.get("prohibited", []):
        if _norm(ph) and _norm(ph) in low:
            errs.append(f"prohibited: {ph}")
    keep = {_norm(k) for k in pol.get("keep", [])}  # brand lines exempt
    hist = [h for h in runtime.history if _norm(h) not in keep]
    if _norm(text) in {_norm(h) for h in hist}:
        errs.append("exact repeat of history")
    exempt = set().union(set(), *(_shingles(k) for k in keep))
    seen = set().union(set(), *(_shingles(h) for h in hist))
    dup = (_shingles(text) & seen) - exempt
    if dup:
        errs.append(f"repeats phrase: {sorted(dup)[0]}")
    branded = any(k.startswith(_opener(text)) or low.startswith(k) for k in keep if k)
    if text and not branded and _opener(text) in {_opener(h) for h in hist}:
        errs.append(f"repeats opener: {_opener(text)}")
    total = sum(_seconds(p) for p in parts)
    if (mx := pol.get("max_seconds")) and total > mx:
        errs.append(f"too long: {total:.1f}s > {mx}s")
    if not any(p.kind == "words" and p.text.strip() for p in parts):
        errs.append("no words")
    return errs


def timeline(parts: list[Part]) -> list[dict]:
    t, out = 0.0, []
    for p in parts:
        d = round(_seconds(p), 2)
        out.append({"module": p.module, "kind": p.kind, "text": p.text,
                    "start": round(t, 2), "end": round(t + d, 2)})
        t += d
    return out


def fingerprint(runtime: Runtime, parts: list[Part]) -> str:
    blob = json.dumps({"rt": asdict(runtime), "parts": [asdict(p) for p in parts]},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def compose(runtime: Runtime, generator: Generator | Callable, retries: int = 2) -> dict:
    """Run M1..M5 through the generator, validate, retry with feedback."""
    feedback: list[str] = []
    for attempt in range(retries + 1):
        parts: list[Part] = []
        for m in MODULES:
            parts.append(generator(m, runtime, list(parts), attempt, feedback))
        errs = validate(parts, runtime)
        if not errs:
            break
        feedback = errs
    return {"ok": not errs, "errors": errs, "attempts": attempt + 1,
            "text": " ".join(p.text for p in parts if p.kind == "words" and p.text),
            "timeline": timeline(parts),
            "seconds": round(sum(_seconds(p) for p in parts), 2),
            "seed": runtime.seed, "model_version": runtime.model_version,
            "hash": fingerprint(runtime, parts)}
