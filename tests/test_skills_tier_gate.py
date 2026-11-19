from nougen_shards import skills


def _pkg(root, name, tier):
    d = root / name
    d.mkdir()
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: d\ntier: {tier}\n---\n# body\n", encoding="utf-8"
    )


def test_candidate_skills_are_not_discovered(tmp_path, monkeypatch):
    monkeypatch.delenv("NOUGEN_SKILLS_INCLUDE_CANDIDATES", raising=False)
    _pkg(tmp_path, "cand", "CANDIDATE")
    _pkg(tmp_path, "pilot", "PILOT")
    names = [s.name for s in skills.discover(roots=[tmp_path])]
    assert names == ["pilot"]


def test_candidates_opt_in_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_SKILLS_INCLUDE_CANDIDATES", "1")
    _pkg(tmp_path, "cand", "CANDIDATE")
    found = {s.name: s.tier for s in skills.discover(roots=[tmp_path])}
    assert found == {"cand": "CANDIDATE"}


def test_untiered_legacy_skill_still_loads(tmp_path):
    (tmp_path / "legacy.md").write_text("# Legacy\nold flat skill\n", encoding="utf-8")
    assert [s.tier for s in skills.discover(roots=[tmp_path])] == [""]
