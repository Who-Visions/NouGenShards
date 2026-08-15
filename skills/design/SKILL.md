---
name: design
description: Author, audit, and emit a design system as a portable DESIGN.md package (manifest.json + DESIGN.md + tokens.css). Use when building any UI, page, report, or visual artifact; when asked for a design system, theme, palette, or design tokens; or when auditing existing CSS for contrast, focus, and scale defects. Conforms to the open-design / Stitch DESIGN.md convention so packages are portable to other tools.
---

# Design

A design system is **two canons that must agree**: prose a human reads (`DESIGN.md`) and
values a machine applies (`tokens.css`). Most weak design skills ship only the first, so
the guidance drifts from the code within a week. This skill keeps both, and validates
that they still match.

## When this skill applies

Any UI, page, report, chart, or visual artifact. Also any request naming a design system,
theme, palette, brand, or tokens — and any audit of existing CSS.

**Resolve intent lazily.** Do not dump the whole system into context before you know what
is being built. Read this file, then open only the sections of the package you actually
need. A button needs the color and component sections; a chart needs the data-viz ramp.

## The package format

Emit a directory: `<slug>/manifest.json`, `<slug>/DESIGN.md`, `<slug>/tokens.css`.

This is the convergent format across the ecosystem (upstream: Google Stitch and
getdesign.md; anchor implementation: `nexu-io/open-design`, Apache-2.0). Conforming means
the package is portable to other tools rather than trapped in this repo.

`manifest.json` pins the schema:

```json
{
  "schemaVersion": "od-design-system-project/v1",
  "name": "<slug>",
  "version": "1.0.0",
  "description": "<one line>",
  "entry": { "prose": "DESIGN.md", "tokens": "tokens.css" },
  "surfaces": { "ground": "--your-bg-token", "ink": "--your-text-token" },
  "themes": ["light", "dark"]
}
```

`surfaces` names the page background and primary text tokens. The contrast gate
needs it because token naming is a brand decision - without it the gate falls
back to guessing common names and gives up on anything named differently.

`DESIGN.md` uses Stitch frontmatter (`version, name, description, colors, typography,
rounded, spacing, components`) over an ordered body. **The body needs at least 7 `##`
headings** — that is the actual machine check downstream validators run, and they check
the *count*, not the titles. The nine-section dialect below satisfies every consumer:

1. `## Overview` — what this system is for, one paragraph
2. `## Color` — the ramp, with role names not just hexes
3. `## Typography` — families, scale, weights, tracking, leading
4. `## Spacing` — the ramp and what unit it is expressed in
5. `## Radii` — named steps
6. `## Elevation` — shadow or glow tiers
7. `## Components` — per-component states, including focus
8. `## Motion` — durations, easings, reduced-motion policy
9. `## Accessibility` — the contrast floor and measured pairs

`tokens.css` carries the values. Downstream quality gates want **≥26 custom properties**,
which is a real floor — a system below it is under-specified, not minimal.

## Non-negotiable floors

These are gates, not preferences. Fail them and the package is not done.

**Every interactive element has a visible `:focus-visible` state.** This is the single most
common defect in real systems — they are hover-rich and keyboard-blind. Never write
`focus:outline-none` without replacing the ring in the same rule. Apply the ring through a
zero-specificity selector so every component inherits it:

```css
:where(a, button, input, select, textarea, [tabindex]):focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--surface), 0 0 0 4px var(--focus);
}
```

The double ring keeps a visible edge on both light and dark grounds. Do not build the ring
out of the border token — border tokens sit near 1.2:1 and are invisible to low-vision
users.

**Contrast is computed, not eyeballed.** Body text ≥4.5:1, large text and UI components
≥3:1. Compute the real pairs — text on each surface, and text on each *filled* control.
A brand color that passes as text on the page background routinely fails as a fill behind
light text; those are different measurements and both must be run.

**Both themes are designed, and colors are defined at token level only.** A color whose
only definition lives inside a `@media` or `[data-theme]` block never applies in the
unstamped default state, and the page renders one theme's text on the other theme's
ground. Define the complete palette on bare `:root`, then redefine only the tokens under
`@media (prefers-color-scheme: …)` and `:root[data-theme="…"]`. Always paint `body`
background from a token.

**Invert by rotation, not negation.** A dark ramp's deep accent becomes the light ramp's
mid accent; the mid becomes the light. Keeping the same hues in play preserves gradient
relationships across the switch. Naive inversion breaks them.

**Motion is gated.** Every animation sits behind `@media (prefers-reduced-motion: reduce)`.

**No magic values in shipped lines.** Anything environment-, path-, threshold-, or
model-shaped resolves from env → config → probe, with the constant as a logged fallback.
A bare hex in application code is a defect; it belongs in `tokens.css`.

## Data visualization

Categorical series need to separate by **lightness as well as hue** — that is what survives
color-blindness and greyscale print. Two rules:

- Anchor series 1 on the brand hue so charts read as native to the system.
- Do not walk the color wheel evenly. Even spacing crowds whatever hues the brand ramp
  already occupies. Space slots 80–100° apart and alternate contrast high/low.

Verify every series against the chart background at ≥3:1. **A dark-mode ramp will not
survive on a light ground** — light needs its own deepened set, computed separately.

## Writing the prose

`DESIGN.md` is read by people and by models. Both are ill-served by padding.

- Say what the rule is and why it exists. Skip the throat-clearing.
- Mark provenance per token: **observed** (measured from real code), **inferred**
  (derived from usage patterns), or **invented** (nothing in the source implies it).
  A reader who cannot tell which is which cannot trust any of it.
- Sentences over bullet stacks. No manufactured "not X, it's Y" contrasts, no bolded
  verdict openers, no emoji section markers.
- Structural devices encode something true. Numbered steps mean an actual sequence.

## Auditing an existing system

When pointed at existing CSS rather than a blank page, extract before you invent:

1. Read the token declarations. Those are the ground truth.
2. Scales usually are not declared — derive them from actual class usage frequency
   across components, then propose the smallest ramp covering ~85% of observed values.
3. Look for a constant in the CSS that corroborates the derived ramp. A grid size or
   fixed dimension landing exactly on a proposed step means the ramp is real, not fitted.
4. Grep for the failure signatures: `focus-visible` count, `focus:outline-none` count,
   `hover:` count. A system with many hovers and zero focus states is keyboard-blind.
5. Compute contrast on every real pair before proposing anything new.
6. Report what is observed, inferred, and invented separately.

## Quality gates

Run `python skills/design/validate.py <package-dir>`. It returns one of three
verdicts per gate — `passed`, `failed`, or `confirmation-required` — and exits non-zero
only on `failed`, so ambiguous cases surface for a human instead of blocking.

The floors quoted above are enforced as constants in `validate.py`. Nothing structural
ties prose to code, so `tests/test_skills.py` asserts they still agree - change one and
the suite fails.

## Installing into an agent harness

This directory is the canonical, version-controlled copy. Agent harnesses read skills
from their own private directory (`.agents/skills/`, `.claude/skills/`, or equivalent),
which is deliberately excluded from version control. Copy or symlink it in:

```sh
cp -r skills/design .agents/skills/design      # or .claude/skills/design
```

Edit the tracked copy here, never the harness copy, or the two will drift.

## More than one brand

An organization usually runs several brands, and they do not share a palette. Keep one
package per brand, side by side:

```
brands/
  nougen-shards/   manifest.json  DESIGN.md  tokens.css
  nougen-ai/       manifest.json  DESIGN.md  tokens.css
  nougen-builds/   manifest.json  DESIGN.md  tokens.css
```

**Every asset declares which brand it serves.** Before designing anything, resolve the
brand and load only that package. An asset that does not name its brand cannot be
reviewed, because there is no single correct palette to review it against.

Brands differ by more than hue. One may be dark-first and another light-first; they may
use different display faces and different radii. Do not force them into a shared shape —
what they share is the method and the floors in this file, not their values.

Point the validator at the `brands/` directory to check every package at once, or at a
single package directory to check one.

## Reference implementations

`brands/` holds complete conforming packages. Read one to see what "done" looks like.

**They are references, not defaults.** Those palettes belong to these brands. Building
for someone else means writing a new package with their values — the method, the floors,
and the structure carry over; the hexes do not. Shipping someone else's project in one of
these brands is a failure, not a shortcut.
