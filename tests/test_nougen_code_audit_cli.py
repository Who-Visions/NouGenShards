"""
Unit tests for NouGenCode Audit & Pre-Execution Cleanup CLI.
"""
import json
import pytest
from pathlib import Path
from nougen_shards.nougen_code_audit_cli import audit_files


def test_audit_files_on_grant_compiler(tmp_path: Path):
    test_file = tmp_path / "sample_module.py"
    test_file.write_text("""
def calculate_stipend(total: float, ratio: float = 0.6) -> float:
    return total * ratio

def validate_stipend(stipend: float, total: float) -> bool:
    return stipend >= (total * 0.5)
""", encoding="utf-8")

    res = audit_files([test_file])
    assert res["status"] == "PASS"
    assert res["total_files"] == 1
    assert res["total_loc"] > 0
    assert res["average_intelligence_density"] > 0
    assert res["refactor_candidates"] == 0
    assert len(res["reports"]) == 1
    assert res["reports"][0]["refactor_candidate"] is False
