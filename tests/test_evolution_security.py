"""Security regression: evolved-skill paths must stay inside skills/."""
from pathlib import Path
from unittest.mock import patch

import pytest

import nougen_shards.evolution as evolution


def test_skill_id_sanitization_blocks_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(evolution.core, "GLOBAL_DIR", tmp_path)

    # Force the verifier to pass so deployment runs.
    with patch.object(evolution.nougen_sandbox, "execute_sandboxed", return_value="Virtual Task Passed"), \
         patch.object(evolution.core, "capture", return_value=True):
        engine = evolution.EvolutionEngine(verbose=False)
        res = engine.evolve_skill("../../etc/passwd injection")

    skills_dir = (tmp_path / "skills").resolve()
    written_path = Path(res["path"]).resolve()
    # The file must live directly under skills/, never outside it.
    assert skills_dir in written_path.parents
    assert ".." not in res["skill_id"]
    assert "/" not in res["skill_id"]
    assert written_path.exists()


class _NoOpSanitizer:
    """Stand-in for `re` inside evolution only: makes the slug sanitizer a no-op
    so it cannot be the thing that stops the traversal."""

    @staticmethod
    def sub(_pattern, _repl, _string, *_args, **_kwargs):
        return "../../pwned"


def test_containment_check_blocks_paths_escaping_skills_dir(tmp_path, monkeypatch):
    """The test above passes even with the containment check deleted, because
    the slug sanitizer already neutralizes `../`. This one disables the
    sanitizer so ONLY the `skill_dir not in skill_path.parents` check can stop
    the write -- deleting that check makes this test fail."""
    monkeypatch.setattr(evolution.core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(evolution, "re", _NoOpSanitizer)

    escaped = (tmp_path / "skills" / ".." / ".." / "pwned.md").resolve()

    with patch.object(evolution.nougen_sandbox, "execute_sandboxed",
                      return_value="Virtual Task Passed"), \
         patch.object(evolution.core, "capture", return_value=True):
        engine = evolution.EvolutionEngine(verbose=False)
        with pytest.raises(ValueError):
            engine.evolve_skill("harmless looking instruction")

    assert not escaped.exists(), f"skill escaped containment and was written to {escaped}"
