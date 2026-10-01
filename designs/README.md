# NouGenDesigns v0

`design.json` is the reviewed specification. The compiler emits the portable
`manifest.json`, prose-first `DESIGN.md`, `tokens.css`, and `mutations.json`.
The latter is a reviewable mutation plan, not executable arbitrary code.

```sh
python tools/nougendesigns.py inspect ui/src
python tools/nougendesigns.py compile designs/nougen-core/design.json designs/nougen-core
python tools/nougendesigns.py lint designs/nougen-core/design.json --css ui/src/styles.css
python tools/nougendesigns.py check designs/nougen-core/design.json designs/nougen-core
python tools/nougendesigns.py diff before.json after.json
```

Repository adapters inspect CSS, HTML, TS and TSX files, exclude build and
dependency directories, and record hashes, observed custom properties,
component/control counts, and anti-pattern counts. `analyze` combines these
measurements with a saved brief and a reviewed profile to create a deterministic
review draft:

```sh
python tools/nougendesigns.py analyze ui/src brief.md designs/nougen-core/design.json .reports/design-review
```

The draft contains `DESIGN.md`, `tokens.css`, `manifest.json`, `mutations.json`,
`analysis.json`, and `lint.json`. The brief is preserved verbatim. The reviewed
profile remains the source of design intent; source analysis does not invent
palette or interaction decisions, and recommendations never rewrite source
files. Screenshots register binary hashes only, with visual interpretation
supplied separately as inferred prose. This deterministic pass does not fetch
sites or infer design intent from pixels.
Local Ollama can draft prose from private evidence; NouGenOpen can review a
text-only contract. Review their output before entering it in a specification.

All 14 dialect sections require non-empty prose. Tokens are sorted and reject
CSS declaration injection. Evidence distinguishes observed, inferred and
invented choices. Contrast checks cover declared pairs across all themes.
Lint rejects gradients, blur glass, giant pill radii and glow shadows. These
measurable signatures do not substitute for a human composition review.
`check` fails on generated drift; `diff` prints semantic specification changes.
Lint exits 1 on failure; input errors exit 2 with a concise diagnostic.

Donor conventions: https://github.com/google-labs-code/design.md and the existing
NouGen design skill. No donor source is vendored. Local Ollama drafted the
design intent; Codex reviewed it and implemented the compiler. NouGenOpen's
Qwen review supplied acceptance-test categories.
