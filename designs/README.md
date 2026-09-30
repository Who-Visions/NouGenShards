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

Repository adapters inspect CSS files, exclude build/dependency directories and
record hashes, observed tokens and anti-pattern counts. Site input uses a saved
HTML/CSS export; a brief uses a saved text file. Screenshots register binary
hashes, with visual interpretation supplied separately as inferred prose.
This v0 does not fetch sites or infer design intent from pixels automatically.
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
