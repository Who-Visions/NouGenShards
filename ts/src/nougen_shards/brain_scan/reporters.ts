/**
 * Scan / import reporters. (TS mimic of brain_scan/reporters.py)
 *
 * Python `print` -> console.log. f-string field widths like `{tool:<12}` are
 * reproduced with String.padEnd. c.path.name -> path.basename(c.path).
 */
import * as path from "node:path";
import type { CandidateFile } from "./candidate.js";
import type { ImportResult } from "./importer.js";

/** Formats and prints the result of a Brain Scan. */
export function print_scan_report(candidates: CandidateFile[], as_json: boolean = false): void {
  if (as_json) {
    const data = candidates.map((c) => ({
      path: c.path,
      tool: c.tool,
      score: c.score_tier,
      size_mb: c.size_mb,
    }));
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  console.log("\n🧠 NouGenShards Brain Scan\n");

  const high = candidates.filter((c) => c.score_tier === "high");
  const med = candidates.filter((c) => c.score_tier === "medium");

  const tools: Record<string, number> = {};
  for (const c of candidates) {
    tools[c.tool] = (tools[c.tool] ?? 0) + 1;
  }

  console.log("High-confidence AI memory:");
  for (const [tool, count] of Object.entries(tools)) {
    if (tool !== "unknown") {
      console.log(`  .${tool.padEnd(12)} found   ${count} files likely`);
    }
  }

  console.log("\nProject context:");
  for (const c of candidates.filter((c) => c.is_project_context).slice(0, 5)) {
    console.log(`  ${path.basename(c.path)}`);
  }
  if (candidates.filter((c) => c.is_project_context).length > 5) {
    console.log("  ... and more.");
  }

  console.log("\nSkipped danger zones:");
  console.log("  .ssh         skipped by default");
  console.log("  .aws         skipped by default");
  console.log("  .azure       skipped by default");
  console.log("  .config      skipped by default");

  console.log(`\nEstimated new shards: ${high.length * 2 + med.length}`); // Heuristic
  console.log("Cloud calls: 0");
  console.log("Files modified: 0");
  console.log("\nNothing imported.");
  console.log("Run: nougen brain import --confirm");
}

/** Formats and prints the result of a Brain Import. */
export function print_import_report(result: ImportResult, dry_run: boolean, as_json: boolean = false): void {
  if (as_json) {
    console.log(
      JSON.stringify(
        {
          dry_run: dry_run,
          files_scanned: result.files_scanned,
          records_parsed: result.records_parsed,
          shards_created: result.shards_created,
          duplicates_skipped: result.duplicates_skipped,
          secrets_redacted: result.secrets_redacted,
        },
        null,
        2,
      ),
    );
    return;
  }

  if (dry_run) {
    console.log("\n🧠 NouGenShards Brain Import (Dry Run)\n");
    console.log(`Files to scan: ${result.files_scanned}`);
    console.log(`Estimated records: ${result.records_parsed}`);
    console.log("\nRun: nougen brain import --confirm to write to memory.");
  } else {
    console.log("\n🧠 NouGenShards Brain Import Complete\n");
    console.log(`Files scanned:      ${result.files_scanned}`);
    console.log(`Records parsed:     ${result.records_parsed}`);
    console.log(`Shards created:     ${result.shards_created}`);
    console.log(`Duplicates skipped: ${result.duplicates_skipped}`);
    console.log(`Secrets redacted:   ${result.secrets_redacted}`);
    console.log("\n✅ Local memory enriched.");
  }
}
