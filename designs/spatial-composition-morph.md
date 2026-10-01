# Spatial composition morph: arXiv 2609.00476v1

Source: [Less Is More: Balancing Positive and Negative Space in Visual Concept Blending](https://arxiv.org/html/2609.00476v1), Xiao, Coscia and Laidlaw. Read sections 3, 4, 5 and 6 on 2026-10-01.

The paper studies concept blending with primary/secondary interpretation, positive/negative spatial roles and editable contours. It combines geometric region selection, semantic planning and pixel/vector refinement. Its evaluation concerns generated images; the novice user study has 12 participants. The authors identify expert interactive use as future work. The infographic case preserves chart geometry. These findings motivate the adaptation below; they do not establish dashboard spacing thresholds or usability improvements.

## NouGen adaptation

- Plan the primary task, supporting information and separating space before choosing ornament.
- Keep independent machine cards separate. Share structure only among information belonging to the same machine.
- Reflow columns from actual panel width. Preserve a named cluster-gap token instead of squeezing three columns until borders or text collide.
- Keep identity and status legible; supporting specifications wrap or stack. Do not use hidden visual interpretation for operational status.
- Preserve measured chart geometry. Missing readings remain unavailable.
- Review the whole page and each dense region separately. Fix the failing region, then check the page again.

The 23rem preferred card width, 1.25rem card gap and 18rem row-stack threshold are NouGen choices, not paper findings. They are in design.json and compiled DESIGN.md/tokens.css/mutations.json.

## Dashboard reassessment

The reported split-pane failure was a forced three-column fleet grid. The correction uses auto-fit with a container-limited minimum width, non-shrinking status badges and stacked label/value rows at narrow card widths.

Observed in-browser on the updated layout before substituting the same values with design tokens:

| Viewport | Result |
| --- | --- |
| 1000px | Two 454px fleet cards per row; 20px gap; document width 1000px |
| 320px | One 274px card per row; labels/values stack; document width 313px |

Live fleet identity, local RAM/GPU/temperature, resolved LAN addresses and responding service status were inspected. Storage showed measured sizes and the configured 2048MB partition capacity. Handoffs preserved open/acked/closed states. Usage tests distinguish absent records from recorded zero; prices and per-model request counts remain unavailable without evidence.

Limits: remote nodes do not currently publish hardware readings through the probed health payloads. Daily ledger history is not current live provider billing. The complete tab verification was interrupted by a stalled browser inspection call; no paper-derived usability score is claimed.
