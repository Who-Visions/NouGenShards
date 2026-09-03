"""Skill registry: discovery, frontmatter parsing, matching, and doc parity."""
import re
from pathlib import Path

import pytest

import nougen_shards.skills as skills


def _write(root: Path, name: str, description: str, body: str = "Body text.") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    path = d / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_discovers_canonical_layout(tmp_path):
    _write(tmp_path, "design", "Author and audit design systems.")
    found = skills.discover([tmp_path])
    assert [s.name for s in found] == ["design"]
    assert found[0].description == "Author and audit design systems."
    assert "Body text." in found[0].body


def test_frontmatter_survives_crlf(tmp_path):
    """These files are authored on Windows; a LF-only parser silently sees none."""
    d = tmp_path / "winskill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\r\nname: winskill\r\ndescription: Written with CRLF.\r\n---\r\n\r\nBody.\r\n",
        encoding="utf-8", newline="",
    )
    found = skills.discover([tmp_path])
    assert len(found) == 1
    assert found[0].description == "Written with CRLF."


def test_frontmatter_strips_quotes_and_ignores_nested_keys():
    meta, body = skills.parse_frontmatter(
        '---\nname: "quoted"\ncolors:\n  brand: "#fff"\ndescription: A thing.\n---\nBody\n'
    )
    assert meta["name"] == "quoted"
    assert meta["description"] == "A thing."
    assert "brand" not in meta  # nested keys are out of scope, not guessed at
    assert body.strip() == "Body"


def test_no_frontmatter_returns_whole_text():
    meta, body = skills.parse_frontmatter("# Just a heading\n\ntext")
    assert meta == {}
    assert body.startswith("# Just a heading")


def test_legacy_flat_file_is_still_readable(tmp_path):
    """Skills evolved before the canonical layout must not be stranded."""
    (tmp_path / "old-skill-abc123.md").write_text(
        "# SKILL: something old\n\n## Grounding\nstuff\n", encoding="utf-8"
    )
    found = skills.discover([tmp_path])
    assert [s.name for s in found] == ["old-skill-abc123"]
    assert found[0].description  # derived from the first meaningful line


def test_earlier_root_shadows_later_on_name_collision(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    _write(first, "design", "Wins.")
    _write(second, "design", "Loses.")
    found = skills.discover([first, second])
    assert len(found) == 1
    assert found[0].description == "Wins."


def test_match_returns_governing_skill(tmp_path):
    _write(tmp_path, "design", "Author design systems, palettes and tokens.")
    _write(tmp_path, "accounting", "Reconcile ledgers and produce tax reports.")
    matched = skills.match("build a palette for a landing page", roots=[tmp_path])
    assert [s.name for s in matched] == ["design"]


def test_match_by_skill_name_in_task(tmp_path):
    _write(tmp_path, "design", "Unrelated wording entirely.")
    assert [s.name for s in skills.match("use the design skill", roots=[tmp_path])] == ["design"]


def test_match_ignores_stopwords(tmp_path):
    """Filler words must not make every skill match every task."""
    _write(tmp_path, "design", "Author design systems.")
    assert skills.match("can you do the thing for me", roots=[tmp_path]) == []


def test_match_threshold_is_env_configurable(tmp_path, monkeypatch):
    _write(tmp_path, "design", "Author design systems and palettes.")
    monkeypatch.setenv("NOUGEN_SKILL_MATCH_MIN", "2")
    assert skills.match("palettes", roots=[tmp_path]) == []
    monkeypatch.setenv("NOUGEN_SKILL_MATCH_MIN", "1")
    assert len(skills.match("palettes", roots=[tmp_path])) == 1


def test_roster_reports_empty_state(tmp_path):
    assert skills.roster([tmp_path]) == "(no skills installed)"


def test_skills_dir_env_overrides_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_SKILLS_DIR", str(tmp_path))
    assert skills.resolve_skill_roots() == [tmp_path]


def test_unreadable_root_is_skipped_not_fatal(tmp_path):
    assert skills.discover([tmp_path / "does-not-exist"]) == []


# --- Dual-canon guard -------------------------------------------------------
# The design SKILL.md states numeric floors that also live as constants in its
# validator. Nothing structurally ties them together, so this test is the tie:
# if either side changes alone, this fails.

_DESIGN_SKILL = Path(__file__).resolve().parents[1] / "skills" / "design" / "SKILL.md"
_DESIGN_VALIDATOR = Path(__file__).resolve().parents[1] / "skills" / "design" / "validate.py"


@pytest.mark.skipif(not _DESIGN_SKILL.is_file(), reason="design skill not installed")
def test_design_skill_prose_matches_validator_constants():
    prose = _DESIGN_SKILL.read_text(encoding="utf-8")
    code = _DESIGN_VALIDATOR.read_text(encoding="utf-8")

    def constant(key: str) -> int:
        found = re.search(rf'"{key}":\s*(\d+)', code)
        assert found, f"{key} not found in validate.py"
        return int(found.group(1))

    h2_floor = constant("NOUGEN_DESIGN_MIN_H2")
    token_floor = constant("NOUGEN_DESIGN_MIN_TOKENS")

    assert f"at least {h2_floor}" in prose, (
        f"SKILL.md must state the H2 floor of {h2_floor} that validate.py enforces"
    )
    assert f"{token_floor} custom properties" in prose, (
        f"SKILL.md must state the token floor of {token_floor} that validate.py enforces"
    )


@pytest.mark.skipif(not _DESIGN_SKILL.is_file(), reason="design skill not installed")
def test_design_skill_documents_a_real_validator_path():
    """A documented command that does not exist on a fresh clone is worse than none."""
    prose = _DESIGN_SKILL.read_text(encoding="utf-8")
    for cited in re.findall(r"python\s+(\S*validate\.py)", prose):
        resolved = Path(__file__).resolve().parents[1] / cited
        assert resolved.is_file(), f"SKILL.md cites {cited}, which does not exist"


# --- nougen-ctx skill verification -----------------------------------------
_NOUGEN_CTX_SKILL = Path(__file__).resolve().parents[1] / "skills" / "nougen-ctx" / "SKILL.md"


@pytest.mark.skipif(not _NOUGEN_CTX_SKILL.is_file(), reason="nougen-ctx skill not installed")
def test_nougen_ctx_skill_discovered_in_repo():
    discovered = skills.discover()
    names = [s.name for s in discovered]
    assert "nougen-ctx" in names, f"'nougen-ctx' missing from discovered skills: {names}"

    ctx_skill = next(s for s in discovered if s.name == "nougen-ctx")
    assert "Rule 0.0" in ctx_skill.description or "Context Mode" in ctx_skill.description
    assert ctx_skill.path == _NOUGEN_CTX_SKILL


@pytest.mark.skipif(not _NOUGEN_CTX_SKILL.is_file(), reason="nougen-ctx skill not installed")
def test_nougen_ctx_skill_frontmatter_and_content():
    text = _NOUGEN_CTX_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: nougen-ctx" in text
    assert "ctx_execute" in text
    assert "ctx_search" in text
    assert "ctx_batch_execute" in text

