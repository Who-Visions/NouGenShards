# AI-unlock video morph: tube:h5zkzon0gM4

Source: [The AI unlock has begun](https://youtu.be/h5zkzon0gM4), AI Search, published 2026-10-06, 14m29s. Ingested verbatim by nougentube as shard **#33310** (`tube:h5zkzon0gM4`, db9), era-stamped at the video's true publish date. Captions via youtube-transcript-api; third-party content preserved verbatim, not re-summarised.

## What the video claims

The video asserts that frontier models now reverse-engineer software and game binaries at "over 99% success after four attempts" on a benchmark, and walks through three ways people mash up games: a **pass-through bridge** (keep both engines, AI builds a translation layer between them — "the most limited option", like duct tape), a **full rebuild** in a new engine (most control, most cost), and **porting one mechanic** into another game ("done in around a day"). It names tools (Ghidra/IDA MCPs, ILSpy, "Universal Modder", "reverse engineer anything") and stresses "there are no magic prompts" — plain intent plus linked skills does the work. It is a claims-and-demos video, not a methods paper; no implementation or measurement is shown.

These are **the video's claims**, not fleet-verified facts. The pass@k figure is quoted once with its k ("after four attempts") and again without it.

## Candidates and gate results

Scored through `NouGenMorphEngine` (threshold 0.50). All six **held** — correctly: the donor is assertion-level evidence (ceiling 0.3–0.6) with no mechanism to reproduce.

| Candidate | Score | Note |
|---|---|---|
| ownership-and-licence-boundary | 0.456 | closest; the licence line is the real transferable rule |
| pass-at-k-claim-hygiene | 0.309 | a pass@k number keeps its k or is tagged unverified |
| behavior-over-implementation | 0.285 | already the D-step of NouGenMorph |
| tools-over-magic-prompts | 0.154 | invest in the toolset, keep prompts short |
| absorption-ladder | 0.142 | bridge vs rebuild vs mechanic-port, by cost |
| translation-bridge-adapter | 0.030 | event-verb mapping table per surface pair |

## What's worth keeping

Two ideas are worth carrying, both as discipline rather than capability:

1. **pass@k claim hygiene** — a success-rate figure travels with its attempt count and benchmark name, or it is downgraded to unverified. The video itself drops the "after four attempts" qualifier within one video; the fleet should not. Target: `morph_gate` / shard hygiene.
2. **ownership-and-licence boundary** — the dividing line between legitimate and abusive use of any "reverse anything" capability is entitlement to the subject. This reinforces the same rule derived from [morluto/rea](rea-morph.md): the fleet studies open, owned, or observed-behaviour donors, and quarantines proprietary or decompiled third-party code at intake.

Full scored records alongside this file were produced by the scoring run. Nothing from this video is implemented; it is recorded so a future lane recalls it before re-morphing the same video (the exact failure nougentube exists to stop).
