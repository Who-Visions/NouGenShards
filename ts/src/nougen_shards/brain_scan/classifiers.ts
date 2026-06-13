/**
 * File signal classifiers. (TS mimic of brain_scan/classifiers.py)
 *
 * Python pathlib.Path operations are mapped to node:path basename/dirname/extname.
 * Inputs are absolute path strings instead of Path objects.
 */
import * as path from "node:path";
import { HIGH_SIGNAL_TERMS, LOW_SIGNAL_TERMS, MEDIUM_SIGNAL_TERMS } from "./registry.js";

/** Splits a path into its components, mirroring pathlib.Path.parts. */
function path_parts(p: string): string[] {
  // Normalize separators, drop empty segments and any drive-letter root.
  const normalized = p.replace(/\\/g, "/");
  return normalized.split("/").filter((seg) => seg.length > 0);
}

/** Scores a file as 'high', 'medium', or 'low' signal based on path and name heuristics. */
export function classify_file(p: string): string {
  const name_lower = path.basename(p).toLowerCase();
  const parent_lower = path.basename(path.dirname(p)).toLowerCase();

  // 1. Immediate Low Signal Rejection
  for (const term of LOW_SIGNAL_TERMS) {
    if (name_lower.includes(term) || parent_lower.includes(term)) {
      return "low";
    }
  }

  // 2. Check High Signal
  for (const term of HIGH_SIGNAL_TERMS) {
    if (name_lower.includes(term) || parent_lower.includes(term)) {
      return "high";
    }
  }

  // 3. Check Medium Signal
  for (const term of MEDIUM_SIGNAL_TERMS) {
    if (name_lower.includes(term) || parent_lower.includes(term)) {
      return "medium";
    }
  }

  // Default fallback for recognized extensions that didn't match specific terms
  const suffix = path.extname(p);
  if (suffix === ".md" || suffix === ".txt") {
    return "medium";
  }

  return "low";
}

/** Attempts to identify the source tool from the path. */
export function detect_tool(p: string): string {
  const parts = path_parts(p).map((part) => part.toLowerCase());
  for (const tool of [
    "claude", "gemini", "codex", "cursor", "continue", "copilot",
    "openhands", "mem0", "ollama", "qwen", "roo", "vscode", "github",
  ]) {
    if (parts.includes(`.${tool}`) || parts.includes(tool)) {
      return tool;
    }
  }
  return "unknown";
}
