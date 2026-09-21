#!/usr/bin/env python
"""Run a paced simulated speaking session through NouGen Q Live Prompt Loop v1 and write proof artifacts.

The SPEAKER lines below are a fixed stand-in for a live human; Q never sees a line before it is "spoken",
and the cues are entirely Q's own (retrieval + model + ranking). Real gateway, real local model.

  python tools/q_live_sim.py --out DIR [--pace 7.5] [--limit N] [--fleet blade=GREEN,phoebus=GREEN,whoart=UNCONFIGURED]

Outputs in DIR: trace.jsonl (every turn), summary.json (latency distribution, coverage, outcomes),
replay.html (rendered teleprompter frames), receipt.txt (plain-text proof). Keep DIR OUT of any public repo:
the trace quotes short snippets of whatever memory was retrieved.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from nougen_shards import q_live  # noqa: E402

# A ~5 minute unscripted-style monologue: topic drifts, a tangent, an audience question, a correction,
# a callback to something said earlier, and a close. ~19 words per turn at a natural pace.
SPEAKER = [
    "So the reason I even started building NouGen is pretty simple, my AI kept forgetting what we were working on.",
    "Every new chat felt like meeting a stranger who had to be briefed from scratch about the whole project.",
    "And I thought, memory should not live inside one conversation, it should live somewhere that outlasts every session.",
    "That is what the shards are, small pieces of memory that any of my AI lanes can read and write.",
    "Each shard has a title, a body, tags, and a record of where it came from so nothing is a mystery.",
    "Now the interesting part is the gateway, because all of those lanes talk to memory through one front door.",
    "The gateway handles who is asking, where the question gets routed, and how much of the memory we can actually reach.",
    "And honestly the biggest lesson this week was about search speed, it was taking about twenty seconds on some queries.",
    "The cause was a fuzzy scan that ran whenever a search found nothing, grinding through thousands of rows in Python.",
    "We added a switch to turn that scan off for anything that needs an answer fast, and it dropped to a few seconds.",
    "That matters a lot for something live, because nobody can wait twenty seconds for a memory while they are talking.",
    "Okay, tangent, this connects to my photography work too, because I shoot weddings and events for Who Visions.",
    "When I deliver an album, I want to remember what the couple loved, the little stories, the lens I used for the first dance.",
    "Nobody keeps that in their head across dozens of clients, so memory that follows me around is a real advantage.",
    "Someone asked me earlier, how do you stop the AI from just making up memories it does not have?",
    "Good question, the rule is it can only cite a memory that was actually returned, otherwise it has to say it has nothing.",
    "And if part of the system is offline, it has to tell you that, instead of pretending it searched everything.",
    "Actually, no, let me correct that, it does not store everything I say, it stores what I decide is worth keeping.",
    "That distinction matters for privacy, because a memory system that records everything is a liability, not an asset.",
    "So we keep the live conversation separate from the durable memory, one is the moment, the other is the record.",
    "Which brings me to the thing I am most excited about, a teleprompter that writes itself while I am speaking.",
    "Imagine going live with no script, and a screen that quietly shows the next useful thing you could say.",
    "It listens to what I am actually saying, pulls the relevant memory, and suggests the next line just ahead of me.",
    "If I use the line, great, if I ignore it or go somewhere else, it drops it and adapts to where I went.",
    "That is the difference between a script and a partner, a script keeps talking, a partner keeps listening.",
    "Back to the memory point for a second, this is why continuity matters so much for anything long running.",
    "Projects that take months only work if the context survives the gaps, the busy weeks, the switching between tools.",
    "And that is really the whole story of NouGen, it exists because I got tired of starting over every single time.",
    "So what do I want people to take away from this, honestly, that memory is infrastructure, not a feature.",
    "Once your tools remember what matters, you stop spending your energy re-explaining and start actually building.",
    "The other thing I would say is be honest about what your system knows, because trust comes from admitting the gaps.",
    "When it does not have an answer it says so, and that honesty is what makes the times it does answer believable.",
    "I think that is where all of this is heading, tools that keep continuity and tell you the truth about their limits.",
    "Anyway, that is the arc, from a forgetful assistant to a memory layer that follows the work around.",
    "If you take one thing home, let it be this, write down what matters and build systems that keep it for you.",
    "Thanks for hanging out, I will share more as this teleprompter idea turns from a prototype into something real.",
    "And if you have questions about the memory, the gateway, or the photography side, drop them in the chat.",
    "I read those and they end up shaping what I build next, so keep them coming.",
    "Alright, that is the show, thanks everybody for spending the time with me tonight.",
]


def pct(vals, p):
    s = sorted(vals)
    return round(s[min(len(s) - 1, max(0, int(round(p / 100 * len(s))) - 1))], 1) if s else None


def dist(vals):
    return {"n": len(vals), "p50": pct(vals, 50), "p95": pct(vals, 95), "max": round(max(vals), 1) if vals else None,
            "mean": round(sum(vals) / len(vals), 1) if vals else None}


def html_replay(rows, fleet):
    cards = []
    for r in rows:
        dp, cov = r["display_prompt"], r["coverage"]
        cue = html.escape(dp["text"]) if dp else "(no cue)"
        src = html.escape(", ".join(dp["shards"])) if dp and dp["shards"] else "context only (no memory cited)"
        cards.append(
            f'<section><p class="said"><b>#{r["turn"]} said:</b> {html.escape(r["said"])}</p>'
            f'<p class="cue">NEXT &gt; {cue}</p><p class="meta">{html.escape(dp["why_now"]) if dp else ""}</p>'
            f'<p class="meta badge {cov["state"]}">{cov["state"]} | conf={dp["confidence"] if dp else "-"} | {src} '
            f'| prev cue: {r["previous_cue_outcome"] or "-"} | {r["latency_ms"]:.0f} ms</p></section>')
    css = ("body{background:#0b0d10;color:#e8e8e8;font:18px/1.4 system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px}"
           "section{border-left:4px solid #2c3540;margin:14px 0;padding:6px 14px}.said{color:#8b98a5;font-size:15px}"
           ".cue{font-size:30px;font-weight:600;color:#fff;margin:6px 0}.meta{font-size:14px;color:#9aa7b3;margin:2px 0}"
           ".GREEN{color:#5fd38d}.DEGRADED{color:#f0c14b}.UNAVAILABLE{color:#ff6b6b}h1{font-size:22px}")
    return (f'<!doctype html><meta charset="utf-8"><title>NouGen Q replay</title><style>{css}</style>'
            f"<h1>NouGen Q Live Prompt Loop v1: session replay</h1>"
            f'<p class="meta">Fleet vaults at start: {html.escape(json.dumps(fleet))}. Speaker lines are simulated; cues are Q\'s own.</p>'
            + "".join(cards))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pace", type=float, default=float(os.environ.get("Q_LIVE_SIM_PACE_S", "7.5")),
                    help="seconds between spoken lines (real-time pacing)")
    ap.add_argument("--limit", type=int, default=len(SPEAKER))
    ap.add_argument("--adopt-every", type=int, default=6,
                    help="every Nth line the simulated speaker glances at the displayed cue and reads it aloud first "
                         "(0 = never). Exercises the 'used' path; the cue is Q's own, never scripted.")
    ap.add_argument("--fleet", default="", help="vault=STATE,... at session start (from NouGen Context Mode hydration)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    fleet = dict(kv.split("=", 1) for kv in a.fleet.split(",") if "=" in kv)
    trace = os.path.join(a.out, "trace.jsonl")
    if os.path.exists(trace):
        os.remove(trace)

    cfg = q_live.QConfig.from_env()
    gen = q_live.OllamaCandidateGenerator(cfg)
    print(f"warming {gen.model} ...", flush=True)
    print(f"model warm in {gen.warm():.0f} ms", flush=True)   # a cold load is 15-35s; do it before the show
    ql = q_live.QLive(generator=gen, cfg=cfg, fleet_vaults=fleet, trace_path=trace)
    print(f"session {ql.session_id} model={gen.model} pace={a.pace}s lines={min(a.limit, len(SPEAKER))} fleet={fleet}")

    rows, t_start = [], time.monotonic()
    for i, line in enumerate(SPEAKER[:a.limit]):
        t0 = time.monotonic()
        prev_dp = rows[-1]["display_prompt"] if rows else None
        adopted = bool(a.adopt_every and i and i % a.adopt_every == 0 and prev_dp)
        spoken = f"{prev_dp['text']} {line}" if adopted else line
        out = ql.on_utterance(spoken)
        out["said"] = spoken
        out["adopted_cue"] = adopted
        rows.append(out)
        print(f"[{time.monotonic() - t_start:6.1f}s] turn {out['turn']:>2} {out['latency_ms']:7.0f} ms "
              f"wait[r={out['timings_ms']['retrieval_wait']:5.0f} g={out['timings_ms']['generation_wait']:5.0f}] "
              f"call[r={out['timings_ms']['retrieval_call']:5.0f} g={out['timings_ms']['generation_call']:5.0f}] "
              f"mem={out['retrieval']['memory']:<7} "
              f"{out['coverage']['state']:<10} {out['generator']:<9} prev={out['previous_cue_outcome'] or '-':<12} "
              f"cue: {(out['display_prompt'] or {}).get('text', '(none)')[:70]}", flush=True)
        time.sleep(max(0.0, a.pace - (time.monotonic() - t0)))
    ql.close()

    lat = [r["latency_ms"] for r in rows]
    cues = [r["display_prompt"] for r in rows if r["display_prompt"]]
    summary = {
        "session_id": ql.session_id, "model": gen.model, "gateway": cfg.gateway_origin, "pace_s": a.pace,
        "wall_clock_s": round(time.monotonic() - t_start, 1), "turns": len(rows), "fleet_at_start": fleet,
        "cue_latency_ms": dist(lat),
        "retrieval_wait_ms": dist([r["timings_ms"]["retrieval_wait"] for r in rows]),
        "generation_wait_ms": dist([r["timings_ms"]["generation_wait"] for r in rows]),
        "retrieval_call_ms_background": dist([r["timings_ms"]["retrieval_call"] for r in rows if r["timings_ms"]["retrieval_call"]]),
        "generation_call_ms_background": dist([r["timings_ms"]["generation_call"] for r in rows if r["timings_ms"]["generation_call"]]),
        "memory_states": dict(Counter(r["retrieval"]["memory"] for r in rows)),
        "carried_cues": sum(1 for r in rows if r["display_prompt"] and r["display_prompt"]["age_turns"] >= 1),
        "fuzzy_scans_used": sum(1 for r in rows if r["retrieval"]["fuzzy"]),
        "coverage_states": dict(Counter(r["coverage"]["state"] for r in rows)),
        "cue_modes": dict(Counter(c["mode"] for c in cues)), "confidence": dict(Counter(c["confidence"] for c in cues)),
        "generators": dict(Counter(r["generator"] for r in rows)),
        "previous_cue_outcomes": dict(Counter(r["previous_cue_outcome"] or "pending_or_first" for r in rows)),
        "cues_with_shard_refs": sum(1 for c in cues if c["shards"]),
        "cues_total": len(cues),
        "every_cue_traceable": all(set(r["display_prompt"]["shards"]) <= set(r["retrieval"]["refs"])
                                   for r in rows if r["display_prompt"]),
        "turns_within_pace": sum(1 for x in lat if x <= a.pace * 1000),
        "distinct_cues": len({c["text"] for c in cues}),
        "adopted_turns": sum(1 for r in rows if r.get("adopted_cue")),
        "adopted_turns_scored_used": sum(1 for r in rows if r.get("adopted_cue") and r["previous_cue_outcome"] == "used"),
        "lanes_not_consulted": sorted({x for r in rows for x in r["coverage"].get("lanes_not_consulted", [])}),
        "refresh_errors": sum(1 for r in rows if r["coverage"].get("refresh_error")),
    }
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    with open(os.path.join(a.out, "replay.html"), "w", encoding="utf-8") as fh:
        fh.write(html_replay(rows, fleet))
    with open(os.path.join(a.out, "receipt.txt"), "w", encoding="utf-8") as fh:
        for r in rows[:: max(1, len(rows) // 8)]:
            fh.write(f"--- turn {r['turn']} said: {r['said']}\n{q_live.render_cue(r)}\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
