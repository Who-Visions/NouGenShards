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
  for (const f of (findings || []).filter(validFinding)) {
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
export function pickParent(archive: Checklist[], rejectedStreak: number, stall = 3, rand: () => number = Math.random): Checklist {
  const sorted = [...archive].sort((a, b) => a.version - b.version);
  const latest = sorted.at(-1)!;
  if (rejectedStreak < stall) return latest;
  // stalled: DGM-style weighted draw over the archive (score-weighted, child-penalised) instead of greedy best
  return dgmParent(sorted, rand);
}

/** JSONL that survives a truncated/corrupt line (a crash mid-append must not take down review/poll/score). */
export function parseJsonl(text: string): any[] {
  const out: any[] = [];
  for (const l of (text || "").split("\n")) { if (!l.trim()) continue; try { const v = JSON.parse(l); if (v && typeof v === "object") out.push(v); } catch { /* skip */ } }
  return out;
}

/** PR heads poll() must not re-queue: anything posted, plus no-verdict runs only inside a cooldown, so a transient
 *  402/429 delays the retry instead of blocking that SHA forever. */
export function seenKeys(entries: any[], now = Date.now(), cooldownMs = 6 * 3600_000): Set<string> {
  const s = new Set<string>();
  for (const e of entries) {
    const k = `${e.repo}#${e.pr}@${e.sha}`;
    if (e.posted) s.add(k);
    else if (e.outcome === "no-verdict" && now - Date.parse(e.finished || e.started || "") < cooldownMs) s.add(k);
  }
  return s;
}

/** Exclusive file lock (O_EXCL create); a lock older than staleMs is taken over. Returns fn's result. */
export function withLock<T>(path: string, fn: () => T, staleMs = 10 * 60_000, waitMs = 30_000): T {
  const fs = require("node:fs");
  const t0 = Date.now();
  for (;;) {
    try { fs.writeFileSync(path, String(process.pid), { flag: "wx" }); break; }
    catch (e: any) {
      if (e.code !== "EEXIST") throw e;
      try { if (Date.now() - fs.statSync(path).mtimeMs > staleMs) { fs.unlinkSync(path); continue; } } catch { continue; }
      if (Date.now() - t0 > waitMs) throw new Error(`lock busy: ${path}`);
      Bun.sleepSync(50);
    }
  }
  try { return fn(); } finally { try { fs.unlinkSync(path); } catch {} }
}

/** Rollback is append-only: the target version's items+lessons are re-issued as a NEW version (history is kept). */
export function rollbackTo(archive: Checklist[], target: number): Checklist {
  const src = archive.find((c) => c.version === target);
  if (!src) throw new Error(`no checklist v${target} in archive`);
  const top = Math.max(...archive.map((c) => c.version));
  return { ...structuredClone(src), version: top + 1, parent: target, created: new Date().toISOString(), gate: { rollback_of: target } };
}

/** One-screen status of the loop: versions, active one, rejected streak, recent gate decisions, per-item weights. */
export function rsiStatus(archive: Checklist[], streak: number, scores: any[]) {
  const sorted = [...archive].sort((a, b) => a.version - b.version);
  const active = sorted.at(-1);
  const judged = scores.filter((s) => s.checklist);
  return {
    versions: sorted.map((c) => ({ v: c.version, parent: c.parent ?? null, gate: c.gate ?? null, created: c.created ?? null })),
    active: active?.version ?? null,
    rejected_streak: streak,
    judged: judged.length, held: judged.filter((s) => s.held).length,
    rejections: scores.filter((s) => s.gate === "rejected").slice(-5),
    weights: (active?.items || []).map((i) => ({ id: i.id, weight: i.weight, seed: i.seed_weight ?? null, stats: i.stats ?? null })),
  };
}

/** Follow GitHub's 100-per-page lists until a short page (or `max` pages). */
export async function collectPages(fetchPage: (page: number) => Promise<any[]>, max = 30): Promise<any[]> {
  const out: any[] = [];
  for (let page = 1; page <= max; page++) { const b = await fetchPage(page); out.push(...b); if (b.length < 100) break; }
  return out;
}

/** Model verdicts arrive in any case ("approve"); compare only after normalising. */
export const normVerdict = (v: unknown) => String(v ?? "").trim().toUpperCase();

// ---- from the fleet's code read of jennyzzt/dgm and metaevo-ai/harness-zero (analysis/awesome-rsi-reverse) ----

/** DGM `choose_selfimproves` (score_child_prop): parent weight = sigmoid(10*(score-0.5)) / (1 + children).
 *  Good versions get picked more, but a version that has already spawned many children yields to its siblings,
 *  so the archive keeps exploring instead of hill-climbing one line. `rand` is injectable for tests. */
export function dgmParent(archive: Checklist[], rand: () => number = Math.random): Checklist {
  const kids = new Map<number, number>();
  for (const c of archive) if (c.parent != null) kids.set(c.parent, (kids.get(c.parent) || 0) + 1);
  const w = archive.map((c) => { const s = c.gate?.after ?? 0.5; return 1 / (1 + Math.exp(-10 * (s - 0.5))) / (1 + (kids.get(c.version) || 0)); });
  const total = w.reduce((a, b) => a + b, 0);
  let r = rand() * total;
  for (let i = 0; i < archive.length; i++) { r -= w[i]; if (r <= 0) return archive[i]; }
  return archive.at(-1)!;
}

/** harness-zero drift guard: evolution may change weights, notes and stats — never an item's id or its check text.
 *  Returns the list of violations (empty = safe to write). */
export function driftViolations(prev: Checklist, next: Checklist): string[] {
  const out: string[] = [];
  const before = new Map(prev.items.map((i) => [i.id, i.check]));
  for (const it of next.items) {
    if (!before.has(it.id)) out.push(`new item ${it.id} appeared outside a proposal`);
    else if (before.get(it.id) !== it.check) out.push(`check text of ${it.id} changed`);
    if (!(it.weight >= 0 && it.weight <= 1)) out.push(`weight of ${it.id} out of [0,1]`);
  }
  for (const id of before.keys()) if (!next.items.some((i) => i.id === id)) out.push(`item ${id} dropped`);
  return out;
}

/** DGM `is_compiled_self_improve`: only well-formed records feed the loop (a finding needs path, numeric line,
 *  checklist id). Malformed records are skipped instead of scoring as dismissed. */
export function validFinding(f: any): boolean {
  return !!f && typeof f.path === "string" && f.path.length > 0 && Number.isFinite(Number(f.line)) && Number(f.line) > 0 && typeof f.checklist === "string" && f.checklist.length > 0;
}

/** score(): the compare result's file list, or null when the compare failed / is malformed (judge later, not "dismissed"). */
export function compareFilesOrNull(cmp: any): any[] | null {
  return cmp && Array.isArray(cmp.files) ? cmp.files : null;
}
