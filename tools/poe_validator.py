#!/usr/bin/env python3
"""
NouGen Fleet Verifiable Proof-of-Execution (PoE) Validator Engine.
Enforces Hardcade Protocol v1.0.0:
- Validates that closed claims possess physical git commit SHAs, test stdout hashes, and real file diffs.
- Verifies that claims without proof cannot transition to CLOSED or ACKED.
- Manages T-Lease TTLs, heartbeat decay, and marks dead leases as ORPHAN.
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, Any

HOME = Path.home()
RELAY_BASE = HOME / ".nougen" / "relay"
CLAIMS_DIR = RELAY_BASE / ".claims"
DEFAULT_LEASE_TTL_SECONDS = 1800  # 30 minutes
HEARTBEAT_DECAY_THRESHOLD = 300   # 5 minutes without heartbeat = STALE/ORPHAN


try:
    from nougen_shards.poe_validator import PoEValidationError, PoEValidator
except ModuleNotFoundError:
    # Keep direct `python tools/poe_validator.py` use working from a source checkout.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from nougen_shards.poe_validator import PoEValidationError, PoEValidator

__all__ = ["PoEValidationError", "PoEValidator", "audit_all_claims"]


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
