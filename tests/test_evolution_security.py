"""Security regression: evolved-skill paths must stay inside skills/."""
from pathlib import Path
from unittest.mock import patch

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
