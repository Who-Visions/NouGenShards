---
name: "mono-violet"
version: "0.1.1"
description: "One violet-branded console design system with four colorways: Dark, Light, Arcade and Hardcade. Colorways remap tokens only; layout, permissions, telemetry meaning and component behavior never change."
colors: {"--accent": "#a47bff", "--bad": "#ff8a8a", "--bg": "#0b0911", "--border": "#332b43", "--border-strong": "#7d7094", "--chart-1": "#a47bff", "--chart-2": "#4fd1e5", "--chart-3": "#f2b84b", "--chart-4": "#5bd6a0", "--control-ink": "#0b0911", "--extra": "#d2bbff", "--focus": "#d2bbff", "--good": "#4cc38a", "--muted": "#a79cb9", "--raised": "#211a30", "--surface": "#171321", "--text": "#f5f1ff", "--warn": "#e6aa3a"}
---

# mono-violet

## referenceWorld

Cloud and AI developer consoles (the model-API and cloud-resource consoles of the large providers, used as analogies, not authority), precision instrument panels, and for the optional colorways retro arcade cabinets (Arcade) and competitive hardware control surfaces (Hardcade). Hardcade is the GM's own aesthetic label, not a standardized UI category. Inside NouGen, docs/hardcade-lexicon.md uses Hardcade for the fleet command lexicon (relay verbs and moves); that document carries no color values, so the Hardcade palette in this spec is provisional.

## antiPatterns

Reject decorative gradients on data surfaces, backdrop blur on content, glow on text or chart marks, pill radii larger than the control, meaning carried by color alone, and any theme that moves, hides or renames a control. Arcade and Hardcade effects are opt-in and never the default.

## materiality

Dark and Light use opaque matte surfaces, fine dividers and violet as the single accent. Arcade uses flat rounded panels (16px) with warm secondary colors. Hardcade uses angular panels (2px radius), 2px outlines and no soft shadows. An optional decorative grid texture sits behind content on its own layer, is off by default, and never sits behind text or data. Glow is limited to the focus ring and one primary control, and only when effects are enabled.

## density

Compact operator density in every theme: 0.25rem spacing steps, tables and inspectors sized for scanning. Theme choice never changes spacing, column counts or information density.

## motionGrammar

Fast 140ms and base 220ms transitions for hover, selection and panel changes. Nonessential motion is disabled under prefers-reduced-motion. Arcade and Hardcade may add stepped or pixel-style transitions only when effects are on. No looping animation on data, status or charts.

## interactionPhysics

All four colorways share the same components and behavior. A theme change applies instantly, follows the operating-system preference when nothing is chosen, and for signed-in users persists on the server so it follows them across devices. Every route authorizes on the server regardless of theme.

## informationHierarchy

Same five-element console shell in every theme: organization and project switcher, global command search, categorized sidebar, main work surface and optional inspector. The primary reading of each page (health, the active resource, the chart) is identical across themes; a colorway changes atmosphere, never hierarchy.

## responsiveBehavior

Navigation collapses to a drawer at narrow widths and the inspector becomes a panel. Tables and code scroll inside their own containers. Panels use container width, long identifiers wrap, and no theme adds a fixed width that breaks a phone layout.

## Accessibility

Body text and muted text meet 4.5:1 on their surface in all four themes, status text meets 4.5:1, focus indicators and chart marks meet 3:1, and every contrast pair is checked by the compiler for every theme. Decorative effects are off by default, contrast takes priority over decoration, and the focus ring stays visible in every colorway. Respect forced-colors and reduced-motion.

## brandVoice

Mono Violet stays the brand in every colorway. Labels and errors are plain and concrete, with identical wording across themes. Arcade and Hardcade may add flavor only in decorative text, never in controls, errors or billing copy.

## iconography

Monochrome line icons with one stroke weight and the same glyphs in every theme; Hardcade may sharpen stroke terminals but not change meaning. Unfamiliar symbols are paired with text.

## dataViz

Four chart series tokens per theme, all at least 3:1 on the surface, with labeled axes and legends. Good, warning and error keep fixed meanings in every theme and always pair color with a text label or shape, so a colorway cannot reverse a signal.

## stateGrammar

Specify default, hover, focus, selected, disabled, loading, empty, error, stale, offline and permission-denied states per component. Status chips read LIVE, WARN and ERROR as text. Colorways remap color only, never the set of states or what they mean.

## provenance

Dark, Light, Arcade and Hardcade primary, background, surface and text hex values are observed from a GM-supplied brief of 2026-11-10 written by an outside assistant. Muted, border, status, chart and radius tokens are NouGen derivations chosen so the compiler contrast checks pass. The brief did not verify Hardcade as an established category and neither does this spec. The brief itself says to check contrast per theme instead of assuming WCAG AA, which this spec does. Recovery check 2026-11-10: 34 files in NouGenShards mention Hardcade and none put a color value near it, so no canonical Hardcade palette was found. The Hardcade tokens here come from the brief and stay provisional until the GM supplies or points to the canon.
