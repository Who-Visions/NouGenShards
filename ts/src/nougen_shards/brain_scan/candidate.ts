/**
 * Brain Scan data structures. (TS mimic of brain_scan/candidate.py)
 *
 * Python dataclasses become TS interfaces. `NormalizedRecord` has defaults, so a
 * small factory function carries them. `CandidateFile.path` is a pathlib.Path in
 * Python; here it is stored as an absolute path string.
 */

/** Mirrors the Python NormalizedRecord dataclass. */
export interface NormalizedRecord {
  source_tool: string;
  source_kind: string;
  source_path: string;
  project_path: string | null;
  conversation_id: string | null;
  role: string;
  timestamp: string;
  title: string;
  content: string;
  metadata: Record<string, any>;
  parser: string;
  confidence: number;
  source_hash: string | null;
  content_hash: string | null;
}

/** Fields required to build a NormalizedRecord; defaults supplied by the factory. */
export interface NormalizedRecordInit {
  source_tool: string;
  source_kind: string;
  source_path: string;
  project_path: string | null;
  conversation_id: string | null;
  role: string;
  timestamp: string;
  title: string;
  content: string;
  metadata?: Record<string, any>;
  parser?: string;
  confidence?: number;
  source_hash?: string | null;
  content_hash?: string | null;
}

/** Factory mirroring dataclass field defaults. */
export function make_normalized_record(init: NormalizedRecordInit): NormalizedRecord {
  return {
    source_tool: init.source_tool,
    source_kind: init.source_kind,
    source_path: init.source_path,
    project_path: init.project_path,
    conversation_id: init.conversation_id,
    role: init.role,
    timestamp: init.timestamp,
    title: init.title,
    content: init.content,
    metadata: init.metadata ?? {},
    parser: init.parser ?? "unknown",
    confidence: init.confidence ?? 0.0,
    source_hash: init.source_hash ?? null,
    content_hash: init.content_hash ?? null,
  };
}

/** Mirrors the Python CandidateFile dataclass. `path` is an absolute path string. */
export interface CandidateFile {
  path: string;
  tool: string;
  is_project_context: boolean;
  score_tier: string; // "high", "medium", "low"
  size_mb: number;
}

/** Helper: build a CandidateFile (positional parity with the Python constructor). */
export function make_candidate_file(
  path: string,
  tool: string,
  is_project_context: boolean,
  score_tier: string,
  size_mb: number,
): CandidateFile {
  return { path, tool, is_project_context, score_tier, size_mb };
}
