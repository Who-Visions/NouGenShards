# ITERATE — <target>

**Vision (GM):** <one line: who this is for and what "done" feels like>
**Caps:** max rounds <N> · max cost $<X> · plateau = 3 rounds with no gain

## Rubric (0-5 each, judged by a different rung than the maker)
| criterion | what a 5 looks like | baseline |
|---|---|---|
| clarity | a user finds the primary action in under 5 s | |
| primary flow works | the core task completes with no dead ends | |
| visual craft | consistent type, spacing, and contrast | |
| restraint | nothing a user would not miss | |

## Do not change
- <brand, critical flows, URLs, data contracts>

## Regression gate
- tests: `<command>`
- smoke: <every feature that worked at baseline: load, primary flow, toggles>

## Round log
| round | change | ref source | score before -> after | tests | lines +/- | kept/reverted |
|---|---|---|---|---|---|---|
