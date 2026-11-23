// NouGen msgs: native Cloudflare front for the NouGenMsg host.
//
// Sits on a ROUTE in front of the existing origin (a tunnel to a home node). The
// origin stays the fallback: anything this Worker does not handle natively, or
// cannot handle because a binding failed, is passed through unchanged.
//
//   POST /msg                       native accept: lane mailbox (Durable Object,
//                                   ordered seq) + Queue fan-out to the origin
//   GET  /mailbox/<lane>?after=N    read a lane's mailbox in order
//   POST /mailbox/<lane>/ack        {"upto": N} marks entries up to N acked
//   *                               pass-through to the origin
//
// Native auth: Authorization: Bearer <token> whose sha256 hex is listed in the
// secret MSGS_NATIVE_TOKEN_SHA256 (comma separated). Tokens are never stored.
// Lane names come from the request, never from this file.

const ENC = new TextEncoder();
export const VIA = "msgs-worker";
const LANE_RE = /^@?[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/;

const num = (v, d) => { const n = Number(v); return Number.isFinite(n) && n > 0 ? n : d; };
export const limits = (env = {}) => ({
  maxBody: num(env.MSGS_MAX_BODY_BYTES, 256 * 1024),
  pageSize: num(env.MSGS_PAGE_SIZE, 100),
  originTimeoutMs: num(env.MSGS_ORIGIN_TIMEOUT_MS, 15000),
  retryBaseS: num(env.MSGS_RETRY_BASE_S, 5),
});

export async function sha256Hex(s) {
  const d = await crypto.subtle.digest("SHA-256", ENC.encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

export async function nativeAuthorized(env, req) {
  const list = String(env.MSGS_NATIVE_TOKEN_SHA256 || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  if (!list.length) return false;
  const m = /^Bearer\s+(.+)$/i.exec(req.headers.get("authorization") || "");
  if (!m) return false;
  const h = await sha256Hex(m[1].trim());
  return list.some((x) => timingSafeEqual(x, h));
}

export const laneKey = (target) => {
  const t = String(target || "@all").trim();
  return LANE_RE.test(t) ? t.replace(/^@/, "").toLowerCase() : null;
};

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

export function originUrl(env, path) {
  const base = String(env.MSGS_ORIGIN_URL || "").trim().replace(/\/$/, "");
  return base ? base + path : null;
}

// Pass-through keeps today's tunnel path. On a route, fetch(request) goes to the
// origin behind the hostname; MSGS_ORIGIN_URL only matters for queue delivery.
async function passThrough(req, why) {
  console.log(JSON.stringify({ evt: "pass_through", why, path: new URL(req.url).pathname }));
  return fetch(req);
}

async function nativeMsg(req, env) {
  const { maxBody } = limits(env);
  const raw = await req.text();
  if (ENC.encode(raw).length > maxBody) return json({ error: "body too large", max: maxBody }, 413);
  let payload;
  try { payload = JSON.parse(raw); } catch { return json({ error: "body must be JSON" }, 400); }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return json({ error: "body must be an object" }, 400);
  const lane = laneKey(payload.target);
  if (!lane) return json({ error: "invalid target" }, 400);
  const box = env.MAILBOX.get(env.MAILBOX.idFromName(lane));
  const put = await box.fetch("https://mailbox/append", { method: "POST", body: JSON.stringify({ payload }) });
  if (!put.ok) throw new Error("mailbox append " + put.status);
  const { seq, at } = await put.json();
  await env.FANOUT.send({ lane, seq, payload });
  console.log(JSON.stringify({ evt: "native_accept", lane, seq }));
  return json({ delivered: false, status: "unverified", queued: true, lane, seq, at, via: VIA }, 202);
}

async function mailboxApi(req, env, lane, rest) {
  const box = env.MAILBOX.get(env.MAILBOX.idFromName(lane));
  const url = new URL(req.url);
  if (req.method === "GET" && rest === "") {
    const after = Number(url.searchParams.get("after") || 0) || 0;
    return box.fetch(`https://mailbox/list?after=${after}&limit=${limits(env).pageSize}`);
  }
  if (req.method === "POST" && rest === "/ack") return box.fetch("https://mailbox/ack", { method: "POST", body: await req.text() });
  return json({ error: "not found" }, 404);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    // Loop guard: our own queue deliveries must always reach the origin.
    if (req.headers.get("x-nougen-via") === VIA) return passThrough(req, "loop_guard");
    const mb = /^\/mailbox\/([^/]+)(\/ack)?$/.exec(url.pathname);
    const native = (req.method === "POST" && url.pathname === "/msg") || mb;
    if (!native) return passThrough(req, "not_native");
    if (!(await nativeAuthorized(env, req))) {
      return mb ? json({ error: "unauthorized" }, 401) : passThrough(req, "not_native_auth");
    }
    try {
      if (mb) {
        const lane = laneKey(decodeURIComponent(mb[1]));
        if (!lane) return json({ error: "invalid lane" }, 400);
        return await mailboxApi(req, env, lane, mb[2] || "");
      }
      return await nativeMsg(req.clone(), env);
    } catch (err) {
      console.error(JSON.stringify({ evt: "native_error", err: String(err && err.message || err) }));
      if (mb) return json({ error: "mailbox unavailable" }, 503);
      return passThrough(req, "native_error");
    }
  },

  // Queue consumer: the home node is the consumer of record. Deliver each message
  // to the origin; ack on 2xx, retry with backoff otherwise (DLQ after max_retries).
  async queue(batch, env) {
    const { originTimeoutMs, retryBaseS } = limits(env);
    const target = originUrl(env, "/msg");
    for (const m of batch.messages) {
      const { lane, seq, payload } = m.body || {};
      if (!target) { m.retry({ delaySeconds: retryBaseS }); continue; }
      let ok = false, status = 0;
      try {
        const headers = { "content-type": "application/json", "x-nougen-via": VIA };
        // The msgs origin (nougenmsg_node) authenticates on X-NGS-Token, not Authorization.
        if (env.MSGS_ORIGIN_TOKEN) headers["x-ngs-token"] = env.MSGS_ORIGIN_TOKEN;
        const res = await fetch(target, { method: "POST", headers, body: JSON.stringify(payload), signal: AbortSignal.timeout(originTimeoutMs) });
        status = res.status; ok = res.ok;
      } catch (err) { status = 0; }
      console.log(JSON.stringify({ evt: "origin_delivery", lane, seq, status, attempt: m.attempts }));
      if (ok) {
        try {
          const box = env.MAILBOX.get(env.MAILBOX.idFromName(lane));
          await box.fetch("https://mailbox/delivered", { method: "POST", body: JSON.stringify({ seq, status }) });
        } catch {}
        m.ack();
      } else {
        m.retry({ delaySeconds: Math.min(retryBaseS * 2 ** Math.max(0, (m.attempts || 1) - 1), 900) });
      }
    }
  },
};

// One Durable Object per lane: strict append order, read, ack, delivery marks.
export class LaneMailbox {
  constructor(state) {
    this.sql = state.storage.sql;
    this.sql.exec(
      "CREATE TABLE IF NOT EXISTS box (seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, acked INTEGER NOT NULL DEFAULT 0)"
    );
  }
  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/append") {
      const { payload } = await req.json();
      const at = new Date().toISOString();
      const row = this.sql.exec("INSERT INTO box (at, payload) VALUES (?, ?) RETURNING seq", at, JSON.stringify(payload)).one();
      return json({ seq: row.seq, at });
    }
    if (url.pathname === "/list") {
      const after = Number(url.searchParams.get("after") || 0) || 0;
      const lim = Math.min(Number(url.searchParams.get("limit") || 100) || 100, 1000);
      const rows = this.sql.exec("SELECT seq, at, payload, delivered, acked FROM box WHERE seq > ? ORDER BY seq LIMIT ?", after, lim).toArray();
      return json({ messages: rows.map((r) => ({ seq: r.seq, at: r.at, delivered: !!r.delivered, acked: !!r.acked, payload: JSON.parse(r.payload) })) });
    }
    if (url.pathname === "/ack") {
      const upto = Number((await req.json()).upto);
      if (!Number.isInteger(upto) || upto < 1) return json({ error: "upto must be a positive integer" }, 400);
      this.sql.exec("UPDATE box SET acked = 1 WHERE seq <= ?", upto);
      return json({ acked_upto: upto });
    }
    if (url.pathname === "/delivered") {
      const { seq } = await req.json();
      this.sql.exec("UPDATE box SET delivered = 1 WHERE seq = ?", Number(seq));
      return json({ ok: true });
    }
    return json({ error: "not found" }, 404);
  }
}
