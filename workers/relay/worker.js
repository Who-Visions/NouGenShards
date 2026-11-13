// NouGen Relay: a tunnel fallback for nodes whose network blocks cloudflared.
//
// The node dials OUT to wss://<relay host>/_relay/connect on port 443 (through an
// HTTP proxy if it has to) and keeps that one socket open. Public requests to
// <id>.<RELAY_HOST_SUFFIX> (or /n/<id>/... on the preview host) land here, go to the
// node's Durable Object, travel down the socket as a JSON frame, and the node's reply
// comes back the same way.
//
//   GET  /_relay/connect?id=<id>   WebSocket upgrade, Authorization: Bearer <node token>
//   GET  /_relay/status?id=<id>    {"live":bool,"transport":"relay","since":ms|null}
//   *    <id>.<suffix>/<path>       proxied to the node
//   *    /n/<id>/<path>             same, for workers.dev / preview routes
//
// Auth: KV RELAY_AUTH key "relay:<id>" holds the sha256 hex of the node's existing join
// token (written at provisioning; see relayAuthRecord). The token itself is never stored.
//
// Free plan only: one SQLite-backed Durable Object per node, hibernatable WebSockets,
// auto-responded heartbeats so an idle node costs no DO wall time.

const ENC = new TextEncoder();
export const PROTOCOL = 1;
const num = (v, d) => { const n = Number(v); return Number.isFinite(n) && n > 0 ? n : d; };
export const limits = (env = {}) => ({
  timeoutMs: num(env.RELAY_REQUEST_TIMEOUT_MS, 30000),
  maxBody: num(env.RELAY_MAX_BODY_BYTES, 8 * 1024 * 1024),
});
const ID_RE = /^[a-z0-9][a-z0-9-]{0,62}$/;
export const validId = (id) => typeof id === "string" && ID_RE.test(id);

export async function sha256Hex(s) {
  const d = await crypto.subtle.digest("SHA-256", ENC.encode(String(s)));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// What the join worker writes at provisioning so a node can authenticate here.
export async function relayAuthRecord(t) {
  return { key: "relay:" + String(t.id).toLowerCase(), value: await sha256Hex(t.token) };
}

function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let x = 0;
  for (let i = 0; i < a.length; i++) x |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return x === 0;
}

export async function authorized(env, id, req) {
  const m = /^Bearer\s+(\S+)$/i.exec(req.headers.get("authorization") || "");
  if (!m || !env.RELAY_AUTH) return false;
  const want = await env.RELAY_AUTH.get("relay:" + id);
  return !!want && timingSafeEqual(await sha256Hex(m[1]), want);
}

// Which node does this public request belong to, and what path should it see?
export function route(url, env = {}) {
  const suffix = String(env.RELAY_HOST_SUFFIX || "").toLowerCase();
  const host = url.hostname.toLowerCase();
  if (suffix && host.endsWith(suffix)) {
    const id = host.slice(0, -suffix.length);
    if (validId(id)) return { id, path: url.pathname + url.search };
  }
  const m = /^\/n\/([^/]+)(\/.*)?$/.exec(url.pathname);
  if (m && validId(m[1])) return { id: m[1], path: (m[2] || "/") + url.search };
  return null;
}

const b64 = (buf) => { let s = ""; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
const unb64 = (s) => Uint8Array.from(atob(s || ""), (c) => c.charCodeAt(0));
const HOP = new Set(["connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer", "host", "content-length"]);
const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

const OFFLINE = (id) => new Response(
  `<!doctype html><meta charset="utf-8"><title>Node offline</title><body style="font-family:system-ui;background:#0d0d0d;color:#f2eee6;display:grid;place-items:center;min-height:100vh;margin:0"><div style="max-width:32rem;padding:1rem"><h1>This node is offline</h1><p>${id} is not connected right now. If this is your computer, make sure it is on and NouGen is running.</p></div>`,
  { status: 502, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });

export class RelaySession {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.pending = new Map(); // rid -> {resolve, timer}
    this.seq = 0;
    // Heartbeats are answered by the runtime without waking the object.
    try { state.setWebSocketAutoResponse(new WebSocketRequestResponsePair('{"t":"ping"}', '{"t":"pong"}')); } catch { /* not in tests */ }
  }

  node() { return this.state.getWebSockets("node")[0] || null; }

  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/_relay/connect") return this.connect(req, url);
    if (url.pathname === "/_relay/status") {
      const ws = this.node();
      const att = ws && ws.deserializeAttachment ? ws.deserializeAttachment() : null;
      return json({ live: !!ws, transport: "relay", since: (att && att.since) || null });
    }
    return this.forward(req, url.searchParams.get("path") || "/");
  }

  connect(req, url) {
    if ((req.headers.get("upgrade") || "").toLowerCase() !== "websocket") return new Response("expected websocket", { status: 426 });
    // One node, one session: a re-register replaces whatever was there.
    for (const old of this.state.getWebSockets("node")) { try { old.close(4000, "replaced"); } catch { /* gone */ } }
    for (const [rid, p] of this.pending) { clearTimeout(p.timer); p.resolve(null); this.pending.delete(rid); }
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.state.acceptWebSocket(server, ["node"]);
    const since = Date.now();
    try { server.serializeAttachment({ since, id: url.searchParams.get("id") }); } catch { /* tests */ }
    server.send(JSON.stringify({ t: "ready", v: PROTOCOL, since }));
    return new Response(null, { status: 101, webSocket: client });
  }

  async forward(req, path) {
    const ws = this.node();
    const id = new URL(req.url).searchParams.get("id") || "node";
    if (!ws) return OFFLINE(id);
    const { timeoutMs, maxBody } = limits(this.env);
    const body = req.body ? await req.arrayBuffer() : new ArrayBuffer(0);
    if (body.byteLength > maxBody) return new Response("request too large for relay", { status: 413 });
    const headers = {};
    for (const [k, v] of req.headers) if (!HOP.has(k.toLowerCase())) headers[k] = v;
    const rid = String(++this.seq) + "-" + Date.now().toString(36);
    const res = await new Promise((resolve) => {
      const timer = setTimeout(() => { this.pending.delete(rid); resolve(null); }, timeoutMs);
      this.pending.set(rid, { resolve, timer });
      try {
        ws.send(JSON.stringify({ t: "req", rid, method: req.method, path, headers, body: b64(body) }));
      } catch { clearTimeout(timer); this.pending.delete(rid); resolve(null); }
    });
    if (!res) return new Response("node did not answer in time", { status: 504 });
    const h = new Headers();
    for (const [k, v] of Object.entries(res.headers || {})) if (!HOP.has(k.toLowerCase())) { try { h.append(k, v); } catch { /* bad header */ } }
    h.set("x-nougen-transport", "relay");
    const status = Number(res.status) || 502;
    const nullBody = status === 204 || status === 304 || req.method === "HEAD";
    return new Response(nullBody ? null : unb64(res.body), { status, headers: h });
  }

  webSocketMessage(ws, msg) {
    let f;
    try { f = JSON.parse(typeof msg === "string" ? msg : new TextDecoder().decode(msg)); } catch { return; }
    if (f.t === "ping") { ws.send('{"t":"pong"}'); return; }
    if (f.t === "res" && this.pending.has(f.rid)) {
      const p = this.pending.get(f.rid);
      this.pending.delete(f.rid);
      clearTimeout(p.timer);
      p.resolve(f);
    }
  }

  webSocketClose(ws, code) {
    if (this.node()) return; // a replacement is already live
    for (const [rid, p] of this.pending) { clearTimeout(p.timer); p.resolve(null); this.pending.delete(rid); }
    try { ws.close(code === 1005 ? 1000 : code, "bye"); } catch { /* closed */ }
  }

  webSocketError(ws) { this.webSocketClose(ws, 1011); }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const stub = (id) => env.RELAY.get(env.RELAY.idFromName(id));
    if (url.pathname === "/_relay/health") return new Response("ok");
    if (url.pathname === "/_relay/connect" || url.pathname === "/_relay/status") {
      const id = (url.searchParams.get("id") || "").toLowerCase();
      if (!validId(id)) return json({ error: "bad id" }, 400);
      if (url.pathname === "/_relay/connect" && !(await authorized(env, id, req))) return json({ error: "unauthorized" }, 401);
      const u = new URL(req.url); u.searchParams.set("id", id);
      return stub(id).fetch(new Request(u, req));
    }
    const r = route(url, env);
    if (!r) return new Response("Not found", { status: 404 });
    const u = new URL("https://relay.internal/forward");
    u.searchParams.set("id", r.id);
    u.searchParams.set("path", r.path);
    return stub(r.id).fetch(new Request(u, { method: req.method, headers: req.headers, body: req.body, redirect: "manual", duplex: "half" }));
  },
};
