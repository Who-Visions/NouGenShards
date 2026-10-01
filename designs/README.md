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

## Recursive research is part of NouGenDesigns

```sh
python tools/nougendesigns.py discover 2609.00476 --depth 2 --max-papers 8
```

Use discover, review full sources, morph applicable principles in `design.json`,
compile, lint/check, then reassess the rendered interface. Discovery is the
explicit network stage; compilation stays deterministic and offline.
The catalogue records citation parents, depth, metadata, topic matches and errors.
Candidates become authority only after source and applicability review with
observed evidence separated from inferred adaptations.

See [discovery.json](discovery.json), [discovery-guide.md](discovery-guide.md),
and the reviewed [spatial adaptation](spatial-composition-morph.md).

Workspace-awareness rules and their evidence limits: [1910.03380 morph](workspace-awareness-morph.md).
