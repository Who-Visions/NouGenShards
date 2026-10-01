# NouGen Context Mode

Inherit ../AGENTS.md: use NouGen Context Mode for all inspection, recall, search,
git reads, logs, test/build output and diagnostics. Analyze inside ctx_execute,
ctx_execute_file or ctx_batch_execute; return concise evidence, not raw dumps.
Native tools remain available for edits/writes and documented bounded fallback.

# UI design

Before changing a NouGen UI, read root DESIGN.md and the applicable brand package.
For the fleet workbench use designs/nougen-core/DESIGN.md. Preserve explicit
reference-world intent and evidence provenance. Change design.json, regenerate
the package, run its lint and drift checks, and verify the rendered interface
at desktop and narrow widths with keyboard focus and reduced motion.
