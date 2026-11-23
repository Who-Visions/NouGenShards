"""Coverage for response_contract.response_metadata and pr_context helpers."""
from nougen_shards.pr_context import RULE_FILENAMES, ReviewContext, gather_context
from nougen_shards.response_contract import UNKNOWN_MODEL, response_metadata


def test_complete_response_is_verified():
    m = response_metadata("m1", "m1", "hello", "stop")
    assert m.complete and m.status == "complete"
    assert m.to_dict()["identity_verified"] is True


def test_missing_actual_model_is_unknown_not_verified():
    m = response_metadata("m1", None, "hello", "end_turn")
    assert m.actual_model == UNKNOWN_MODEL
    assert m.complete
    assert m.to_dict()["identity_verified"] is False


def test_identity_mismatch():
    m = response_metadata("m1", "m2", "hello", "stop")
    assert (m.complete, m.status) == (False, "identity_mismatch")


def test_token_limit_is_partial():
    m = response_metadata("m1", "m1", "hello", "MAX_TOKENS")
    assert (m.complete, m.status, m.reason) == (False, "partial", "token_limit")


def test_empty_content():
    assert response_metadata("m1", "m1", "  ", "stop").status == "empty"
    assert response_metadata("m1", "m1", None, "stop").status == "empty"


def test_refusal_and_filter_are_safety():
    assert response_metadata("m1", "m1", "x", "stop", refusal="no").status == "safety"
    assert response_metadata("m1", "m1", "x", "content_filter").status == "safety"


def test_content_safety_model_is_safety_only():
    m = response_metadata("m1", "acme-content-safety", "safe", "stop")
    assert m.status == "safety_only" and not m.complete


def test_missing_finish_reason_incomplete():
    assert response_metadata("m1", "m1", "x", None).status == "incomplete"


def test_gather_context_collects_rules_and_skills(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("rules", encoding="utf-8")
    (tmp_path / "skills" / "b").mkdir(parents=True)
    (tmp_path / "skills" / "a").mkdir(parents=True)
    (tmp_path / "skills" / "a" / "SKILL.md").write_text("a", encoding="utf-8")
    (tmp_path / "skills" / "b" / "SKILL.md").write_text("b", encoding="utf-8")
    ctx = gather_context(str(tmp_path), relay_objective="obj", gm_instruction="gm")
    assert list(ctx.rule_files) == ["CLAUDE.md"]
    assert [p.replace("\\", "/") for p in ctx.skill_files] == [
        "skills/a/SKILL.md", "skills/b/SKILL.md"]
    block = ctx.as_prompt_block()
    assert block.index("## GM instruction") < block.index("## CLAUDE.md")
    assert block.index("## CLAUDE.md") < block.index("## Active relay objective")
    assert "## Relevant skills" in block


def test_gather_context_empty_repo(tmp_path):
    ctx = gather_context(str(tmp_path))
    assert ctx.rule_files == {} and ctx.skill_files == []
    assert ctx.as_prompt_block() == ctx.precedence_note()
    assert "CLAUDE.md" in RULE_FILENAMES


def test_prompt_block_truncates_per_file():
    ctx = ReviewContext(repo_root=".", rule_files={"CLAUDE.md": "x" * 10})
    block = ctx.as_prompt_block(max_chars_per_file=4)
    assert "xxxx\n...[truncated, 6 more chars]" in block
