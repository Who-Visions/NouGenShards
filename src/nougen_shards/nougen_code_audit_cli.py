"""
NouGenCode Audit & Pre-Execution Cleanup CLI.
Executes an automated cleanup and intelligence density evaluation pass across
target codebases before new feature work begins.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from nougen_shards.nougen_code_scorer import NouGenCodeAuditor, CodeAuditReport


def audit_files(target_paths: List[Path]) -> Dict[str, Any]:
    reports = []
    total_loc = 0
    refactor_count = 0

    for path in target_paths:
        if path.is_dir():
            files = list(path.glob("**/*.py")) + list(path.glob("**/*.ts")) + list(path.glob("**/*.tsx"))
        else:
            files = [path]

        for file in files:
            if not file.exists() or not file.is_file():
                continue
            try:
                content = file.read_text(encoding="utf-8")
                report = NouGenCodeAuditor.audit_source_text(content, file_name=file.name)
                total_loc += report.loc
                if report.refactor_candidate:
                    refactor_count += 1
                reports.append({
                    "file": report.file_path,
                    "loc": report.loc,
                    "intelligence_density": report.intelligence_density,
                    "dead_code_prob": report.dead_code_probability,
                    "trust_risk": report.trust_boundary_risk,
                    "refactor_candidate": report.refactor_candidate,
                    "reason": report.refactor_reason,
                })
            except Exception as e:
                reports.append({
                    "file": str(file),
                    "error": str(e),
                })

    avg_density = round(sum(r.get("intelligence_density", 0) for r in reports if "error" not in r) / max(1, len(reports)), 2)

    return {
        "status": "PASS" if refactor_count == 0 else "REFACTOR_REQUIRED",
        "total_files": len(reports),
        "total_loc": total_loc,
        "average_intelligence_density": avg_density,
        "refactor_candidates": refactor_count,
        "reports": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="NouGenCode Audit & Cleanup Runner")
    parser.add_argument("paths", nargs="+", type=str, help="Target files or directories to audit")
    parser.add_argument("--json", action="store_true", help="Output raw JSON summary")
    args = parser.parse_args()

    target_paths = [Path(p) for p in args.paths]
    result = audit_files(target_paths)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"NouGenCode Audit: {result['status']} | Files: {result['total_files']} | LOC: {result['total_loc']} | Avg Density: {result['average_intelligence_density']}")
        for r in result["reports"]:
            if "error" in r:
                print(f"  [ERROR] {r['file']}: {r['error']}")
            else:
                flag = "⚠️" if r["refactor_candidate"] else "✅"
                print(f"  {flag} {r['file']:<30} | Density: {r['intelligence_density']:<5.1f} | Refactor: {r['reason']}")

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
