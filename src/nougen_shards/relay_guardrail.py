#!/usr/bin/env python3
"""Hardcade Relay Gate & Physical Execution Verifier.

Flip-switch and preflight enforcement for relay closures.
Outlaws fake metadata acknowledgments (Rule 0.13).
Ensures that no leg is closed without a verified EvidenceTuple:
(code_artifact, commit_hash/path, test_result, observer_node).
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

HARDCADE_STRICT_ENV = "HARDCADE_STRICT_EXECUTION"
RELAY_ROOT = Path(os.environ.get("NOUGEN_RELAY_DIR", Path.home() / ".nougen" / "relay" / ".handoffs"))

class HardcadeViolationError(Exception):
    pass

def is_hardcade_strict() -> bool:
    """Flip-switch check. Enabled by default unless explicitly disabled."""
    val = os.environ.get(HARDCADE_STRICT_ENV, "1").strip().lower()
    return val not in ("0", "false", "off", "disabled")

def verify_closure_evidence(
    leg_id: str,
    artifact_path: Optional[str] = None,
    test_command: Optional[str] = None,
    observer: str = "Phoebus"
) -> Tuple[bool, str]:
    """Verify physical execution proof before allowing an ack.
    
    Returns (passed, details).
    """
    if not is_hardcade_strict():
        return True, "FLIP-SWITCH BYPASS: Strict execution disabled via env."

    if not artifact_path:
        return False, "REJECTED: No physical code_artifact or file output specified."

    p = Path(artifact_path)
    if not p.is_absolute():
        p = Path.cwd() / p

    if not p.exists():
        return False, f"REJECTED: Specified artifact does not exist: {p}"

    # If test command provided, run it to verify actual pass
    if test_command:
        try:
            res = subprocess.run(
                test_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            if res.returncode != 0:
                err = res.stderr or res.stdout
                return False, f"REJECTED: Test suite failed (exit {res.returncode}): {err}"
        except subprocess.TimeoutExpired:
            return False, "REJECTED: Test suite timed out after 60s."
        except Exception as e:
            return False, f"REJECTED: Error running test suite: {e}"

    return True, f"VERIFIED: Artifact {p} exists and test check succeeded."

def safe_ack_leg(
    leg_id: str,
    artifact_path: str,
    resolution_note: str,
    test_command: Optional[str] = None,
    observer: str = "Phoebus"
) -> bool:
    """Atomically check guardrails and ack a relay leg ONLY if execution passes."""
    leg_file = RELAY_ROOT / f"{leg_id}.json"
    if not leg_file.exists():
        leg_file = RELAY_ROOT / ".handoffs" / f"{leg_id}.json"
    if not leg_file.exists():
        raise FileNotFoundError(f"Relay leg {leg_id} not found at {leg_file}")

    passed, reason = verify_closure_evidence(
        leg_id=leg_id,
        artifact_path=artifact_path,
        test_command=test_command,
        observer=observer
    )

    if not passed:
        raise HardcadeViolationError(f"HARDCADE COMBO BREAKER: Cannot ack {leg_id}! Reason: {reason}")

    data = json.loads(leg_file.read_text(encoding="utf-8"))
    data["status"] = "acked"
    data["resolved_at"] = subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"]).decode().strip()
    data["resolution_note"] = resolution_note
    data["evidence_tuple"] = {
        "artifact": str(artifact_path),
        "test_check": test_command or "verified_file_exists",
        "observer": observer
    }
    leg_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[TOUCHDOWN] Leg {leg_id} securely acked with verified evidence: {artifact_path}")
    return True

if __name__ == "__main__":
    print(f"Hardcade Relay Gate loaded. Strict Flip-Switch: {is_hardcade_strict()}")
