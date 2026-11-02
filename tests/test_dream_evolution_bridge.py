"""Tests for the recursive Dream-to-Evolution bridge.

Verifies that semantic invariants consolidated during dream cycles are recursively
synthesized into progressive skills, held at CANDIDATE until they have a real task, and kept out
of skill discovery until then (visible only with NOUGEN_SKILLS_INCLUDE_CANDIDATES=1).
"""
from pathlib import Path
from unittest.mock import patch
import pytest

from nougen_shards import dream, skills
from nougen_shards.progressive_skills import SkillTier


@pytest.fixture
def dream_workspace(tmp_path, monkeypatch):
    """Provides an isolated environment for dream and skill synthesis."""
    monkeypatch.setattr(dream.core, "GLOBAL_DIR", tmp_path)
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NOUGEN_SKILLS_DIR", str(skills_dir))
    return tmp_path


def test_synthesize_skills_from_invariants_empty():
    """Empty rule lists return empty evolved skills without crashing."""
    assert dream.synthesize_skills_from_invariants([]) == []
    assert dream.synthesize_skills_from_invariants(None) == []


def test_synthesize_skills_from_invariants_creates_and_verifies_skills(dream_workspace, monkeypatch):
    """Extracted rules produce sandbox-verified progressive skills in the global skills directory."""
    rules = [
        {"subject": "FTS5Engine", "predicate": "always use MATCH syntax for rank scoring"},
        {"subject": "FTS5Engine", "predicate": "escape single quotes before building queries"},
        {"subject": "SandboxSecurity", "predicate": "execute trusted stubs with restricted AST"},
    ]

    with patch.object(dream.core, "capture", return_value=True):
        evolved = dream.synthesize_skills_from_invariants(rules, limit=2)

    assert len(evolved) == 2
    assert evolved[0]["name"] == "evolved-fts5engine"
    assert evolved[0]["tier"] == SkillTier.CANDIDATE.value
    assert evolved[0]["verified"] is False
    assert evolved[0]["invariants_count"] == 2

    assert evolved[1]["name"] == "evolved-sandboxsecurity"
    assert evolved[1]["tier"] == SkillTier.CANDIDATE.value
    assert evolved[1]["verified"] is False
    assert evolved[1]["invariants_count"] == 1

    # Check that SKILL.md was deployed and matches canonical frontmatter
    skill_file = Path(evolved[0]["path"])
    assert skill_file.is_file()
    text = skill_file.read_text(encoding="utf-8")

    meta, body = skills.parse_frontmatter(text)
    assert meta["name"] == "evolved-fts5engine"
    assert meta["tier"] == SkillTier.CANDIDATE.value
    assert "FTS5Engine" in meta["description"]
    assert "always use MATCH syntax" in body

    # Unverified candidates must not reach the registry that governs live work...
    monkeypatch.delenv("NOUGEN_SKILLS_INCLUDE_CANDIDATES", raising=False)
    assert [s.name for s in skills.discover([dream_workspace / "skills"])] == []
    # ...but the packages are on disk and visible once an operator opts in.
    monkeypatch.setenv("NOUGEN_SKILLS_INCLUDE_CANDIDATES", "1")
    names = [s.name for s in skills.discover([dream_workspace / "skills"])]
    assert "evolved-fts5engine" in names
    assert "evolved-sandboxsecurity" in names


def test_dream_wake_triggers_recursive_evolution(dream_workspace, monkeypatch):
    """Calling dream.wake() executes consolidation and populates evolved_skills."""
    mock_rules = [
        {"subject": "CachePolicy", "predicate": "invalidate memory cache on write operations"}
    ]
    mock_consolidation = {
        "shards_scanned": 1,
        "shards_consolidated": 1,
        "new_invariants_extracted": 1,
        "rules": mock_rules,
        "errors": [],
        "complete": True,
    }

    monkeypatch.setattr(dream.core, "decay_utility_scores", lambda: None)
    monkeypatch.setattr(dream, "fetch_high_utility_shards", lambda limit=50: [])
    monkeypatch.setattr(dream, "synthesize_invariants", lambda shards: [])
    monkeypatch.setattr(dream, "parametric_burn_in", lambda pairs: str(dream_workspace / "burn_in.jsonl"))
    monkeypatch.setattr(dream, "consolidate_episodic_data", lambda limit=10: mock_consolidation)
    monkeypatch.setattr(dream.core, "capture", lambda **kwargs: True)

    summary = dream.wake()

    assert "evolved_skills" in summary
    assert len(summary["evolved_skills"]) == 1
    sk = summary["evolved_skills"][0]
    assert sk["name"] == "evolved-cachepolicy"
    assert sk["verified"] is False
    assert sk["tier"] == SkillTier.CANDIDATE.value
