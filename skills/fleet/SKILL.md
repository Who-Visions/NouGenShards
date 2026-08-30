---
name: fleet
description: Use whenever the operator says "fleet", "workers", "agents", "swarm", "fan out", "in parallel", "consensus", or asks for many models to work at once — dispatching prompts across many routes concurrently, health-checking the route registry, getting independent opinions from decorrelated models, or diagnosing a route that returns empty content or reads as down. Covers Rule 0.5.1, the existing Fleet dispatcher at NouGen/tools/fleet.py, the max_tokens starvation trap, and the DHCP host rules. Does not cover routing a single drafting task to the local model — that is e2b.
---

# Fleet — plural, always

**"Fleet", "workers", "agents" and "swarm" always mean many routes in
parallel.** Dispatching a single worker when the operator said "fleet" is a rule
violation, not a shortcut. The operator runs 14+ email accounts across providers
precisely so work can be parallelised — roughly 8 OpenRouter accounts, 13 Ollama
Cloud, 9 HF Spaces, 3 Arli AI, plus local Ollama and LM Studio. Use them.

## Do not rebuild the dispatcher

It already exists at `~\Outpost\NouGen\tools\fleet.py`. It loads
and priority-ranks every OpenAI-compatible route in the registry
(`~\.gemini\antigravity-ide\mcp_config.json`).

```python
import os, sys; sys.path.insert(0, os.path.expanduser(r"~\Outpost\NouGen\tools"))
from fleet import Fleet

f = Fleet()                              # loads + ranks all routes
f.probe()                                # parallel health check, fills f.healthy
out = f.map(prompts, max_tokens=2048)    # fan N prompts across ALL healthy routes
```

```bash
python "$HOME/Outpost/NouGen/tools/fleet.py" probe
```

| Call | Behaviour |
| --- | --- |
| `Fleet(config_path, include_local=True, include_vertex=None)` | Builds the route list, sorted by priority. |
| `probe(timeout=25, workers=16, verbose=True)` | Health-checks every route concurrently; populates `.healthy`. |
| `ask(prompt, **kw)` | One question, first healthy route by priority, falls through on failure. |
| `map(prompts, workers=None, retries=2, **kw)` | Fans prompts across all healthy routes; returns sorted `(index, route_name, output)`; rotates to another route on failure. |
| `diversify()` | Re-points OpenRouter keys at different vendors' models. |
| `by_vendor()` | Groups healthy routes by distinct model, for real consensus sampling. |

## Priority (Rule 0.5)

Lower is tried first: `hf-space` 1, `openrouter` 2, `arliai` 3, `lmstudio` 4,
`local` 4, `ollama-cloud` 5, `vertex` 6.

**Vertex is billed** while every other lane is free-tier or local GPU, so it
never joins the fleet by accident. It requires `NOUGEN_VERTEX=1` or
`include_vertex=True`. Opt in deliberately or not at all.

## The max_tokens trap — the failure mode to know

`Fleet._call` defaults to **`max_tokens=800`**, which is *below* the ~1400 floor
that Gemma E-series and other reasoning models need. Those models spend a hidden
reasoning budget before emitting any visible content, so when starved they
return **empty content at HTTP 200 with no error raised**. Nothing looks broken;
you just get nothing.

- Pass `max_tokens=2048` for E-series, JSON, verbose or enumeration prompts.
- A route may declare its own floor via a `min_tokens` key, which `_call` honours.
- This is also why `probe()` uses `max_tokens=128` rather than 8 — at 8,
  reasoning models probe as dead.

Empty output is a budget symptom first. Check that before concluding a route is down.

## 429 is about the model, not the account

A 429 is a statement about one **model's** shared upstream pool, not about the
**account**. `probe()` retries once on a decorrelated fallback model before
condemning a route.

Concretely: on 2026-08-29 all 8 OpenRouter routes were configured to probe
`google/gemma-4-31b-it:free`, which sits behind a saturated Google AI Studio
pool — so every account read "down" while the same keys answered fine on
nemotron. One saturated model must not mark a whole account dead.

## Account diversity is not model diversity

Eight accounts all pointed at one model is account diversity. Consensus over it
just reproduces that one family's blind spots. `diversify()` pairs each
OpenRouter key with a *different vendor's* free model; `by_vendor()` groups
healthy routes by distinct model so a consensus sample is genuinely independent.
For any "get several opinions" task, sample across vendors, not across keys.

## Hosts are mDNS names, never literal IPs

Fleet boxes run on DHCP, so a literal address is a route that works until the
next lease and then fails as "host down". Use the names, overridable by env:

- `NOUGEN_BLADE_HOST` — default `blade1tb.local`
- `NOUGEN_WHOART_HOST` — default `whoart.local`

**A route named for a machine must address that machine.** Defaulting the whoart
route to `localhost` meant that whenever Fleet dispatched from any other box,
the "whoart" lane loaded a ~7 GB gemma4 onto *that* box instead. On phoebus
(16 GB, CPU-only) it evicted the `kaedracode:e2b` model the Kaedra gateway pins
with `keep_alive=-1`, so the pin looked broken while whoart's own Ollama — which
actually holds `gemma4:e2b-qat` — sat idle.

Every route is an OpenAI-compatible `/v1/chat/completions` endpoint with a
bearer token in `headers.Authorization`. Never use raw `/api/generate`.

## Before and after

Parallel lanes collide. Claim scope on the [[relay]] before you fan out, and
file a leg when you land. Durable findings go to [[shards-memory]]. For a single
drafting or summarization task, this is the wrong tool — use [[e2b]].
