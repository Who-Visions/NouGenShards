#!/usr/bin/env bun
// aiwithdav3 failsafe reviewer (phoebus). Fails closed: any error, timeout, unparsable answer,
// gate failure, head change or missing quorum means NO approval.
//
//   bun aiwithdav3_review.ts <owner/repo> <pr> [--dry-run]
//
// Pipeline (pattern: pre-review gate -> guidelines -> parallel specialists -> adversarial
// validation -> one batched review):
//   1. Pre-review gate: PR is open, not draft, not authored by aiwithdav3, head pinned.
//   2. Local gate (~/.nougen/bin/local_gate.sh) on a fresh checkout of that exact head.
//   3. Specialists in parallel, each a different lane: codex (bugs), agy (security + error
//      paths), NouGenOpen (guidelines + tests). Each must return strict JSON.
//   4. Supervisor: NouGenOpen re-checks every finding with confidence >= 80 against the diff
//      and rules each CONFIRMED or REJECTED. Only confirmed blocking findings block.
//   5. Approve as aiwithdav3 only if: gate PASS, quorum (>= 2 lanes answered), supervisor
//      READY, zero confirmed blockers, head unchanged. Otherwise one COMMENT review.
// Self-improvement: every run appends to ~/.nougen/state/review_rsi.jsonl (per-lane answered /
// agreed-with-supervisor / false positives). Lanes that failed or were overruled most in the
// last 20 runs are named in the next prompts, and a lane failing 5 runs in a row is benched.
// Token: Keymaker GITHUB_TOKEN_AIWITHDAV3_REVIEW (fallback GITHUB_TOKEN_AIWITHDAV3). Never printed.

import { $ } from "bun";
import { appendFileSync, existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { changedFiles, normalize, parseJson, playbookText, ungrounded, type Finding, type LaneOut, type Lesson } from "./aiwithdav3_review_lib.ts";

const HOME = process.env.HOME!;
const SHARDS = `${HOME}/The Observatory/NouGen/nougenshards`;
const OPEN = `${HOME}/The Observatory/NouGen/NouGenOpen`;
const PY = `${SHARDS}/.venv/bin/python`;
const RSI = `${HOME}/.nougen/state/review_rsi.jsonl`;
const PLAYBOOK = `${HOME}/.nougen/state/review_playbook.jsonl`;
const REVIEWER = "aiwithdav3";
const MIN_CONF = 80;
const QUORUM = 2;
const LANE_MS = 15 * 60_000;
process.env.PATH = `/usr/local/bin:${HOME}/.local/bin:${HOME}/.bun/bin:${process.env.PATH}`;

const [repo, prArg, ...flags] = process.argv.slice(2);
const DRY = flags.includes("--dry-run");
const pr = Number(prArg);
if (!repo || !/^[\w.-]+\/[\w.-]+$/.test(repo) || !Number.isInteger(pr)) {
  console.error("usage: aiwithdav3_review.ts <owner/repo> <pr> [--dry-run]"); process.exit(2);
}
const log = (m: string) => console.log(`[${repo}#${pr}] ${m}`);
const stop = (why: string): never => { log(`NO APPROVAL: ${why}`); process.exit(1); };


// ---------- helpers
async function secret(name: string): Promise<string> {
  const r = await $`${PY} -c ${"import sys;sys.path.insert(0,'src');from nougen_shards import keymaker as k;v=k.get_secret(sys.argv[1]);print(v or '')"} ${name}`
    .cwd(SHARDS).quiet().nothrow();
  return r.stdout.toString().trim();
}
function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return Promise.race([p, new Promise<T>((_, rej) => setTimeout(() => rej(new Error(`${label} timed out`)), ms))]);
}
function lessons(): { text: string; benched: Set<string> } {
  if (!existsSync(RSI)) return { text: "", benched: new Set() };
  const runs = readFileSync(RSI, "utf8").trim().split("\n").slice(-20).flatMap((l) => { try { return [JSON.parse(l)]; } catch { return []; } });
  const stat: Record<string, { n: number; fail: number; fp: number; streak: number }> = {};
  for (const r of runs) for (const [lane, s] of Object.entries<any>(r.lanes || {})) {
    const x = (stat[lane] ||= { n: 0, fail: 0, fp: 0, streak: 0 });
    x.n++; if (!s.ok) { x.fail++; x.streak++; } else x.streak = 0; x.fp += s.false_positives || 0;
  }
  const benched = new Set(Object.entries(stat).filter(([, s]) => s.streak >= 5).map(([l]) => l));
  const lines = Object.entries(stat).map(([l, s]) => `${l}: answered ${s.n - s.fail}/${s.n}, findings overruled ${s.fp}`);
  return { text: lines.length ? `Track record of the review lanes over the last ${runs.length} runs (be more precise than the lanes that were overruled):\n${lines.join("\n")}` : "", benched };
}

// ---------- 1. pre-review gate
const ghUser = Bun.spawnSync(["gh", "api", "user", "-q", ".login"]).stdout.toString().trim();
const pv = await $`gh pr view ${pr} -R ${repo} --json state,isDraft,author,headRefOid,headRefName,title,body,files`.quiet().nothrow();
if (pv.exitCode) stop("cannot read PR");
const P = JSON.parse(pv.stdout.toString());
if (P.state !== "OPEN") stop(`PR is ${P.state}`);
if (P.isDraft) stop("PR is a draft");
if ((P.author?.login || "").toLowerCase() === REVIEWER) stop("aiwithdav3 authored this PR; it cannot review itself");
const HEAD: string = P.headRefOid;
log(`head ${HEAD.slice(0, 9)} "${P.title}" (operator gh: ${ghUser || "?"})`);

let asReviewer: Record<string, string | undefined> = process.env;
if (!DRY) {
  const token = (await secret("GITHUB_TOKEN_AIWITHDAV3_REVIEW")) || (await secret("GITHUB_TOKEN_AIWITHDAV3"));
  if (!token) stop("no aiwithdav3 token in Keymaker");
  asReviewer = { ...process.env, GH_TOKEN: token };
  const who = await $`gh api user -q .login`.env(asReviewer).quiet().nothrow();
  if (who.stdout.toString().trim() !== REVIEWER) stop("Keymaker token does not authenticate as aiwithdav3");
  const canSee = await $`gh api repos/${repo} -q .full_name`.env(asReviewer).quiet().nothrow();
  if (canSee.exitCode) stop(`aiwithdav3 token cannot see ${repo} (add the repo to the token's access)`);
} else log("dry run: reviewer token checks skipped, nothing will be posted");

// ---------- 2. local gate on the exact head
const work = mkdtempSync(join(tmpdir(), "aiw-review-"));
const W = join(work, "tree");
try {
  if ((await $`gh repo clone ${repo} ${W} -- -q --filter=blob:none`.quiet().nothrow()).exitCode) stop("clone failed");
  await $`git -C ${W} fetch -q origin pull/${pr}/head`.quiet();
  await $`git -C ${W} checkout -q --detach ${HEAD}`.quiet();
  const name = repo.split("/")[1];
  for (const d of [`${HOME}/The Observatory/${name}`, `${HOME}/The Observatory/NouGen/${name}`])
    for (const x of [".venv", "node_modules"]) if (existsSync(`${d}/${x}`) && !existsSync(`${W}/${x}`)) await $`ln -s ${d}/${x} ${W}/${x}`.quiet().nothrow();
  const gate = await $`${HOME}/.nougen/bin/local_gate.sh ${W}`.quiet().nothrow();
  const gateLine = gate.stdout.toString().split("\n").filter((l) => l.startsWith("GATE ")).pop() || "GATE ?";
  log(gateLine);
  if (gate.exitCode !== 0 || gateLine.includes("GATE NONE")) stop(`local gate not green: ${gateLine}`);

  const diff = (await $`git -C ${W} diff --no-color ${"origin/" + (await $`gh pr view ${pr} -R ${repo} --json baseRefName -q .baseRefName`.text()).trim()}...HEAD`.quiet().nothrow()).stdout.toString();
  if (!diff.trim()) stop("empty diff");
  const DIFF = diff.length > 120_000 ? diff.slice(0, 120_000) + "\n[diff truncated]" : diff;
  const guides = ["CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md"].flatMap((f) => existsSync(`${W}/${f}`) ? [`--- ${f}\n${readFileSync(`${W}/${f}`, "utf8").slice(0, 6000)}`] : []).join("\n");
  const { text: track0, benched } = lessons();
  const book: Lesson[] = existsSync(PLAYBOOK) ? readFileSync(PLAYBOOK, "utf8").trim().split("\n").flatMap((l) => { try { return [JSON.parse(l)]; } catch { return []; } }) : [];
  const track = [track0, playbookText(book)].filter(Boolean).join("\n\n");

  const schema = `Answer with ONLY this JSON, nothing after it:
{"verdict":"READY"|"CHANGES","findings":[{"file":"path","line":123,"severity":"blocking"|"minor","confidence":0-100,"claim":"one sentence: concrete input -> wrong result"}]}
Rules: a finding is blocking only if it is a real defect a test or user would hit. No style nits as blocking. Confidence below ${MIN_CONF} is ignored. At most 8 findings, most serious first; one sentence each. READY means no blocking finding.`;
  const brief = (focus: string) => `You are reviewing ${repo} PR #${pr} at ${HEAD} ("${P.title}"). The local gate already passed (${gateLine}).
Your focus: ${focus}
PR description:\n${(P.body || "").slice(0, 3000)}
Project guidelines:\n${guides || "(none)"}
${track}
Diff:\n${DIFF}\n\n${schema}`;

  const openAsk = async (prompt: string, extra: string[] = []) =>
    (await $`${PY} -m nougen_open.cli ask ${extra} ${prompt}`.cwd(OPEN).env({ ...process.env, PYTHONPATH: `src:${SHARDS}/src` }).quiet()).stdout.toString();

  // ---------- 3. specialists in parallel
  const lanes: Record<string, () => Promise<string>> = {
    codex: async () => (await $`codex exec --skip-git-repo-check -C ${W} ${brief("correctness bugs: logic errors, off-by-one, wrong conditions, broken contracts, missing cases.")}`.quiet()).stdout.toString(),
    agy: async () => (await $`agy --dangerously-skip-permissions --print-timeout 900s -p ${brief("security and error handling: injection, auth, secrets, unsafe input, swallowed errors, resource leaks, failure paths.")}`.cwd(W).quiet()).stdout.toString(),
    nougenopen: async () => openAsk(brief("tests and guidelines: is the change tested, do tests prove the claim, does it follow the project guidelines above.")),
    // A second, independent model family through NouGenOpen, so one exhausted lane (Codex hits
    // usage limits) does not cost the quorum.
    "nougenopen-nvidia": async () => openAsk(brief("correctness bugs: logic errors, off-by-one, wrong conditions, broken contracts, missing cases."), ["--provider", "nvidia"]),
  };
  const RAW = `${HOME}/.nougen/state/aiw_raw`; await $`mkdir -p ${RAW}`.quiet();
  const outs: LaneOut[] = await Promise.all(Object.entries(lanes).map(async ([lane, run]) => {
    if (benched.has(lane)) return { lane, ok: false, findings: [], err: "benched (5 failures in a row)" };
    let raw = "";
    try {
      raw = await withTimeout(run(), LANE_MS, lane);
      try { return normalize(lane, parseJson(raw)); }
      catch {
        // One repair pass: the same answer, reformatted into the schema by NouGenOpen. It may not
        // invent findings, only carry over what the lane said.
        const fixed = await withTimeout(openAsk(`Convert this code review into the JSON below. Keep its verdict and findings exactly; add nothing.\n\nREVIEW:\n${raw.slice(-12000)}\n\n${schema}`), 5 * 60_000, `${lane} repair`);
        return normalize(lane, parseJson(fixed));
      }
    } catch (e: any) {
      Bun.write(`${RAW}/${repo.replace("/", "_")}-${pr}-${lane}.txt`, raw || String(e?.stderr || e));
      return { lane, ok: false, findings: [], err: String(e?.message || e).slice(0, 200) };
    }
  }));
  for (const o of outs) log(`lane ${o.lane}: ${o.ok ? `${o.verdict}, ${o.findings.length} finding(s)` : `failed (${o.err})`}`);
  const answered = outs.filter((o) => o.ok);

  // ---------- 4. supervisor: adversarial validation by NouGenOpen
  // CRITIC-style grounding before any model judges a finding.
  const files = changedFiles(diff);
  const lineCount = (f: string) => { try { return readFileSync(join(W, f), "utf8").split("\n").length; } catch { return null; } };
  const strong = answered.flatMap((o) => o.findings).filter((f) => f.confidence >= MIN_CONF);
  const groundless = strong.flatMap((f) => { const why = ungrounded(f, files, lineCount); return why ? [{ f, why }] : []; });
  for (const g of groundless) log(`grounding rejected [${g.f.lane}] ${g.f.file}:${g.f.line ?? "?"}: ${g.why}`);
  const claims = strong.filter((f) => !groundless.some((g) => g.f === f));
  let sup: { verdict: "READY" | "CHANGES"; rulings: { i: number; ruling: "CONFIRMED" | "REJECTED"; why: string }[] } | null = null;
  // Nothing to validate: the supervisor is not asked, because a verdict with no finding behind
  // it is ungrounded (it flipped READY/CHANGES between identical runs).
  if (!claims.length) { sup = { verdict: "READY", rulings: [] }; log("supervisor: no findings at or above the bar, nothing to rule on"); }
  else try {
    const ask = `You supervise a PR review of ${repo} #${pr} at ${HEAD}. Lanes answered: ${answered.map((o) => `${o.lane}=${o.verdict}`).join(", ") || "none"}.
Adversarially check each claimed finding against the diff. CONFIRMED only if the diff really shows the defect; otherwise REJECTED.
Findings:\n${claims.map((f, i) => `${i}. [${f.lane}] ${f.file}:${f.line ?? "?"} (${f.severity}, ${f.confidence}) ${f.claim}`).join("\n") || "(none)"}
Diff:\n${DIFF}
Answer with ONLY: {"verdict":"READY"|"CHANGES","rulings":[{"i":0,"ruling":"CONFIRMED"|"REJECTED","why":"short"}]}
verdict is CHANGES if any CONFIRMED finding is blocking.`;
    const raw = (await withTimeout($`${PY} -m nougen_open.cli ask ${ask}`.cwd(OPEN).env({ ...process.env, PYTHONPATH: `src:${SHARDS}/src` }).quiet().then((r) => r.stdout.toString()), LANE_MS, "supervisor"));
    const o = parseJson(raw);
    if (o.verdict !== "READY" && o.verdict !== "CHANGES") throw new Error("bad supervisor verdict");
    sup = { verdict: o.verdict, rulings: Array.isArray(o.rulings) ? o.rulings : [] };
  } catch (e: any) { log(`supervisor failed: ${e?.message || e}`); }

  const confirmed = claims.filter((_, i) => sup?.rulings.find((r) => r.i === i)?.ruling === "CONFIRMED");
  const blockers = confirmed.filter((f) => f.severity === "blocking");
  // Every claim the supervisor did not rule on counts as unresolved, so silence never approves.
  const unruled = claims.filter((_, i) => !sup?.rulings.some((r) => r.i === i));

  // ---------- record for self-improvement
  const laneStats: Record<string, any> = {};
  for (const o of outs) {
    const mine = claims.map((f, i) => ({ f, i })).filter(({ f }) => f.lane === o.lane);
    laneStats[o.lane] = { ok: o.ok, verdict: o.verdict ?? null, err: o.err ?? null,
      false_positives: mine.filter(({ i }) => sup?.rulings.find((r) => r.i === i)?.ruling === "REJECTED").length + groundless.filter((g) => g.f.lane === o.lane).length };
  }

  // ---------- 5. decide (fail closed)
  const reasons: string[] = [];
  if (answered.length < QUORUM) reasons.push(`only ${answered.length} lane(s) answered (need ${QUORUM})`);
  // The decision comes from the per-finding rulings, never from a bare verdict word.
  if (!sup) reasons.push("supervisor gave no usable ruling");
  else if (sup.verdict !== "READY" && !blockers.length) log("supervisor said CHANGES without confirming a blocking finding; ignored as ungrounded");
  else if (sup.verdict === "READY" && blockers.length) log("supervisor said READY but confirmed a blocking finding; the finding wins");
  if (blockers.length) reasons.push(`${blockers.length} confirmed blocking finding(s)`);
  if (unruled.length) reasons.push(`${unruled.length} finding(s) the supervisor did not rule on`);
  const nowHead = (await $`gh pr view ${pr} -R ${repo} --json headRefOid -q .headRefOid`.text()).trim();
  if (nowHead !== HEAD) reasons.push(`head moved to ${nowHead.slice(0, 9)} during review`);
  const approve = reasons.length === 0;

  // Distil rejected findings into playbook lessons for the next reviews.
  const lessonsNow: Lesson[] = [
    ...groundless.map((g) => ({ at: new Date().toISOString(), repo, lesson: `${g.f.lane} claimed "${g.f.claim.slice(0, 140)}" but ${g.why}` })),
    ...claims.flatMap((f, i) => { const r = sup?.rulings.find((x) => x.i === i); return r?.ruling === "REJECTED" ? [{ at: new Date().toISOString(), repo, lesson: `Wrong: "${f.claim.slice(0, 140)}" (${r.why.slice(0, 120)})` }] : []; }),
  ];
  for (const l of lessonsNow) appendFileSync(PLAYBOOK, JSON.stringify(l) + "\n");
  appendFileSync(RSI, JSON.stringify({ at: new Date().toISOString(), repo, pr, head: HEAD, gate: gateLine, approve, reasons, lanes: laneStats,
    supervisor: sup?.verdict ?? null, confirmed: confirmed.length, rejected: claims.length - confirmed.length - unruled.length }) + "\n");

  const fmt = (f: Finding) => `- \`${f.file}${f.line ? `:${f.line}` : ""}\` (${f.severity}, ${f.lane}) ${f.claim}`;
  const body = [`aiwithdav3 failsafe review (phoebus, headless) at \`${HEAD.slice(0, 9)}\`: ${approve ? "READY TO MERGE" : "CHANGES NEEDED"}`, "",
    `Local gate: ${gateLine}`,
    `Lanes: ${outs.map((o) => `${o.lane} ${o.ok ? o.verdict : "no answer"}`).join(", ")}. Supervisor (NouGenOpen): ${sup?.verdict ?? "no ruling"}.`,
    ...(confirmed.length ? ["", "Confirmed findings:", ...confirmed.map(fmt)] : []),
    ...(reasons.length ? ["", "Not approved because:", ...reasons.map((r) => `- ${r}`)] : [])].join("\n");

  if (DRY) { log(`dry run, would ${approve ? "APPROVE" : "COMMENT"}:\n${body}`); process.exit(approve ? 0 : 1); }
  const r = await $`gh pr review ${pr} -R ${repo} ${approve ? "--approve" : "--comment"} -b ${body}`.env(asReviewer).quiet().nothrow();
  if (r.exitCode) stop(`posting the review failed: ${r.stderr.toString().slice(0, 200)}`);
  log(approve ? "APPROVED as aiwithdav3" : `commented CHANGES NEEDED (${reasons.join("; ")})`);
  process.exit(approve ? 0 : 1);
} finally {
  rmSync(work, { recursive: true, force: true });
}
