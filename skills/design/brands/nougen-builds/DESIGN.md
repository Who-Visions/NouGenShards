---
version: 1.0.0
name: nougen-builds
description: Light-first contractor system. Navy carries trust, orange carries action, and the two are never asked to do each other's job.
colors:
  primary: "#0e3a56"
  primaryDark: "#072234"
  accent: "#f28c38"
  accentHover: "#d77320"
  bgLight: "#eef4f7"
  bgWhite: "#ffffff"
  textDark: "#2d3748"
  borderColor: "#e2e8f0"
typography:
  sans: Inter
  display: Space Grotesk
  scale: [0.8125, 1, 1.125, 1.375, 1.875, 2.5]
rounded: [6, 12]
spacing: [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4]
components: [card, panel, button, form, step, faq]
---

# Navy & Signal

## Overview

The property business. Light-first, plainspoken, built to convert a visitor into a quote
request. Navy carries trust and structure; orange carries action and appears rarely
enough that it still means something when it does.

The system's one real trap is asking orange to do navy's job. Orange is a **fill** color
and a **large-display** color. It is not a text color on light ground, and it is not
strong enough to sit behind white text. Both mistakes are live in the source; see
Accessibility.

Provenance is marked throughout. **Observed** means measured from shipped CSS. **Invented**
means the source was silent and the value was authored here.

## Color

Four brand steps, three surfaces, two inks. [observed]

| Token | Value | Role |
| --- | --- | --- |
| `--primary` | `#0e3a56` | navy — structure, trust, headings on light |
| `--primary-dark` | `#072234` | inverted sections, footer, ink on orange |
| `--accent` | `#f28c38` | orange — fills and large display only |
| `--accent-hover` | `#d77320` | orange hover state |
| `--bg-white` | `#ffffff` | page ground |
| `--bg-light` | `#eef4f7` | alternating section ground |
| `--border-color` | `#e2e8f0` | hairline — decorative only |
| `--text-dark` | `#2d3748` | primary text |

Semantic colors exist in the source as raw inline hex rather than tokens; they are
tokenized here as `--color-error`, `--color-success`, `--color-success-bg` and
`--color-success-border`.

## Typography

Space Grotesk for display, Inter for body, both wired through `next/font`. [observed]

**Naming mismatch on record.** The CSS variable is `--font-outfit`, but the face actually
loaded is Space Grotesk, not Outfit. The name is kept here for compatibility with existing
markup — renaming it silently would break every consumer — but anyone reading the variable
should know it does not describe its contents.

Display carries `h1`–`h6`, the logo, step numbers, FAQ summaries, form labels and the
footer signoff. Everything else is Inter.

Scale runs micro `0.8125` → body `1` → lead `1.125` → h3 `1.375` → h2 `1.875` → h1 `2.5`,
in rem at an unmodified 16px root. [invented — the source hardcodes sizes per class]

## Spacing

An eight-step rem ramp: `0.25 · 0.5 · 0.75 · 1 · 1.5 · 2 · 3 · 4`. [invented]

No spacing scale exists in the source; every value is written per class. This ramp is a
proposal to consolidate against, not a measurement of current usage.

## Radii

`--radius 12px` and `--radius-sm 6px`. [observed]

Only two steps, and that restraint is correct for this brand — cards and panels at 12,
chips and inputs at 6. Resist adding more.

## Elevation

Three shadows, all **tinted with the navy or the orange** rather than neutral grey.
[observed]

`--shadow-card` uses `rgba(14, 58, 86, .08)`, and the two CTA shadows use the accent at
20% and 30%. This is the detail that keeps the system from looking like a generic
bootstrap page, so preserve it. A neutral grey shadow here reads as unfinished.

## Components

| Component | Default | Hover | Disabled | Focus-visible |
| --- | --- | --- | --- | --- |
| card | white + `--shadow-card` | lift −4px, accent border | — | inherited ring |
| panel | `--bg-light`, hairline border | — | — | inherited ring |
| btn-cta | `--accent` fill + `--on-accent` | `--accent-hover` fill | 0.45 opacity | inherited ring |
| btn-outline | navy border, navy text | fill navy, white text | 0.45 opacity | inherited ring |
| form field | hairline border on white | border → navy | 0.45 opacity | inherited ring |
| step / faq | display face, navy | — | — | inherited ring |

Card hover lifts −4px with a `0.3s cubic-bezier(0.4, 0, 0.2, 1)` transition and swaps the
border to accent. [observed]

The focus ring is **invented** — the source defines no focus state. It is built from
`--primary` (11.94 on white), never from `--border-color`, which is a hairline at
decorative contrast and invisible as an indicator.

## Motion

No keyframes at all — the system is transitions only, on a single shared
`--transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1)`. [observed]

This brand is the one that already gets accessibility right here: the source contains a
proper `@media (prefers-reduced-motion: reduce)` block killing transitions, animations and
smooth scrolling, plus a `@media print` block. Both are preserved.

## Accessibility

Floor: body text ≥4.5:1, large text and UI components ≥3:1, computed.

| Pair | Ratio | Verdict |
| --- | --- | --- |
| white → primary-dark fill | 16.31 | AAA |
| text-dark → white | 11.99 | AAA |
| white → primary fill | 11.94 | AAA |
| primary → white | 11.94 | AAA |
| text-dark → bg-light | 10.80 | AAA |
| primary → bg-light | 10.76 | AAA |
| primary-dark → accent fill | 6.67 | AA — the pattern that works |
| success → success ground | 6.51 | AA |
| error → white | 5.47 | AA |
| accent → primary fill | 4.88 | AA |
| text-muted → white | 4.02 | **fails body**, large only |
| accent-hover → white | 3.30 | **fails body**, large only |
| text-muted → bg-light | 3.62 | **fails body**, large only |
| accent → white | 2.45 | **fails both** |
| **white → accent fill (`.btn-cta`)** | **2.45** | **fails both** |
| accent → bg-light | 2.20 | **fails both** |

Three rules follow, in order of how much they cost.

**Orange fills carry navy ink, never white.** `.btn-cta` is the primary conversion control
on a lead-generation site, and at 2.45 it fails every level — the single most expensive
defect in any of these brands, because it sits on the path to a quote request. The source
already contains the fix: `.storm-banner` puts `--primary-dark` on accent at 6.67. The
`--on-accent` token generalizes that so the correct pairing is the default.

**Orange is not a text color on light ground.** It currently is one in section labels,
card links, breadcrumbs, the logo span, nav hover and list bullets, all at 2.45 or 2.20.
Use `--accent-text` (`#9a4a06`, 6.26 on white and 5.64 on `--bg-light`), which holds the
signal-orange read and clears the floor. Accent as text is only sound on the dark
sections, where it reaches 4.88 on navy.

**Secondary text needs to be darker.** The shipped `--text-muted` (`#718096`) lands at
4.02 and 3.62, missing AA body on both surfaces, and it is used for section intros, card
copy, step copy, FAQ answers, notes and chips — most of the running prose on the site.
`--text-muted` here is `#596478` (5.97 / 5.38). The original is retained as
`--text-muted-legacy` for large text only.

**Open work:** this brand is light-only by design. The dark passages — hero, CTA band,
trust strip, footer — are inverted *sections*, not a dark theme, and should not be
mistaken for one. A genuine dark mode would need its own computed ramp.
