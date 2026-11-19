# NouGenTube Morph: what the operator asked for

Source: the operator's own messages in the build session, 2026-11-10 to 2026-11-11. No issue tracker entry exists; this file is the spec the review checks against.

## Morph tab (asked 2026-11-10)

"Probably we should have a morph tab, and then it can cross-reference with the tenant's vault to see how the YouTube can morph the existing shards it can see into like code architecture or an app or a website or whatever it may be, you know, inherently reverse the intents of the YouTube."

- M1. A Morph tab beside Transcript, Summary, Chat, Highlights.
- M2. It cross-references the vault (NouGenShards) and uses what is already there.
- M3. Targets: code architecture, app, website, "whatever it may be" (open-ended).
- M4. It reverses the video's intent: from what was said to what it lets you build.
- M5. The sign-in / per-tenant vault is deferred ("we'll do the sign in later"), so the vault is whatever the local bridge can see.

## Reliability bar (asked 2026-11-10)

"It needs to work end to end flawlessly. Fail safe, fallbacks. We have a lot of lane routes, local and cloud."

- R1. Every step has a fallback; nothing dead-ends.
- R2. Any provider's key can be brought in (Claude, Gemini, OpenAI, DeepSeek, any).

## Latest web (asked 2026-11-11)

"Is there a free Google search api we can use to give it latest web search web fetch to cross reference"

"Edit code and use key ... use the api" (Context.dev key supplied). "Keymaker has keys you just didn't look right."

- W1. Morph cross-references the latest web: search plus fetching pages.
- W2. Context.dev is used as asked. Other keys the keymaker holds (Exa, Tavily, SerpAPI/Google) are used too.
- W3. Keys stay server-side on the bridge. No key in the browser, no key hardcoded, none printed.
- W4. Tests do not hit live APIs.

## Valerion 21 steps (asked 2026-11-11)

"Does morph respect valuations 21 steps? As well" (read as: Valerion / NouGenMorph's 21 steps of orchestration, `NouGen/docs/architecture.md`).

- V1. Morph applies the 21 steps, in order, by their documented names, across the five phases.
- V2. Output is checkable: a missing step is reported.

## Output quality (standing)

- Q1. Citations are verified in code: shards cited must have been returned by the vault, web tags must have been fetched, timestamps must be inside the video.
- Q2. A cut-off or partial plan is flagged, not presented as complete.
- Q3. Hosted app and repo text carries no personal name; refer to "the operator".
