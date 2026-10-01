"""U-Fuzz/FAME-style memory validation: query mutation, memory-state mutation, counterfactuals.

Leg 20261001T210010Z item 5. Black-box and deterministic: it needs only a retriever
``retrieve(query, memory, k) -> list[id]`` over ``memory = [{"id": str, "text": str}, ...]``.
Not wired into live paths; it is a verification harness a caller points at one.

Cases and what each EXPECTS of a correct retriever
--------------------------------------------------
query mutation
  case, whitespace   semantics-preserving   -> result set invariant     (expect "invariant")
  drop_token, swap_adjacent, append_noise
                     perturbing             -> bounded change only      (expect "bounded")
memory-state mutation
  shuffle            order is not content   -> result set invariant     (expect "invariant")
  drop_irrelevant    remove items outside top-k -> result invariant     (expect "invariant")
  duplicate          repeat the top item    -> no id returned twice     (expect "no_dupes")
counterfactual belief/output divergence
  drop_top           remove the top-1 item  -> it must vanish, result changes (expect "must_exclude")

divergence(a, b) = 1 - |A ∩ B| / |A ∪ B| over the top-k id sets (0 identical, 1 disjoint).
Every report carries the seed and a digest of (query, memory), so a failure replays exactly.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any, Callable, Dict, List, Mapping, Sequence

Memory = Sequence[Mapping[str, str]]
Retrieve = Callable[[str, Memory, int], List[str]]
VERSION = "memfuzz-0.1.0"
BOUNDED_MAX_DIVERGENCE = 0.75   # uncalibrated default for "bounded" perturbations
_NOISE = ("please", "the", "kindly")


def divergence(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    return 0.0 if not (sa | sb) else 1.0 - len(sa & sb) / len(sa | sb)


def mutate_query(query: str, kind: str, seed: int) -> str:
    rng, toks = random.Random(f"{seed}:{kind}"), query.split()
    if kind == "case":
        return query.swapcase()
    if kind == "whitespace":
        return "  " + "   ".join(toks) + "  "
    if kind == "drop_token":
        if len(toks) < 2:
            return query
        del toks[rng.randrange(len(toks))]
        return " ".join(toks)
    if kind == "swap_adjacent":
        if len(toks) < 2:
            return query
        i = rng.randrange(len(toks) - 1)
        toks[i], toks[i + 1] = toks[i + 1], toks[i]
        return " ".join(toks)
    if kind == "append_noise":
        return query + " " + rng.choice(_NOISE)
    raise ValueError(f"unknown query mutation {kind!r}")


def mutate_memory(memory: Memory, kind: str, seed: int, protect: Sequence[str] = ()) -> List[Dict[str, str]]:
    rng, items = random.Random(f"{seed}:{kind}"), [dict(m) for m in memory]
    if kind == "shuffle":
        rng.shuffle(items)
        return items
    if kind == "drop_irrelevant":
        return [m for m in items if m["id"] in protect]
    if kind == "duplicate":
        top = next((m for m in items if m["id"] in protect), None)
        return items + ([dict(top)] if top else [])
    if kind == "drop_top":
        return [m for m in items if m["id"] not in protect]
    raise ValueError(f"unknown memory mutation {kind!r}")


def _digest(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def run_fuzz(retrieve: Retrieve, query: str, memory: Memory, k: int = 3, seed: int = 0) -> Dict[str, Any]:
    base = retrieve(query, memory, k)
    cases: List[Dict[str, Any]] = []

    def add(name: str, expect: str, got: List[str], ok: bool) -> None:
        cases.append({"case": name, "expect": expect, "divergence": divergence(base, got), "ok": ok})

    for kind, expect in (("case", "invariant"), ("whitespace", "invariant"), ("drop_token", "bounded"),
                         ("swap_adjacent", "bounded"), ("append_noise", "bounded")):
        got = retrieve(mutate_query(query, kind, seed), memory, k)
        d = divergence(base, got)
        add(f"query:{kind}", expect, got, d == 0 if expect == "invariant" else d <= BOUNDED_MAX_DIVERGENCE)
    for kind in ("shuffle", "drop_irrelevant"):
        got = retrieve(query, mutate_memory(memory, kind, seed, protect=base), k)
        add(f"memory:{kind}", "invariant", got, set(got) == set(base))
    dup = retrieve(query, mutate_memory(memory, "duplicate", seed, protect=base[:1]), k)
    add("memory:duplicate", "no_dupes", dup, len(dup) == len(set(dup)))
    top = base[:1]
    cf = retrieve(query, mutate_memory(memory, "drop_top", seed, protect=top), k)
    add("counterfactual:drop_top", "must_exclude", cf, bool(top) and top[0] not in cf and set(cf) != set(base))
    return {"version": VERSION, "seed": seed, "k": k, "digest": _digest(query, list(memory)),
            "baseline": base, "cases": cases, "failures": [c["case"] for c in cases if not c["ok"]]}


# Reference retriever (lexical overlap) so the harness can be exercised and calibrated against.
def overlap_retrieve(query: str, memory: Memory, k: int) -> List[str]:
    q = set(re.findall(r"[a-z0-9]+", query.lower()))
    seen, scored = set(), []
    for m in memory:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        score = len(q & set(re.findall(r"[a-z0-9]+", m["text"].lower())))
        if score:
            scored.append((-score, m["id"]))
    return [i for _, i in sorted(scored)[:k]]
