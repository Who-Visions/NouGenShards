import json
from typing import List
from .candidate import CandidateFile
from .importer import ImportResult

def print_scan_report(candidates: List[CandidateFile], as_json: bool = False):
    """Formats and prints the result of a Brain Scan."""
    if as_json:
        data = [{"path": str(c.path), "tool": c.tool, "score": c.score_tier, "size_mb": c.size_mb} for c in candidates]
        print(json.dumps(data, indent=2))
        return

    print("\n🧠 NouGenShards Brain Scan\n")
    
    high = [c for c in candidates if c.score_tier == "high"]
    med = [c for c in candidates if c.score_tier == "medium"]
    
    tools = {}
    for c in candidates:
        tools[c.tool] = tools.get(c.tool, 0) + 1

    print("High-confidence AI memory:")
    for tool, count in tools.items():
        if tool != "unknown":
            print(f"  .{tool:<12} found   {count} files likely")
            
    print("\nProject context:")
    for c in [c for c in candidates if c.is_project_context][:5]:
        print(f"  {c.path.name}")
    if len([c for c in candidates if c.is_project_context]) > 5:
        print("  ... and more.")

    print("\nSkipped danger zones:")
    print("  .ssh         skipped by default")
    print("  .aws         skipped by default")
    print("  .azure       skipped by default")
    print("  .config      skipped by default")

    print(f"\nEstimated new shards: {len(high) * 2 + len(med)}") # Heuristic
    print("Cloud calls: 0")
    print("Files modified: 0")
    print("\nNothing imported.")
    print("Run: nougen brain import --confirm")

def print_import_report(result: ImportResult, dry_run: bool, as_json: bool = False):
    """Formats and prints the result of a Brain Import."""
    if as_json:
        print(json.dumps({
            "dry_run": dry_run,
            "files_scanned": result.files_scanned,
            "records_parsed": result.records_parsed,
            "shards_created": result.shards_created,
            "duplicates_skipped": result.duplicates_skipped,
            "secrets_redacted": result.secrets_redacted
        }, indent=2))
        return

    if dry_run:
        print("\n🧠 NouGenShards Brain Import (Dry Run)\n")
        print(f"Files to scan: {result.files_scanned}")
        print(f"Estimated records: {result.records_parsed}")
        print("\nRun: nougen brain import --confirm to write to memory.")
    else:
        print("\n🧠 NouGenShards Brain Import Complete\n")
        print(f"Files scanned:      {result.files_scanned}")
        print(f"Records parsed:     {result.records_parsed}")
        print(f"Shards created:     {result.shards_created}")
        print(f"Duplicates skipped: {result.duplicates_skipped}")
        print(f"Secrets redacted:   {result.secrets_redacted}")
        print("\n✅ Local memory enriched.")
