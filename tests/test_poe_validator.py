import subprocess
from pathlib import Path
from tools.poe_validator import PoEValidator

def _current_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

def _current_commit_sha() -> str:
    try:
        res = subprocess.run(
            ["git", "-C", str(_current_repo_root()), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "14ded9b7966e03f673d1e065756532aa2dd46e97"

def test_poe_validator_git_check_valid():
    repo_path = _current_repo_root()
    sha = _current_commit_sha()
    assert PoEValidator.verify_git_commit(repo_path, sha) is True

def test_poe_validator_git_check_invalid():
    repo_path = _current_repo_root()
    assert PoEValidator.verify_git_commit(repo_path, "0000000000000000000000000000000000000000") is False

def test_poe_block_validation_success():
    repo_path = _current_repo_root()
    sha = _current_commit_sha()
    poe = {
        "git": {
            "commit_sha": sha,
            "files_changed": ["src/nougen_shards/nougenmsg.py"],
            "repo_path": str(repo_path)
        },
        "test_evidence": {
            "runner": "pytest tests/test_nougen_time.py",
            "exit_code": 0,
            "stdout_hash": "a1b2c3d4e5f607182930415263748596"
        },
        "verifier": {
            "observer_node": "phoebus"
        }
    }
    valid, errors = PoEValidator.validate_poe_block(poe, workspace_root=repo_path)
    assert valid is True
    assert len(errors) == 0

def test_poe_block_validation_missing_commit():
    poe = {
        "git": {
            "commit_sha": "",
            "files_changed": ["src/file.py"]
        },
        "test_evidence": {
            "runner": "pytest",
            "exit_code": 0,
            "stdout_hash": "a1b2c3d4e5f607182930415263748596"
        },
        "verifier": {
            "observer_node": "phoebus"
        }
    }
    valid, errors = PoEValidator.validate_poe_block(poe)
    assert valid is False
    assert any("commit_sha" in e for e in errors)

def test_claim_payload_anti_simulation_enforcement():
    claim = {
        "status": "closed",
        "task_id": "test_leg"
    }
    res = PoEValidator.evaluate_claim_payload(claim)
    assert res["valid"] is False
    assert res["target_status"] == "unclaimed"
    assert "ANTI-SIMULATION BREACH" in res["reason"]
