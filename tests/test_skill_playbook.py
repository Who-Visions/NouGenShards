"""Outcome playbook for skills: counters, delta field notes, tie-break ranking."""
import pytest

import nougen_shards.skill_playbook as playbook
import nougen_shards.skills as skills


@pytest.fixture(autouse=True)
def sidecar(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_SKILL_PLAYBOOK_DB", str(tmp_path / "skill_playbook.db"))
    skills.invalidate_cache()
    yield
    skills.invalidate_cache()


def _skill(root, name, description):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n\nbody of {name}\n",
                                encoding="utf-8")


def test_unmarked_skill_has_no_counts_and_no_bonus():
    assert playbook.counts("never-used") == (0, 0)
    assert playbook.bonuses() == {}
    assert playbook.field_notes("never-used") == []
    assert playbook.stats()["skills"] == 0


def test_mark_increments_the_right_counter_case_insensitively():
    playbook.mark("Relay", True)
    playbook.mark("relay", True)
    result = playbook.mark(" RELAY ", False)
    assert (result["helpful"], result["harmful"]) == (2, 1)
    assert playbook.counts("relay") == (2, 1)


def test_bonus_needs_samples_and_stays_under_one_term():
    assert playbook.bonus_from_counts(2, 0) == 0.0
    assert 0 < playbook.bonus_from_counts(50, 0) < 0.5
    assert -0.5 < playbook.bonus_from_counts(0, 50) < 0
    assert playbook.bonus_from_counts(3, 3) == 0.0


def test_note_is_added_as_a_delta_and_deduplicated():
    first = playbook.mark("fleet", False, note="Pass max_tokens explicitly; 800 starves E-series.")
    assert first["note_added"] == "sk-00001"
    again = playbook.mark("fleet", True, note="pass MAX_TOKENS explicitly - 800 starves e-series")
    assert again["note_added"] is None and again["notes_bumped"] == ["sk-00001"]
    notes = playbook.field_notes("fleet")
    assert len(notes) == 1 and notes[0]["helpful"] == 1
    assert playbook.format_field_notes("fleet").startswith("[sk-00001] helpful=1 harmful=0 :: Pass max_tokens")


def test_note_is_one_bounded_line():
    cleaned = playbook.clean_note("line one\n\n## heading\n```\ncode\n```\n" + "x" * 500)
    assert "\n" not in cleaned and "`" not in cleaned
    assert len(cleaned) <= playbook.NOTE_MAX_CHARS


def test_contradicted_note_is_held_back_but_kept():
    added = playbook.mark("relay", True, note="Ack before reading the body.")["note_added"]
    playbook.mark("relay", False, note_ids=[added])
    assert playbook.field_notes("relay") == []
    playbook.mark("relay", True, note_ids=[f"[{added}]"])
    playbook.mark("relay", True, note_ids=[added])
    assert [n["id"] for n in playbook.field_notes("relay")] == [added]


def test_note_ids_of_another_skill_are_ignored():
    added = playbook.mark("relay", True, note="A relay lesson.")["note_added"]
    result = playbook.mark("fleet", False, note_ids=[added, "not-an-id"])
    assert result["notes_bumped"] == []
    assert playbook.field_notes("relay")[0]["harmful"] == 0


def test_outcomes_break_ties_but_never_outrank_relevance(tmp_path):
    _skill(tmp_path, "alpha-palette", "build a colour palette for a landing page")
    _skill(tmp_path, "beta-palette", "build a colour palette for a landing page")
    _skill(tmp_path, "weak", "landing page")
    task = "build a colour palette for a landing page"
    assert [s.name for s in skills.match(task, roots=[tmp_path])][:2] == ["alpha-palette", "beta-palette"]

    for _ in range(4):
        playbook.mark("beta-palette", True)
        playbook.mark("alpha-palette", False)
        playbook.mark("weak", True)
    ranked = [s.name for s in skills.match(task, roots=[tmp_path])]
    assert ranked[:2] == ["beta-palette", "alpha-palette"]
    assert ranked[-1] == "weak"            # more praise, less relevance: still last
    assert len(ranked) == 3                # outcomes never drop a skill


def test_match_survives_a_broken_sidecar(tmp_path, monkeypatch):
    _skill(tmp_path, "alpha-palette", "build a colour palette for a landing page")
    _skill(tmp_path, "beta-palette", "build a colour palette for a landing page")
    monkeypatch.setattr(playbook, "bonuses", lambda: (_ for _ in ()).throw(RuntimeError("locked")))
    assert len(skills.match("build a colour palette for a landing page", roots=[tmp_path])) == 2


def test_stats_names_strong_and_problematic_skills():
    for _ in range(5):
        playbook.mark("good", True)
    playbook.mark("bad", False)
    summary = playbook.stats()
    assert summary["strong"] == ["good"] and summary["problematic"] == ["bad"]
    assert summary["outcomes"] == 6


def test_mcp_mark_skill_feeds_apply_skills(tmp_path, monkeypatch):
    mcp_mod = pytest.importorskip("nougen_shards.mcp")
    _skill(tmp_path, "relay", "read open handoff legs before work")
    found = skills.discover([tmp_path])
    monkeypatch.setattr(mcp_mod.skill_registry, "match", lambda task: found)
    monkeypatch.setattr(mcp_mod.skill_registry, "get", lambda name: found[0] if name.lower() == "relay" else None)

    assert "Nothing recorded" in mcp_mod.mark_skill("no-such-skill", True)
    out = mcp_mod.mark_skill("Relay", False, note="Read the leg body before acking.")
    assert "harmful=1" in out and "sk-00001" in out

    text = mcp_mod.apply_skills("read the open legs")
    assert "FIELD NOTES" in text and "[sk-00001] helpful=0 harmful=0 :: Read the leg body before acking." in text
    assert 'mark_skill("<name>"' in text


def test_default_sidecar_follows_the_active_vault(tmp_path, monkeypatch):
    import nougen_shards.core as core
    monkeypatch.delenv("NOUGEN_SKILL_PLAYBOOK_DB")
    owner, tenant = tmp_path / "owner", tmp_path / "tenant"
    monkeypatch.setattr(core, "active_vault_dir", lambda: owner)
    playbook.mark("relay", True, note="Owner lesson.")
    monkeypatch.setattr(core, "active_vault_dir", lambda: tenant)
    assert playbook.counts("relay") == (0, 0) and playbook.field_notes("relay") == []
    playbook.mark("relay", False)
    assert (tenant / "skill_playbook.db").exists() and (owner / "skill_playbook.db").exists()
    monkeypatch.setattr(core, "active_vault_dir", lambda: owner)
    assert playbook.counts("relay") == (1, 0)
