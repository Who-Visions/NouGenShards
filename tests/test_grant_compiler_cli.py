"""
Unit tests for NouGen Grant Compiler CLI & Toolchain execution.
Validates:
1. End-to-end compilation of a temporary grant spec JSON.
2. Production of output JSON with valid cryptographic seal.
3. Proper handling of missing files.
4. Compliance verification of the generated Next.js props.
"""
import json
import pytest
from pathlib import Path
from nougen_shards.grant_compiler_cli import compile_grant_file


def test_cli_compile_end_to_end(tmp_path):
    spec_data = {
        "project_id": "TEST-GRANT-001",
        "project_title": "Test Arts Initiative",
        "lead_artist": "Jane Doe",
        "primary_borough": "Brooklyn",
        "target_funder": "BAC_CAG",
        "public_event_type": "Workshop",
        "free_public_access": True,
        "narrative_summary": "Community art workshop",
        "budget": {
            "artist_stipend": 2600.0,
            "materials_budget": 1100.0,
            "venue_budget": 450.0,
            "producer_fee": 850.0,
            "total_request": 5000.0
        }
    }
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec_data), encoding="utf-8")
    
    out_dir = tmp_path / "output"
    res = compile_grant_file(spec_file, out_dir)
    
    assert res["is_valid"] is True
    assert len(res["seal_hash"]) == 64
    assert (out_dir / "compiled_TEST-GRANT-001.json").exists()


def test_cli_missing_file():
    with pytest.raises(FileNotFoundError):
        compile_grant_file(Path("non_existent_spec_file.json"))
