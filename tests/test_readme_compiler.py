#!/usr/bin/env python3
"""Tests for tools/readme_compiler.py — the native NouGen README compiler.

Run under pytest:
    .venv/bin/python -m pytest tests/test_readme_compiler.py --noconftest
Run standalone (no pytest needed):
    python3 tests/test_readme_compiler.py

Deterministic, no network, no Ollama. Covers: v1 byte-compatibility against
the golden output of the pre-merge compiler, every extension, determinism,
fail-closed validation, baseline truth store, ask, recurse, history/restore,
init --auto guesses.

Note on --noconftest: the suite conftest imports nougen_shards and isolates
the secrets vault; this module never touches the vault or the shard store,
so it skips conftest.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import pytest
    _parametrize = pytest.mark.parametrize
except ImportError:  # standalone run without pytest installed
    pytest = None  # type: ignore[assignment]

    def _parametrize(*args, **kwargs):  # type: ignore[no-redef]
        def deco(fn):
            return fn
        return deco

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "readme_compiler"
COMPILER_PATH = REPO_ROOT / "tools" / "readme_compiler.py"


def _load_compiler():
    spec = importlib.util.spec_from_file_location("readme_compiler_under_test", COMPILER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RC = _load_compiler()

PLAIN_V1 = {
    "$schema": "https://raw.githubusercontent.com/Who-Visions/NouGenShards/main/schemas/readme-manifest.schema.json",
    "schema_version": 1,
    "project": {"title": "Plain Project", "description": "Plain v1 manifest.", "emoji": ""},
    "table_of_contents": True,
    "badges": [{"label": "Build", "image": "https://example.com/badge.svg", "url": "https://example.com/actions"}],
    "sections": [
        {"title": "Overview", "content": "Plain overview.", "emoji": "auto"},
        {"title": "Quick Start", "content": "```sh\nmake install\n```", "emoji": "auto"},
        {"title": "License", "content": "See [LICENSE](LICENSE).", "emoji": "auto"},
    ],
    "links": [{"label": "Docs", "url": "https://example.com/docs"}],
}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fresh_v1() -> dict:
    return json.loads(json.dumps(PLAIN_V1))


def test_v1_byte_compatible(tmp_path: Path) -> None:
    """A plain v1 manifest compiles byte-identical to the pre-merge compiler."""
    golden = (FIXTURES / "plain-v1.expected.md").read_text(encoding="utf-8")
    out = RC.compile_readme(_fresh_v1(), tmp_path)
    assert out == golden, "v1 output drifted from the pre-merge compiler"


def test_sample(tmp_path: Path) -> None:
    """Sample manifest: includes, merge, footer, extension marker."""
    project = tmp_path / "sample"
    shutil.copytree(FIXTURES / "sample", project)
    assert RC.main(["compile", str(project)]) == 0
    out = (project / "README.md").read_text(encoding="utf-8")
    assert "Install note, pulled in by `#include`" in out
    assert out.index("Part one of the combined guide.") < out.index("Part two of the combined guide.")
    assert "Built with the NouGen README compiler." in out
    assert "nougen-readme-compiler: extensions:" in out
    assert out.startswith("<!-- nougen-readme-compiler: v1 -->")
    assert RC.main(["check", str(project)]) == 0
    first = (project / "README.md").read_bytes()
    mtime1 = (project / "README.md").stat().st_mtime_ns
    time.sleep(0.01)
    assert RC.main(["compile", str(project)]) == 0
    assert (project / "README.md").read_bytes() == first
    assert (project / "README.md").stat().st_mtime_ns == mtime1
    r1 = subprocess.run([sys.executable, str(COMPILER_PATH), "compile", "--dry-run", str(project)],
                        capture_output=True, text=True)
    r2 = subprocess.run([sys.executable, str(COMPILER_PATH), "compile", "--dry-run", str(project)],
                        capture_output=True, text=True)
    assert r1.stdout == r2.stdout and r1.returncode == 0


def test_recurse(tmp_path: Path) -> None:
    project = tmp_path / "recurse_sample"
    shutil.copytree(FIXTURES / "sample", project)
    assert RC.main(["compile", "--recurse", str(project)]) == 0
    assert (project / "sub" / "README.md").is_file()
    assert "Child project overview." in (project / "sub" / "README.md").read_text(encoding="utf-8")
    assert RC.main(["check", "--recurse", str(project)]) == 0


def test_profile(tmp_path: Path) -> None:
    project = tmp_path / "profile"
    shutil.copytree(FIXTURES / "sample-profile", project)
    assert RC.main(["compile", str(project)]) == 0
    out = (project / "README.md").read_text(encoding="utf-8")
    assert "Sample Person" in out and "BUILDER OF SYSTEMS" in out
    assert "| DIRECT | nougen-readme |" in out
    assert "nougen-readme" in out and "COMPILE" in out
    assert "## 📚" not in out and "## 🚀" not in out
    assert "primary #00A7D1" in out


def test_ask(tmp_path: Path) -> None:
    project = tmp_path / "ask"
    project.mkdir()
    answers = {
        "title": "Asked Project", "description": "Built from answers.",
        "install": "pip install asked", "usage": "asked --help",
        "license": "MIT", "github": "example/asked", "email": "a@example.com",
    }
    _write_json(project / "answers.json", answers)
    assert RC.main(["ask", "--answers", "answers.json", "--apply", str(project)]) == 0
    manifest = json.loads((project / "README.nougen.json").read_text(encoding="utf-8"))
    assert manifest["project"]["title"] == "Asked Project"
    assert RC.main(["compile", str(project)]) == 0
    out = (project / "README.md").read_text(encoding="utf-8")
    assert "pip install asked" in out
    assert "https://github.com/example/asked" in out and "mailto:a@example.com" in out
    project2 = tmp_path / "ask2"
    project2.mkdir()
    _write_json(project2 / "answers.json", answers)
    assert RC.main(["ask", "--answers", "answers.json", str(project2)]) == 0
    assert (project2 / "README.nougen.draft.json").is_file()
    assert not (project2 / "README.nougen.json").exists()


def test_baseline(tmp_path: Path) -> None:
    project = tmp_path / "baseline_sample"
    shutil.copytree(FIXTURES / "sample", project)
    assert RC.main(["compile", "--write-baseline", str(project)]) == 0
    assert (project / ".readme-baseline.json").is_file()
    assert RC.main(["check", "--baseline", str(project)]) == 0
    (project / "docs" / "part-one.md").write_text("Part one, EDITED.\n", encoding="utf-8")
    assert RC.main(["check", "--baseline", str(project)]) == 1
    assert RC.main(["compile", str(project)]) == 0
    assert RC.main(["check", "--baseline", str(project)]) == 1
    assert RC.main(["compile", "--write-baseline", str(project)]) == 0
    assert RC.main(["check", "--baseline", str(project)]) == 0


def _fail_closed_case(tmp_path: Path, label: str, manifest: dict, files: dict[str, str] | None = None) -> None:
    project = tmp_path / ("fail_" + label.replace(" ", "_"))
    project.mkdir()
    _write_json(project / "README.nougen.json", manifest)
    for name, body in (files or {}).items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    try:
        RC.compile_readme(RC._read_manifest(project / "README.nougen.json"), project)
    except RC.ReadmeError:
        return
    raise AssertionError(f"fail-closed case compiled without error: {label}")


def _fail_closed_manifests() -> list[tuple[str, dict, dict[str, str] | None]]:
    bad = _fresh_v1(); bad["surprise"] = 1
    cases: list[tuple[str, dict, dict[str, str] | None]] = [("unknown field", bad, None)]
    bad = _fresh_v1()
    bad["sections"] = [{"title": "Overview", "content": "a"}, {"title": "Overview", "content": "b"}]
    cases.append(("duplicate anchor", bad, None))
    bad = _fresh_v1()
    bad["sections"] = [{"title": "A", "content": '#include "a.md"'}]
    cases.append(("missing include", bad, None))
    bad = _fresh_v1()
    bad["sections"] = [{"title": "A", "content": '#include "loop.md"'}]
    cases.append(("include cycle", bad, {"loop.md": '#include "loop.md"\n'}))
    bad = _fresh_v1()
    bad["sections"] = [{"title": "A", "content": '#include "../escape.md"'}]
    cases.append(("include path escape", bad, None))
    bad = _fresh_v1()
    bad["sections"] = [{"title": "A", "content": "x", "merge": ["a.md"]}]
    cases.append(("content+merge conflict", bad, None))
    bad = _fresh_v1(); bad["kind"] = "profile"
    cases.append(("profile without identity", bad, None))
    bad = _fresh_v1(); bad["kind"] = "profile"
    bad["identity"] = {"name": "X"}
    bad["theme"] = {"preset": "nope"}
    cases.append(("bad preset", bad, None))
    return cases


@_parametrize("label,manifest,files", _fail_closed_manifests())
def test_fail_closed(tmp_path: Path, label: str, manifest: dict, files: dict[str, str] | None) -> None:
    _fail_closed_case(tmp_path, label, manifest, files)


def test_init_auto(tmp_path: Path) -> None:
    project = tmp_path / "auto"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "auto-proj"\ndescription = "Auto."\n', encoding="utf-8")
    (project / "LICENSE").write_text("MIT\n", encoding="utf-8")
    assert RC.main(["init", "--auto", str(project)]) == 0
    manifest = json.loads((project / "README.nougen.json").read_text(encoding="utf-8"))
    quick = next(s for s in manifest["sections"] if s["title"] == "Quick Start")
    assert "[guess]" in quick["content"]
    assert RC.main(["compile", str(project)]) == 0


def test_history_restore(tmp_path: Path) -> None:
    project = tmp_path / "history_sample"
    shutil.copytree(FIXTURES / "sample", project)
    RC.main(["compile", str(project)])
    first = (project / "README.md").read_bytes()
    manifest = json.loads((project / "README.nougen.json").read_text(encoding="utf-8"))
    manifest["project"]["description"] = "Changed description."
    _write_json(project / "README.nougen.json", manifest)
    RC.main(["compile", str(project)])
    second = (project / "README.md").read_bytes()
    assert first != second
    snapshots = sorted((project / ".readme-archive" / "README.md").glob("*.md"))
    assert len(snapshots) == 1
    assert RC.main(["history", str(project)]) == 0
    assert RC.main(["restore", snapshots[0].relative_to(project).as_posix(), str(project)]) == 0
    assert (project / "README.md").read_bytes() == first


def test_init_from_readme(tmp_path: Path) -> None:
    """init --from-readme: H1 verbatim, first paragraph, H2 sections verbatim, SHA recorded."""
    project = tmp_path / "MyCoolRepo"
    project.mkdir()
    readme = (
        "# MyCoolRepo Title\n\n"
        "First paragraph description here.\n"
        "Second line of the same paragraph.\n\n"
        "## Overview\n\n"
        "Overview body, verbatim *with* `code`.\n\n"
        "## Quick Start\n\n"
        "```sh\nmake install\n```\n"
    )
    (project / "README.md").write_text(readme, encoding="utf-8")
    assert RC.main(["init", "--from-readme", str(project)]) == 0
    manifest = json.loads((project / "README.nougen.json").read_text(encoding="utf-8"))
    assert manifest["project"]["title"] == "MyCoolRepo Title"
    assert manifest["project"]["description"] == "First paragraph description here. Second line of the same paragraph."
    assert [s["title"] for s in manifest["sections"]] == ["Overview", "Quick Start"]
    assert manifest["sections"][0]["content"] == "Overview body, verbatim *with* `code`."
    assert manifest["sections"][1]["content"] == "```sh\nmake install\n```"
    assert manifest["source_readme_sha256"] == hashlib.sha256(readme.encode("utf-8")).hexdigest()
    assert RC.main(["compile", "--force", str(project)]) == 0
    out = (project / "README.md").read_text(encoding="utf-8")
    assert "# MyCoolRepo Title" in out and "Overview body, verbatim *with* `code`." in out


def test_init_from_readme_missing(tmp_path: Path) -> None:
    """init --from-readme with no README: loud warning, manifest all [guess]."""
    project = tmp_path / "empty"
    project.mkdir()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert RC.main(["init", "--from-readme", str(project)]) == 0
    assert "no README.md" in err.getvalue() and "all [guess]" in err.getvalue()
    manifest = json.loads((project / "README.nougen.json").read_text(encoding="utf-8"))
    assert manifest["project"]["title"] == "empty"
    assert manifest["sections"] and all("[guess]" in s["content"] for s in manifest["sections"])
    assert "source_readme_sha256" not in manifest


def test_init_auto_verbatim_title(tmp_path: Path) -> None:
    """init --auto uses the directory name verbatim — NuStack1, never Nustack1."""
    project = tmp_path / "NuStack1"
    project.mkdir()
    assert RC.main(["init", "--auto", str(project)]) == 0
    manifest = json.loads((project / "README.nougen.json").read_text(encoding="utf-8"))
    assert manifest["project"]["title"] == "NuStack1"


def test_init_auto_empty_project_warning(tmp_path: Path) -> None:
    """init --auto on an empty dir warns the manifest is all guesses."""
    project = tmp_path / "bare"
    project.mkdir()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert RC.main(["init", "--auto", str(project)]) == 0
    assert "all guesses" in err.getvalue()


def test_absolute_output(tmp_path: Path) -> None:
    """compile/check --output with an absolute path uses it as-is (no doubling)."""
    project = tmp_path / "sample"
    shutil.copytree(FIXTURES / "sample", project)
    target = tmp_path / "elsewhere" / "README-abs.md"
    assert RC.main(["compile", str(project), "--output", str(target)]) == 0
    assert target.is_file()
    assert "Plain inline content section." in target.read_text(encoding="utf-8")
    assert not (project / "elsewhere").exists()
    assert not (project / str(target).lstrip("/")).exists()
    assert RC.main(["check", str(project), "--output", str(target)]) == 0


def test_banner_status_subtitle(tmp_path: Path) -> None:
    """banner (verbatim), subtitle, status render under the title, in order."""
    manifest = _fresh_v1()
    manifest["subtitle"] = "Who Visions LLC | Compliance: March 2026"
    manifest["status"] = "v0.1 in progress"
    manifest["banner"] = "╔═══╗\n║ ART ║\n╚═══╝"
    out = RC.compile_readme(manifest, tmp_path)
    assert "# Plain Project" in out
    assert out.index("# Plain Project") < out.index("Who Visions LLC | Compliance: March 2026")
    assert out.index("Who Visions LLC | Compliance: March 2026") < out.index("**Status:** v0.1 in progress")
    assert out.index("**Status:** v0.1 in progress") < out.index("╔═══╗\n║ ART ║\n╚═══╝")
    assert out.index("╔═══╗\n║ ART ║\n╚═══╝") < out.index("Plain v1 manifest.")


def test_profile_banner_status_subtitle(tmp_path: Path) -> None:
    project = tmp_path / "profile"
    shutil.copytree(FIXTURES / "sample-profile", project)
    manifest = json.loads((project / "README.nougen.json").read_text(encoding="utf-8"))
    manifest["subtitle"] = "Profile subtitle"
    manifest["status"] = "active"
    manifest["banner"] = "BANNER"
    _write_json(project / "README.nougen.json", manifest)
    assert RC.main(["compile", str(project)]) == 0
    out = (project / "README.md").read_text(encoding="utf-8")
    assert "Profile subtitle" in out and "**Status:** active" in out and "BANNER" in out


def test_source_readme_sha_ignored(tmp_path: Path) -> None:
    """source_readme_sha256 is provenance only: output is identical with or without it."""
    plain = RC.compile_readme(_fresh_v1(), tmp_path)
    marked = _fresh_v1()
    marked["source_readme_sha256"] = "0" * 64
    assert RC.compile_readme(marked, tmp_path) == plain
    bad = _fresh_v1()
    bad["source_readme_sha256"] = "not-a-sha"
    try:
        RC.compile_readme(bad, tmp_path)
    except RC.ReadmeError:
        pass
    else:
        raise AssertionError("malformed source_readme_sha256 compiled without error")


def test_duplicate_emoji_warning(tmp_path: Path) -> None:
    """A section title that already starts with its emoji warns (stderr), still compiles."""
    manifest = _fresh_v1()
    manifest["sections"] = [{"title": "🚀 Quick Start", "content": "Go.", "emoji": "🚀"}]
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        out = RC.compile_readme(manifest, tmp_path)
    assert "already starts with its emoji" in err.getvalue()
    assert "## 🚀 🚀 Quick Start" in out


def test_verbatim_content(tmp_path: Path) -> None:
    """Section content passes through byte-identical — no rewriting."""
    body = (
        "Line *one* with `code` & <html> — ünïcode\n\n"
        "```sh\necho \"hi\"  # $HOME\n```\n\n"
        "- a\n- b\n\n"
        "| x | y |\n| --- | --- |\n| 1 | 2 |\n\n"
        "See [LICENSE](LICENSE) and https://example.com/a?b=c&d=e."
    )
    manifest = _fresh_v1()
    manifest["sections"] = [{"title": "Overview", "content": body, "emoji": "auto"}]
    out = RC.compile_readme(manifest, tmp_path)
    assert body in out, "section body was rewritten instead of passed through verbatim"


def test_badge_anchor_links(tmp_path: Path) -> None:
    """Badge links may be in-page anchors; relative links stay as-is."""
    manifest = _fresh_v1()
    manifest["badges"] = [
        {"label": "Hardware", "image": "https://example.com/badge.svg", "url": "#-hardware-integration"},
        {"label": "Overview", "image": "https://example.com/badge.svg", "url": "#overview"},
        {"label": "License", "image": "https://example.com/badge.svg", "url": "LICENSE"},
    ]
    out = RC.compile_readme(manifest, tmp_path)
    assert "](<#-hardware-integration>)" in out
    assert "](<#overview>)" in out
    assert "](<LICENSE>)" in out
    bad = _fresh_v1()
    bad["badges"] = [{"label": "Bad", "image": "https://example.com/badge.svg", "url": "#!"}]
    try:
        RC.compile_readme(bad, tmp_path)
    except RC.ReadmeError:
        pass
    else:
        raise AssertionError("malformed anchor badge link compiled without error")


def test_dropped_empty_sections_reported(tmp_path: Path) -> None:
    """Compile reports dropped empty sections as a deterministic sorted list on stderr."""
    manifest = _fresh_v1()
    manifest["sections"] = [
        {"title": "Overview", "content": "Kept.", "emoji": "auto"},
        {"title": "Zebra Empty", "content": "", "emoji": "auto"},
        {"title": "Alpha Empty", "content": "", "emoji": "auto"},
    ]
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        out = RC.compile_readme(manifest, tmp_path)
    assert "dropped empty sections: Alpha Empty, Zebra Empty" in err.getvalue()
    assert "Zebra Empty" not in out and "Alpha Empty" not in out


# ---------------------------------------------------------------------------
# Standalone runner (no pytest needed): python3 tests/test_readme_compiler.py
# ---------------------------------------------------------------------------

_STANDALONE_TESTS = [
    test_v1_byte_compatible,
    test_sample,
    test_recurse,
    test_profile,
    test_ask,
    test_baseline,
    test_init_auto,
    test_history_restore,
    test_init_from_readme,
    test_init_from_readme_missing,
    test_init_auto_verbatim_title,
    test_init_auto_empty_project_warning,
    test_absolute_output,
    test_banner_status_subtitle,
    test_profile_banner_status_subtitle,
    test_source_readme_sha_ignored,
    test_duplicate_emoji_warning,
    test_verbatim_content,
    test_badge_anchor_links,
    test_dropped_empty_sections_reported,
]


def _run_standalone() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nougen-readme-test-") as td:
        tmp = Path(td)
        for fn in _STANDALONE_TESTS:
            case_dir = tmp / fn.__name__
            case_dir.mkdir()
            try:
                fn(case_dir)
            except Exception as exc:  # noqa: BLE001 - report, don't crash
                print(f"[FAIL] {fn.__name__} — {exc}")
                failures.append(fn.__name__)
            else:
                print(f"[ok ] {fn.__name__}")
        for label, manifest, files in _fail_closed_manifests():
            case_dir = tmp / ("fail_" + label.replace(" ", "_"))
            try:
                _fail_closed_case(tmp, label, manifest, files)
            except Exception as exc:  # noqa: BLE001
                print(f"[FAIL] fail-closed: {label} — {exc}")
                failures.append(f"fail-closed: {label}")
            else:
                print(f"[ok ] fail-closed: {label}")
    if failures:
        print(f"\nFAILED: {len(failures)} case(s): {', '.join(failures)}")
        return 1
    print("\nOK: all cases passed, deterministic, no network, no Ollama")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
