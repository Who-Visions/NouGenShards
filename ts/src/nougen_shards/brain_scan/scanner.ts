/**
 * Environment scanner. (TS mimic of brain_scan/scanner.py)
 *
 * Python's `Path.rglob("*")` is reproduced via a recursive fs.readdirSync walk
 * (`_rglob`) that yields every descendant path. SKIP_DIRS / DANGER_ZONES, the
 * depth limit of 5 under each global root, the 25MB cap, and absolute-path
 * dedupe are all preserved.
 */
import { readdirSync, statSync } from "node:fs";
import * as path from "node:path";
import { type CandidateFile, make_candidate_file } from "./candidate.js";
import { classify_file, detect_tool } from "./classifiers.js";
import {
  DANGER_ZONES,
  GLOBAL_ROOTS,
  PROJECT_FILES,
  PROJECT_ROOT_NAMES,
  SKIP_DIRS,
  SUPPORTED_EXTS,
} from "./registry.js";

/** Splits a path into components, mirroring pathlib.Path.parts. */
function path_parts(p: string): string[] {
  const normalized = p.replace(/\\/g, "/");
  return normalized.split("/").filter((seg) => seg.length > 0);
}

/** Recursive descendant walk standing in for pathlib's Path.rglob("*"). */
function _rglob(root: string): string[] {
  const out: string[] = [];
  let entries;
  try {
    entries = readdirSync(root, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = path.join(root, entry.name);
    out.push(full);
    let isDir = false;
    try {
      isDir = entry.isDirectory();
    } catch {
      isDir = false;
    }
    if (isDir) {
      // Avoid following into directories that resolve to junk; the caller's
      // _is_safe_dir still filters files, but recursing everywhere matches
      // Python rglob semantics (which does descend all dirs).
      for (const child of _rglob(full)) {
        out.push(child);
      }
    }
  }
  return out;
}

function _is_file(p: string): boolean {
  try {
    return statSync(p).isFile();
  } catch {
    return false;
  }
}

function _exists_dir(p: string): boolean {
  try {
    return statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function _is_safe_dir(p: string): boolean {
  for (const d of path_parts(p)) {
    const lower = d.toLowerCase();
    if (SKIP_DIRS.has(lower) || DANGER_ZONES.has(lower) || d.startsWith(".ssh") || d.startsWith(".aws")) {
      return false;
    }
  }
  return true;
}

/** Scans the environment for local AI tool history and context. */
export function scan_environment(
  project_path: string | null = null,
  include_unknown: boolean = false,
): CandidateFile[] {
  const candidates: CandidateFile[] = [];

  // 1. Project Scan
  if (project_path) {
    const root = path.resolve(project_path);
    for (const p of _rglob(root)) {
      if (_is_file(p) && SUPPORTED_EXTS.has(path.extname(p)) && _is_safe_dir(path.dirname(p))) {
        const parts = path_parts(p);
        const is_proj_ctx =
          parts.some((part) => PROJECT_ROOT_NAMES.includes(part)) || PROJECT_FILES.includes(path.basename(p));
        if (is_proj_ctx || include_unknown) {
          const score = classify_file(p);
          if (score === "high" || score === "medium") {
            const tool = detect_tool(p);
            const sz = statSync(p).size / (1024 * 1024);
            if (sz <= 25) {
              // Skip files > 25MB
              candidates.push(make_candidate_file(p, tool, true, score, sz));
            }
          }
        }
      }
    }
  }

  // 2. Global Scan
  // We skip Path.home() generic rglob to avoid crawling the whole user disk.
  // We only scan the specific tool directories (GLOBAL_ROOTS[1:]).
  for (const g_root of GLOBAL_ROOTS.slice(1)) {
    if (!_exists_dir(g_root)) {
      continue;
    }
    for (const p of _rglob(g_root)) {
      // Limit depth relative to g_root to prevent infinite symlinks
      const rel = path.relative(g_root, p);
      if (path_parts(rel).length > 5) {
        continue;
      }

      if (_is_file(p) && SUPPORTED_EXTS.has(path.extname(p)) && _is_safe_dir(path.dirname(p))) {
        const score = classify_file(p);
        if (score === "high" || score === "medium") {
          const tool = detect_tool(p);
          if (tool !== "unknown" || include_unknown) {
            const sz = statSync(p).size / (1024 * 1024);
            if (sz <= 25) {
              candidates.push(make_candidate_file(p, tool, false, score, sz));
            }
          }
        }
      }
    }
  }

  // Deduplicate candidates by path
  const seen = new Set<string>();
  const unique_cands: CandidateFile[] = [];
  for (const c of candidates) {
    const s_path = path.resolve(c.path);
    if (!seen.has(s_path)) {
      seen.add(s_path);
      unique_cands.push(c);
    }
  }

  return unique_cands;
}
