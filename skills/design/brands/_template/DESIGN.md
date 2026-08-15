---
version: 0.1.0
name: _template
description: Neutral starting point. Copy this directory, rename it, and replace every value.
colors:
  bg: "#ffffff"
  bg2: "#f4f5f7"
  panel: "#ffffff"
  line: "#e3e5e9"
  fg: "#1a1c20"
  muted: "#5a6070"
  brand: "#3b5bdb"
  brandDeep: "#2f4bb8"
typography:
  sans: system-ui
  mono: ui-monospace
  scale: [0.75, 1, 1.125, 1.375, 1.75, 2.25]
rounded: [0.25, 0.5, 0.75, 9999]
spacing: [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4]
components: [surface, card, button, input, chip]
---

# Template

## Overview

Copy this directory, rename it after the brand, and replace every value. It exists so the
easiest way to start is a blank system rather than someone else's — the other packages in
`brands/` carry a real organisation's identity and must not be used as a starting point.

The palette here is deliberately characterless. Shipping it unchanged should look
unfinished, which is the correct signal. It passes every gate, so the validator confirms
your plumbing before you have made a single aesthetic decision.

Replace this paragraph with what the system is actually for: who reads it, what it has to
do, and the one quality that makes it recognisable.

## Color

Replace all of these. Keep the roles; the roles are what the rest of the system reads.

| Token | Role |
| --- | --- |
| `--color-bg` | page ground |
| `--color-bg-2` | inset or alternating ground |
| `--color-panel` | raised surface |
| `--color-line` | hairline rule — decorative only, never an indicator |
| `--color-fg` | primary text |
| `--color-muted` | secondary text |
| `--color-brand` | accent as text or stroke |
| `--color-brand-deep` | large display and fills |
| `--color-on-brand` | ink placed on a brand fill |

`--color-on-brand` is separate from `--color-fg` on purpose. A brand color that passes as
text on the page background routinely fails as a fill behind light text — two different
measurements, both required.

Semantic colors sit outside the brand hue so that state never reads as emphasis. Recompute
them once the brand hue is chosen; a green that reads as "success" beside blue may not
beside another green.

## Typography

A system font stack, so the template renders identically anywhere with no network fetch.
Replace it with real faces, and **load them** — naming a face in a token does nothing on
its own.

Scale: micro `0.75` → body `1` → lead `1.125` → h3 `1.375` → h2 `1.75` → h1 `2.25`, rem at
a 16px root. Weights 400 / 500 / 600 / 700.

## Spacing

`0.25 · 0.5 · 0.75 · 1 · 1.5 · 2 · 3 · 4` in rem.

Lay sibling groups out with flex or grid and `gap`. Per-element margins collapse and
double in ways a ramp cannot protect you from.

## Radii

`sm 0.25` · `md 0.5` · `lg 0.75` · `full 9999px`. Four steps is usually enough; each extra
one is a decision every future component has to make.

## Elevation

Three neutral steps plus a flat ring. Replace with whatever expresses depth in your
system — shadow, glow, border weight, or nothing at all. Flat systems are a legitimate
choice; make it a choice.

## Components

| Component | Default | Hover | Disabled | Focus-visible |
| --- | --- | --- | --- | --- |
| surface | `--color-bg` | — | — | inherited ring |
| card | panel + `--elev-1` | `--elev-2` | — | inherited ring |
| button | `--color-brand` fill + `--color-on-brand` | `--color-brand-deep` | 0.45 opacity | inherited ring |
| input | hairline on `--color-bg-2` | border → brand | 0.45 opacity | inherited ring |
| chip | `--radius-sm`, `--elev-ring` | — | — | inherited ring |

Every row inherits its focus ring from a single zero-specificity rule in `tokens.css`, so
no component declares its own and none can be forgotten.

## Motion

`--dur-fast 0.15s` and `--dur-base 0.25s` on `cubic-bezier(.2, .8, .2, 1)`, all behind
`@media (prefers-reduced-motion: reduce)`.

## Accessibility

Floor: body text ≥4.5:1, large text and UI components ≥3:1, **computed, not estimated**.

| Pair | Ratio | Verdict |
| --- | --- | --- |
| fg → bg | 17.06 | AAA |
| brand-deep → bg | 7.45 | AAA |
| muted → bg | 6.28 | AA |
| brand → bg | 5.67 | AA |
| on-brand → brand fill | 5.67 | AA |
| line → bg | 1.26 | decorative only |

Recompute this whole table after replacing the palette. The numbers above describe the
placeholder colors and mean nothing once those change.

Run the validator to check your work:

```
python skills/design/validate.py <your-package-dir>
```
