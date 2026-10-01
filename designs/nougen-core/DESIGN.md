---
name: "nougen-core"
version: "0.5.0"
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

Inputs respond immediately; asynchronous work exposes progress, cancellation and recovery. Refer to shared objects by stable, scoped identity instead of row position or left/right language. Selection, inspection and handoff refer to the same record; local view changes do not silently imply a synchronized peer view.

## informationHierarchy

Prioritize active work and failures before secondary telemetry. Align numbers in monospace. Each region has one primary reading (machine identity, memory title or chart); badges and supporting telemetry remain subordinate. Shared boundaries are permitted only inside a single related task. Collaborative surfaces keep the task reference frame explicit: name the observed machine, vault scope and selected object before participant representation. Peer presence never substitutes for shared task-state evidence. Settle the page composition (regions, space budget, the primary reading of each region) before detailing components, so a late element does not have to take room an earlier one needs. Text stays live text on its own layer, never baked into an image.

## responsiveBehavior

Stack work regions at narrow widths; allow document scrolling and wrap toolbars. Use rem type and spacing. Full-width regions use their container width rather than 100vw. Long identifiers wrap without losing content. Choose columns from available container width. Fleet cards need 23rem when room permits and retain a 1.25rem gap; below an 18rem card content width, label/value rows stack with a 0.25rem gap. At 320px and split-pane widths, independently meaningful regions must not touch or overlap. Responsive reordering may change placement but must retain record identity, selected state and reference labels. A card moving across columns must not change which object a peer reference identifies.

## Accessibility

Body text must meet 4.5:1 and focus/status indicators 3:1. Preserve labels and keyboard access. Measured default text on ground: 15.92:1; muted on panel: 8.24:1; focus on ground: 10.10:1. These are declared token pairs, not a complete application audit. Inputs have explicit accessible names. Controls have a 24px minimum target and 44px touch target. Reflow at 320px and text-size growth are verification requirements.

## brandVoice

Use concrete verbs, technical accuracy and concise recovery instructions. Keep the same term for the same action. Errors state what happened and the recovery action; do not use metaphors in task-critical copy.

## iconography

Use consistent monochrome line icons; pair unfamiliar symbols with labels.

## dataViz

Use labelled axes and text status; color alone never conveys meaning. Preserve data-bearing bar lengths, baselines, scales and area encodings when applying visual metaphors. Decorative integration belongs outside measured geometry. Missing evidence is unavailable, not zero.

## stateGrammar

Specify default, hover, focus, selected, disabled, loading, empty, offline, success and error states. Full-memory disclosure uses native details and summary, with a visible character count and keyboard access. Memory counts state their vault coverage. Partition filters show configured partitions and distinguish returned-result counts from vault cardinality. Inspect separates the machine observing a vault from record-origin provenance; unresolved ancestry stays explicit. For collaborative inspection distinguish observer, record origin, owner and recipient. Mark independently filtered, stale, unavailable and unsynchronized views explicitly. Transport accepted, recipient acknowledged, work in progress and verified completion are distinct states.

## provenance

Token choices are invented from the relay brief. Existing selectors and token names are observed. Local Ollama draft reviewed by Codex; NouGenOpen reviewed acceptance criteria. Spatial composition adaptations draw on arXiv:2609.00476v1; dashboard gap thresholds are NouGen implementation choices verified in-browser, not empirical findings of that paper. Recursive design research uses the NouGenDesigns discover command. Citation depth, discovery parent and keyword matches identify candidates, not adopted rules. Read the full source, state applicability and limitations, then record inferred adaptations separately from observed metadata before compilation. arXiv:1910.03380v1 supplies a workspace-awareness analogy from two-person 3D telepresence. Stable vault/DB/record references and relay lifecycle distinctions are NouGen adaptations; the paper does not test fleet dashboards or establish faster task performance. arXiv:2507.05601v1 (Accordion) supplies the frame-first ordering and live-text rule; it is a generative layered-design pipeline evaluated on posters and thumbnails, and says nothing about dashboards. arXiv:2609.05364 (SMART) and arXiv:2508.12726 (DESIGNER) were read only as alphaXiv reports; design.json is the durable source and generated artifacts are regenerated and drift-checked, and reusable construction recipes are recorded as an untested candidate in designs/design-process-morph.md, not as a rule.
