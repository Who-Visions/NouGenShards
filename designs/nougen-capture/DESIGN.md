---
name: "nougen-capture"
version: "0.1.0"
description: "Matte graphite capture instrument for browser extension popup, options page, context menu actions, and store listing."
colors: {"--bg": "#141414", "--panel": "#202020", "--panel-solid": "#202020", "--panel-2": "#282828", "--panel-hover": "#333333", "--line": "#777777", "--line-glow": "#777777", "--text": "#f2eee6", "--muted": "#bdb8ad", "--accent": "#e8b86d", "--accent-2": "#e8b86d", "--accent-purple": "#c8bfad", "--accent-green": "#a9c79b", "--danger": "#ffb4ab", "--warn": "#e8b86d", "--focus": "#e8b86d", "--control-ink": "#141414"}
---

# nougen-capture

## referenceWorld

Browser extension toolbar popup (~360px wide), options workspace, browser context menu, and Chrome Web Store listing surfaces.

## antiPatterns

Reject decorative gradients, glass, glow, giant pills, sparkles, waveform noise and generic SaaS card grids.

## materiality

Use opaque graphite surfaces, fine dividers and matte amber accents.

## density

Optimized for a 360px popup container and expansive options page. Compact functional groupings with 14px readable body copy, single-column vertical flow in popup, and monospace data rows for capture telemetry. Negative space defines boundaries between target selection and capture controls.

## motionGrammar

Use short deliberate state transitions. Disable nonessential motion when reduced motion is requested.

## interactionPhysics

Inputs respond immediately; asynchronous work exposes progress, cancellation and recovery. Refer to shared objects by stable, scoped identity instead of row position or left/right language. Selection, inspection and handoff refer to the same record; local view changes do not silently imply a synchronized peer view.

## informationHierarchy

Prioritize active capture target and failure states above secondary vault metadata. Store title follows 'Brand: Function' under 30 characters ('NouGen: Shard Capture'); store summary stays near 100 characters ('Capture web selections, URLs, and context directly into your verified NouGen shard vault without friction.'). Extension UI retains dark graphite palette; light canvas is reserved strictly for store listing hero art. Omit AI badges, sparkles, or promotional AI tags across all user-facing copy.

## responsiveBehavior

Popup operates fixed at ~360px width with intrinsic vertical flow and no horizontal scrolling. Options page stacks sections below 600px width. Context menu binds directly to target selection. Text wraps cleanly without clipping long vault identifiers or target URLs.

## Accessibility

Body text must meet 4.5:1 and focus/status indicators 3:1. Preserve labels and keyboard access. Measured default text on ground: 15.92:1; muted on panel: 8.24:1; focus on ground: 10.10:1. These are declared token pairs, not a complete application audit. Inputs have explicit accessible names. Controls have a 24px minimum target and 44px touch target. Reflow at 320px and text-size growth are verification requirements.

## brandVoice

Technical, precise, and verb-first ('Capture selection', 'Save target', 'Configure vault'). Omit promotional buzzwords, vague superlatives, and AI badges. Errors state the exact operational fault and specific recovery steps without metaphor.

## iconography

Use consistent monochrome line icons; pair unfamiliar symbols with labels.

## dataViz

Use labelled axes and text status; color alone never conveys meaning. Preserve data-bearing bar lengths, baselines, scales and area encodings when applying visual metaphors. Decorative integration belongs outside measured geometry. Missing evidence is unavailable, not zero.

## stateGrammar

Popup lifecycle encompasses four distinct states: 'capture ok', 'not captured', 'not configured', and 'offline'. The interface strictly reads the server-returned 'captured' boolean flag to determine success versus failure, never relying on transport HTTP status codes alone. Options credentials mask tokens permanently after saving; only whether a token is saved is shown, never its value.

## provenance

Adapted from NouGen core design tokens and extension design research. Extension constraints, store metadata patterns, and listing assets are derived from empirical Chrome Web Store top-200 analysis. Palette and layout rules maintain NouGen fleet continuity with inferred store asset transformations.
