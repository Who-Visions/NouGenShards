// Pure helpers for aiwithdav3_review.ts, kept apart so they can be tested without running a review.
export type Finding = { file: string; line?: number; severity: "blocking" | "minor"; confidence: number; claim: string; lane?: string };
export type LaneOut = { lane: string; ok: boolean; verdict?: "READY" | "CHANGES"; findings: Finding[]; err?: string };

// Pull the last JSON object out of a model answer; anything else is a failure.
export function parseJson(text: string): any {
  const fenced = [...text.matchAll(/```(?:json)?\s*([\s\S]*?)```/g)].map((m) => m[1]);
  const cands = fenced.length ? fenced.reverse() : [];
  // The last object that opens with a "verdict" key, pretty-printed or not.
  const starts = [...text.matchAll(/\{\s*"verdict"/g)].map((m) => m.index!);
  if (starts.length) cands.push(text.slice(starts[starts.length - 1]));
  cands.push(text); // whole answer as a last resort
  for (const c of cands) {
    let depth = 0, end = -1;
    const s = c.slice(c.indexOf("{"));
    let inStr = false, esc = false;
    for (let k = 0; k < s.length; k++) {
      const ch = s[k];
      if (inStr) { if (esc) esc = false; else if (ch === "\\") esc = true; else if (ch === '"') inStr = false; continue; }
      if (ch === '"') inStr = true; else if (ch === "{") depth++; else if (ch === "}" && --depth === 0) { end = k; break; }
    }
    if (end < 0) continue;
    try { return JSON.parse(s.slice(0, end + 1)); } catch { /* next */ }
  }
  throw new Error("no JSON verdict in answer");
}
export function normalize(lane: string, o: any): LaneOut {
  const verdict = o?.verdict === "READY" ? "READY" : o?.verdict === "CHANGES" ? "CHANGES" : undefined;
  if (!verdict) throw new Error("verdict missing");
  // Malformed findings fail the whole lane: erasing or downgrading them could hide a blocker.
  if (o.findings != null && !Array.isArray(o.findings)) throw new Error("findings is not a list");
  const findings: Finding[] = (o.findings || []).map((f: any, i: number) => {
    if (typeof f?.file !== "string" || !f.file || typeof f?.claim !== "string" || !f.claim) throw new Error(`finding ${i} lacks file or claim`);
    if (f.severity !== "blocking" && f.severity !== "minor") throw new Error(`finding ${i} has severity ${JSON.stringify(f.severity)}`);
    const c = Number(f.confidence);
    if (!Number.isFinite(c) || c < 0 || c > 100) throw new Error(`finding ${i} has confidence ${JSON.stringify(f.confidence)}`);
    return { file: f.file, line: Number(f.line) || undefined, severity: f.severity, confidence: c, claim: f.claim.slice(0, 600), lane };
  });
  return { lane, ok: true, verdict, findings };
}

// CRITIC-style grounding: check a finding against hard evidence before any model judges it.
// A finding on a file the diff does not touch, or on a line past the end of that file, is
// rejected here. Returns the reason, or null when the finding is grounded.
export function changedFiles(diff: string): Set<string> {
  return new Set([...diff.matchAll(/^\+\+\+ b\/(.+)$/gm)].map((m) => m[1].trim()));
}
export function ungrounded(f: Finding, files: Set<string>, lineCount: (file: string) => number | null): string | null {
  if (!files.has(f.file)) return `${f.file} is not changed by this diff`;
  if (f.line != null) {
    const n = lineCount(f.file);
    if (n == null) return `${f.file} does not exist at the PR head`;
    if (f.line < 1 || f.line > n) return `${f.file} has ${n} lines, no line ${f.line}`;
  }
  return null;
}

// Experience playbook (ExpeL / Reflexion / ACE): lessons distilled from findings the supervisor
// or grounding rejected, kept short and deduplicated, newest first.
export type Lesson = { at: string; repo: string; lesson: string };
export function playbookText(lessons: Lesson[], max = 10): string {
  const seen = new Set<string>(); const out: string[] = [];
  for (const l of [...lessons].reverse()) {
    const k = l.lesson.toLowerCase().replace(/\s+/g, " ").slice(0, 120);
    if (seen.has(k)) continue; seen.add(k); out.push(`- ${l.lesson}`);
    if (out.length >= max) break;
  }
  return out.length ? `Lessons from earlier reviews (findings like these were wrong, do not repeat them):\n${out.join("\n")}` : "";
}
