# Structured GitHub README compiler

`tools/readme_compiler.py` builds `README.md` from a project-owned `README.nougen.json` manifest. It has no third-party runtime dependencies. Section order, badges, links, and Markdown bodies stay explicit in the manifest; the compiler adds consistent headings and a table of contents. Semantic emoji are selected deterministically from section titles and optional keywords, with a per-section override or opt-out.

The compiler is deterministic and fail-closed: it rejects duplicate JSON keys, unknown manifest fields, unsupported schema versions, malformed URLs, duplicate anchors, oversized inputs, and paths that escape the project. Writes use a same-directory temporary file and atomic replacement. Unchanged output is left untouched, including its modification time.

## Start in a GitHub repository

```powershell
python ~\Outpost\NouGen\tools\readme_compiler.py draft C:\path\to\repo --output README.nougen.draft.json
# Review, then copy the accepted draft to README.nougen.json.
python ~\Outpost\NouGen\tools\readme_compiler.py compile C:\path\to\repo
python ~\Outpost\NouGen\tools\readme_compiler.py check C:\path\to\repo
```

`init` reads the project name and description from `pyproject.toml` or `package.json` when available. It creates a starter manifest and does not replace an existing one unless `--force` is passed. A forced manifest replacement saves the prior file as `README.nougen.json.pre-nougen.bak`; it will not replace an existing backup. Empty starter sections are skipped when compiling.

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

Each section uses exactly one of `content` or `file`. File paths are relative to the project directory and cannot escape it. `emoji` accepts `auto` (default), `none`, or a custom emoji string. Automatic choices use keyword boundaries, so a word such as “latest” does not accidentally match “test”.

Unknown fields are errors to catch typos early. `schema_version` currently supports `1`. Badges must use absolute HTTP(S) image URLs; link targets can also be project-relative paths or anchors. Section files are UTF-8 text and are limited to 1 MB. The manifest is limited to 2 MB, a previous README/archive snapshot to 20 MB, and generated output to 5 MB.

## Commands

- `init [project_dir] [--manifest README.nougen.json] [--force]` creates starter JSON.
- `draft [project_dir] [--source PATH ...] [--model TAG] [--host URL] [--output FILE]` asks local Ollama for a validated manifest draft.
- `compile [project_dir] [--manifest ...] [--output README.md]` writes compiled Markdown.
- `compile ... --dry-run` prints the result without writing.
- `compile ... --check` is an alias for the read-only freshness check.
- `compile ... --force` archives an unmanaged existing README before taking it over.
- `compile ... --archive-limit 10` retains ten distinct previous versions (default).
- `check [project_dir] [--manifest ...] [--output README.md] [--diff]` exits 1 when output is missing or stale; `--diff` prints a unified diff.
- `history [project_dir] [--output README.md]` lists verified snapshots, newest first.
- `restore <snapshot-path> [project_dir] [--output README.md]` archives the current README and restores a snapshot listed by `history`.

Each replaced README is saved beneath `.readme-archive/` using a UTC timestamp and a SHA-256 content fingerprint. The archive retains up to ten distinct prior versions per output file. After a successful replacement, only older compiler-named snapshots whose content hashes validate are pruned. To roll back, run `history`, then pass the listed snapshot path to `restore`. Keep `.readme-archive/` in version control if the history should travel with the repository.

The compiler preserves inline body Markdown except for trimming surrounding whitespace; section files are normalized to LF line endings. `draft` is an optional Ollama authoring aid. It reads only the root README, `pyproject.toml`, `package.json`, and license files by default; pass additional project-relative text files with `--source docs/guide.md`. It sends bounded excerpts to a loopback Ollama endpoint (default `http://127.0.0.1:11434`) using `gemma4:e2b-qat`, or the model set by `NOUGEN_README_MODEL`. Use `--model` and `--host` to override them. Drafting never edits the README or canonical manifest: it prints JSON unless `--output` names a separate review file. Review the result, then copy or rename it to `README.nougen.json` and run `compile`. Output files are never replaced unless `--force` is explicit. The model output is validated by the same compiler rules before it is shown or saved. No cloud fallback is used.

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
