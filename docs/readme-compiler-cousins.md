# README compiler — provenance record

> This file is the provenance record for the ideas absorbed into
`tools/readme_compiler.py`. It was written during the universal-merge
work (2026-11-18) and is kept verbatim. The compiler itself carries no
cousin names — it reads as if NouGen wrote it from scratch. The GPLv3
cousin (denwong47/readme-compiler) contributed ideas only; no code was
copied from it.

---

# Cousins — feature matrix

Dave's compiler is the base. Everything else is an idea absorbed into it.
All six cousins were pulled 2026-11-18 via codeload tarballs into `cousins/`
(see each `SOURCE.md` for URL, branch, license). No cousin code was copied
into `universal_readme.py` except where the license allows and the idea was
reimplemented from scratch in stdlib Python; denwong47 is GPLv3, so its
mechanisms were reimplemented, never copied.

## The base

| Source | What it does | Status in the universal compiler |
|---|---|---|
| **Dave — Who-Visions/NouGenShards `tools/readme_compiler.py`** (928 lines, stdlib-only) | Builds README.md from a `README.nougen.json` manifest (schema v1). Commands init/draft/compile/check/history/restore. Deterministic, fail-closed, atomic writes, `.readme-archive/` keeps 10 versions, refuses unmanaged READMEs without `--force`. Smart emoji from section titles. `draft` uses local Ollama only. | **The core, carried over.** Same CLI, same manifest v1, same managed marker. A plain v1 manifest compiles byte-identical under both compilers (verified by selftest). |

## The cousins

| Cousin | Language / License | What it does | Taken into the universal compiler | Not taken, and why |
|---|---|---|---|---|
| **denwong47/readme-compiler** — "Resolve readme files" | Python / **GPLv3** | Walks a repo, renders `.readme.source/*.md` fragments with Django templates, applies a post-render Transformer pipeline (link rewriting, header spacers, footer injection), writes `.readme/*.md` + README.md. Pre-commit hook mode. | Include/fragment resolution (reimplemented as `#include "path"`), footer injection (`footer` field), recursive per-directory compile idea, transformer-pipeline shape (spacing normalizer + footer append). | Django itself (stdlib-only rule); the GPLv3 code (reimplemented from the idea, never copied). |
| **seyLu/md-compile** — "Compile multiple markdowns into one README" | Python / MIT, repo archived | `markdown/main.md` holds `#include "section"` directives; sections in `markdown/sections/*.md` are concatenated in order into `compiled.md`. Also ships a Flask/SCSS web previewer. | `#include "path"` directives (depth-capped, cycle-checked, root-confined) and ordered multi-file merge (section `"merge": [...]`). | The Flask web previewer (out of scope for a stdlib CLI; a `preview` that prints or serves is a future step, needs Dave's word). |
| **mrlane51/readmenow** — "Git README node compiler form" | JavaScript / MIT | Inquirer questionnaire (name, description, technologies, design, usage, contributors, author, license, email, GitHub) → fixed template README with TOC. Shipped code is buggy (requires a bogus `utils` module; the template choice is ignored). | The `ask` subcommand: same question set, merged with Glutey's. Writes a draft manifest by default, `--apply` for canonical, `--answers FILE` for deterministic non-interactive runs. | The fixed template (the manifest is the template now); the bugs. |
| **Glutey/AutoGenerator---ReadMe-compiler** — "Automatically generates a Readme file using Node.js" | JavaScript / **no LICENSE file** (package.json says ISC) | Inquirer questionnaire (title, description, install, usage, guide, test, email, GitHub, LinkedIn) → template README with a Questions/contact block. | Question set merged into `ask` (install/test/contact questions), contact block mapped to `links` (GitHub, LinkedIn, mailto). | Its code (unlicensed — ideas only). |
| **clockworkpc/recursive-readme-demo** — "Recursively Compile Submodule Readmes" | — / **no LICENSE file** | **Nothing pulled.** The repo contains a single file, `README.md`, with one line: `# recursive-readme-demo`. There is no implementation. | The idea only: `compile --recurse [--recurse-depth N]` compiles child dirs with their own manifest and prints a roll-up. | Nothing to copy — recorded honestly in `cousins/clockworkpc-recursive-readme-demo/SOURCE.md`. |
| **majiayu000/profile-control-plane** — "Compile a GitHub identity into an animated profile README" | TypeScript / MIT | Declarative `profile.yaml` (v1) → `profilectl init/build/preview/check`. 16 templates, 4 SVGs each (dark/light, reduced-motion), typed fail-closed errors, no token at render time, staged atomic output, never commits/pushes. | Profile manifest kind (`kind: "profile"` with `identity`/`layers`/`flagships`/`theme`), 4 deterministic layout presets (control-plane, editorial, terminal, minimal), `check` posture, staged output, "review before merge" rule. | The SVG artwork pipeline (16 templates × 4 SVGs) — out of scope for stdlib Python; presets here are layout variants, not artwork. |

## What the universal compiler adds that no cousin had

- **`init --auto`**: heuristic prefill from project files (pyproject/package.json/Cargo/go.mod/Makefile/LICENSE), every guess labelled `[guess]`; `compile` warns about guess sections instead of failing.
- **Baseline truth store**: `compile --write-baseline` records SHA-256 of the manifest, the output, and every section file in `.readme-baseline.json`; `check --baseline` verifies them (grounded in truth, never claims from memory).
- **Merge contract**: same CLI + same manifest v1 + same managed marker as Dave's, so the two compilers accept each other's output. Extension use is recorded in a second comment line, never by changing the first.
