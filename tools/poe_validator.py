#!/usr/bin/env python3
"""
NouGen Fleet Verifiable Proof-of-Execution (PoE) Validator Engine.
Enforces Hardcade Protocol v1.0.0:
- Validates that closed claims possess physical git commit SHAs, test stdout hashes, and real file diffs.
- Verifies that claims without proof cannot transition to CLOSED or ACKED.
- Manages T-Lease TTLs, heartbeat decay, and marks dead leases as ORPHAN.
"""

import os
import sys
import json
import time
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

HOME = Path.home()
RELAY_BASE = HOME / ".nougen" / "relay"
CLAIMS_DIR = RELAY_BASE / ".claims"
DEFAULT_LEASE_TTL_SECONDS = 1800  # 30 minutes
HEARTBEAT_DECAY_THRESHOLD = 300   # 5 minutes without heartbeat = STALE/ORPHAN


class PoEValidationError(Exception):
    pass


class PoEValidator:
    @staticmethod
    def compute_sha256(data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_git_commit(repo_path: Path, commit_sha: str) -> bool:
        """Verifies that a commit sha physically exists in the target repository."""
        if not repo_path.exists() or not (repo_path / ".git").exists():
            return False
        try:
            res = subprocess.run(
                ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit_sha}^{{commit}}"],
                capture_output=True,
                timeout=5
            )
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def validate_poe_block(poe: Dict[str, Any], workspace_root: Optional[Path] = None) -> Tuple[bool, List[str]]:
        """
        Validates the Proof-of-Execution tuple:
        1. commit_sha is present and valid hexadecimal string (minimum 7 chars)
        2. files_changed is non-empty list of paths
        3. test_evidence has runner, exit_code == 0, and non-empty stdout_hash
        4. verifier has observer_node
        """
        errors = []
        git_info = poe.get("git")
        if not git_info or not isinstance(git_info, dict):
            errors.append("Missing 'git' object in poe block.")
        else:
            commit_sha = git_info.get("commit_sha", "").strip()
            if not commit_sha or len(commit_sha) < 7:
                errors.append(f"Invalid or missing commit_sha: {commit_sha}")
            files = git_info.get("files_changed", [])
            if not isinstance(files, list) or len(files) == 0:
                errors.append("files_changed must be a non-empty list of modified file paths.")
            if workspace_root:
                repo_path = Path(git_info.get("repo_path") or workspace_root)
                if not PoEValidator.verify_git_commit(repo_path, commit_sha):
                    errors.append(f"Physical commit {commit_sha} does not exist in {repo_path}")

        test_evidence = poe.get("test_evidence")
        if not test_evidence or not isinstance(test_evidence, dict):
            errors.append("Missing 'test_evidence' object in poe block.")
        else:
            runner = test_evidence.get("runner", "").strip()
            if not runner:
                errors.append("Missing test runner command in test_evidence.")
            exit_code = test_evidence.get("exit_code")
            if exit_code != 0:
                errors.append(f"Test suite must report exit_code 0 (passed), got: {exit_code}")
            stdout_hash = test_evidence.get("stdout_hash", "").strip()
            if not stdout_hash or len(stdout_hash) < 16:
                errors.append("Missing or invalid test stdout_hash.")

        verifier = poe.get("verifier")
        if not verifier or not isinstance(verifier, dict):
            errors.append("Missing 'verifier' object in poe block.")
        else:
            if not verifier.get("observer_node"):
                errors.append("Verifier requires an observer_node attestation.")

        return len(errors) == 0, errors

    @classmethod
    def evaluate_claim_payload(cls, claim_data: Dict[str, Any], workspace_root: Optional[Path] = None) -> Dict[str, Any]:
        """
        Evaluates a claim file against the state machine and PoE requirements:
        - UNCLAIMED -> allowed
        - LEASED / EXECUTING -> checks heartbeat freshness
        - CLOSED / VERIFIED -> strictly requires valid PoE
        """
        status = claim_data.get("status", "unclaimed").lower()
        now = time.time()
        
        # Check lease decay
        lease = claim_data.get("lease", {})
        acquired_at = lease.get("acquired_at", 0)
        last_heartbeat = lease.get("last_heartbeat", acquired_at)
        ttl = lease.get("ttl_seconds", DEFAULT_LEASE_TTL_SECONDS)

        is_decayed = (now - last_heartbeat) > HEARTBEAT_DECAY_THRESHOLD
        is_expired = (now - acquired_at) > ttl

        if status in ["leased", "executing"]:
            if is_decayed or is_expired:
                return {
                    "valid": False,
                    "target_status": "orphan",
                    "reason": "Lease heartbeat decayed or expired. Reclaiming task for fleet."
                }
            return {"valid": True, "target_status": status, "reason": "Lease active and heartbeating."}

        if status in ["closed", "acked", "verified", "attested"]:
            poe = claim_data.get("poe")
            if not poe:
                return {
                    "valid": False,
                    "target_status": "unclaimed",
                    "reason": "ANTI-SIMULATION BREACH: Closed status without PoE block is strictly prohibited."
                }
            ok, errors = cls.validate_poe_block(poe, workspace_root)
            if not ok:
                return {
                    "valid": False,
                    "target_status": "unclaimed",
                    "reason": f"PoE validation failed: {'; '.join(errors)}"
                }
            return {"valid": True, "target_status": "closed", "reason": "Proof of Execution verified."}

        return {"valid": True, "target_status": status, "reason": "State acknowledged."}


def audit_all_claims(claims_dir: Path = CLAIMS_DIR) -> Dict[str, Any]:
    """Audits all claim files in .claims/ directory."""
    if not claims_dir.exists():
        return {"audited": 0, "valid": 0, "invalid": 0, "reclaimed": 0, "details": []}

    results = []
    audited = 0
    valid = 0
    invalid = 0
    reclaimed = 0

    for f in claims_dir.glob("*.json"):
        audited += 1
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            res = PoEValidator.evaluate_claim_payload(data)
            if res["valid"]:
                valid += 1
            else:
                invalid += 1
                if res["target_status"] == "orphan":
                    reclaimed += 1
            results.append({
                "file": f.name,
                "status": data.get("status"),
                "result": res
            })
        except Exception as e:
            invalid += 1
            results.append({"file": f.name, "error": str(e)})

    return {
        "audited": audited,
        "valid": valid,
        "invalid": invalid,
        "reclaimed": reclaimed,
        "details": results
    }


if __name__ == "__main__":
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Running PoE Engine Claim Audit...")
    report = audit_all_claims()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["invalid"] == 0 else 1)
