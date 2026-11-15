#!/usr/bin/env bun
/**
 * aiwithdav3 PR reviewer — failsafe, posts real GitHub reviews, never merges.
 *
 *   bun review.ts review <owner/repo> <pr> [--dry-run] [--fail-lane <lane>[,<lane>]] [--force]
 *   bun review.ts poll [--owner Who-Visions] [--since-hours 72] [--max 5]
 *   bun review.ts score                       # RSI pass over every logged review
 *   bun review.ts rsi status|evolve|rollback <v>   # RSI loop: inspect, run a scoring pass, roll back (append-only)
 *   bun review.ts whoami
 *
 * Failsafe rules:
 *  - token AIWITHDAV3_GITHUB_PAT_20261115 from the keymaker; GET /user must be aiwithdav3 or nothing runs.
 *  - lanes in order: huggingface -> openrouter -> ollama-cloud (NouGenOpen) -> local gemma4:e2b-qat -> agy.
 *    Empty output or no parseable verdict = lane failure, never approval.
 *  - a supervisor pass on a DIFFERENT lane checks the verdict; no supervisor, or a disagreement, means
 *    APPROVE is downgraded to COMMENT.
 *  - PR head SHA is re-read just before posting and pinned as commit_id; a moved head aborts the post.
 *  - one review per repo#pr@sha (ledger + a live check of existing aiwithdav3 reviews).
 *  - the only GitHub write is POST /pulls/{n}/reviews. There is no merge code path.
 */
import { mkdirSync, existsSync, readFileSync, writeFileSync, appendFileSync, readdirSync, renameSync } from "node:fs";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import { consensusFindings, curateLessons, evolve, judgeFindings, collectPages, normVerdict, parseJsonl, pickParent, rollbackTo, rsiStatus, seenKeys, withLock } from "./rsi";

const HERE = dirname(import.meta.path);
const ROOT = join(homedir(), ".nougen", "research", "reviews", "aiwithdav3");
const LEDGER = join(ROOT, "ledger.jsonl");
const CHECKDIR = join(ROOT, "checklist");
const REVIEWER = "aiwithdav3";
// every aiwithdav3 token the keymaker holds, newest first; each repo uses the first one that can read it
// (the fine-grained PAT covers only aiwithdav3-owned + public org repos; the classic one covers private org repos)
const TOKEN_NAMES = (process.env.AIWITHDAV3_TOKEN_NAMES || "AIWITHDAV3_GITHUB_PAT_20261115,GITHUB_TOKEN_AIWITHDAV3_CLASSIC_20261112,GITHUB_TOKEN_AIWITHDAV3").split(",");
const PY = process.env.NOUGEN_PYTHON ||
  [join(homedir(), "Outpost", "NouGen", ".venv", "Scripts", "pythonw.exe"), "pythonw", "python"].find((p) => !p.includes("\\") || existsSync(p))!;
const LANES = ["huggingface", "openrouter", "ollama-cloud", "local-e2b", "agy"] as const;
type Lane = (typeof LANES)[number];
mkdirSync(CHECKDIR, { recursive: true });

// ---------------------------------------------------------------- util
const args = process.argv.slice(2);
const flag = (n: string) => args.includes(`--${n}`);
const opt = (n: string, d = "") => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const stamp = () => new Date().toISOString().replace(/[:.]/g, "").slice(0, 15) + "Z";
const eastern = (d = new Date()) => d.toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
function log(msg: string) { const line = `[${eastern()}] ${msg}`; console.log(line); appendFileSync(join(ROOT, "run.log"), line + "\n"); }

async function py(req: object, timeoutMs = 300_000): Promise<any> {
  const p = Bun.spawn([PY, join(HERE, "bridge.py")], { stdin: "pipe", stdout: "pipe", stderr: "pipe", windowsHide: true });
  p.stdin.write(JSON.stringify(req)); p.stdin.end();
  const timer = setTimeout(() => p.kill(), timeoutMs);
  const out = await new Response(p.stdout).text(); clearTimeout(timer);
  try { return JSON.parse(out); } catch { return { ok: false, error: `bridge gave no JSON (exit ${await p.exited})` }; }
}

// ---------------------------------------------------------------- GitHub (as aiwithdav3)
let TOKEN = "";
async function gh(path: string, init: RequestInit & { accept?: string } = {}): Promise<Response> {
  const url = path.startsWith("http") ? path : `https://api.github.com${path}`;
  return fetch(url, { ...init, signal: AbortSignal.timeout(60_000), headers: {
    Authorization: `Bearer ${TOKEN}`, Accept: init.accept || "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "nougen-pr-reviewer", ...(init.headers || {}) } });
}
async function ghJson(path: string, init: RequestInit = {}) {
  const r = await gh(path, init);
  if (!r.ok) throw new Error(`GitHub ${init.method || "GET"} ${path} -> ${r.status} ${(await r.text()).slice(0, 300)}`);
  return r.json();
}
let TOKENS: { name: string; value: string; fp: string }[] = [];
async function auth() {
  for (const name of TOKEN_NAMES) {
    const s = await py({ op: "secret", name }, 60_000);
    if (!s.ok || !s.value) continue;
    TOKEN = s.value;
    const me = await ghJson("/user").catch(() => null);
    if (me?.login !== REVIEWER) { log(`token ${name} is not ${REVIEWER}; dropped`); continue; }
    TOKENS.push({ name, value: s.value, fp: new Bun.CryptoHasher("sha256").update(s.value).digest("hex").slice(0, 12) });
  }
  if (!TOKENS.length) throw new Error(`no keymaker token answers as ${REVIEWER}; refusing`);
  TOKEN = TOKENS[0].value;
  return { login: REVIEWER, tokens: TOKENS.map((t) => `${t.name} fp ${t.fp}`) };
}
async function useTokenFor(repo: string) {
  for (const t of TOKENS) { TOKEN = t.value; if ((await gh(`/repos/${repo}`)).ok) return t.name; }
  throw new Error(`no ${REVIEWER} token can read ${repo}`);
}

// ---------------------------------------------------------------- checklist (RSI-versioned)
function currentChecklist(): any {
  const vs = readdirSync(CHECKDIR).filter((f) => /^v\d+\.json$/.test(f)).sort((a, b) => +a.slice(1, -5) - +b.slice(1, -5));
  if (!vs.length) { const seed = readFileSync(join(HERE, "checklist.json"), "utf8"); writeFileSync(join(CHECKDIR, "v1.json"), seed); return JSON.parse(seed); }
  return JSON.parse(readFileSync(join(CHECKDIR, vs.at(-1)!), "utf8"));
}

function buildPrompt(ck: any, pr: any, diff: string, truncated: boolean) {
  const items = ck.items.filter((i: any) => i.weight >= 0.25)
    .map((i: any) => `- [${i.id}] (weight ${i.weight.toFixed(2)}) ${i.check}${i.note ? ` NOTE: ${i.note}` : ""}`).join("\n");
  const lessons = (ck.lessons || []).slice(-8).map((l: string) => `- ${l}`).join("\n");
  const system = `You are a senior code reviewer posting a GitHub review. Checklist version v${ck.version}.\n` +
    `How to work:\n${ck.technique.map((t: string) => `- ${t}`).join("\n")}\n` +
    `Checklist (higher weight = historically held up more often):\n${items}\n` +
    (lessons ? `Lessons from past reviews:\n${lessons}\n` : "") +
    `Verdict rules: REQUEST_CHANGES only for a P1 (bug, security, data loss, broken consumer). APPROVE when no P1/P2 remain. ` +
    `COMMENT when unsure or only P2/P3.\nReply with ONE JSON object and nothing else:\n` +
    `{"verdict":"APPROVE|REQUEST_CHANGES|COMMENT","door":"one-way|two-way","summary":"2-4 sentences",` +
    `"findings":[{"checklist":"<item id>","severity":"P1|P2|P3","confidence":0-100,"path":"<file>","line":<RIGHT-side line number in the new file>,"body":"problem. Fix: one line."}]}`;
  const user = `PR ${pr.base.repo.full_name}#${pr.number}: ${pr.title}\nAuthor: ${pr.user.login}\nBody:\n${(pr.body || "(none)").slice(0, 3000)}\n\n` +
    `Diff${truncated ? " (TRUNCATED: say coverage was limited)" : ""}:\n${diff}`;
  return { system, user };
}

// ---------------------------------------------------------------- lanes
function extractJson(text: string): any | null {
  if (!text) return null;
  const t = text.replace(/<think>[\s\S]*?<\/think>/g, "");
  const cands = [...t.matchAll(/```(?:json)?\s*([\s\S]*?)```/g)].map((m) => m[1]);
  const s = t.indexOf("{"), e = t.lastIndexOf("}");
  if (s >= 0 && e > s) cands.push(t.slice(s, e + 1));
  for (const c of cands) { try { return JSON.parse(c); } catch {} }
  return null;
}

async function callLane(lane: Lane, system: string, user: string, failLanes: Set<string>): Promise<{ text: string; model: string }> {
  if (failLanes.has(lane)) throw new Error("forced failure (--fail-lane)");
  if (lane === "local-e2b") {
    const r = await fetch("http://localhost:11434/v1/chat/completions", { method: "POST", signal: AbortSignal.timeout(600_000),
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: "gemma4:e2b-qat", max_tokens: 8192, temperature: 0.1,
        messages: [{ role: "system", content: system }, { role: "user", content: user.slice(0, 14_000) }] }) });
    if (!r.ok) throw new Error(`ollama ${r.status}`);
    const j: any = await r.json();
    return { text: j.choices?.[0]?.message?.content || "", model: "gemma4:e2b-qat" };
  }
  if (lane === "agy") {
    const dir = join(ROOT, "agy-in"); mkdirSync(dir, { recursive: true });
    const f = join(dir, `${stamp()}.md`); writeFileSync(f, `${system}\n\n----\n\n${user}`);
    const exe = Bun.which("agy"); if (!exe) throw new Error("agy not installed");
    const prompt = `Read the file ${f.replace(/\\/g, "/")} and follow its instructions exactly. Read-only: do not edit files, push, comment or merge. Output only the JSON object it asks for.`;
    const p = Bun.spawn([exe, "--dangerously-skip-permissions", "--print-timeout", "900s", "-p", prompt],
      { stdin: "ignore", stdout: "pipe", stderr: "pipe", windowsHide: true });
    const timer = setTimeout(() => p.kill(), 960_000);
    const text = await new Response(p.stdout).text(); clearTimeout(timer);
    return { text, model: "agy" };
  }
  const r = await py({ op: "ask", lane, system, prompt: user, max_tokens: 4096, timeout: 180 }, 900_000);
  if (!r.ok) throw new Error(r.error);
  return { text: r.content, model: `${r.provider}/${r.model}` };
}

const VERDICTS = new Set(["APPROVE", "REQUEST_CHANGES", "COMMENT"]);
async function reviewWithFallback(system: string, user: string, failLanes: Set<string>, attempts: any[]) {
  for (const lane of LANES) {
    const t0 = Date.now();
    try {
      const { text, model } = await callLane(lane, system, user, failLanes);
      const j = extractJson(text);
      const v = String(j?.verdict || "").toUpperCase();
      if (!j || !VERDICTS.has(v) || !String(j.summary || "").trim()) throw new Error(`no verdict (${(text || "").length} chars)`);
      j.verdict = v; j.findings = Array.isArray(j.findings) ? j.findings : [];
      attempts.push({ lane, model, ok: true, ms: Date.now() - t0 });
      log(`  lane ${lane} OK via ${model} -> ${v}`);
      return { lane, model, result: j };
    } catch (e: any) {
      attempts.push({ lane, ok: false, ms: Date.now() - t0, error: String(e?.message || e).slice(0, 300) });
      log(`  lane ${lane} FAILED: ${String(e?.message || e).slice(0, 160)}`);
    }
  }
  return null;
}

async function supervise(primaryLane: Lane, primaryModel: string, verdict: any, diff: string, failLanes: Set<string>, attempts: any[]) {
  const system = `You supervise another reviewer. Check its verdict against the diff. Reject findings that cite lines not in the diff, ` +
    `misread the code, or are style nits. Reply with ONE JSON object: {"agree":true|false,"verdict":"APPROVE|REQUEST_CHANGES|COMMENT",` +
    `"drop":[indexes of findings that are wrong],"reason":"one sentence"}`;
  const user = `Reviewer verdict:\n${JSON.stringify(verdict, null, 1)}\n\nDiff:\n${diff.slice(0, 40_000)}`;
  // any lane may supervise except the exact model that wrote the verdict; same-lane retries rotate models
  const order: Lane[] = [...LANES.filter((l) => l !== primaryLane && l !== "agy"), primaryLane, "agy"].filter((l, i, a) => a.indexOf(l) === i) as Lane[];
  for (const lane of order) {
    const t0 = Date.now();
    try {
      let { text, model } = await callLane(lane, system, user, failLanes);
      if (model === primaryModel) ({ text, model } = await callLane(lane, system, user, failLanes));
      if (model === primaryModel) throw new Error("only the primary model answered");
      const j = extractJson(text);
      if (!j || typeof j.agree !== "boolean") throw new Error("no supervisor verdict");
      attempts.push({ lane, model, role: "supervisor", ok: true, ms: Date.now() - t0 });
      log(`  supervisor ${lane} via ${model}: agree=${j.agree} (${j.reason || ""})`);
      if (j.verdict) j.verdict = normVerdict(j.verdict);
      return { lane, model, ...j };
    } catch (e: any) {
      attempts.push({ lane, role: "supervisor", ok: false, ms: Date.now() - t0, error: String(e?.message || e).slice(0, 300) });
      log(`  supervisor ${lane} FAILED: ${String(e?.message || e).slice(0, 120)}`);
    }
  }
  return null;
}

// ---------------------------------------------------------------- diff geometry
function rightLines(patch: string): Set<number> {
  const s = new Set<number>(); let n = 0;
  for (const l of (patch || "").split("\n")) {
    const h = l.match(/^@@ -\d+(?:,\d+)? \+(\d+)/); if (h) { n = +h[1]; continue; }
    if (l.startsWith("-")) continue;
    if (l.startsWith("+") || l.startsWith(" ")) { s.add(n); n++; }
  }
  return s;
}

// ---------------------------------------------------------------- ledger
function ledger(): any[] { return existsSync(LEDGER) ? parseJsonl(readFileSync(LEDGER, "utf8")) : []; }
// GitHub list endpoints page at 100; follow pages so >100 files/reviews are not silently dropped
async function ghAll(path: string, max = 30): Promise<any[]> {
  const sep = path.includes("?") ? "&" : "?";
  return collectPages((page) => ghJson(`${path}${sep}per_page=100&page=${page}`), max);
}

// ---------------------------------------------------------------- review one PR
async function reviewPr(repo: string, num: number) {
  const dry = flag("dry-run"), force = flag("force");
  const failLanes = new Set(opt("fail-lane").split(",").filter(Boolean));
  const tokenName = await useTokenFor(repo);
  const pr = await ghJson(`/repos/${repo}/pulls/${num}`);
  const sha = pr.head.sha;
  log(`review ${repo}#${num} @${sha.slice(0, 7)} "${pr.title}" (token ${tokenName})`);
  if (pr.state !== "open" || pr.merged) return log(`  skip: PR is ${pr.state}`), "skip";
  if (pr.draft) return log("  skip: draft"), "skip";
  if (pr.user.login === REVIEWER) return log("  skip: authored by the reviewer"), "skip";
  if (!force && !dry) {
    if (ledger().some((e) => e.repo === repo && e.pr === num && e.sha === sha && e.posted)) return log("  skip: already reviewed this SHA (ledger)"), "skip";
    const existing = await ghAll(`/repos/${repo}/pulls/${num}/reviews`);
    if (existing.some((r: any) => r.user?.login === REVIEWER && r.commit_id === sha)) return log("  skip: aiwithdav3 already reviewed this SHA"), "skip";
  }

  const files = await ghAll(`/repos/${repo}/pulls/${num}/files`);
  const diffFull = await (await gh(`/repos/${repo}/pulls/${num}`, { accept: "application/vnd.github.v3.diff" })).text();
  const truncated = diffFull.length > 60_000;
  const diff = truncated ? diffFull.slice(0, 60_000) : diffFull;
  const ck = currentChecklist();
  const { system, user } = buildPrompt(ck, pr, diff, truncated);
  const attempts: any[] = [];
  const primary = await reviewWithFallback(system, user, failLanes, attempts);
  let rec_consensus: any = null;
  const rec: any = { repo, pr: num, sha, title: pr.title, checklist_version: ck.version, started: new Date().toISOString(), attempts, posted: false };
  const out = join(ROOT, `${repo.replace("/", "__")}-${num}-${sha.slice(0, 7)}-${stamp()}.json`);
  if (!primary) { rec.outcome = "no-verdict"; writeFileSync(out, JSON.stringify(rec, null, 1)); withLock(LEDGER + ".lock", () => appendFileSync(LEDGER, JSON.stringify(rec) + "\n")); log("  every lane failed: nothing posted"); return "fail"; }

  // keep confident findings with a valid inline anchor; the rest go into the body
  const valid = new Map<string, Set<number>>(files.map((f: any) => [f.filename, rightLines(f.patch)]));
  const res = primary.result;
  // self-consistency (awesome-rsi: Self-Consistency / multiagent debate): a second, independent lane drafts too;
  // only findings both raise survive. If no second lane answers, the supervisor below is the only filter.
  // Up to three vendors draft (primary + 2 more, each on a lane not yet used); a finding survives when >= 2 raise it.
  if (!flag("no-consensus") && res.findings.length) {
    const drafts = [{ lane: primary.lane as string, model: primary.model, findings: res.findings, verdict: res.verdict }];
    const used = new Set<string>([...failLanes, primary.lane]);
    for (let i = 0; i < +opt("consensus-lanes", "2"); i++) {
      const d = await reviewWithFallback(system, user, used, attempts); if (!d) break;
      used.add(d.lane); drafts.push({ lane: d.lane, model: d.model, findings: d.result.findings, verdict: d.result.verdict });
    }
    if (drafts.length >= 2) { const before = res.findings.length;
      res.findings = consensusFindings(drafts, 2);
      rec_consensus = { drafts: drafts.map(({ lane, model, verdict, findings }) => ({ lane, model, verdict, n: findings.length })), kept: res.findings.length, of: before };
      log(`  consensus over ${drafts.map((d) => d.lane).join("+")}: kept ${res.findings.length}/${before} primary findings`); }
  }
  res.findings = res.findings.filter((f: any) => (Number(f.confidence) || 0) >= 80 && f.body);
  const sup = await supervise(primary.lane as Lane, primary.model, res, diff, failLanes, attempts);
  let verdict = res.verdict as string;
  if (sup) { const drop = new Set((sup.drop || []).map(Number)); res.findings = res.findings.filter((_: any, i: number) => !drop.has(i)); }
  // no supervisor = no binding verdict: only COMMENT goes out unchecked
  if (!sup && verdict !== "COMMENT") { log(`  no supervisor reachable: ${verdict} downgraded to COMMENT`); verdict = "COMMENT"; }
  if (verdict === "APPROVE" && (!sup || !sup.agree || sup.verdict !== "APPROVE")) verdict = "COMMENT";
  if (verdict === "REQUEST_CHANGES" && !res.findings.some((f: any) => f.severity === "P1")) verdict = "COMMENT";
  if (verdict === "REQUEST_CHANGES" && sup && !sup.agree && sup.verdict !== "REQUEST_CHANGES") verdict = "COMMENT";

  const inline: any[] = [], loose: any[] = [];
  for (const f of res.findings) (valid.get(f.path)?.has(Number(f.line)) ? inline : loose).push(f);
  const lanesUsed = `${primary.lane} (${primary.model})` + (sup ? `; supervisor ${sup.lane} (${sup.model}) ${sup.agree ? "agreed" : "disagreed"}` : "; no supervisor reachable");
  const body = [`**aiwithdav3 review — ${verdict.replace("_", " ")}** · ${res.door || "?"} door · checklist v${ck.version}`, "", res.summary,
    ...(loose.length ? ["", "Findings without a diff anchor:", ...loose.map((f: any) => `- **${f.severity}** \`${f.path}:${f.line}\` [${f.checklist}] ${f.body}`)] : []),
    ...(truncated ? ["", "_Diff was over 60k chars; coverage was limited._"] : []),
    "", `<sub>Lanes: ${lanesUsed}. Automated review; it never merges.</sub>`].join("\n");
  const comments = inline.map((f: any) => ({ path: f.path, line: Number(f.line), side: "RIGHT", body: `**${f.severity}** [${f.checklist}] ${f.body}` }));
  Object.assign(rec, { lane: primary.lane, model: primary.model, consensus: rec_consensus, supervisor: sup, verdict, model_verdict: res.verdict, summary: res.summary,
    findings: res.findings.map((f: any) => ({ ...f, inline: inline.includes(f) })) });

  // head SHA guard right before the write
  const now = await ghJson(`/repos/${repo}/pulls/${num}`);
  if (now.head.sha !== sha || now.state !== "open") { rec.outcome = "head-moved"; log(`  head moved to ${now.head.sha.slice(0, 7)}: not posting`); }
  else if (dry) { rec.outcome = "dry-run"; log(`  dry run: would post ${verdict} with ${comments.length} inline`); }
  else {
    const r = await gh(`/repos/${repo}/pulls/${num}/reviews`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ commit_id: sha, event: verdict, body, comments }) });
    const j: any = await r.json().catch(() => ({}));
    if (!r.ok && comments.length) { // a bad anchor rejects the whole review; retry body-only rather than lose it
      log(`  post with inline failed (${r.status}); retrying body-only`);
      const extra = comments.map((c) => `- \`${c.path}:${c.line}\` ${c.body}`).join("\n");
      const r2 = await gh(`/repos/${repo}/pulls/${num}/reviews`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commit_id: sha, event: verdict, body: body + "\n\n" + extra }) });
      Object.assign(j, await r2.json().catch(() => ({}))); rec.posted = r2.ok; rec.inline_fallback = true; rec.retry_status = r2.status;
      log(`  body-only retry -> ${r2.status}`);
    } else rec.posted = r.ok;
    rec.review_id = j.id; rec.review_url = j.html_url; rec.outcome = rec.posted ? "posted" : `post-failed ${rec.retry_status ?? r.status}${JSON.stringify(j).slice(0, 200)}`;
    log(`  ${rec.outcome} ${verdict} (${comments.length} inline) ${j.html_url || ""}`);
  }
  rec.finished = new Date().toISOString();
  writeFileSync(out, JSON.stringify(rec, null, 1)); withLock(LEDGER + ".lock", () => appendFileSync(LEDGER, JSON.stringify(rec) + "\n"));
  log(`  log ${out}`);
  return rec.outcome;
}

// ---------------------------------------------------------------- RSI: score findings, evolve checklist
async function score() {
  const entries = ledger().filter((e) => e.posted && e.findings?.length && !e.scored);
  const scored: any[] = [];
  for (const e of entries) {
    if (!(await useTokenFor(e.repo).catch(() => null))) continue;
    const pr = await ghJson(`/repos/${e.repo}/pulls/${e.pr}`).catch(() => null); if (!pr) continue;
    if (pr.head.sha === e.sha && pr.state === "open") continue; // nothing to judge yet
    const cmp = await ghJson(`/repos/${e.repo}/compare/${e.sha}...${pr.head.sha}`).catch(() => null);
    scored.push(...judgeFindings(e.findings, cmp?.files || [], { repo: e.repo, pr: e.pr }));
    e.scored = new Date().toISOString();
  }
  if (!scored.length) return log("score: no newly judgeable findings");
  // rewrite ledger with scored flags
  const key = (x: any) => `${x.repo}#${x.pr}@${x.sha}@${x.started}`;
  const done = new Map(entries.filter((x) => x.scored).map((x) => [key(x), x.scored]));
  withLock(LEDGER + ".lock", () => { // re-read under the lock so concurrent appends survive; write atomically
    const cur = ledger(), tmp = LEDGER + ".tmp";
    writeFileSync(tmp, cur.map((x) => JSON.stringify(done.has(key(x)) ? { ...x, scored: done.get(key(x)) } : x)).join("\n") + "\n");
    renameSync(tmp, LEDGER);
  });
  appendFileSync(join(ROOT, "scores.jsonl"), scored.map((s) => JSON.stringify({ at: new Date().toISOString(), ...s })).join("\n") + "\n");
  // evolve (rsi.ts): train/holdout split, bounded + seed-anchored steps, holdout gate, curated lessons, archive restart
  const hist = parseJsonl(readFileSync(join(ROOT, "scores.jsonl"), "utf8"));
  const archive = readdirSync(CHECKDIR).filter((f) => /^v\d+\.json$/.test(f)).map((f) => JSON.parse(readFileSync(join(CHECKDIR, f), "utf8")));
  const streakFile = join(CHECKDIR, "rejected_streak");
  const streak = existsSync(streakFile) ? +readFileSync(streakFile, "utf8") || 0 : 0;
  const ck = archive.length ? pickParent(archive, streak) : currentChecklist();
  const { next, adopt, gate } = evolve(ck, hist);
  next.version = Math.max(ck.version, ...archive.map((a: any) => a.version)) + 1; next.created = new Date().toISOString();
  const dismissed = scored.filter((s) => !s.held).slice(0, 3).map((s) => `Dismissed in ${s.repo}#${s.pr} [${s.checklist}]: ${String(s.body).slice(0, 140)}`);
  next.lessons = curateLessons(ck.lessons || [], dismissed);
  if (!adopt) {
    writeFileSync(streakFile, String(streak + 1));
    appendFileSync(join(ROOT, "scores.jsonl"), JSON.stringify({ at: new Date().toISOString(), gate: "rejected", version: next.version, parent: ck.version, ...gate }) + "\n");
    return log(`score: v${next.version} REJECTED by holdout gate (${gate.before} -> ${gate.after} on ${gate.holdout}); keeping v${ck.version}`);
  }
  writeFileSync(streakFile, "0");
  writeFileSync(join(CHECKDIR, `v${next.version}.json`), JSON.stringify(next, null, 1));
  log(`score: ${scored.length} findings judged (${scored.filter((s) => s.held).length} held) -> checklist v${next.version}`);
}

// ---------------------------------------------------------------- poll (the hook)
async function poll() {
  const owner = opt("owner", "Who-Visions"), hours = +opt("since-hours", "72"), max = +opt("max", "5");
  const since = Date.now() - hours * 3600_000;
  const byName = new Map<string, any>();
  for (const t of TOKENS) {
    TOKEN = t.value;
    for (let page = 1; page < 10; page++) {
      const r = await ghJson(`/user/repos?per_page=100&page=${page}&affiliation=owner,collaborator,organization_member&sort=pushed`).catch(() => []);
      for (const x of r) if (!byName.has(x.full_name)) byName.set(x.full_name, x);
      if (r.length < 100) break;
    }
  }
  let repos = [...byName.values()];
  repos = repos.filter((r) => r.owner.login === owner && !r.archived && Date.parse(r.pushed_at) >= since);
  const seen = seenKeys(ledger());
  const queue: [string, number][] = [];
  for (const r of repos) {
    await useTokenFor(r.full_name).catch(() => null);
    const prs = await ghJson(`/repos/${r.full_name}/pulls?state=open&per_page=50&sort=updated&direction=desc`).catch(() => []);
    for (const p of prs) if (!p.draft && p.user.login !== REVIEWER && Date.parse(p.updated_at) >= since && !seen.has(`${r.full_name}#${p.number}@${p.head.sha}`))
      queue.push([r.full_name, p.number]);
  }
  log(`poll: ${repos.length} active ${owner} repos, ${queue.length} PR heads to review (cap ${max})`);
  for (const [repo, n] of queue.slice(0, max)) { try { await reviewPr(repo, n); } catch (e: any) { log(`  ${repo}#${n} error: ${e.message}`); } }
  await score().catch((e) => log(`score error: ${e.message}`));
}

// ---------------------------------------------------------------- main
const lock = join(ROOT, "poll.lock");
try {
  const cmd = args[0];
  // `rsi status|rollback <v>` are local-only (no GitHub token needed); `rsi evolve` = score.
  if (cmd === "rsi" && args[1] !== "evolve") {
    const archive = readdirSync(CHECKDIR).filter((f) => /^v\d+\.json$/.test(f)).map((f) => JSON.parse(readFileSync(join(CHECKDIR, f), "utf8")));
    const sf = join(CHECKDIR, "rejected_streak");
    if (args[1] === "rollback") {
      const next = rollbackTo(archive, +args[2]);
      writeFileSync(join(CHECKDIR, `v${next.version}.json`), JSON.stringify(next, null, 1)); writeFileSync(sf, "0");
      log(`rsi: rolled back to v${args[2]} as v${next.version}`);
      console.log(JSON.stringify({ rolled_back_to: +args[2], active: next.version }));
    } else {
      const scores = existsSync(join(ROOT, "scores.jsonl")) ? parseJsonl(readFileSync(join(ROOT, "scores.jsonl"), "utf8")) : [];
      console.log(JSON.stringify(rsiStatus(archive, existsSync(sf) ? +readFileSync(sf, "utf8") || 0 : 0, scores), null, 1));
    }
    process.exit(0);
  }
  const who = await auth();
  if (cmd === "rsi") await score(); else
  if (cmd === "whoami") console.log(`${who.login}: ${who.tokens.join("; ")}`);
  else if (cmd === "review") { const r = await reviewPr(args[1], +args[2]); process.exitCode = r === "posted" || r === "skip" || r === "dry-run" ? 0 : 1; }
  else if (cmd === "score") await score();
  else if (cmd === "poll") {
    if (existsSync(lock) && Date.now() - Bun.file(lock).lastModified < 3600_000) { log("poll: another run holds the lock"); process.exit(0); }
    writeFileSync(lock, String(process.pid));
    try { await poll(); } finally { try { (await import("node:fs")).unlinkSync(lock); } catch {} }
  } else { console.log(readFileSync(import.meta.path, "utf8").split("*/")[0]); process.exitCode = 2; }
} catch (e: any) { log(`fatal: ${e.message}`); process.exitCode = 3; }
