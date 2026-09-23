---
name: negative-space
description: Use when designing, reviewing or tightening any NouGen web UI's whitespace — "negative space", "white space", clutter, a header that wraps, a side panel that scrolls forever, controls crowding the content, inconsistent margins, or AI text full of emoji. Covers macro/micro/active/passive space, measurable thresholds, the whitespace_audit.py tool (CSS lint, live DOM probe, text sanitizer), and the order to fix things in. Verified on the Who Visions Archive 9/13/2026.
---

# Negative space: measure it, then give it back to the content

Whitespace is a layout material, not leftover room. Sources merged here, all sharded under domain `ui-whitespace-design`: the Wix, Mailchimp and Elementor white-space guides; the NN/g, W3C WCAG (supplemental whitespace pattern, 1.4.12 text spacing, 2.5.8 target size), Smashing (cognitive load) and Mailchimp Gestalt pieces they cite; `consistent_whitespace` (one spacing system enforced by a lint; AGPL, idea only); `demojify-sanitize` (strip emoji clutter and redundant spaces from AI text; Apache-2.0, idea only). The free fleet distilled 12 of the sources into measurable principles: `WhoVisions Photographer fleet\analysis\whitespace_principles.json`.

## The four kinds
- **Macro space:** between regions (header, content, side panel, footer). Decides how much of the screen the content gets.
- **Micro space:** inside components (label to field, icon to text, line height, letter spacing). Decides legibility.
- **Active space:** placed on purpose to steer the eye: room around the one primary action, and the control used on every item placed first.
- **Passive space:** ordinary breathing room from the spacing scale.

## Rules (the thresholds `tools/whitespace_audit.py` checks)
1. **Content first.** Bars around the content take at most 35% of the viewport, measured at the smallest supported size (1280x720 for desktop apps).
2. **One-row toolbar.** If the header wraps, fold rarely changed controls into a drawer (`details` "Filters" or "More", with an active-count badge). Keep at most 12 visible controls.
3. **Primary actions above the fold.** In a side panel the controls used on every item go first; heavy tools such as editors start collapsed and remember their state.
4. **One spacing system.** Every margin, padding and gap comes from the token scale (Who Visions: 4/6/12/18/24/40 px). Only 0-2 px hairlines may be raw. A lint enforces it in the test suite.
5. **Group with space, not boxes (Gestalt proximity).** Related controls sit 4-6 px apart; sibling sections at least 16-18 px apart with one hairline divider.
6. **Micro legibility.** Body line-height at least 1.4-1.5; paragraph gap at least 1em; label-to-field gap smaller than field-to-next-group gap; targets at least 24 px (WCAG 2.5.8).
7. **Two or three font families**, one role each (display, body, UI or mono).
8. **Clean AI text before it reaches the UI or the data:** strip pictographs and emoji, collapse repeated spaces; keep letters of every script and UI symbols such as the star and arrows.

## Workflow
1. **Measure first.** Run `python tools/whitespace_audit.py probe`, paste the snippet into devtools on the page, save the JSON it returns, then `whitespace_audit.py dom metrics.json`. Also `whitespace_audit.py css <styles.css>`. Screenshots that contain private photos never go to cloud lanes.
2. **Fix in order:** macro (chrome share, header rows) -> active (primary action position, collapsed heavy tools) -> micro (tokens, line-height) -> text hygiene.
3. **Re-measure** and record before/after numbers. Keep the lint in the test suite so it cannot regress.
4. Distilling or critiquing **public** design writing can go to the free fleet (`fleet.py`, three decorrelated lanes). Private screenshots cannot.

## Proof (Who Visions Archive, 1280x720, 9/13/2026)
Filter header 167 px -> 57 px (one row); year strip 65 -> 53 px; grid 58% -> 75% of the screen; loupe side panel scroll 2,765 -> 1,392 px with rating, flag and color first and Edit collapsed; 28 raw-px spacing values -> 0, with the lint added as smoke-test check 29.
