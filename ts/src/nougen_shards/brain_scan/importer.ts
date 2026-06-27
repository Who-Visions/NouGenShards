/**
 * Brain Import pipeline. (TS mimic of brain_scan/importer.py)
 *
 * ImportResult dataclass -> interface. run_import scans, parses, redacts, and calls
 * core.capture (the `from .. import core as shards` binding). Dry-run by default;
 * `confirm=true` performs real writes. path.suffix -> path.extname.
 */
import * as path from "node:path";
import * as shards from "../core.js";
import type { CandidateFile } from "./candidate.js";
import { parse_universal } from "./parsers.js";
import { redact_content } from "./redaction.js";
import { scan_environment } from "./scanner.js";

export interface ImportResult {
  files_scanned: number;
  records_parsed: number;
  shards_created: number;
  duplicates_skipped: number;
  secrets_redacted: number;
}

/** Executes the Brain Import pipeline (Dry-Run by default). */
export function run_import(
  project_path: string | null = null,
  include_unknown: boolean = false,
  source_filter: string | null = null,
  redact: boolean = true,
  confirm: boolean = false,
): ImportResult {
  let candidates: CandidateFile[] = scan_environment(project_path, include_unknown);
  if (source_filter) {
    candidates = candidates.filter((c) => c.tool.toLowerCase() === source_filter.toLowerCase());
  }

  const result: ImportResult = {
    files_scanned: candidates.length,
    records_parsed: 0,
    shards_created: 0,
    duplicates_skipped: 0,
    secrets_redacted: 0,
  };

  if (!confirm) {
    // Fast estimation for dry run
    for (const c of candidates) {
      // Estimate 1 record per file on average if small, maybe more if jsonl
      if (path.extname(c.path) === ".jsonl") {
        result.records_parsed += 10; // heuristic
      } else {
        result.records_parsed += 1;
      }
    }
    return result;
  }

  // Real Execution
  for (const c of candidates) {
    const records = parse_universal(c.path, c.tool, c.is_project_context);
    for (const rec of records) {
      result.records_parsed += 1;

      let content = rec.content;
      let title_text = rec.title;
      if (redact) {
        const redacted = redact_content(content);
        const redacted_title = redact_content(title_text);
        if (redacted !== content || redacted_title !== title_text) {
          result.secrets_redacted += 1;
          content = redacted;
          title_text = redacted_title;
        }
      }

      const tags = ["brain_scan", `tool:${rec.source_tool}`, `kind:${rec.source_kind}`];

      const success = shards.capture(
        "IMPORT",
        `[${rec.source_tool.toUpperCase()}] ${title_text}`,
        content,
        tags,
      );

      if (success) {
        result.shards_created += 1;
      } else {
        result.duplicates_skipped += 1;
      }
    }
  }

  return result;
}
