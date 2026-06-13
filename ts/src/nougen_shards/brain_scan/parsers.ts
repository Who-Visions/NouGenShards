/**
 * Source file parsers. (TS mimic of brain_scan/parsers.py)
 *
 * Produces NormalizedRecord[]. md5 hashing via node:crypto createHash. JSON parsing
 * via JSON.parse (a thrown SyntaxError mirrors json.JSONDecodeError). Path objects
 * become absolute path strings; path.basename/extname stand in for Path.name/.suffix.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import * as path from "node:path";
import { make_normalized_record, type NormalizedRecord } from "./candidate.js";

function _safe_read(p: string): string {
  try {
    // errors='replace' equivalent: Node decodes UTF-8 with U+FFFD substitutions.
    return readFileSync(p, { encoding: "utf-8" });
  } catch {
    return "";
  }
}

function _hash(content: string): string {
  return createHash("md5").update(content, "utf-8").digest("hex");
}

function _timestamp(): string {
  return new Date().toISOString() + "Z";
}

/** Mirrors pathlib's str(path.absolute()). */
function _abs(p: string): string {
  return path.resolve(p);
}

export function parse_json(p: string, tool: string, is_project: boolean): NormalizedRecord[] {
  const content = _safe_read(p);
  if (!content) return [];
  try {
    const data = JSON.parse(content);
    let title = path.basename(p);
    // Heuristic extraction
    if (data && typeof data === "object" && !Array.isArray(data)) {
      if ("name" in data) title = String(data.name);
      else if ("title" in data) title = String(data.title);
    }
    return [
      make_normalized_record({
        source_tool: tool,
        source_kind: "json_data",
        source_path: _abs(p),
        project_path: is_project ? path.dirname(p) : null,
        conversation_id: null,
        role: "system",
        timestamp: _timestamp(),
        title,
        content: JSON.stringify(data, null, 2).slice(0, 5000), // truncate huge JSON
        parser: "json_parser",
        confidence: 0.5,
        source_hash: _hash(content),
        content_hash: _hash(JSON.stringify(data)),
      }),
    ];
  } catch {
    return [];
  }
}

export function parse_jsonl(p: string, tool: string, is_project: boolean): NormalizedRecord[] {
  const content = _safe_read(p);
  if (!content) return [];
  const records: NormalizedRecord[] = [];
  const lines = content.split(/\r\n|\r|\n/);
  for (let idx = 0; idx < lines.length; idx++) {
    const line = lines[idx];
    try {
      const data = JSON.parse(line);
      const role = data?.role ?? "system";
      const raw = data?.content ?? JSON.stringify(data);
      const text = typeof raw === "string" ? raw : String(raw);
      records.push(
        make_normalized_record({
          source_tool: tool,
          source_kind: "jsonl_event",
          source_path: _abs(p),
          project_path: is_project ? path.dirname(p) : null,
          conversation_id: data?.session_id ?? null,
          role,
          timestamp: data?.timestamp ?? _timestamp(),
          title: `${path.basename(p)} - Line ${idx}`,
          content: text.slice(0, 5000),
          parser: "jsonl_parser",
          confidence: 0.7,
          source_hash: _hash(line),
          content_hash: _hash(text),
        }),
      );
    } catch {
      continue;
    }
  }
  return records;
}

export function parse_markdown(p: string, tool: string, is_project: boolean): NormalizedRecord[] {
  const content = _safe_read(p);
  if (!content) return [];
  const title = path.basename(p);
  return [
    make_normalized_record({
      source_tool: tool,
      source_kind: "markdown_document",
      source_path: _abs(p),
      project_path: is_project ? path.dirname(p) : null,
      conversation_id: null,
      role: "system",
      timestamp: _timestamp(),
      title,
      content: content.slice(0, 10000),
      parser: "markdown_parser",
      confidence: 0.8,
      source_hash: _hash(content),
      content_hash: _hash(content.slice(0, 10000)),
    }),
  ];
}

export function parse_universal(p: string, tool: string, is_project: boolean): NormalizedRecord[] {
  const suffix = path.extname(p);
  if (suffix === ".json") {
    return parse_json(p, tool, is_project);
  } else if (suffix === ".jsonl") {
    return parse_jsonl(p, tool, is_project);
  } else if (suffix === ".md" || suffix === ".txt") {
    return parse_markdown(p, tool, is_project);
  }

  // Fallback to a basic read for other text files
  const content = _safe_read(p);
  if (!content) return [];
  return [
    make_normalized_record({
      source_tool: tool,
      source_kind: "text_log",
      source_path: _abs(p),
      project_path: is_project ? path.dirname(p) : null,
      conversation_id: null,
      role: "system",
      timestamp: _timestamp(),
      title: path.basename(p),
      content: content.slice(0, 5000),
      parser: "universal_text",
      confidence: 0.3,
      source_hash: _hash(content),
      content_hash: _hash(content.slice(0, 5000)),
    }),
  ];
}
