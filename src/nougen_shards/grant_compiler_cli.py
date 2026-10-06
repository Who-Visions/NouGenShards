"""
NouGen Toolchain CLI Runner for Universal Grant Compiler.
Executes end-to-end grant compilation, compliance validation, and package generation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from nougen_shards.grant_compiler import ArtistProjectSpec, GrantBudget


def compile_grant_file(spec_path: Path, output_dir: Path | None = None) -> Dict[str, Any]:
    if not spec_path.exists():
        raise FileNotFoundError(f"Grant spec file not found: {spec_path}")

    raw_data = json.loads(spec_path.read_text(encoding="utf-8"))
    
    # Parse budget
    b_data = raw_data.get("budget", {})
    budget = GrantBudget(
        artist_stipend=float(b_data.get("artist_stipend", 0.0)),
        materials_budget=float(b_data.get("materials_budget", 0.0)),
        venue_budget=float(b_data.get("venue_budget", 0.0)),
        producer_fee=float(b_data.get("producer_fee", 0.0)),
        total_request=float(b_data.get("total_request", 0.0)),
    )

    spec = ArtistProjectSpec(
        project_id=raw_data.get("project_id", "PROJ-001"),
        project_title=raw_data.get("project_title", "Untitled Project"),
        lead_artist=raw_data.get("lead_artist", "Unknown Artist"),
        primary_borough=raw_data.get("primary_borough", "Brooklyn"),
        target_funder=raw_data.get("target_funder", "BAC_CAG"),
        public_event_type=raw_data.get("public_event_type", "Public Exhibition"),
        free_public_access=bool(raw_data.get("free_public_access", True)),
        budget=budget,
        narrative_summary=raw_data.get("narrative_summary", ""),
    )

    compiled = spec.compile_package()

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"compiled_{spec.project_id}.json"
        out_file.write_text(json.dumps(compiled, indent=2), encoding="utf-8")
        compiled["saved_to"] = str(out_file)

    return compiled


def main() -> int:
    parser = argparse.ArgumentParser(description="NouGen Universal Grant Compiler CLI")
    parser.add_argument("spec_file", type=str, help="Path to input grant spec JSON")
    parser.add_argument("--out", type=str, default=None, help="Optional output directory")
    args = parser.parse_args()

    res = compile_grant_file(Path(args.spec_file), Path(args.out) if args.out else None)
    print(json.dumps(res, indent=2))
    return 0 if res.get("is_valid") else 1


if __name__ == "__main__":
    sys.exit(main())
