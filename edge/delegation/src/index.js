// nougen-delegation: durable claim/lease/fencing board for NouGenMsg work.
// One Durable Object (SQLite) is the single writer, so take/heartbeat/commit are
// atomic without locks. Behaviour mirrors src/nougen_shards/claim_lifecycle.py.
import { DurableObject } from "cloudflare:workers";
import { ClaimLifecycle, LifecycleError, badRequest, DEFAULT_LEASE_SECONDS } from "./lifecycle.js";

const DEFAULT_SWEEP_SECONDS = 60;
const MAX_BODY_BYTES = 64 * 1024;
const MAX_JSON_BYTES = 16 * 1024;
const ID_PATTERN = /^[A-Za-z0-9_.:@/+-]{1,200}$/;

const STATUS = { FENCING: 409, INVALID_STATE: 409, NOT_FOUND: 404, AUTHORITY: 403, BAD_REQUEST: 400 };

function str(args, key, max = 200) {
  const v = args[key];
  if (typeof v !== "string" || !v.trim() || v.length > max) throw badRequest(`${key} must be a non-empty string up to ${max} chars`);
  return v;
}
function msgId(args) {
  const v = str(args, "msg_id");
  if (!ID_PATTERN.test(v)) throw badRequest("msg_id has characters outside A-Za-z0-9_.:@/+-");
  return v;
}
function int(args, key) {
  if (!Number.isInteger(args[key])) throw badRequest(`${key} must be an integer`);
  return args[key];
}
function lease(args) {
  if (args.lease_seconds === undefined) return DEFAULT_LEASE_SECONDS;
  const n = args.lease_seconds;
  if (typeof n !== "number" || !Number.isFinite(n) || n < 1 || n > 86_400) throw badRequest("lease_seconds must be 1..86400");
  return n;
}
function obj(args, key) {
  const v = args[key];
  if (v === null || typeof v !== "object" || Array.isArray(v)) throw badRequest(`${key} must be a JSON object`);
  if (JSON.stringify(v).length > MAX_JSON_BYTES) throw badRequest(`${key} is larger than ${MAX_JSON_BYTES} bytes`);
  return v;
}
function optStr(args, key, fallback = "") {
  const v = args[key];
  return typeof v === "string" ? v.slice(0, 2000) : fallback;
}

// op name -> handler(life, args). Whitelisted; nothing else is callable.
const OPS = {
  register: (l, a) => l.registerReceived(msgId(a), optStr(a, "lane", "unknown")),
  take: (l, a) => l.takeMsg(msgId(a), str(a, "lane", 100), lease(a), optStr(a, "semantic_version", "v1")),
  heartbeat: (l, a) => ({ renewed: l.heartbeat(msgId(a), int(a, "epoch"), optStr(a, "state", "WORKING"), lease(a)) }),
  checkpoint: (l, a) => l.checkpoint(msgId(a), int(a, "epoch"), obj(a, "evidence"), lease(a)),
  verify: (l, a) => l.verifyStep(msgId(a), int(a, "epoch"), obj(a, "evidence")),
  commit: (l, a) => l.commitStep(msgId(a), int(a, "epoch"), str(a, "idempotency_key")),
  complete: (l, a) => l.complete(msgId(a), int(a, "epoch"), obj(a, "proof")),
  fail: (l, a) => l.fail(msgId(a), int(a, "epoch"), optStr(a, "reason")),
  interrupt: (l, a) => l.interrupt(msgId(a), int(a, "epoch"), optStr(a, "state"), optStr(a, "reason")),
  requeue: (l, a) => l.requeue(msgId(a), optStr(a, "reason")),
  cancel: (l, a) => l.cancel(msgId(a), optStr(a, "reason")),
  claim: (l, a) => l.getClaim(msgId(a)),
  open: (l, a) => l.listOpen(Number.isInteger(a.limit) ? a.limit : 200),
  stalled: (l, a) => l.detectStalled(typeof a.no_progress_seconds === "number" ? a.no_progress_seconds : 900),
  sweep: (l, a) => l.detectAndReclaimStale(typeof a.grace_seconds === "number" ? a.grace_seconds : 0),
};

export class DelegationBoard extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.sweepMs = (Number(env.SWEEP_SECONDS) > 0 ? Number(env.SWEEP_SECONDS) : DEFAULT_SWEEP_SECONDS) * 1000;
    const allowed = (env.ALLOWED_LANES || "").split(",").map((s) => s.trim()).filter(Boolean);
    this.life = new ClaimLifecycle({
      sql: (q, ...p) => this.ctx.storage.sql.exec(q, ...p).toArray(),
      tx: (fn) => this.ctx.storage.transactionSync(fn),
      // Authority is re-checked at commit and complete, not only when work was claimed.
      authorityCheck: (snap) => (allowed.length && !allowed.includes(snap.agent_lane)
        ? [false, `lane ${snap.agent_lane} is not in ALLOWED_LANES`] : [true, ""]),
    });
    ctx.blockConcurrencyWhile(async () => this.life.init());
  }

  // RPC. Lifecycle refusals come back as data so the caller never depends on
  // custom Error classes surviving the RPC boundary.
  async invoke(op, args) {
    const handler = Object.hasOwn(OPS, op) ? OPS[op] : null;
    if (!handler) return { ok: false, error: { code: "BAD_REQUEST", message: `unknown op ${op}` } };
    try {
      const result = handler(this.life, args && typeof args === "object" ? args : {});
      await this.#armSweep();
      return { ok: true, result };
    } catch (err) {
      if (err instanceof LifecycleError) return { ok: false, error: { code: err.code, message: err.message } };
      throw err;
    }
  }

  async #armSweep() {
    if (this.life.hasLive() && (await this.ctx.storage.getAlarm()) === null) {
      await this.ctx.storage.setAlarm(Date.now() + this.sweepMs);
    }
  }

  // Watchdog: an expired lease returns the task to SUBMITTED so another lane can take it.
  async alarm() {
    this.life.detectAndReclaimStale();
    await this.#armSweep();
  }
}

async function sameSecret(given, expected) {
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(given)),
    crypto.subtle.digest("SHA-256", enc.encode(expected)),
  ]);
  return crypto.subtle.timingSafeEqual(a, b);
}

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return json({ ok: true, service: "nougen-delegation" });

    // Fail closed: with no token configured nothing is served.
    if (!env.DELEGATION_TOKEN) return json({ ok: false, error: { code: "UNCONFIGURED", message: "DELEGATION_TOKEN is not set" } }, 503);
    const bearer = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    if (!bearer || !(await sameSecret(bearer, env.DELEGATION_TOKEN))) {
      return json({ ok: false, error: { code: "UNAUTHORIZED", message: "bad or missing bearer token" } }, 401);
    }

    const match = url.pathname.match(/^\/v1\/([a-z]+)$/);
    if (!match) return json({ ok: false, error: { code: "NOT_FOUND", message: "no such route" } }, 404);
    const op = match[1];
    if (!Object.hasOwn(OPS, op)) return json({ ok: false, error: { code: "NOT_FOUND", message: "no such route" } }, 404);
    const readOnly = op === "claim" || op === "open" || op === "stalled";
    if (request.method !== (readOnly ? "GET" : "POST")) {
      return json({ ok: false, error: { code: "BAD_REQUEST", message: `use ${readOnly ? "GET" : "POST"}` } }, 405);
    }

    let args = Object.fromEntries(url.searchParams);
    if (!readOnly) {
      const text = await request.text();
      if (text.length > MAX_BODY_BYTES) return json({ ok: false, error: { code: "BAD_REQUEST", message: "body too large" } }, 413);
      try { args = text ? JSON.parse(text) : {}; } catch { return json({ ok: false, error: { code: "BAD_REQUEST", message: "body is not JSON" } }, 400); }
    } else {
      for (const k of ["limit", "no_progress_seconds"]) if (args[k] !== undefined) args[k] = Number(args[k]);
    }

    const board = env.BOARD.getByName(env.BOARD_NAME || "main");
    const out = await board.invoke(op, args);
    return out.ok ? json(out) : json(out, STATUS[out.error.code] ?? 500);
  },
};
