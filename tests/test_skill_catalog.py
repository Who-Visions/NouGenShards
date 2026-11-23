"""skill_catalog: external skill-repository manifest bridge."""
import json
from pathlib import Path

import pytest

from nougen_shards import skill_catalog


def _repo(tmp_path: Path, names=("alpha", "beta"), listed=None) -> Path:
    root = tmp_path / "repo"
    for n in names:
        d = root / "skills" / n
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {n}\ndescription: Skill {n}.\n---\n\nBody.\n", encoding="utf-8"
        )
    listed = names if listed is None else listed
    (root / "skills_index.json").write_text(
        json.dumps([{"id": n, "path": f"skills/{n}"} for n in listed]), encoding="utf-8"
    )
    return root


def test_unconfigured(monkeypatch):
    monkeypatch.delenv("NOUGEN_SKILLS_DIR", raising=False)
    assert skill_catalog.repository_root() is None
    assert skill_catalog.manifest() == []
    assert skill_catalog.workflows() == []
    assert skill_catalog.status()["configured"] is False


def test_root_accepts_skills_subdir(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setenv("NOUGEN_SKILLS_DIR", str(root / "skills"))
    assert skill_catalog.repository_root() == root.resolve()


def test_root_rejects_dir_without_index(tmp_path, monkeypatch):
    (tmp_path / "skills").mkdir()
    monkeypatch.setenv("NOUGEN_SKILLS_DIR", str(tmp_path))
    assert skill_catalog.repository_root() is None


def test_manifest_filters_non_dicts_and_bad_json(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setenv("NOUGEN_SKILLS_DIR", str(root))
    (root / "skills_index.json").write_text('[{"id": "a"}, 3, "x"]', encoding="utf-8")
    assert skill_catalog.manifest() == [{"id": "a"}]
    (root / "skills_index.json").write_text("{not json", encoding="utf-8")
    assert skill_catalog.manifest() == []


def test_status_counts_match_files(tmp_path, monkeypatch):
    root = _repo(tmp_path, names=("alpha", "beta"), listed=("alpha", "gamma"))
    monkeypatch.setenv("NOUGEN_SKILLS_DIR", str(root))
    s = skill_catalog.status()
    assert s["manifest_count"] == 2
    assert s["discovered_count"] == 2
    assert s["missing_from_files"] == 1  # gamma listed, no file
    assert s["unlisted_files"] == 1  # beta on disk, not listed


def test_workflow_roster_is_compact(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    (root / "data").mkdir()
    (root / "data" / "workflows.json").write_text(
        json.dumps({"workflows": [
            {"id": "w1", "name": "W", "description": "d", "category": "c", "extra": 1,
             "steps": [{"title": "s1", "recommendedSkills": ["alpha"]}, "junk", {"title": "s2"}]},
            "junk",
        ]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOUGEN_SKILLS_DIR", str(root))
    roster = skill_catalog.workflow_roster()
    assert roster == [{
        "id": "w1", "name": "W", "description": "d", "category": "c",
        "steps": [{"title": "s1", "recommendedSkills": ["alpha"]},
                  {"title": "s2", "recommendedSkills": []}],
    }]
