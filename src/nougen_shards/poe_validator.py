"""Reusable Proof-of-Execution validation for NouGen runtime consumers."""

import hashlib
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class PoEValidationError(Exception):
    """Raised when execution evidence cannot be validated."""


class PoEValidator:
    DEFAULT_LEASE_TTL_SECONDS = 1800
    HEARTBEAT_DECAY_THRESHOLD = 300

    @staticmethod
    def compute_sha256(data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_git_commit(repo_path: Path, commit_sha: str) -> bool:
        """Return whether a commit exists in a normal checkout or worktree."""
        repo_path = Path(repo_path)
        if not repo_path.exists() or not (repo_path / ".git").exists():
            return False
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit_sha}^{{commit}}"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @classmethod
    def validate_poe_block(
        cls, poe: Dict[str, Any], workspace_root: Optional[Path] = None
    ) -> Tuple[bool, List[str]]:
        """Validate the PoE tuple and, when a repo is named, its physical commit."""
        errors: List[str] = []
        git_info = poe.get("git") if isinstance(poe, dict) else None
        if not isinstance(git_info, dict):
            errors.append("Missing 'git' object in poe block.")
        else:
            commit_sha = str(git_info.get("commit_sha") or "").strip()
            if len(commit_sha) < 7 or any(ch not in "0123456789abcdefABCDEF" for ch in commit_sha):
                errors.append(f"Invalid or missing commit_sha: {commit_sha}")
            files = git_info.get("files_changed")
            if not isinstance(files, list) or not files or any(not isinstance(p, str) or not p.strip() for p in files):
                errors.append("files_changed must be a non-empty list of file paths.")
            repo_value = git_info.get("repo_path")
            repo_path = (Path(repo_value).expanduser().resolve()
                         if isinstance(repo_value, str) and repo_value.strip()
                         else Path(workspace_root).expanduser().resolve() if workspace_root else None)
            if repo_path is None:
                errors.append("Missing repo_path for physical commit verification.")
            elif commit_sha and len(commit_sha) >= 7 and not cls.verify_git_commit(repo_path, commit_sha):
                errors.append(f"Physical commit {commit_sha} does not exist in {repo_path}")

        test_evidence = poe.get("test_evidence") if isinstance(poe, dict) else None
        if not isinstance(test_evidence, dict):
            errors.append("Missing 'test_evidence' object in poe block.")
        else:
            if not str(test_evidence.get("runner") or "").strip():
                errors.append("Missing test runner command in test_evidence.")
            if test_evidence.get("exit_code") != 0:
                errors.append(f"Test suite must report exit_code 0 (passed), got: {test_evidence.get('exit_code')}")
            stdout_hash = str(test_evidence.get("stdout_hash") or "").strip()
            if len(stdout_hash) < 16 or any(ch not in "0123456789abcdefABCDEF" for ch in stdout_hash):
                errors.append("Missing or invalid test stdout_hash.")

        verifier = poe.get("verifier") if isinstance(poe, dict) else None
        if not isinstance(verifier, dict) or not str(verifier.get("observer_node") or "").strip():
            errors.append("Verifier requires an observer_node attestation.")
        return not errors, errors

    @classmethod
    def evaluate_claim_payload(cls, claim_data: Dict[str, Any], workspace_root: Optional[Path] = None) -> Dict[str, Any]:
        """Preserve the fleet claim auditor's lease and PoE state checks."""
        status = str(claim_data.get("status", "unclaimed")).lower()
        now = time.time()
        lease = claim_data.get("lease", {})
        acquired_at = lease.get("acquired_at", 0)
        last_heartbeat = lease.get("last_heartbeat", acquired_at)
        ttl = lease.get("ttl_seconds", cls.DEFAULT_LEASE_TTL_SECONDS)
        expired = (now - acquired_at) > ttl
        stale = (now - last_heartbeat) > cls.HEARTBEAT_DECAY_THRESHOLD
        if status in {"leased", "executing"}:
            if expired or stale:
                return {
                    "valid": False,
                    "target_status": "orphan",
                    "reason": "Lease heartbeat decayed or expired. Reclaiming task for fleet.",
                }
            return {"valid": True, "target_status": status, "reason": "Lease active and heartbeating."}
        if status in {"closed", "acked", "verified", "attested"}:
            poe = claim_data.get("poe")
            if not poe:
                return {
                    "valid": False,
                    "target_status": "unclaimed",
                    "reason": "ANTI-SIMULATION BREACH: Closed status without PoE block is strictly prohibited.",
                }
            valid, errors = cls.validate_poe_block(poe, workspace_root)
            if not valid:
                return {
                    "valid": False,
                    "target_status": "unclaimed",
                    "reason": "PoE validation failed: " + "; ".join(errors),
                }
            return {"valid": True, "target_status": "closed", "reason": "Proof of Execution verified."}
        return {"valid": True, "target_status": status, "reason": "State acknowledged."}
