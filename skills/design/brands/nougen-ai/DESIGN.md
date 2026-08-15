---
version: 1.0.0
name: nougen-ai
description: Warm editorial dark system in obsidian and gold. Earth-toned, weight-based depth, display type carrying the personality.
colors:
  obsidian: "#111111"
  carbon: "#1c1c1c"
  ivory: "#f4f1ea"
  stone: "#a6a29c"
  gold: "#cfaf5a"
  copper: "#8b5e34"
  emerald: "#2f8f79"
  terracotta: "#c44e3a"
typography:
  sans: Inter
  display: Syne
  scale: [0.75, 1, 1.125, 1.5, 2, 2.75, 4]
rounded: [0.25, 0.5, 0.875, 9999]
spacing: [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4]
components: [surface, card, button, link, marquee]
---

# Gilded Obsidian

## Overview

The company brand. Warm, editorial, and earth-toned — a deliberate contrast with the
neon violet of `nougen-shards`. These are sibling brands, not variants of one system, and
they are not meant to be reconciled. Where the Shards system expresses depth as violet
glow, this one expresses it as weight: plain dark shadow, no luminance.

The character lives in the display face and in the gold. Use both sparingly; gold at
large area turns the page into a jewelry advert rather than a company site.

Provenance is marked throughout. **Observed** means measured from shipped CSS. **Invented**
means the source was silent and the value was authored here.

## Color

Two surfaces, two inks, two brand metals, two accents. [observed]

| Token | Value | Role |
| --- | --- | --- |
| `--color-obsidian` | `#111111` | page ground |
| `--color-carbon` | `#1c1c1c` | raised surface |
| `--color-ivory` | `#f4f1ea` | primary text |
| `--color-stone` | `#a6a29c` | secondary text |
| `--color-gold` | `#cfaf5a` | primary brand |
| `--color-copper` | `#8b5e34` | secondary brand |
| `--color-emerald` | `#2f8f79` | accent |
| `--color-terracotta` | `#c44e3a` | accent |

Ink-on-fill tokens are **invented** and exist to prevent the system's worst failure. See
Accessibility.

## Typography

Syne for display, Inter for body. [observed by name]

**Defect on record.** In the source both faces are named in tokens and **never loaded** —
there is no `next/font` import, no `@font-face`, and no stylesheet link anywhere in the
application. Both silently fall back to system UI, which means the display face does not
exist on the rendered page and display differs from body in token name only. A package
that names a face must also load it; treat this as the first thing to fix when adopting
this brand.

Scale runs micro `0.75` → body `1` → lead `1.125` → h3 `1.5` → h2 `2` → h1 `2.75` →
display `4`, in rem, at an unmodified 16px root. [invented — the source hardcodes sizes
per class] Body line-height `1.6` is observed; all other tracking and leading values are
invented.

## Spacing

An eight-step rem ramp: `0.25 · 0.5 · 0.75 · 1 · 1.5 · 2 · 3 · 4`. [invented]

No spacing tokens exist in the source at all — spacing is expressed entirely through
utility classes in components. This ramp is a proposal, not a measurement.

## Radii

`--radius-sm 0.25` · `--radius-md 0.5` · `--radius-lg 0.875` · `--radius-full 9999px`
[invented]

Tighter than the sibling brand. Editorial layouts read better with restrained corners;
soft radii undercut the weight this system is built on.

## Elevation

Four steps of plain dark shadow. [invented]

Do not port the violet glow from `nougen-shards`. Luminous edges belong to that system's
personality and read as a foreign object here. Earth tones want weight.

## Components

| Component | Default | Hover | Disabled | Focus-visible |
| --- | --- | --- | --- | --- |
| surface | obsidian ground | — | — | inherited ring |
| card | carbon + `--elev-2` | `--elev-3` | — | inherited ring |
| button (gold) | gold fill + `--color-on-gold` | — | 0.45 opacity | inherited ring |
| button (copper) | copper fill + white | — | 0.45 opacity | inherited ring |
| link | gold text | — | — | inherited ring |
| marquee | 30s / 60s loops | — | — | n/a |

The focus treatment is the one thing the source already gets right — a 2px gold outline,
and gold on obsidian is 8.93. It has been promoted to `--focus-ring` and applied through
a zero-specificity `:where(…):focus-visible` rule so every control inherits it rather
than each re-declaring it.

## Motion

Four marquee and progress loops at 30s, 60s and 6s, plus scanline and shimmer keyframes
that are defined but currently have no utility class. [observed]

**Defect on record, fixed in `tokens.css`.** The source has no
`@media (prefers-reduced-motion: reduce)` block anywhere, so all five keyframes run
unconditionally regardless of the viewer's stated preference. The gate is included here.

## Accessibility

Floor: body text ≥4.5:1, large text and UI components ≥3:1, computed.

| Pair | Ratio | Verdict |
| --- | --- | --- |
| ivory → obsidian | 16.74 | AAA |
| ivory → carbon | 15.11 | AAA |
| gold → obsidian | 8.93 | AAA |
| gold → carbon | 8.06 | AAA |
| obsidian → gold fill | 8.93 | AAA |
| stone → obsidian | 7.44 | AAA |
| stone → carbon | 6.71 | AAA |
| white → copper fill | 5.60 | AA |
| emerald → obsidian | 4.79 | AA |
| white → terracotta fill | 4.67 | AA |
| terracotta → obsidian | 4.04 | **fails body**, large only |
| white → emerald fill | 3.94 | **fails body**, large only |
| copper → obsidian | 3.37 | **fails body**, large only |
| stone at 50% → obsidian | 2.74 | **fails both** — in use in nav |
| white → gold fill | 2.11 | **fails both** — worst pair in the system |

Three rules follow from this table.

**Gold fills carry obsidian ink, never white.** White on gold is 2.11 and fails every
level. The shipped `::selection` rule already pairs gold with obsidian correctly; the
`--color-on-*` tokens generalize that so the correct pairing is the default rather than
something each component rediscovers.

**Copper and terracotta are display colors, not text colors.** Both fail AA body on
obsidian. Where the earth tones must carry running text, use `--color-copper-text`
(6.34) and `--color-terracotta-text` (6.34), which hold the hue and clear the floor.

**Do not fade `stone` with opacity.** `stone` at 50% lands at 2.74 and fails both levels;
it is currently used that way in navigation. Secondary text is already `--color-stone` at
full strength (7.44). If something needs to recede further than that, it is not text —
it is decoration, and it should not be carrying information.

**Open work:** this brand is dark-only, by design. No light branch exists in the source
and none is proposed here. If a light context ever becomes necessary, it needs its own
computed ramp — gold in particular does not survive being placed on a light ground.
