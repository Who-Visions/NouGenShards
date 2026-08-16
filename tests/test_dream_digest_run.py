"""Dream digestion must redact inputs and prove generation before writes."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPT = Path(__file__).parents[1] / "tools" / "dream_digest_run.py"
SPEC = importlib.util.spec_from_file_location("dream_digest_run", SCRIPT)
DREAM = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DREAM)


def test_extract_redacts_secret_patterns(tmp_path):
    secret = "nougen_fleet_token_AB12cd34"
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(json.dumps({
        "message": {"role": "user", "content": f"token: {secret}"}
    }) + "\n", encoding="utf-8")

    turns = DREAM.extract(transcript)
    assert secret not in turns[0]
    assert "REDACTED" in turns[0]


def test_preflight_fails_before_digesting_on_generation_error():
    with patch.object(DREAM.urllib.request, "urlopen", side_effect=OSError("runner missing")):
        with pytest.raises(SystemExit, match="INFERENCE PREFLIGHT FAILED"):
            DREAM.inference_preflight("test-model")


def test_explicit_sources_bypass_rolling_window_without_redigesting_handoffs(tmp_path):
    source = tmp_path / "old.jsonl"
    source.write_text("", encoding="utf-8")
    with patch.object(DREAM, "pick_model", return_value="test-model"), \
         patch.object(DREAM, "inference_preflight"), \
         patch.object(DREAM, "extract", return_value=[]), \
         patch.object(DREAM.glob, "glob") as glob_mock, \
         patch.object(DREAM.os, "makedirs"):
        DREAM.main([str(source)])
    glob_mock.assert_not_called()
