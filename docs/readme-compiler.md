# Structured GitHub README compiler

`tools/readme_compiler.py` builds `README.md` from a project-owned `README.nougen.json` manifest. It has no third-party runtime dependencies. Section order, badges, links, and Markdown bodies stay explicit in the manifest; the compiler adds consistent headings and a table of contents. Semantic emoji are selected deterministically from section titles and optional keywords, with a per-section override or opt-out.

The compiler is deterministic and fail-closed: it rejects duplicate JSON keys, unknown manifest fields, unsupported schema versions, malformed URLs, duplicate anchors, oversized inputs, and paths that escape the project. Writes use a same-directory temporary file and atomic replacement. Unchanged output is left untouched, including its modification time. Optional extensions cover fragment includes, multi-file merge, footer blocks, profile manifests, recursive compilation, an interactive questionnaire, heuristic auto-prefill, and a baseline truth store — all declared in the manifest, all optional; a plain v1 manifest compiles exactly as before.

**Verbatim content guarantee.** Section bodies pass through byte-identical: the compiler never rewrites body Markdown — no re-wrapping, no escaping, no link or heading changes. It only trims surrounding whitespace and normalizes CRLF to LF in file-sourced bodies. Fenced code blocks, tables, lists, and inline HTML survive rendering unchanged; the test suite asserts this on tricky content (see `tests/test_readme_compiler.py::test_verbatim_content`).

## Start in a GitHub repository

```powershell
python ~\Outpost\NouGen\tools\readme_compiler.py draft C:\path\to\repo --output README.nougen.draft.json
# Review, then copy the accepted draft to README.nougen.json.
python ~\Outpost\NouGen\tools\readme_compiler.py compile C:\path\to\repo
python ~\Outpost\NouGen\tools\readme_compiler.py check C:\path\to\repo
python ~\Outpost\NouGen\tools\readme_compiler.py ask C:\path\to\repo
python ~\Outpost\NouGen\tools\readme_compiler.py init --auto C:\path\to\repo
python ~\Outpost\NouGen\tools\readme_compiler.py compile --recurse C:\path\to\repo
```

`init` reads the project name and description from `pyproject.toml` or `package.json` when available. It creates a starter manifest and does not replace an existing one unless `--force` is passed. A forced manifest replacement saves the prior file as `README.nougen.json.pre-nougen.bak`; it will not replace an existing backup. Empty starter sections are skipped when compiling — and `compile`/`check` report them on stderr as a deterministic sorted list (`dropped empty sections: Contributing, Features`), so what vanished is confirmed rather than silently gone.

`init --from-readme` prefills the manifest from the project's existing `README.md` instead of the generic skeleton: title is the first H1 verbatim (never title-cased), description is the first paragraph after the H1, sections are the H2 headings in order with body content verbatim, and the manifest records `source_readme_sha256` (the SHA-256 of the source README; `compile` ignores it for output, so it never changes the rendered README). If there is no `README.md`, or it is empty, `init --from-readme` warns loudly on stderr and marks every starter section `[guess]` — it never silently produces a plausible-looking manifest from nothing. `init --auto` on a directory with no README and no recognizable project files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, `LICENSE`, …) likewise warns on stderr that the manifest is all guesses. The directory name is used verbatim as the fallback title — `NuStack1` stays `NuStack1`, never `Nustack1`.

If `README.md` already exists and is not marked as compiler-managed, `compile` refuses to replace it. Review `--dry-run`, then pass `--force` to take over. The current README is archived before replacement. Generated output starts with a management marker; subsequent compiles can update it without `--force`.

## Manifest shape

```json
{
  "$schema": "https://raw.githubusercontent.com/Who-Visions/NouGenShards/main/schemas/readme-manifest.schema.json",
  "schema_version": 1,
  "project": {
    "title": "Example Project",
    "description": "A short, plain-language summary.",
    "emoji": ""
  },
  "table_of_contents": true,
  "badges": [
    {
      "label": "Build status",
      "image": "https://example.com/badge.svg",
      "url": "https://example.com/actions"
    }
  ],
  "sections": [
    {
      "title": "Quick Start",
      "keywords": ["install"],
      "content": "```sh\nnpm install\n```"
    },
    {
      "title": "Architecture",
      "file": "docs/architecture.md",
      "emoji": "🏗️"
    },
    {
      "title": "License",
      "content": "See [LICENSE](LICENSE).",
      "emoji": "none"
    }
  ],
  "links": [
    {"label": "Documentation", "url": "https://example.com/docs"}
  ]
}
```

Each section uses exactly one of `content`, `file`, or `merge` (an ordered list of files concatenated into one section). File paths are relative to the project directory and cannot escape it. Section bodies may also use `#include "path"` directives, resolved project-relative with a depth cap; a missing file or a cycle is an error, never a silent skip. `emoji` accepts `auto` (default), `none`, or a custom emoji string. Automatic choices use keyword boundaries, so a word such as “latest” does not accidentally match “test”.

Unknown fields are errors to catch typos early. `schema_version` currently supports `1`. Badges must use absolute HTTP(S) image URLs; link targets can also be project-relative paths or anchors. Badge links may be in-page anchors (`#overview`, `#-hardware-integration` — validated for form, never rejected for being an anchor); relative badge links are left as-is and are **not** rewritten against any repo URL (documented limitation — rewrite them to absolute URLs by hand when the README is read outside the repo). Section files are UTF-8 text and are limited to 1 MB. The manifest is limited to 2 MB, a previous README/archive snapshot to 20 MB, and generated output to 5 MB.

Optional top-level fields `banner`, `subtitle`, and `status` render under the title, in that order after the title and before the description: `subtitle` is a plain one-line subtitle, `status` renders as `**Status:** <status>`, and `banner` is a verbatim block (for ASCII-art banners — surrounding whitespace trimmed, internal lines untouched). `source_readme_sha256` is provenance only and never affects output. A section title that already starts with its emoji (explicit or auto-resolved, e.g. title `🚀 Quick Start` with emoji `🚀`) produces a stderr warning at compile/check time — the heading would otherwise show the emoji twice — but still compiles.

`--output` accepts an absolute path and uses it as-is; a relative path is resolved inside the project directory (an absolute path used to double up as `<project>/<absolute-path>`).

## Commands

- `init [project_dir] [--manifest README.nougen.json] [--force]` creates starter JSON.
- `init --from-readme` prefills from the existing `README.md` (first H1 verbatim as title, first paragraph as description, H2 sections verbatim) and records `source_readme_sha256`. With no README it warns loudly and marks the manifest all-`[guess]`.
- `init --auto` prefills starter sections from project files (pyproject.toml, package.json, Cargo.toml, go.mod, Makefile, LICENSE); every prefilled line is labelled `[guess]`. `compile` warns about guess sections instead of failing. On an empty project (no README, no recognizable project files) it warns on stderr that the manifest is all guesses.
- `ask [project_dir] [--answers FILE] [--output FILE] [--apply] [--force]` runs the interactive questionnaire and writes a draft manifest (or the canonical manifest with `--apply`). `--answers FILE` makes the flow non-interactive and deterministic.
- `draft [project_dir] [--source PATH ...] [--model TAG] [--host URL] [--output FILE]` asks local Ollama for a validated manifest draft.
- `compile [project_dir] [--manifest ...] [--output README.md]` writes compiled Markdown.
- `compile --recurse [--recurse-depth N]` also compiles child dirs with their own manifest, sorted, with a roll-up.
- `compile --write-baseline` records `.readme-baseline.json` (SHA-256 of the manifest, the output, and every section file) after compiling.
- `check --baseline` also verifies the stored baseline hashes.
- `compile ... --dry-run` prints the result without writing.
- `compile ... --check` is an alias for the read-only freshness check.
- `compile ... --force` archives an unmanaged existing README before taking it over.
- `compile ... --archive-limit 10` retains ten distinct previous versions (default).
- `check [project_dir] [--manifest ...] [--output README.md] [--diff]` exits 1 when output is missing or stale; `--diff` prints a unified diff.
- `history [project_dir] [--output README.md]` lists verified snapshots, newest first.
- `restore <snapshot-path> [project_dir] [--output README.md]` archives the current README and restores a snapshot listed by `history`.

Each replaced README is saved beneath `.readme-archive/` using a UTC timestamp and a SHA-256 content fingerprint. The archive retains up to ten distinct prior versions per output file. After a successful replacement, only older compiler-named snapshots whose content hashes validate are pruned. To roll back, run `history`, then pass the listed snapshot path to `restore`. Keep `.readme-archive/` in version control if the history should travel with the repository.

The compiler preserves inline body Markdown except for trimming surrounding whitespace; section files are normalized to LF line endings. `draft` is an optional Ollama authoring aid. It reads only the root README, `pyproject.toml`, `package.json`, and license files by default; pass additional project-relative text files with `--source docs/guide.md`. It sends bounded excerpts to a loopback Ollama endpoint (default `http://127.0.0.1:11434`) using `gemma4:e2b-qat`, or the model set by `NOUGEN_README_MODEL`. Use `--model` and `--host` to override them. Drafting never edits the README or canonical manifest: it prints JSON unless `--output` names a separate review file. Review the result, then copy or rename it to `README.nougen.json` and run `compile`. Output files are never replaced unless `--force` is explicit. The model output is validated by the same compiler rules before it is shown or saved. No cloud fallback is used.

## Profile manifests

Set `"kind": "profile"` and add `identity` (name, headline, tagline), plus optional `layers` (name, project, description), `flagships` (repo, role, description), and `theme` (preset, primary, secondary). Presets are small deterministic layout variants: `control-plane`, `editorial`, `terminal`, `minimal`. Emoji headings follow the preset (`editorial` and `minimal` render plain headings). A profile manifest still uses the same `project` and `sections` fields as a project manifest.

## Footer

`"footer"` is a string, or an object with exactly one of `file` or `text`. It is appended after Links.

## Baseline truth store

`compile --write-baseline` records SHA-256 hashes of the manifest, the generated output, and every section file in `.readme-baseline.json`. `check --baseline` compares the current files against that record and reports mismatches (manifest changed, output changed, section file changed or missing). Recompile with `--write-baseline` to record a new baseline.

## Smart emoji map

| Section meaning | Marker |
|---|---|
| Overview or about | 🧠 |
| Features | ✨ |
| Install or quick start | 🚀 |
| Usage and examples | 🧭 |
| Architecture | 🏗️ |
| Configuration | ⚙️ |
| API | 🔌 |
| Security and privacy | 🔐 |
| Tests | 🧪 |
| Deployment | 🚢 |
| Roadmap | 🗺️ |
| Contributing | 🤝 |
| License | 📄 |
| Troubleshooting or FAQ | 🩺 |
| Support or community | 💬 |

Unknown section names get the neutral 📌 marker. Set `emoji: "none"` when a heading should remain plain.

Provenance for the ideas absorbed into this compiler: `docs/readme-compiler-cousins.md`.
