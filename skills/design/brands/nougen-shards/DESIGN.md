---
version: 1.0.0
name: nougen-shards
description: Dark-first violet-on-obsidian system for NouGen Shards. Dense, atmospheric, glow-based rather than shadow-based.
colors:
  night: "#08060f"
  panel: "#110c22"
  ink: "#e9e5f6"
  muted: "#a79fc4"
  brand: "#a855f7"
  brandDeep: "#7c3aed"
  brandLight: "#c084fc"
  brandFill: "#6d28d9"
typography:
  sans: Inter
  mono: ui-monospace
  scale: [0.75, 0.875, 1, 1.25, 1.875, 2.25, 3]
rounded: [0.25, 0.75, 1, 1.5, 9999]
spacing: [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4]
components: [surface, card, input, button, chip, chart]
---

# Obsidian Violet

## Overview

A dark-first system built for dense technical surfaces — dashboards, shard browsers,
audit views. It reads as atmospheric rather than flat: the ground always carries a faint
violet wash, and depth is expressed as **glow** (a hairline violet ring plus a long soft
throw) rather than as grey shadow. That single decision is what makes the system look
like itself, so preserve it when extending.

Provenance is marked throughout. **Observed** means measured from shipped CSS.
**Inferred** means derived from real class-usage frequency. **Invented** means nothing
in the source implied it and it was authored here. Treat invented values as proposals.

## Color

Six surface and ink tokens, three brand steps, one compliant fill. [observed, except fill]

| Token | Value | Role |
| --- | --- | --- |
| `--color-night` | `#08060f` | page ground |
| `--color-night-2` | `#0c0a18` | inset / recessed |
| `--color-panel` | `#110c22` | raised card |
| `--color-line` | `#221a3d` | hairline rule — decorative only |
| `--color-ink` | `#e9e5f6` | primary text |
| `--color-muted` | `#a79fc4` | secondary text |
| `--color-brand` | `#a855f7` | accent as text or stroke |
| `--color-brand-deep` | `#7c3aed` | large display and fills |
| `--color-brand-light` | `#c084fc` | emphasis, focus ring |
| `--color-brand-fill` | `#6d28d9` | the only compliant solid fill [invented] |

The ground is never flat. Two fixed radial washes sit behind everything, and a 44px
violet grid at 6% opacity sits above them. Removing either flattens the system.

Semantic color (`--color-pass`, `--color-warn`, `--color-fail`) is deliberately outside
the violet hue so state never reads as brand emphasis.

## Typography

Inter for text, `ui-monospace` for data, identifiers, and anything in a column. [observed]

The source root is `11px`, so every rem is 0.6875× standard. This is a deliberate density
choice, but it leaks: components repeatedly escape the scale with arbitrary pixel values,
and one of those escapes is byte-identical to a scale step. If you inherit this root,
expect that pressure. If you are starting fresh, prefer a 16px root and express density
through the scale instead.

Sizes run micro `0.75` → body `0.875` → lead `1` → h3 `1.25` → h2 `1.875` → h1 `2.25` →
display `3`, in rem. [inferred] Weights are 400 body, 500 medium, 600 semibold, 700 bold;
body 400 is implicit since it is never declared. [observed]

Tracking and leading are **invented** — the source contains zero letter-spacing and zero
line-height declarations. Display type takes `-0.02em`, uppercase labels `0.08em`, body
line-height `1.6`.

## Spacing

An eight-step ramp in rem, covering roughly 85% of observed usage. [inferred]

`0.25 · 0.5 · 0.75 · 1 · 1.5 · 2 · 3 · 4`

The ramp is corroborated rather than merely fitted: the shipped grid utility uses a
`44px` background size, which lands exactly on `--space-16`. That is the only spacing
constant literally present in the source CSS.

Lay out sibling groups with flex or grid and `gap`. Per-element margins collapse and
double in ways the ramp cannot protect you from.

## Radii

`--radius-sm 0.25` · `--radius-md 0.75` · `--radius-lg 1` · `--radius-xl 1.5` ·
`--radius-full 9999px` [inferred]

Cards take `lg`, inputs and buttons take `md`, chips take `sm`, hero panels take `xl`,
pills take `full`. Intermediate steps from the utility framework are dropped because they
land within 4px of a kept step and add no distinguishable difference at this root size.

## Elevation

Three tiers plus a flat ring, all built from the same formula — a 1px violet ring and a
long, heavily negative-spread violet throw.

`--elev-1` is invented, extrapolating the formula downward. `--elev-2` (resting glow) and
`--elev-3` (hover lift) are observed. `--elev-ring` is a bare hairline for elements that
need definition without lift.

Do not introduce grey shadows. A grey drop shadow on this ground reads as a rendering bug.

## Components

| Component | Default | Hover | Active | Disabled | Focus-visible |
| --- | --- | --- | --- | --- | --- |
| surface | `--glass` + `--color-line` + blur(8px) | — | — | — | inherited ring |
| card | panel + `--elev-2` | −3px, ring 0.4α, `--elev-3` | — | — | inherited ring |
| input | `--color-line` border on night-2 | border → brand | — | 0.45 opacity | inherited ring |
| button | `--color-brand-fill` + `--color-on-brand` | fill → brand-deep | scale 0.98 | 0.45 opacity | inherited ring |
| chip | sm radius, `--elev-ring` | — | — | — | inherited ring |
| chart | see ramp below | series emphasis | — | — | inherited ring |

Every row inherits the focus ring from one zero-specificity rule in `tokens.css`, so no
component defines its own. This is the fix for the defect this system shipped with:
`focus-visible` appeared **zero** times across the source while `hover:` appeared 105
times, and `focus:outline-none` removed the native ring in four places without replacing
it. Hover-rich and keyboard-blind is the most common failure in a real system — check for
it first when auditing.

Button fill uses `--color-brand-fill` (`#6d28d9`), not `--color-brand`. Light text on
`#a855f7` computes to 3.20:1 and fails AA.

## Motion

Motion is atmospheric, not decorative: slow drifting blurred orbs, a periodic sheen
across the wordmark, a pulse on live indicators, a scan line on data surfaces. Durations
run 18–30s for ambient loops; interaction transitions use `0.25s` with
`cubic-bezier(.2, .8, .2, 1)`. [observed]

Everything sits behind `@media (prefers-reduced-motion: reduce)`. No exceptions.

## Accessibility

Floor: body text ≥4.5:1, large text and UI components ≥3:1, measured — not estimated.

| Pair | Ratio | Verdict |
| --- | --- | --- |
| ink → night | 16.30 | AAA |
| muted → night | 8.05 | AAA |
| muted → panel | 7.64 | AAA |
| brand-light → night | 7.62 | AAA |
| brand → night | 5.09 | AA |
| ink → brand-deep | 4.61 | AA, thin margin |
| brand-deep → night | 3.53 | large text only |
| ink → brand | 3.20 | **fails** — do not use as a fill |
| line → night | 1.23 | decorative only, never an indicator |

Two rules follow directly from this table. `--color-brand-deep` is restricted to fills and
large display type. `--color-line` can never carry a focus ring or a meaningful boundary,
which is why `--focus-ring` is built from `--color-brand-light` instead.

The chart ramp is eight categorical series, each verified ≥3:1 on `--color-night`, with
six clearing 4.5:1 so they double as label text. Series 1 anchors on the brand hue. Hues
are spaced 80–100° apart rather than evenly, because even spacing crowds the
violet/indigo/fuchsia band the brand ramp already occupies, and contrast alternates
high/low so adjacent series separate by lightness as well as hue.

**Open work:** the chart ramp is dark-only. All eight colors fall between 1.4:1 and 3.1:1
on the light ground and fail there. A light ramp must be computed independently, not
produced by lightening these.
