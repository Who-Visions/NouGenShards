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
  const findings: Finding[] = (Array.isArray(o.findings) ? o.findings : []).flatMap((f: any) =>
    typeof f?.claim === "string" && typeof f?.file === "string"
      ? [{ file: f.file, line: Number(f.line) || undefined, severity: f.severity === "blocking" ? "blocking" : "minor",
           confidence: Math.max(0, Math.min(100, Number(f.confidence) || 0)), claim: f.claim.slice(0, 600), lane }]
      : []);
  return { lane, ok: true, verdict, findings };
}
