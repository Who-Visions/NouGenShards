---
name: nougen-iterate
description: Discipline for repeated "make it better" / autonomous improvement loops on a site, UI, skill, prompt, or pipeline. Requires a GM vision and rubric, research each round, a regression gate, the option to ship nothing or remove things, a plateau stop, and cheap-rung iteration with expensive-rung judging. Use when asked to iterate, polish, improve repeatedly, run N rounds, or sweep sections (e.g. NouGenFlix F-sweeps). Not for shipping a single change (use nougen-loop).
---

# nougen iterate

Evidence (YouTube DByAR5Su1Yw, 2026): "make it better" was sent 100 times to Sonnet 5.5 and Opus 5.5 in a clean room. Real milestones landed by about round 32. After that the models mostly added code: Sonnet grew to about 3k lines, Opus to about 21k. Opus cost $137 over 8.5 hours, about six times Sonnet, and broke its own features (a dead language toggle, a dead section, buggy widgets). It also buried the UX in upsells. Neither model searched the web for inspiration. The root cause was "you must ship a change every time": a loop with no vision turns into adding things.

## Contract (every loop, every round)

1. **Vision + rubric first.** Before round 1, write `ITERATE.md` in the target: goal, audience, 3-6 scored criteria (0-5), and things that must not change. The GM supplies the taste. If no vision is given, draft one in a single line and state it. Never iterate toward a bare "better".
2. **Research step.** Each round looks at at least one outside reference first (award-winning sites, component libraries, competitor pages) via `nougen-web-research` or Exa. Record the source in the round log.
3. **One change, measured.** Make one coherent change, then re-score it against the rubric. A judge on a different rung than the maker does the scoring.
4. **Regression gate.** Run the project's tests plus a smoke check of every feature that worked before (load, primary flow, any toggles). If anything goes red, revert the round. A feature that silently stops working is a failure, not a trade-off.
5. **Null and subtractive rounds are valid.** A round may ship nothing, or delete code, if that keeps or raises the score. Track the line count and flag growth that brings no score gain.
6. **Plateau stop.** Stop after 3 consecutive rounds with no rubric gain, or once the round or cost cap is hit. Report the best-scoring round, not the last one.
7. **Rung split.** Iterate on the cheap rung (custom e2b/e4b, then Sonnet-class) and judge on the expensive rung only (see `smart-ladder`). Cost tracks code volume, not quality.

## Round log (append to ITERATE.md)

`| round | change | ref source | score before -> after | tests | lines +/- | kept/reverted |`

## Done

Report the best round, its score, total rounds, the stop reason, test evidence, and cost. Capture a shard tagged `nougen-iterate`.
