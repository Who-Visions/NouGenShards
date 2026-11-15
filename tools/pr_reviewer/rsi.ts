/**
 * rsi.ts — pure RSI mechanics for the aiwithdav3 reviewer (no I/O; every function is unit-tested in rsi.test.ts).
 * Ported from lobehub/awesome-rsi donors; see RSI.md for the source of each mechanism.
 */

export type Score = { checklist: string; held: boolean; repo: string; pr: number; body: string };
export type Item = { id: string; check: string; weight: number; seed_weight?: number; note?: string; stats?: any };
export type Checklist = { version: number; items: Item[]; lessons?: string[]; gate?: any; created?: string; parent?: number };

/** Old-side line numbers a unified-diff patch deletes or modifies. */
export function touchedOldLines(patch: string): Set<number> {
  const s = new Set<number>(); let n = 0;
  for (const l of (patch || "").split("\n")) {
    const h = l.match(/^@@ -(\d+)/); if (h) { n = +h[1]; continue; }
    if (l.startsWith("+")) continue;
    if (l.startsWith("-")) s.add(n);
    n++;
  }
  return s;
}

/** Churn guard (reward hacking): a wholesale rewrite/reformat touches everything and would mark every finding "held".
 *  Files with no patch (binary / too large) or more than `maxTouched` touched lines give no credit and no blame. */
export const MAX_TOUCHED = 150;

/** Judge findings against the follow-up compare. Returns scores; ambiguous findings are omitted, not dismissed. */
export function judgeFindings(findings: any[], compareFiles: any[], ctx: { repo: string; pr: number }, window = 3): Score[] {
  const touched = new Map<string, Set<number> | null>();
  for (const f of compareFiles || []) {
    const s = f.patch ? touchedOldLines(f.patch) : null;
    touched.set(f.previous_filename || f.filename, s && s.size <= MAX_TOUCHED ? s : null);
  }
  const out: Score[] = [];
  for (const f of findings || []) {
    const t = touched.get(f.path);
    if (t === null) continue; // ambiguous churn
    const ln = Number(f.line);
    const held = !!t && [...t].some((x) => Math.abs(x - ln) <= window);
    out.push({ checklist: f.checklist, held, repo: ctx.repo, pr: ctx.pr, body: String(f.body || "") });
  }
  return out;
}

/** Deterministic ~20% holdout (RecurSE-style validation split): the same finding always lands on the same side. */
export function isHoldout(s: Pick<Score, "repo" | "pr" | "body">): boolean {
  let h = 7;
  for (const c of `${s.repo}#${s.pr}:${s.body}`) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 5 === 0;
}

/** Weighted precision of a checklist on a score set: how well the weights rank findings that held. */
export function weightedPrecision(ck: Checklist, rows: Score[]): number {
  let num = 0, den = 0;
  for (const s of rows) { const w = ck.items.find((i) => i.id === s.checklist)?.weight ?? 0.5; num += w * (s.held ? 1 : 0); den += w; }
  return den ? num / den : 0;
}

export const STEP = 0.15, ANCHOR = 0.1, FLOOR = 0.1, GATE_TOL = 0.02, MIN_HOLDOUT = 5;

/** Propose the next checklist version from history.
 *  - learns only from the train split (holdout stays unseen)
 *  - Laplace-smoothed precision, target 0.5*w + 0.5*1.25p
 *  - bounded step per pass (STEP) and a pull toward the seed weight (ANCHOR) — RRSI-style regularisation against drift
 *  - adopt only if holdout weighted precision does not drop by more than GATE_TOL */
export function evolve(ck: Checklist, hist: Score[]): { next: Checklist; adopt: boolean; gate: any } {
  const rows = hist.filter((s) => s && s.checklist);
  const train = rows.filter((s) => !isHoldout(s)), hold = rows.filter(isHoldout);
  const next: Checklist = structuredClone(ck);
  next.version = ck.version + 1; next.parent = ck.version;
  for (const it of next.items) {
    if (it.seed_weight === undefined) it.seed_weight = it.weight;
    const h = train.filter((s) => s.checklist === it.id); if (!h.length) continue;
    const held = h.filter((s) => s.held).length; const p = (held + 1) / (h.length + 2);
    it.stats = { scored: h.length, held, precision: +p.toFixed(2) };
    let target = Math.min(1, Math.max(FLOOR, 0.5 * it.weight + 0.5 * p * 1.25));
    target = (1 - ANCHOR) * target + ANCHOR * it.seed_weight;
    it.weight = +Math.max(FLOOR, it.weight + Math.max(-STEP, Math.min(STEP, target - it.weight))).toFixed(2);
    it.note = h.length >= 3 && p < 0.35 ? "Often dismissed by authors: report only with a concrete failing input." : undefined;
  }
  const before = weightedPrecision(ck, hold), after = weightedPrecision(next, hold);
  const gate = { holdout: hold.length, before: +before.toFixed(3), after: +after.toFixed(3) };
  next.gate = gate;
  const adopt = hold.length < MIN_HOLDOUT || after >= before - GATE_TOL;
  return { next, adopt, gate };
}

/** ACE-style curator: delta-append lessons, merge near-duplicates (token Jaccard), keep the newest `cap`. */
export function curateLessons(old: string[], add: string[], cap = 20, sim = 0.6): string[] {
  const toks = (s: string) => new Set(s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((w) => w.length > 2));
  const jac = (a: Set<string>, b: Set<string>) => { let i = 0; for (const x of a) if (b.has(x)) i++; return i / Math.max(1, a.size + b.size - i); };
  const out: string[] = [];
  for (const l of [...(old || []), ...(add || [])]) {
    const t = toks(l);
    const dup = out.findIndex((o) => jac(toks(o), t) >= sim);
    if (dup >= 0) out.splice(dup, 1); // newer phrasing replaces the older near-duplicate
    out.push(l);
  }
  return out.slice(-cap);
}

/** Self-consistency over independent lane drafts: keep a finding only when >= k distinct lanes raise the same
 *  path within ±window lines. The surviving copy is the highest-confidence one, tagged with its votes. */
export function consensusFindings(drafts: { lane: string; findings: any[] }[], k = 2, window = 3): any[] {
  const all = drafts.flatMap((d) => (d.findings || []).map((f) => ({ ...f, _lane: d.lane })));
  const kept: any[] = [];
  for (const f of all.sort((a, b) => (Number(b.confidence) || 0) - (Number(a.confidence) || 0))) {
    if (kept.some((x) => x.path === f.path && Math.abs(Number(x.line) - Number(f.line)) <= window)) continue;
    const lanes = new Set(all.filter((g) => g.path === f.path && Math.abs(Number(g.line) - Number(f.line)) <= window).map((g) => g._lane));
    if (lanes.size >= k) { const { _lane, ...rest } = f; kept.push({ ...rest, votes: lanes.size }); }
  }
  return kept;
}

/** DGM/OpenEvolve-style archive parent: evolve from the latest version unless the last `stall` proposals were all
 *  rejected by the gate — then restart from the archived version with the best holdout score. */
export function pickParent(archive: Checklist[], rejectedStreak: number, stall = 3): Checklist {
  const sorted = [...archive].sort((a, b) => a.version - b.version);
  const latest = sorted.at(-1)!;
  if (rejectedStreak < stall) return latest;
  return sorted.reduce((best, c) => ((c.gate?.after ?? -1) > (best.gate?.after ?? -1) ? c : best), latest);
}
