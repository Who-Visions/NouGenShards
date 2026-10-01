---
name: "nougen-core"
version: "0.3.0"
description: "Matte instrument surfaces for the NouGen fleet workbench."
colors: {"--bg": "#141414", "--panel": "#202020", "--panel-solid": "#202020", "--panel-2": "#282828", "--panel-hover": "#333333", "--line": "#777777", "--line-glow": "#777777", "--text": "#f2eee6", "--muted": "#bdb8ad", "--accent": "#e8b86d", "--accent-2": "#e8b86d", "--accent-purple": "#c8bfad", "--accent-green": "#a9c79b", "--danger": "#ffb4ab", "--warn": "#e8b86d", "--focus": "#e8b86d", "--control-ink": "#141414"}
---

# nougen-core

## referenceWorld

Precision instrument, editorial technical publishing, broadcast control room and premium creative software.

## antiPatterns

Reject decorative gradients, glass, glow, giant pills, sparkles, waveform noise and generic SaaS card grids.

## materiality

Use opaque graphite surfaces, fine dividers and matte amber accents.

## density

Keep functional clusters compact; use whitespace to separate tasks, with readable 14px body text. Keep sustained reading near 65ch while metadata and tables use the workbench width. Summarize long records with an explicit full-content disclosure. Treat negative space as a functional separator: independent cards retain a cluster gap, while related label/value pairs remain visibly grouped. Reflow content before reducing separation.

## motionGrammar

Use short deliberate state transitions. Disable nonessential motion when reduced motion is requested.

## interactionPhysics

Inputs respond immediately; asynchronous work exposes progress, cancellation and recovery.

## informationHierarchy

Prioritize active work and failures before secondary telemetry. Align numbers in monospace. Each region has one primary reading (machine identity, memory title or chart); badges and supporting telemetry remain subordinate. Shared boundaries are permitted only inside a single related task.

## responsiveBehavior

Stack work regions at narrow widths; allow document scrolling and wrap toolbars. Use rem type and spacing. Full-width regions use their container width rather than 100vw. Long identifiers wrap without losing content. Choose columns from available container width. Fleet cards need 23rem when room permits and retain a 1.25rem gap; below an 18rem card content width, label/value rows stack with a 0.25rem gap. At 320px and split-pane widths, independently meaningful regions must not touch or overlap.

## Accessibility

Body text must meet 4.5:1 and focus/status indicators 3:1. Preserve labels and keyboard access. Measured default text on ground: 15.92:1; muted on panel: 8.24:1; focus on ground: 10.10:1. These are declared token pairs, not a complete application audit. Inputs have explicit accessible names. Controls have a 24px minimum target and 44px touch target. Reflow at 320px and text-size growth are verification requirements.

## brandVoice

Use concrete verbs, technical accuracy and concise recovery instructions. Keep the same term for the same action. Errors state what happened and the recovery action; do not use metaphors in task-critical copy.

## iconography

Use consistent monochrome line icons; pair unfamiliar symbols with labels.

## dataViz

Use labelled axes and text status; color alone never conveys meaning. Preserve data-bearing bar lengths, baselines, scales and area encodings when applying visual metaphors. Decorative integration belongs outside measured geometry. Missing evidence is unavailable, not zero.

## stateGrammar

Specify default, hover, focus, selected, disabled, loading, empty, offline, success and error states. Full-memory disclosure uses native details and summary, with a visible character count and keyboard access. Memory counts state their vault coverage. Partition filters show configured partitions and distinguish returned-result counts from vault cardinality. Inspect separates the machine observing a vault from record-origin provenance; unresolved ancestry stays explicit.

## provenance

Token choices are invented from the relay brief. Existing selectors and token names are observed. Local Ollama draft reviewed by Codex; NouGenOpen reviewed acceptance criteria. Spatial composition adaptations draw on arXiv:2609.00476v1; dashboard gap thresholds are NouGen implementation choices verified in-browser, not empirical findings of that paper. Recursive design research uses the NouGenDesigns discover command. Citation depth, discovery parent and keyword matches identify candidates, not adopted rules. Read the full source, state applicability and limitations, then record inferred adaptations separately from observed metadata before compilation.
