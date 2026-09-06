"""Security regression: evolved-skill paths must stay inside skills/."""
from pathlib import Path
from unittest.mock import patch

import nougen_shards.evolution as evolution
from nougen_shards import skills
import json
import pytest


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


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(evolution.core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(evolution, "get_best_available_client", lambda: None)
    monkeypatch.setattr(evolution.core, "capture", lambda **kwargs: True)
    monkeypatch.setattr(evolution.nougen_sandbox, "execute_sandboxed",
                        lambda *args, **kwargs: "Virtual Task Passed")
    return evolution.EvolutionEngine(verbose=False)


def test_generated_metadata_round_trips_unicode_and_yaml_punctuation(engine, tmp_path):
    instruction = 'Kreyòl: "whisper" # canon\n---\n日本語 paths \\ examples'
    result = engine.evolve_skill(instruction)
    text = Path(result["path"]).read_text(encoding="utf-8")
    expected = " ".join(instruction.split())
    # Generated scalars are JSON quoted, a valid YAML subset, and the actual
    # registry must decode them without dropping Unicode or quoted words.
    assert json.loads(text.splitlines()[1].split(": ", 1)[1]) == expected
    found = skills.discover([tmp_path / "skills"])
    assert found[0].name == expected
    assert found[0].description == expected


def test_long_instructions_keep_bounded_distinct_paths(engine):
    first = engine.evolve_skill("a" * 500 + " one")
    second = engine.evolve_skill("a" * 500 + " two")
    assert len(first["skill_id"].encode()) <= 129
    assert first["path"] != second["path"]
    assert Path(first["path"]).is_file()
    assert Path(second["path"]).is_file()


@pytest.mark.parametrize("instruction", ["", "  \n", None, 42])
def test_empty_or_invalid_instruction_creates_no_skill(engine, tmp_path, instruction):
    assert not engine.evolve_skill(instruction)["verified"]
    assert not (tmp_path / "skills").exists()
