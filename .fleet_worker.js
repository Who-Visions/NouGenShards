var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// worker.js
var MCP_PATH = "/mcp";
var PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"];
var CHARACTER_LIMIT = 25e3;
var ACCESS_TTL_S = 30 * 24 * 3600;
var REFRESH_TTL_S = 90 * 24 * 3600;
var CODE_TTL_S = 300;
var SERVER_INFO = { name: "nougen-fleet", version: "1.0.0" };
var enc = new TextEncoder();
function b64url(bytes) {
  let s = "";
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (const b of arr) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
__name(b64url, "b64url");
function b64urlDecode(str) {
  const pad = "=".repeat((4 - str.length % 4) % 4);
  const raw = atob(str.replace(/-/g, "+").replace(/_/g, "/") + pad);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}
__name(b64urlDecode, "b64urlDecode");
async function sha256(text2) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(text2)));
}
__name(sha256, "sha256");
async function hmac(secret, text2) {
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(text2)));
}
__name(hmac, "hmac");
function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
__name(timingSafeEqual, "timingSafeEqual");
function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { "content-type": "application/json", ...headers }
  });
}
__name(json, "json");
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
__name(esc, "esc");
function nowIso() {
  return (/* @__PURE__ */ new Date()).toISOString().replace(/\.\d{3}Z$/, (m) => m);
}
__name(nowIso, "nowIso");
function legStamp(d = /* @__PURE__ */ new Date()) {
  return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}
__name(legStamp, "legStamp");
function truncate(text2, note) {
  if (text2.length <= CHARACTER_LIMIT) return text2;
  return text2.slice(0, CHARACTER_LIMIT) + `

[truncated at ${CHARACTER_LIMIT} chars \u2014 ${note || "narrow the request to see more"}]`;
}
__name(truncate, "truncate");
function fleetKeys(env) {
  const map = /* @__PURE__ */ new Map();
  for (const pair of (env.FLEET_KEYS || "").split(",")) {
    const i = pair.indexOf(":");
    if (i > 0) map.set(pair.slice(0, i).trim(), pair.slice(i + 1).trim());
  }
  return map;
}
__name(fleetKeys, "fleetKeys");
function googleAllowed(env) {
  return new Set((env.GOOGLE_ALLOWED_EMAILS || "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean));
}
__name(googleAllowed, "googleAllowed");
async function signBlob(env, payload) {
  const body = b64url(enc.encode(JSON.stringify(payload)));
  const sig = b64url(await hmac(env.SIGNING_SECRET, "v1." + body));
  return `v1.${body}.${sig}`;
}
__name(signBlob, "signBlob");
async function verifyBlob(env, token) {
  const parts = (token || "").split(".");
  if (parts.length !== 3 || parts[0] !== "v1") return null;
  const expect = b64url(await hmac(env.SIGNING_SECRET, "v1." + parts[1]));
  if (!timingSafeEqual(expect, parts[2])) return null;
  let payload;
  try {
    payload = JSON.parse(new TextDecoder().decode(b64urlDecode(parts[1])));
  } catch {
    return null;
  }
  if (typeof payload.exp !== "number" || payload.exp * 1e3 < Date.now()) return null;
  return payload;
}
__name(verifyBlob, "verifyBlob");
async function issueTokens(env, keyId, email) {
  const iat = Math.floor(Date.now() / 1e3);
  const extra = email ? { eml: email } : {};
  return {
    access_token: await signBlob(env, { typ: "access", key: keyId, ...extra, iat, exp: iat + ACCESS_TTL_S }),
    refresh_token: await signBlob(env, { typ: "refresh", key: keyId, ...extra, iat, exp: iat + REFRESH_TTL_S }),
    token_type: "Bearer",
    expires_in: ACCESS_TTL_S,
    scope: "fleet"
  };
}
__name(issueTokens, "issueTokens");
function identityStillEnrolled(env, payload) {
  if ((payload.key || "").startsWith("g-")) {
    return googleAllowed(env).has((payload.eml || "").toLowerCase());
  }
  return fleetKeys(env).has(payload.key);
}
__name(identityStillEnrolled, "identityStillEnrolled");
async function authenticate(request, env) {
  const m = (request.headers.get("authorization") || "").match(/^Bearer (.+)$/i);
  if (!m) return null;
  const payload = await verifyBlob(env, m[1]);
  if (!payload || payload.typ !== "access") return null;
  if (!identityStillEnrolled(env, payload)) return null;
  return payload.key;
}
__name(authenticate, "authenticate");
async function clientIdFor(env, redirectUri) {
  return "ngf-" + b64url(await hmac(env.SIGNING_SECRET, "client|" + redirectUri)).slice(0, 32);
}
__name(clientIdFor, "clientIdFor");
function redirectAllowed(uri) {
  if (!uri || typeof uri !== "string") return false;
  try {
    const u = new URL(uri);
    if (u.protocol === "https:") {
      return Boolean(u.hostname && u.hostname.includes(".") && !u.hostname.includes(" "));
    }
    if (u.protocol === "http:") {
      return u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "[::1]";
    }
    if (["vscode:", "vscode-insiders:", "cursor:", "windsurf:", "cursor-url:"].includes(u.protocol)) {
      return true;
    }
    return false;
  } catch {
    return false;
  }
}
__name(redirectAllowed, "redirectAllowed");
function oauthMetadata(origin) {
  return {
    issuer: origin,
    authorization_endpoint: origin + "/authorize",
    token_endpoint: origin + "/token",
    registration_endpoint: origin + "/register",
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["none"],
    scopes_supported: ["fleet"]
  };
}
__name(oauthMetadata, "oauthMetadata");
function resourceMetadata(origin) {
  return {
    resource: origin + MCP_PATH,
    authorization_servers: [origin],
    bearer_methods_supported: ["header"],
    scopes_supported: ["fleet"]
  };
}
__name(resourceMetadata, "resourceMetadata");
async function handleRegister(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_client_metadata" }, 400);
  }
  const uris = Array.isArray(body.redirect_uris) ? body.redirect_uris : [];
  if (!uris.length || !uris.every(redirectAllowed)) {
    return json({
      error: "invalid_redirect_uri",
      error_description: "redirect_uris must be a valid https:// callback, localhost, or supported IDE URI scheme"
    }, 400);
  }
  return json({
    client_id: await clientIdFor(env, uris[0]),
    redirect_uris: uris,
    token_endpoint_auth_method: "none",
    grant_types: ["authorization_code", "refresh_token"],
    response_types: ["code"],
    client_name: body.client_name || "mcp-client"
  }, 201);
}
__name(handleRegister, "handleRegister");
function consentPage(params, error, env) {
  const hidden = [
    "client_id",
    "redirect_uri",
    "state",
    "code_challenge",
    "code_challenge_method",
    "scope",
    "response_type"
  ].map((k) => `<input type="hidden" name="${k}" value="${esc(params.get(k) || "")}">`).join("\n      ");
  const qs = new URLSearchParams();
  for (const k of [
    "client_id",
    "redirect_uri",
    "state",
    "code_challenge",
    "code_challenge_method",
    "scope",
    "response_type"
  ]) {
    if (params.get(k)) qs.set(k, params.get(k));
  }
  const googleBtn = env && env.GOOGLE_CLIENT_ID ? `<a class="gbtn" href="/google/start?${esc(qs.toString())}">Continue with Google</a>
      <div class="or">or paste a fleet key</div>` : "";
  return new Response(`<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NouGen Fleet</title>
<style>
  body{background:#0d1117;color:#e6edf3;font:16px/1.5 system-ui,sans-serif;
       display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}
  .card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:2rem;max-width:22rem;width:90%}
  h1{font-size:1.2rem;margin:0 0 .25rem} p{color:#8b949e;font-size:.9rem;margin:.25rem 0 1.25rem}
  input[type=password]{width:100%;box-sizing:border-box;padding:.6rem .8rem;border-radius:8px;
       border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:1rem}
  button{width:100%;margin-top:1rem;padding:.6rem;border:0;border-radius:8px;
       background:#238636;color:#fff;font-size:1rem;cursor:pointer}
  .err{color:#f85149;font-size:.85rem;margin-top:.5rem}
  .gbtn{display:block;text-align:center;padding:.6rem;border-radius:8px;margin-bottom:.25rem;
       background:#fff;color:#1f1f1f;font-weight:600;text-decoration:none;border:1px solid #30363d}
  .or{color:#8b949e;font-size:.8rem;text-align:center;margin:.75rem 0}
</style></head>
<body><form class="card" method="POST" action="/authorize">
      <h1>\u{1F6F0}\uFE0F NouGen Fleet</h1>
      <p>A Claude client wants access to relay, tracker and shard tools.</p>
      ${googleBtn}
      ${hidden}
      <input type="password" name="fleet_key" placeholder="fleet key" autofocus autocomplete="off">
      ${error ? `<div class="err">${esc(error)}</div>` : ""}
      <button type="submit">Authorize</button>
</form></body></html>`, { headers: { "content-type": "text/html; charset=utf-8" } });
}
__name(consentPage, "consentPage");
async function handleAuthorize(request, env, url) {
  const params = request.method === "POST" ? new URLSearchParams(await request.text()) : url.searchParams;
  const redirectUri = params.get("redirect_uri") || "";
  const clientId = params.get("client_id") || "";
  const challenge = params.get("code_challenge") || "";
  if (!redirectAllowed(redirectUri)) return json({ error: "invalid_redirect_uri" }, 400);
  if (clientId !== await clientIdFor(env, redirectUri)) {
    return json({ error: "invalid_client" }, 400);
  }
  if (!challenge || params.get("code_challenge_method") !== "S256") {
    return json({ error: "invalid_request", error_description: "PKCE S256 required" }, 400);
  }
  if (request.method === "GET") return consentPage(params, null, env);
  const presented = (params.get("fleet_key") || "").replace(/\s+/g, "");
  let keyId = null;
  for (const [name, secret] of fleetKeys(env)) {
    if (timingSafeEqual(secret, presented)) {
      keyId = name;
      break;
    }
  }
  if (!keyId) return consentPage(params, "that key does not open this door", env);
  const iat = Math.floor(Date.now() / 1e3);
  const code = await signBlob(env, {
    typ: "code",
    key: keyId,
    cid: clientId,
    uri: redirectUri,
    chal: challenge,
    iat,
    exp: iat + CODE_TTL_S
  });
  const dest = new URL(redirectUri);
  dest.searchParams.set("code", code);
  if (params.get("state")) dest.searchParams.set("state", params.get("state"));
  return Response.redirect(dest.toString(), 302);
}
__name(handleAuthorize, "handleAuthorize");
async function handleToken(request, env) {
  const form = new URLSearchParams(await request.text());
  const grant = form.get("grant_type");
  if (grant === "authorization_code") {
    const payload = await verifyBlob(env, form.get("code") || "");
    if (!payload || payload.typ !== "code") return json({ error: "invalid_grant" }, 400);
    if (payload.uri !== form.get("redirect_uri")) return json({ error: "invalid_grant" }, 400);
    if (form.get("client_id") && form.get("client_id") !== payload.cid) {
      return json({ error: "invalid_client" }, 400);
    }
    const verifier = form.get("code_verifier") || "";
    if (b64url(await sha256(verifier)) !== payload.chal) {
      return json({ error: "invalid_grant", error_description: "PKCE verification failed" }, 400);
    }
    return json(await issueTokens(env, payload.key, payload.eml));
  }
  if (grant === "refresh_token") {
    const payload = await verifyBlob(env, form.get("refresh_token") || "");
    if (!payload || payload.typ !== "refresh") return json({ error: "invalid_grant" }, 400);
    if (!identityStillEnrolled(env, payload)) return json({ error: "invalid_grant" }, 400);
    return json(await issueTokens(env, payload.key, payload.eml));
  }
  return json({ error: "unsupported_grant_type" }, 400);
}
__name(handleToken, "handleToken");
function googleCallback(env, url) {
  const origin = (env.GOOGLE_REDIRECT_ORIGIN || url.origin).replace(/\/$/, "");
  return origin + "/google/callback";
}
__name(googleCallback, "googleCallback");
async function handleGoogleStart(request, env, url) {
  if (!env.GOOGLE_CLIENT_ID) return json({ error: "google_not_configured" }, 404);
  const p = url.searchParams;
  const redirectUri = p.get("redirect_uri") || "";
  const clientId = p.get("client_id") || "";
  const challenge = p.get("code_challenge") || "";
  if (!redirectAllowed(redirectUri) || clientId !== await clientIdFor(env, redirectUri) || !challenge || p.get("code_challenge_method") !== "S256") {
    return json({ error: "invalid_request" }, 400);
  }
  const iat = Math.floor(Date.now() / 1e3);
  const state = await signBlob(env, {
    typ: "gstate",
    cid: clientId,
    uri: redirectUri,
    chal: challenge,
    st: p.get("state") || "",
    iat,
    exp: iat + 600
  });
  const g = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  g.searchParams.set("client_id", env.GOOGLE_CLIENT_ID);
  g.searchParams.set("redirect_uri", googleCallback(env, url));
  g.searchParams.set("response_type", "code");
  g.searchParams.set("scope", "openid email");
  g.searchParams.set("state", state);
  g.searchParams.set("prompt", "select_account");
  return Response.redirect(g.toString(), 302);
}
__name(handleGoogleStart, "handleGoogleStart");
async function handleGoogleCallback(request, env, url) {
  const st = await verifyBlob(env, url.searchParams.get("state") || "");
  if (!st || st.typ !== "gstate") return json({ error: "invalid_state" }, 400);
  const gcode = url.searchParams.get("code");
  if (!gcode) return json({ error: "access_denied" }, 400);
  const tr = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code: gcode,
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET || "",
      redirect_uri: googleCallback(env, url),
      grant_type: "authorization_code"
    })
  });
  if (!tr.ok) return json({ error: "google_exchange_failed" }, 502);
  const { id_token } = await tr.json();
  const vr = await fetch("https://oauth2.googleapis.com/tokeninfo?id_token=" + encodeURIComponent(id_token || ""));
  if (!vr.ok) return json({ error: "google_token_invalid" }, 401);
  const info = await vr.json();
  const email = (info.email || "").toLowerCase();
  if (info.aud !== env.GOOGLE_CLIENT_ID || info.email_verified !== "true" || !googleAllowed(env).has(email)) {
    return json({
      error: "forbidden",
      error_description: `${email || "that account"} is not on the fleet allowlist`
    }, 403);
  }
  const keyId = "g-" + email.split("@")[0].replace(/[^a-z0-9._-]/g, "");
  const iat = Math.floor(Date.now() / 1e3);
  const ourCode = await signBlob(env, {
    typ: "code",
    key: keyId,
    eml: email,
    cid: st.cid,
    uri: st.uri,
    chal: st.chal,
    iat,
    exp: iat + CODE_TTL_S
  });
  const dest = new URL(st.uri);
  dest.searchParams.set("code", ourCode);
  if (st.st) dest.searchParams.set("state", st.st);
  return Response.redirect(dest.toString(), 302);
}
__name(handleGoogleCallback, "handleGoogleCallback");
async function gh(env, path, init = {}) {
  if (!env.GITHUB_TOKEN) {
    throw new Error("GITHUB_TOKEN secret is not set \u2014 relay tools need it. Mint a fine-grained token with contents:read/write on " + env.RELAY_REPO);
  }
  const res = await fetch(`https://api.github.com/repos/${env.RELAY_REPO}${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "user-agent": "nougen-fleet-mcp",
      ...init.headers || {}
    }
  });
  if (!res.ok) {
    const detail = res.status === 404 ? `not found \u2014 check RELAY_REPO (${env.RELAY_REPO}) and token repo access` : `${res.status} ${await res.text().then((t) => t.slice(0, 200))}`;
    throw new Error(`GitHub API ${path}: ${detail}`);
  }
  return res.json();
}
__name(gh, "gh");
function decodeContent(entry) {
  return new TextDecoder().decode(b64urlDecode(
    entry.content.replace(/\n/g, "").replace(/\+/g, "-").replace(/\//g, "_")
  ));
}
__name(decodeContent, "decodeContent");
async function ghReadFile(env, path) {
  const entry = await gh(env, `/contents/${path}?ref=${env.RELAY_BRANCH}`);
  return { text: decodeContent(entry), sha: entry.sha };
}
__name(ghReadFile, "ghReadFile");
async function ghWriteFile(env, path, text2, message, sha) {
  let content = "";
  const bytes = enc.encode(text2);
  for (const b of bytes) content += String.fromCharCode(b);
  return gh(env, `/contents/${path}`, {
    method: "PUT",
    body: JSON.stringify({
      message,
      branch: env.RELAY_BRANCH,
      content: btoa(content),
      ...sha ? { sha } : {}
    })
  });
}
__name(ghWriteFile, "ghWriteFile");
async function listLegs(env) {
  const entries = await gh(env, `/contents/.handoffs?ref=${env.RELAY_BRANCH}`);
  return entries.filter((e) => e.type === "file" && e.name.endsWith(".json")).map((e) => e.name.replace(/\.json$/, "")).sort().reverse();
}
__name(listLegs, "listLegs");
async function readLeg(env, id) {
  const { text: text2, sha } = await ghReadFile(env, `.handoffs/${id}.json`);
  const rec = JSON.parse(text2);
  rec._file = `${id}.json`;
  return { rec, sha };
}
__name(readLeg, "readLeg");
function legSummary(rec) {
  return {
    id: (rec._file || "").replace(/\.json$/, ""),
    machine: rec.machine,
    agent: rec.agent,
    goal: rec.goal,
    status: rec.status || "open",
    created_utc: rec.created_utc,
    branch: rec.branch,
    sha: rec.sha
  };
}
__name(legSummary, "legSummary");
function trackerHost(env) {
  const sub = env.TRACKER_SPACE.toLowerCase().replace("/", "-");
  return `https://${sub}.static.hf.space`;
}
__name(trackerHost, "trackerHost");
async function trackerTree(env, path) {
  const res = await fetch(
    `https://huggingface.co/api/spaces/${env.TRACKER_SPACE}/tree/main/${path}`,
    { headers: { "user-agent": "nougen-fleet-mcp" } }
  );
  if (!res.ok) throw new Error(`tracker tree ${path}: ${res.status}`);
  return res.json();
}
__name(trackerTree, "trackerTree");
async function trackerDaily(env, lane, date) {
  const res = await fetch(
    `${trackerHost(env)}/dailies/${lane}/${date}.json`,
    { headers: { "user-agent": "nougen-fleet-mcp" } }
  );
  if (!res.ok) throw new Error(`no daily for ${lane} on ${date} (${res.status})`);
  return res.json();
}
__name(trackerDaily, "trackerDaily");
async function shardHeaders(env) {
  return {
    // blade's _TokenGatedMCP reads x-ngs-token (or ?token=) only — it never
    // looks at Authorization, so a bearer here 401s every shards call, which
    // the recall path surfaces as an empty vault rather than an auth error.
    "x-ngs-token": env.SHARD_GATEWAY_TOKEN || "",
    "x-nougen-lane": env.SHARD_LANE
  };
}
__name(shardHeaders, "shardHeaders");
function gatewayUnconfigured(env) {
  if (!env.SHARD_GATEWAY_URL) {
    return "shard gateway not configured \u2014 set SHARD_GATEWAY_URL once blade's tunnel is up (see the Aug 14 relay leg: NGS node on blade is the blocker)";
  }
  return null;
}
__name(gatewayUnconfigured, "gatewayUnconfigured");
async function shardRpcHttp(env, method, params, id) {
  const res = await fetch(env.SHARD_GATEWAY_URL.replace(/\/$/, "") + "/mcp/", {
    method: "POST",
    headers: {
      ...await shardHeaders(env),
      "content-type": "application/json",
      accept: "application/json, text/event-stream"
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params })
  });
  if (!res.ok) throw new Error(`gateway ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const text2 = await res.text();
  const data = text2.startsWith("event:") || text2.startsWith("data:") ? JSON.parse(text2.split("\n").find((l) => l.startsWith("data:")).slice(5)) : JSON.parse(text2);
  if (data.error) throw new Error(`gateway rpc: ${data.error.message}`);
  return data.result;
}
__name(shardRpcHttp, "shardRpcHttp");
async function shardCallSse(env, toolName, args) {
  const base = env.SHARD_GATEWAY_URL.replace(/\/$/, "");
  const headers = await shardHeaders(env);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 2e4);
  try {
    const sse = await fetch(base + "/sse", {
      headers: { ...headers, accept: "text/event-stream" },
      signal: ctrl.signal
    });
    if (!sse.ok) throw new Error(`gateway /sse ${sse.status}`);
    const reader = sse.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let messagesUrl = null;
    const results = /* @__PURE__ */ new Map();
    const post = /* @__PURE__ */ __name((msg) => fetch(messagesUrl, {
      method: "POST",
      headers: { ...headers, "content-type": "application/json" },
      body: JSON.stringify(msg)
    }), "post");
    let sent = false;
    for (; ; ) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const event = (frame.match(/^event: ?(.*)$/m) || [])[1];
        const data = frame.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("\n");
        if (event === "endpoint") {
          messagesUrl = new URL(data, base).toString();
          await post({
            jsonrpc: "2.0",
            id: 1,
            method: "initialize",
            params: {
              protocolVersion: "2024-11-05",
              capabilities: {},
              clientInfo: { name: "nougen-fleet-mcp", version: SERVER_INFO.version }
            }
          });
        } else if (data) {
          let msg;
          try {
            msg = JSON.parse(data);
          } catch {
            continue;
          }
          if (msg.id !== void 0) results.set(msg.id, msg);
          if (results.has(1) && !sent) {
            sent = true;
            await post({ jsonrpc: "2.0", method: "notifications/initialized" });
            await post({
              jsonrpc: "2.0",
              id: 2,
              method: "tools/call",
              params: { name: toolName, arguments: args }
            });
          }
          if (results.has(2)) {
            const reply = results.get(2);
            if (reply.error) throw new Error(`gateway tool: ${reply.error.message}`);
            return reply.result;
          }
        }
      }
    }
    throw new Error("gateway SSE stream ended before the tool answered");
  } finally {
    clearTimeout(timer);
    ctrl.abort();
  }
}
__name(shardCallSse, "shardCallSse");
async function shardCall(env, toolName, args) {
  if (env.SHARD_GATEWAY_STYLE === "http") {
    await shardRpcHttp(env, "initialize", {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "nougen-fleet-mcp", version: SERVER_INFO.version }
    }, 1);
    return shardRpcHttp(env, "tools/call", { name: toolName, arguments: args }, 2);
  }
  return shardCallSse(env, toolName, args);
}
__name(shardCall, "shardCall");
function griotRows(result) {
  const items = (result?.content || []).map((c) => c.text || "").filter(Boolean);
  const rows = [];
  const take = /* @__PURE__ */ __name((v) => {
    if (Array.isArray(v)) {
      for (const r of v) take(r);
      return;
    }
    if (v && typeof v === "object") {
      if (Array.isArray(v.result)) {
        take(v.result);
        return;
      }
      rows.push(v);
    }
  }, "take");
  const structured = result?.structuredContent;
  if (structured) take(structured);
  if (!rows.length) {
    for (const item of items) {
      try {
        take(JSON.parse(item));
      } catch {
      }
    }
  }
  return rows;
}
__name(griotRows, "griotRows");
function griotEra(row) {
  const ts = typeof row?.timestamp === "string" ? row.timestamp.trim() : "";
  return /^\d{4}-\d{2}/.test(ts) ? ts.slice(0, 7) : null;
}
__name(griotEra, "griotEra");
function griotInEra(row, since, until) {
  const ts = typeof row?.timestamp === "string" ? row.timestamp.trim() : "";
  if (!ts) return false;
  if (since && ts < since) return false;
  if (until && ts > until + "\uFFFF") return false;
  return true;
}
__name(griotInEra, "griotInEra");
function griotFlags(row) {
  const flags = [];
  const title = String(row?.title || "");
  const content = String(row?.content || "");
  if (title.startsWith("[RETRACTED]") || /\n--- RETRACTED /.test(content)) flags.push("[retracted]");
  if (/\n--- UPDATE /.test(content)) flags.push("[amended]");
  return flags;
}
__name(griotFlags, "griotFlags");
function griotKey(row) {
  return [row?.source ?? row?._db_index ?? "?", row?.id ?? row?.title ?? "?"].join("::");
}
__name(griotKey, "griotKey");
function text(t, structured) {
  return {
    content: [{ type: "text", text: t }],
    ...structured !== void 0 ? { structuredContent: structured } : {}
  };
}
__name(text, "text");
function toolError(message) {
  return { content: [{ type: "text", text: "Error: " + message }], isError: true };
}
__name(toolError, "toolError");
var TOOLS = [
  {
    name: "fleet_whoami",
    title: "Fleet Connector Status",
    description: "Who you are to the fleet and what this connector can reach. Call first if any tool group misbehaves: reports the authenticated key, the connector lane, and which backends (relay repo, tracker space, shard gateway) are configured.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false }
  },
  {
    name: "relay_open",
    title: "Open Relay Legs",
    description: "Legs nobody has acked \u2014 work handed to the fleet and not yet picked up. Returns id, machine/agent, goal, created_utc per leg, newest first. Take one with relay_ack.\n\nArgs: limit (1-25, default 10).",
    inputSchema: {
      type: "object",
      properties: {
        limit: {
          type: "integer",
          minimum: 1,
          maximum: 25,
          default: 10,
          description: "Maximum open legs to return"
        }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "relay_latest",
    title: "Latest Relay Leg",
    description: "The most recent handoff leg regardless of status, with its full markdown body. Use to catch up on where the fleet left off.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "relay_read",
    title: "Read Relay Leg",
    description: "Read one leg by id (the filename stem, e.g. '20260814T174747Z__mondy__claude-cli'): record fields plus markdown body.",
    inputSchema: {
      type: "object",
      properties: {
        id: {
          type: "string",
          minLength: 10,
          description: "Leg id \u2014 filename without extension"
        }
      },
      required: ["id"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "relay_ack",
    title: "Ack Relay Leg",
    description: "Take the baton on an open leg \u2014 commits status='acked' plus a relay event to the registry, exactly like the CLI. A leg stays open until someone acks, so acking is claiming responsibility to continue it.\n\nArgs: id (leg id), note (why you're taking it).",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", minLength: 10, description: "Leg id to ack" },
        note: { type: "string", default: "", description: "Short note recorded with the ack" }
      },
      required: ["id"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "relay_create",
    title: "Create Relay Leg",
    description: "Write a new handoff leg to the registry \u2014 what you want done or where you left off. Lands as an open leg other lanes see on their next relay check.\n\nArgs: goal (one line), message (markdown body).",
    inputSchema: {
      type: "object",
      properties: {
        goal: {
          type: "string",
          minLength: 4,
          maxLength: 200,
          description: "One-line goal, shown in every relay listing"
        },
        message: {
          type: "string",
          minLength: 1,
          description: "Markdown body: situation, ask, done-when"
        }
      },
      required: ["goal", "message"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "relay_claim_list",
    title: "Active Fleet Claims",
    description: "What each machine says it is working on right now \u2014 active, unexpired claims. Check before starting overlapping work.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "tracker_lanes",
    title: "Tracker Lanes",
    description: "Lanes with usage dailies in the tracker, each with its file count and most recent date.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "tracker_daily",
    title: "Tracker Daily",
    description: "One lane's usage daily for a date: token counts (exact + estimated), invocations, per-model breakdown.\n\nArgs: lane (e.g. 'blade1tb'), date (YYYY-MM-DD).",
    inputSchema: {
      type: "object",
      properties: {
        lane: { type: "string", minLength: 2, description: "Lane name, e.g. 'blade1tb'" },
        date: { type: "string", pattern: "^\\d{4}-\\d{2}-\\d{2}$", description: "YYYY-MM-DD" }
      },
      required: ["lane", "date"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "tracker_spend",
    title: "Tracker Spend Summary",
    description: "Aggregate usage across dailies: total invocations and exact token counts, per lane. Dates are inclusive; omit lane to sweep all lanes. Scans at most 92 dailies per call \u2014 narrow the range if truncated.\n\nArgs: lane (optional), since (YYYY-MM-DD, optional), until (YYYY-MM-DD, optional).",
    inputSchema: {
      type: "object",
      properties: {
        lane: { type: "string", description: "Restrict to one lane" },
        since: { type: "string", pattern: "^\\d{4}-\\d{2}-\\d{2}$", description: "Start date, inclusive" },
        until: { type: "string", pattern: "^\\d{4}-\\d{2}-\\d{2}$", description: "End date, inclusive" }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_status",
    title: "Shard Gateway Status",
    description: "Health-check blade's shard gateway. Reports up/down and whether shard recall is available to this connector.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_recall",
    title: "Recall Fleet Memory",
    description: "Semantic recall over the fleet shard grid via blade's gateway. Needs the gateway online (shards_status first if unsure).\n\nArgs: query (what to remember), limit (1-20, default 5).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", minLength: 2, description: "What to recall" },
        limit: { type: "integer", minimum: 1, maximum: 20, default: 5 }
      },
      required: ["query"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_search",
    title: "Search Fleet Context",
    description: "Keyword/context search over the shard grid via blade's gateway.\n\nArgs: query, limit (1-20, default 5).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", minLength: 2, description: "Search terms" },
        limit: { type: "integer", minimum: 1, maximum: 20, default: 5 }
      },
      required: ["query"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_coverage",
    title: "What the Grid Actually Holds",
    description: 'Span, total and per-month shard counts for the node behind this connector, plus the months that are empty.\n\nCall this before concluding a recall miss means the memory does not exist. An empty result is ambiguous in the worst way \u2014 it reads as "never happened" when it can mean "this node never held that era" (a partial mount) or "nothing was captured that month" (a real gap between live months). This tells them apart.',
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_window",
    title: "Browse the Grid by Era",
    description: 'Recall filtered by DATE, newest first \u2014 use this whenever the question is about a time period rather than a topic.\n\nshards_recall ranks on content relevance only, so "what was I doing in March 2026" just matches shards whose text contains those words and buries them under whatever is densest today. This filters on the timestamp before scoring, so a quiet era still returns its shards.\n\nsince/until are ISO prefixes, both inclusive: since="2026-03", until="2026-03" is all of March; until="2026-03-14" covers that whole day. query is optional \u2014 omit it to page an era, supply it to search within one.\n\nArgs: query (optional), since, until, limit (1-50).',
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Optional terms to search within the window" },
        since: { type: "string", description: "Inclusive ISO lower bound, e.g. 2026-03" },
        until: { type: "string", description: "Inclusive ISO upper bound, e.g. 2026-03" },
        limit: { type: "integer", minimum: 1, maximum: 50, default: 10 }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "ask_griot",
    title: "Ask the Archive",
    description: "Ask the archive a question and receive the story raw. The griot GATHERS, it does not tell: it runs recall + keyword search (+ an era window when since/until are given) across the federated stores and returns ONE provenance-marked packet, oldest memory first. Each memory carries its era (YYYY-MM), source store, id, and correction flags ([amended]/[retracted]) \u2014 corrections are part of the story, never erased. YOU are the teller: narrate from the packet, and pull any memory in full by id (shards_recall / shards_window) when the excerpt is not enough.\n\nsince/until are inclusive ISO era bounds and are enforced on EVERY arm: a memory that cannot be proven inside the window \u2014 including an undated one from a vault lane \u2014 is held back and counted, never shown as evidence for a bounded question.\n\nArgs: question (required), limit (1-20, default 8), since/until (optional inclusive ISO era bounds, e.g. 2025-06).",
    inputSchema: {
      type: "object",
      properties: {
        question: { type: "string", minLength: 3, description: "What you want the archive to remember" },
        limit: { type: "integer", minimum: 1, maximum: 20, default: 8, description: "Memories to gather per lane" },
        since: { type: "string", description: "Inclusive ISO lower era bound, e.g. 2025-06" },
        until: { type: "string", description: "Inclusive ISO upper era bound, e.g. 2026-03" }
      },
      required: ["question"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_capture",
    title: "Write a Shard",
    description: "Store a durable learning in the fleet grid. The write half of shards_recall - without it a lane can read the vault but never add to it, so anything learned has to detour through a relay leg and wait for a lane that has capture access.\n\nThe node deduplicates by content and reports success either way, so re-capturing identical text is a safe no-op (it does NOT create a second shard). Write what a future lane needs to ACT on: the finding and why it holds, not a status update.\n\nArgs: title, content, event_type (KNOWLEDGE default), tags (optional array).",
    inputSchema: {
      type: "object",
      properties: {
        title: {
          type: "string",
          minLength: 4,
          maxLength: 200,
          description: "One line, specific enough to recognise in a hit list"
        },
        content: {
          type: "string",
          minLength: 10,
          description: "The durable content. Include the why, not just the what."
        },
        event_type: {
          type: "string",
          default: "KNOWLEDGE",
          description: "KNOWLEDGE (default), DECISION, FAILURE, or your own label"
        },
        tags: {
          type: "array",
          items: { type: "string" },
          description: 'Retrieval tags, e.g. ["infrastructure","gateway"]'
        }
      },
      required: ["title", "content"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_mark",
    title: "Mark a Shard Useful",
    description: "Feed back whether a recalled shard actually helped. This is the outcome-weighting loop: marked-useful shards rank higher for every lane afterwards, so recall gets better instead of just bigger. Use the id from a recall hit.\n\nArgs: shard_id, worked (true/false), db_index (optional).",
    inputSchema: {
      type: "object",
      properties: {
        shard_id: { type: "integer", description: "id from a recall/search hit" },
        worked: { type: "boolean", description: "true if it helped, false if it misled" },
        db_index: { type: "integer", description: "Shard DB index, if the hit names one" }
      },
      required: ["shard_id", "worked"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_amend",
    title: "Amend a Shard",
    description: "Append a dated note to an existing shard, keeping everything already there. The append-only way to correct or extend: history grows, it is never rewritten. Use for living dossiers and for a shard that turned out partly wrong.\n\nIds repeat across the 9 cluster DBs \u2014 pass db_index from the recall hit's _db_index, or the call is refused as ambiguous.\n\nArgs: shard_id, note, db_index (recommended).",
    inputSchema: {
      type: "object",
      properties: {
        shard_id: { type: "integer", description: "id from a recall/search hit" },
        note: { type: "string", minLength: 4, description: "Text to append under a dated heading" },
        db_index: { type: "integer", description: "_db_index from the recall hit" },
        confirm_title: {
          type: "string",
          description: "Title you believe you are amending. Strongly recommended \u2014 recall is fuzzy and can return a neighbour's id."
        }
      },
      required: ["shard_id", "note"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "shards_retract",
    title: "Retract a Shard",
    description: "Withdraw a shard WITHOUT erasing it: title gets [RETRACTED], the reason is appended, it is tagged `retracted`, and its utility is floored so recall stops surfacing it.\n\nPrefer this over shards_forget. The row survives, so the grid still records that this was once believed and why it stopped being true \u2014 which is what makes the vault a witness rather than a cache.\n\nArgs: shard_id, reason, db_index (recommended).",
    inputSchema: {
      type: "object",
      properties: {
        shard_id: { type: "integer", description: "id from a recall/search hit" },
        reason: { type: "string", minLength: 4, description: "Why it no longer holds" },
        db_index: { type: "integer", description: "_db_index from the recall hit" },
        confirm_title: {
          type: "string",
          description: "Title you believe you are retracting. Strongly recommended \u2014 on 2026-08-15 a fuzzy recall hit caused a real shard to be retracted by mistake."
        }
      },
      required: ["shard_id", "reason"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_forget",
    title: "Permanently Delete a Shard",
    description: "IRREVERSIBLE. Deletes the row and its search-index entry. No undo, no tombstone, nothing records that it existed.\n\nconfirm_title must match the shard's CURRENT title exactly (including a [RETRACTED] prefix if present). That is a real guard, not ceremony: ids repeat across the 9 cluster DBs, so an id alone can name a shard you have never seen.\n\nUse shards_retract instead unless the content must not exist \u2014 a secret pasted in by mistake, or something legally required to be gone.\n\nArgs: shard_id, confirm_title, db_index.",
    inputSchema: {
      type: "object",
      properties: {
        shard_id: { type: "integer", description: "id from a recall/search hit" },
        confirm_title: {
          type: "string",
          minLength: 1,
          description: "Exact current title \u2014 proves you are looking at what you delete"
        },
        db_index: { type: "integer", description: "_db_index from the recall hit" }
      },
      required: ["shard_id", "confirm_title"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "vault_put",
    title: "Write a Vault Secret",
    description: "Store or rotate a credential in the keymaker vault. WRITE-ONLY: there is deliberately no vault_get anywhere in this connector, so a lane can rotate a credential but can never read one back. Reading secrets over a network surface would put every provider key behind a single bearer token.\n\nReturns a SHA-256 fingerprint (first 12 hex) so you can prove the stored value is the one you meant \u2014 compare fingerprints, never values.\n\nArgs: key, value.",
    inputSchema: {
      type: "object",
      properties: {
        key: { type: "string", minLength: 2, description: "Secret name, e.g. OPENROUTER_KEY_X" },
        value: { type: "string", minLength: 1, description: "The secret. Never echoed back." }
      },
      required: ["key", "value"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "vault_list",
    title: "List Vault Secrets",
    description: 'Secret NAMES, rotation dates and fingerprints \u2014 never values. Enough to answer "is this credential present, and is it the one I think?" (compare fingerprints) without the vault becoming readable.',
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "ask_rhea",
    title: "Ask Rhea-Noir",
    description: "Ask Rhea-Noir, the grid's resident agent living in the NouGen Space (Kimi K3 brain with a free-lane fallback - her reply names which brain answered, never faked). She recalls from the memory grid, consults the griot's gather for provenance-marked history, reads the tracker and the relay, and captures shards worth keeping. Expect 10-60s. Args: prompt (required).",
    inputSchema: {
      type: "object",
      properties: {
        prompt: { type: "string", minLength: 3, description: "What you want Rhea-Noir to consider" }
      },
      required: ["prompt"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "kaedra_ask",
    title: "Ask Kaedra (phoebus)",
    description: "Run a prompt on Kaedra, the local Ollama lane on phoebus, through the token-gated kaedra gateway. Free per token - route bulk drafting, summarisation, triage and distillation here before spending a cloud call. Models are allow-listed server-side (kaedracode / gemma4 personas); naming one outside the list is a 403, not a pull. First call after a reboot pays a ~38s cold load, later calls are inference-speed because the gateway pins the model resident. Args: prompt (required), model, system, temperature, num_predict.",
    inputSchema: {
      type: "object",
      properties: {
        prompt: { type: "string", minLength: 3, description: "What you want Kaedra to generate" },
        model: { type: "string", description: "Allow-listed model name; omit for the gateway default" },
        system: { type: "string", description: "Optional system prompt" },
        temperature: { type: "number", description: "Sampling temperature" },
        num_predict: { type: "integer", description: "Max tokens to generate" }
      },
      required: ["prompt"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  }
];
var KAEDRA_URL_FALLBACK = "https://kaedra.nougenai.com";
var KAEDRA_TIMEOUT_FALLBACK_MS = 15e4;
var HANDLERS = {
  // Rhea-Noir lives in the Space; the connector carries the question to her
  // /agent endpoint and hands her JSON back verbatim (answer + which brain
  // answered + which tools she used).
  async ask_rhea(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const base = env.SHARD_GATEWAY_URL.replace(/\/$/, "");
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), Number(env.RHEA_TIMEOUT_MS || 9e4));
    try {
      const res = await fetch(base + "/agent", {
        method: "POST",
        headers: { ...await shardHeaders(env), "content-type": "application/json" },
        body: JSON.stringify({ prompt: args.prompt }),
        signal: ctrl.signal
      });
      if (!res.ok) return toolError("rhea /agent " + res.status + ": " + (await res.text()).slice(0, 200));
      return { content: [{ type: "text", text: JSON.stringify(await res.json()) }] };
    } catch (err) {
      return toolError("rhea unreachable: " + (err.message || String(err)));
    } finally {
      clearTimeout(timer);
    }
  },
  // Kaedra is phoebus's local Ollama lane, fenced behind a token gateway because
  // Ollama has no auth of its own. Every value here resolves from env with the
  // constant only as a logged fallback (Rule 0.2) - the URL moves when the
  // tunnel is rebuilt, and the cold-load budget is a property of the box.
  async kaedra_ask(args, env) {
    const base = (env.KAEDRA_GATEWAY_URL || KAEDRA_URL_FALLBACK).replace(/\/$/, "");
    if (!env.KAEDRA_GATEWAY_URL) {
      console.log("kaedra_ask: KAEDRA_GATEWAY_URL unset, falling back to " + KAEDRA_URL_FALLBACK);
    }
    if (!env.KAEDRA_GATEWAY_TOKEN) {
      return toolError("kaedra gateway token not configured - set KAEDRA_GATEWAY_TOKEN");
    }
    const body = { prompt: args.prompt };
    for (const k of ["model", "system"]) if (args[k]) body[k] = args[k];
    if (typeof args.temperature === "number") body.temperature = args.temperature;
    if (Number.isInteger(args.num_predict)) body.num_predict = args.num_predict;
    let budgetMs = Number(env.KAEDRA_TIMEOUT_MS);
    if (!Number.isFinite(budgetMs) || budgetMs <= 0) {
      if (env.KAEDRA_TIMEOUT_MS !== void 0) {
        console.log("kaedra_ask: KAEDRA_TIMEOUT_MS is not a positive number (" + env.KAEDRA_TIMEOUT_MS + "), using " + KAEDRA_TIMEOUT_FALLBACK_MS);
      }
      budgetMs = KAEDRA_TIMEOUT_FALLBACK_MS;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), budgetMs);
    try {
      const res = await fetch(base + "/generate", {
        method: "POST",
        headers: {
          // The gateway reads X-Kaedra-Token (bearer also accepted); it compares
          // in constant time and 401s on any mismatch.
          "x-kaedra-token": env.KAEDRA_GATEWAY_TOKEN,
          "content-type": "application/json"
        },
        body: JSON.stringify(body),
        signal: ctrl.signal
      });
      const raw = await res.text();
      if (!res.ok) return toolError("kaedra /generate " + res.status + ": " + raw.slice(0, 300));
      let out;
      try {
        out = JSON.parse(raw);
      } catch {
        return toolError("kaedra returned non-JSON: " + raw.slice(0, 200));
      }
      return text(out.response || "(empty response)", {
        model: out.model,
        eval_count: out.eval_count,
        total_ms: out.total_ms
      });
    } catch (err) {
      const msg = err.name === "AbortError" ? "kaedra timed out - phoebus may be cold-loading the model, retry once" : "kaedra unreachable: " + (err.message || String(err));
      return toolError(msg);
    } finally {
      clearTimeout(timer);
    }
  },
  async fleet_whoami(args, env, keyId) {
    const out = {
      key: keyId,
      lane: env.CONNECTOR_LANE,
      relay: { repo: env.RELAY_REPO, token_set: Boolean(env.GITHUB_TOKEN) },
      tracker: { space: env.TRACKER_SPACE },
      shards: {
        gateway_url: env.SHARD_GATEWAY_URL || "(not configured)",
        token_set: Boolean(env.SHARD_GATEWAY_TOKEN),
        lane: env.SHARD_LANE
      }
    };
    return text(
      `Authenticated as fleet key **${keyId}**, writing to the registry as lane **${env.CONNECTOR_LANE}**.

- relay: ${env.RELAY_REPO} (token ${out.relay.token_set ? "set" : "MISSING"})
- tracker: ${env.TRACKER_SPACE}
- shards: ${out.shards.gateway_url} (token ${out.shards.token_set ? "set" : "missing"})`,
      out
    );
  },
  async relay_open(args, env) {
    const limit = args.limit ?? 10;
    const ids = await listLegs(env);
    const open = [];
    for (let i = 0; i < ids.length && open.length < limit && i < 40; i += 8) {
      const batch = await Promise.all(
        ids.slice(i, i + 8).map((id) => readLeg(env, id).then(({ rec }) => rec))
      );
      for (const rec of batch) {
        if ((rec.status || "open") === "open") open.push(legSummary(rec));
        if (open.length >= limit) break;
      }
    }
    if (!open.length) {
      return text(
        "\u2705 no unacked legs \u2014 every baton has been picked up",
        { open: [], count: 0 }
      );
    }
    const lines = [`\u26A0\uFE0F ${open.length} leg(s) waiting for an ack (newest ${Math.min(40, ids.length)} scanned):`, ""];
    for (const leg of open) {
      lines.push(`- **${leg.machine}/${leg.agent}** \u2014 ${leg.goal}`);
      lines.push(`  id \`${leg.id}\` \xB7 ${leg.created_utc}`);
    }
    lines.push("", "Take one with relay_ack.");
    return text(lines.join("\n"), { open, count: open.length });
  },
  async relay_latest(args, env) {
    const ids = await listLegs(env);
    if (!ids.length) return text("registry has no legs");
    const { rec } = await readLeg(env, ids[0]);
    let body = "";
    try {
      body = (await ghReadFile(env, `.handoffs/${ids[0]}.md`)).text;
    } catch {
      body = "(no markdown body)";
    }
    return text(truncate(body, "use relay_read for specific legs"), legSummary(rec));
  },
  async relay_read(args, env) {
    const id = args.id.replace(/[^A-Za-z0-9_.-]/g, "");
    const { rec } = await readLeg(env, id);
    let body = "";
    try {
      body = (await ghReadFile(env, `.handoffs/${id}.md`)).text;
    } catch {
      body = "(no markdown body)";
    }
    const summary = legSummary(rec);
    return text(
      `**${summary.id}** \u2014 ${summary.status}
${summary.machine}/${summary.agent} \xB7 ${summary.created_utc}

` + truncate(body, "leg body truncated"),
      { ...summary, relay: rec.relay || [] }
    );
  },
  async relay_ack(args, env, keyId) {
    const id = args.id.replace(/[^A-Za-z0-9_.-]/g, "");
    const { rec, sha } = await readLeg(env, id);
    if ((rec.status || "open") !== "open") {
      return toolError(`leg ${id} is '${rec.status}', not open \u2014 someone already has the baton. relay_read to see who.`);
    }
    delete rec._file;
    rec.status = "acked";
    (rec.relay = rec.relay || []).push({
      event: "ack",
      machine: env.CONNECTOR_LANE,
      agent: keyId,
      at: nowIso(),
      note: args.note || ""
    });
    await ghWriteFile(
      env,
      `.handoffs/${id}.json`,
      JSON.stringify(rec, null, 2) + "\n",
      `relay(${env.CONNECTOR_LANE}): ack ${rec.goal || id}`,
      sha
    );
    return text(
      `\u2705 baton taken by ${env.CONNECTOR_LANE}/${keyId}: ${rec.goal || id}`,
      { id, status: "acked" }
    );
  },
  async relay_create(args, env, keyId) {
    const stamp = legStamp();
    const id = `${stamp}__${env.CONNECTOR_LANE}__${keyId}`;
    const record = {
      id,
      machine: env.CONNECTOR_LANE,
      agent: keyId,
      goal: args.goal,
      branch: "n/a",
      sha: "connector",
      remote: "origin",
      created_utc: nowIso(),
      stack: { manifests: [], frameworks: [] },
      dirty: false,
      status: "open"
    };
    const md = [
      `# \u{1F91D} Git Handoff \u2014 ${env.CONNECTOR_LANE} / ${keyId}`,
      "",
      `**Goal**: ${args.goal}`,
      `**Branch**: \`n/a\` (written via fleet connector)`,
      `**When**: ${record.created_utc}`,
      "",
      "---",
      args.message.trim(),
      ""
    ].join("\n");
    await ghWriteFile(
      env,
      `.handoffs/${id}.json`,
      JSON.stringify(record, null, 2) + "\n",
      `handoff(${env.CONNECTOR_LANE}): ${args.goal}`
    );
    await ghWriteFile(
      env,
      `.handoffs/${id}.md`,
      md,
      `handoff(${env.CONNECTOR_LANE}): ${args.goal} (body)`
    );
    return text(
      `\u2705 leg published: \`${id}\`
Other lanes see it on their next relay check.`,
      { id, goal: args.goal }
    );
  },
  async relay_claim_list(args, env) {
    const entries = await gh(env, `/contents/.handoffs/claims?ref=${env.RELAY_BRANCH}`);
    const names = entries.filter((e) => e.type === "file" && e.name.endsWith(".json")).map((e) => e.name).sort().reverse().slice(0, 20);
    const claims = await Promise.all(names.map((n) => ghReadFile(env, `.handoffs/claims/${n}`).then(({ text: t }) => JSON.parse(t))));
    const active = claims.filter((c) => {
      if (c.status === "released") return false;
      const ttlMs = (c.ttl_hours ?? 8) * 3600 * 1e3;
      return Date.parse(c.created_utc) + ttlMs > Date.now();
    });
    if (!active.length) return text("no active claims \u2014 every scope is free", { claims: [] });
    const lines = ["Active claims:", ""];
    for (const c of active) {
      lines.push(`- **${c.machine}/${c.agent}** \u2014 ${c.goal}`);
      lines.push(`  scope \`${c.scope}\` \xB7 since ${c.created_utc} \xB7 ttl ${c.ttl_hours}h`);
    }
    return text(lines.join("\n"), { claims: active });
  },
  async tracker_lanes(args, env) {
    const dirs = (await trackerTree(env, "dailies")).filter((e) => e.type === "directory");
    const lanes = await Promise.all(dirs.map(async (d) => {
      const files = (await trackerTree(env, d.path)).filter((e) => e.path.endsWith(".json")).map((e) => e.path.split("/").pop().replace(".json", "")).sort();
      return { lane: d.path.split("/").pop(), dailies: files.length, latest: files.at(-1) || null };
    }));
    const lines = ["Tracker lanes:", ""];
    for (const l of lanes) lines.push(`- **${l.lane}** \u2014 ${l.dailies} dailies, latest ${l.latest}`);
    return text(lines.join("\n"), { lanes });
  },
  async tracker_daily(args, env) {
    const daily = await trackerDaily(env, args.lane, args.date);
    const e = daily.exact || {};
    const md = [
      `**${args.lane} \u2014 ${args.date}**`,
      "",
      `invocations: ${daily.invocations ?? "?"}`,
      `exact tokens: in ${e.input_tokens ?? 0} / out ${e.output_tokens ?? 0} / cache-read ${e.cache_read ?? 0} / cache-create ${e.cache_creation ?? 0}`,
      `models: ${Object.keys(daily.models || {}).join(", ") || "(none)"}`
    ].join("\n");
    return text(md, daily);
  },
  async tracker_spend(args, env) {
    const dirs = (await trackerTree(env, "dailies")).filter((e) => e.type === "directory");
    const lanes = dirs.map((d) => d.path.split("/").pop()).filter((l) => !args.lane || l === args.lane);
    if (!lanes.length) return toolError(`no such lane '${args.lane}' in the tracker`);
    const perLane = [];
    let budget = 92;
    let skipped = 0;
    for (const lane of lanes) {
      const dates = (await trackerTree(env, `dailies/${lane}`)).filter((e) => e.path.endsWith(".json")).map((e) => e.path.split("/").pop().replace(".json", "")).filter((d) => (!args.since || d >= args.since) && (!args.until || d <= args.until)).sort();
      const take = dates.slice(-budget);
      skipped += dates.length - take.length;
      budget -= take.length;
      const totals = {
        lane,
        days: take.length,
        invocations: 0,
        input_tokens: 0,
        output_tokens: 0,
        cache_read: 0,
        cache_creation: 0
      };
      const dailies = await Promise.all(take.map((d) => trackerDaily(env, lane, d).catch(() => null)));
      for (const daily of dailies) {
        if (!daily) continue;
        totals.invocations += daily.invocations || 0;
        const e = daily.exact || {};
        totals.input_tokens += e.input_tokens || 0;
        totals.output_tokens += e.output_tokens || 0;
        totals.cache_read += e.cache_read || 0;
        totals.cache_creation += e.cache_creation || 0;
      }
      perLane.push(totals);
    }
    const grand = perLane.reduce((acc, t) => {
      for (const k of ["days", "invocations", "input_tokens", "output_tokens", "cache_read", "cache_creation"]) {
        acc[k] = (acc[k] || 0) + t[k];
      }
      return acc;
    }, {});
    const lines = ["Spend summary" + (args.since || args.until ? ` (${args.since || "\u2026"} \u2192 ${args.until || "\u2026"})` : " (all time scanned)") + ":", ""];
    for (const t of perLane) {
      lines.push(`- **${t.lane}**: ${t.days} days, ${t.invocations} invocations, in ${t.input_tokens.toLocaleString()} / out ${t.output_tokens.toLocaleString()} tokens`);
    }
    lines.push("", `**Total**: ${grand.invocations || 0} invocations, in ${(grand.input_tokens || 0).toLocaleString()} / out ${(grand.output_tokens || 0).toLocaleString()} tokens`);
    if (skipped > 0) {
      lines.push("", `\u26A0\uFE0F ${skipped} dailies skipped (92-file scan cap) \u2014 narrow the date range.`);
    }
    return text(lines.join("\n"), { lanes: perLane, total: grand, skipped });
  },
  async shards_status(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return text("\u{1F534} " + unset, { up: false, configured: false });
    try {
      const res = await fetch(
        env.SHARD_GATEWAY_URL.replace(/\/$/, "") + "/health",
        { headers: await shardHeaders(env), signal: AbortSignal.timeout(8e3) }
      );
      return text(
        res.ok ? "\u{1F7E2} shard gateway is up \u2014 recall and search are live" : `\u{1F7E1} gateway answered ${res.status} \u2014 check SHARD_GATEWAY_TOKEN and lane`,
        { up: res.ok, status: res.status, configured: true }
      );
    } catch (err) {
      return text(
        `\u{1F534} gateway unreachable (${err.message}) \u2014 blade's tunnel is likely down; see the open relay leg about the NGS node`,
        { up: false, configured: true }
      );
    }
  },
  async shards_recall(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(
      env,
      env.SHARD_TOOL_RECALL,
      { query: args.query, limit: args.limit ?? 5 }
    );
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    return text(truncate(body || "(no recall results)", "lower the limit"), result.structuredContent);
  },
  async shards_search(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(
      env,
      env.SHARD_TOOL_SEARCH,
      { query: args.query, limit: args.limit ?? 5 }
    );
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    return text(truncate(body || "(no matches)", "lower the limit"), result.structuredContent);
  },
  async shards_coverage(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, env.SHARD_TOOL_COVERAGE || "substrate_coverage", {});
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body);
    let d;
    try {
      d = JSON.parse(body);
    } catch {
      return text(body, result.structuredContent);
    }
    const lines = [
      `**${(d.total_shards ?? 0).toLocaleString()} shards**`,
      `span: ${(d.span?.earliest || "?").slice(0, 10)} \u2192 ${(d.span?.latest || "?").slice(0, 10)}`,
      "",
      "per month:"
    ];
    const months = d.months || {};
    const peak = Math.max(1, ...Object.values(months));
    for (const [m, n] of Object.entries(months)) {
      lines.push(`  ${m}  ${String(n).padStart(6)}  ${"#".repeat(Math.max(1, Math.round(30 * n / peak)))}`);
    }
    if (d.empty_months?.length) {
      lines.push(
        "",
        `\u26A0\uFE0F empty months inside the span: ${d.empty_months.join(", ")}`,
        "A month with live months on both sides is a capture gap, not a missing memory."
      );
    }
    return text(lines.join("\n"), d);
  },
  async shards_window(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const payload = { limit: args.limit ?? 10 };
    if (args.query) payload.query = args.query;
    if (args.since) payload.since = args.since;
    if (args.until) payload.until = args.until;
    const result = await shardCall(env, env.SHARD_TOOL_WINDOW || "recall_window", payload);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body);
    const span = [args.since || "\u2026", args.until || "\u2026"].join(" \u2192 ");
    return text(
      truncate(
        body || `(no shards in ${span} \u2014 that era may live on another node)`,
        "narrow the window or lower the limit"
      ),
      result.structuredContent
    );
  },
  async ask_griot(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const question = String(args.question || "").trim();
    const limit = Math.max(1, Math.min(args.limit ?? 8, 20));
    const since = args.since ? String(args.since).trim() : null;
    const until = args.until ? String(args.until).trim() : null;
    const bounded = Boolean(since || until);
    const arms = [
      { lane: "recall", tool: env.SHARD_TOOL_RECALL, args: { query: question, limit } },
      { lane: "search", tool: env.SHARD_TOOL_SEARCH, args: { query: question, limit } }
    ].filter((arm, i, all2) => (
      // SHARD_TOOL_SEARCH is currently pinned to recall_memory: the node's MCP
      // surface registers no search_context, so the two arms would be the same
      // call twice — one wasted round trip against a cold Space, and a second
      // chance to time out. Collapse identical arms instead of paying for them.
      Boolean(arm.tool) && all2.findIndex((a) => a.tool === arm.tool) === i
    ));
    if (bounded) {
      const windowArgs = { query: question, limit };
      if (since) windowArgs.since = since;
      if (until) windowArgs.until = until;
      arms.push({ lane: "window", tool: env.SHARD_TOOL_WINDOW || "recall_window", args: windowArgs });
    }
    const failures = [];
    const gathered = await Promise.all(arms.map(async (arm) => {
      try {
        const result = await shardCall(env, arm.tool, arm.args);
        if (result?.isError) {
          const why = (result.content || []).map((c) => c.text || "").join(" ").slice(0, 200);
          failures.push({ lane: arm.lane, error: why || "gateway reported an error" });
          return [];
        }
        return griotRows(result).map((row) => ({ ...row, _lane: arm.lane }));
      } catch (err) {
        failures.push({ lane: arm.lane, error: String(err?.message || err).slice(0, 200) });
        return [];
      }
    }));
    const byKey = /* @__PURE__ */ new Map();
    for (const row of gathered.flat()) {
      const key = griotKey(row);
      if (!byKey.has(key)) byKey.set(key, row);
    }
    const all = [...byKey.values()];
    let kept = all;
    let heldBack = 0;
    if (bounded) {
      kept = all.filter((row) => griotInEra(row, since, until));
      heldBack = all.length - kept.length;
    }
    kept.sort((a, b) => String(a.timestamp || "\uFFFF").localeCompare(String(b.timestamp || "\uFFFF")));
    const shown = kept.slice(0, limit);
    const packet = {
      question,
      shown: shown.length,
      total: all.length,
      held_back: heldBack,
      failures,
      memories: shown.map((row) => ({
        id: row.id,
        db: row._db_index ?? row.db ?? null,
        era: griotEra(row) || "era unknown",
        title: row.title || "(untitled)",
        source: row.source ?? String(row._db_index ?? "?"),
        flags: griotFlags(row)
      }))
    };
    if (bounded) packet.era_bounds = { since: since || null, until: until || null };
    const span = bounded ? ` (${since || "\u2026"} \u2192 ${until || "\u2026"})` : "";
    const lines = [`**${shown.length} memories**${span}, oldest first \u2014 you are the teller.`];
    if (heldBack) {
      lines.push(`${heldBack} held back: outside the era, or undated and so not provable inside it. An undated memory is not evidence for a bounded question.`);
    }
    if (failures.length) {
      lines.push(`\u26A0\uFE0F ${failures.length} arm(s) did not answer: ` + failures.map((f) => `${f.lane} (${f.error})`).join("; ") + " \u2014 this packet is incomplete, say so when you narrate it.");
    }
    if (!shown.length) {
      lines.push("", bounded ? "Nothing in that era reached this node. That may be a real gap or a partial mount \u2014 check shards_coverage before calling it a silence." : "No memory matched. Try shards_coverage to see what this node holds.");
    }
    lines.push("");
    for (const m of packet.memories) {
      lines.push(`${m.era}  ${m.title}${m.flags.length ? "  " + m.flags.join(" ") : ""}`);
      lines.push(`        id ${m.id} \xB7 store ${m.source}`);
    }
    return text(truncate(lines.join("\n"), "lower the limit"), packet);
  },
  async shards_capture(args, env, keyId) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const tags = Array.isArray(args.tags) ? args.tags.slice() : [];
    const via = `via:${env.CONNECTOR_LANE}/${keyId}`;
    if (!tags.includes(via)) tags.push(via);
    const result = await shardCall(env, env.SHARD_TOOL_CAPTURE || "capture_experience", {
      title: args.title,
      content: args.content,
      event_type: args.event_type || "KNOWLEDGE",
      tags
    });
    const captured = result.structuredContent?.captured;
    return text(
      captured === false ? `\u21A9\uFE0F not stored \u2014 the node rejected this write: "${args.title}"` : `\u2705 stored: "${args.title}"
tags: ${tags.join(", ")}
(the node dedups by content \u2014 if this text was already in the grid, nothing was added and no duplicate was made)`,
      result.structuredContent ?? { captured }
    );
  },
  async shards_mark(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const payload = { shard_id: args.shard_id, worked: args.worked };
    if (args.db_index !== void 0) payload.db_index = args.db_index;
    const result = await shardCall(env, env.SHARD_TOOL_MARK || "mark_utility", payload);
    return text(
      `${args.worked ? "\u{1F44D}" : "\u{1F44E}"} shard ${args.shard_id} marked ${args.worked ? "useful" : "unhelpful"} \u2014 future recalls reweight`,
      result.structuredContent
    );
  },
  // The node returns list results as one content item per entry, not a single
  // JSON array (FastMCP behaviour, verified 2026-08-15) — so joining content
  // is the only way to see every row.
  async shards_amend(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const payload = { shard_id: args.shard_id, note: args.note };
    if (args.db_index !== void 0) payload.db_index = args.db_index;
    if (args.confirm_title) payload.confirm_title = args.confirm_title;
    const result = await shardCall(env, env.SHARD_TOOL_AMEND || "shard_amend", payload);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body);
    return text(
      `\u{1F4DD} amended shard ${args.shard_id} \u2014 note appended under today's date
${body}`,
      result.structuredContent
    );
  },
  async shards_retract(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const payload = { shard_id: args.shard_id, reason: args.reason };
    if (args.db_index !== void 0) payload.db_index = args.db_index;
    if (args.confirm_title) payload.confirm_title = args.confirm_title;
    const result = await shardCall(env, env.SHARD_TOOL_RETRACT || "shard_retract", payload);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body);
    return text(
      `\u{1F6AB} retracted shard ${args.shard_id} \u2014 kept in the grid, demoted out of recall
${body}`,
      result.structuredContent
    );
  },
  async shards_forget(args, env, keyId) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const payload = { shard_id: args.shard_id, confirm_title: args.confirm_title };
    if (args.db_index !== void 0) payload.db_index = args.db_index;
    const result = await shardCall(env, env.SHARD_TOOL_FORGET || "shard_forget", payload);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body);
    return text(
      `\u{1F525} shard ${args.shard_id} permanently deleted by ${keyId} \u2014 irreversible
${body}`,
      result.structuredContent
    );
  },
  async vault_put(args, env, keyId) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(
      env,
      env.SHARD_TOOL_VAULT_PUT || "vault_put",
      { key: args.key, value: args.value }
    );
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body);
    let fp = "";
    try {
      fp = JSON.parse(body).fingerprint || "";
    } catch {
    }
    return text(
      `\u{1F510} vault key "${args.key}" written by ${keyId}
` + (fp ? `fingerprint: ${fp}  (compare this to your source \u2014 the value is never echoed)` : body),
      result.structuredContent
    );
  },
  async vault_list(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, env.SHARD_TOOL_VAULT_LIST || "vault_list", {});
    const entries = (result.content || []).map((c) => {
      try {
        return JSON.parse(c.text || "{}");
      } catch {
        return null;
      }
    }).filter(Boolean);
    if (!entries.length) return text("(vault empty, or the node exposes no vault listing)");
    const lines = [`\u{1F510} ${entries.length} secret(s) \u2014 names and fingerprints only, no values:`, ""];
    for (const e of entries) {
      lines.push(`- \`${e.key}\` \xB7 fp ${e.fingerprint || "?"} \xB7 rotated ${e.last_rotated || "?"}`);
    }
    return text(truncate(lines.join("\n"), "too many secrets to list"), { secrets: entries });
  }
};
async function handleRpc(msg, env, keyId) {
  const { id, method, params } = msg;
  const reply = /* @__PURE__ */ __name((result) => ({ jsonrpc: "2.0", id, result }), "reply");
  const fail = /* @__PURE__ */ __name((code, message) => ({ jsonrpc: "2.0", id, error: { code, message } }), "fail");
  if (method === "initialize") {
    const requested = params?.protocolVersion;
    return reply({
      protocolVersion: PROTOCOL_VERSIONS.includes(requested) ? requested : PROTOCOL_VERSIONS[0],
      capabilities: { tools: {} },
      serverInfo: SERVER_INFO,
      instructions: "NouGen fleet connector. fleet_whoami shows what is reachable; relay_* is the handoff baton, tracker_* is usage dailies, shards_* is fleet memory (needs blade's gateway online)."
    });
  }
  if (method === "ping") return reply({});
  if (method === "tools/list") return reply({ tools: TOOLS });
  if (method === "tools/call") {
    const handler = HANDLERS[params?.name];
    if (!handler) return fail(-32602, `unknown tool: ${params?.name}`);
    try {
      return reply(await handler(params.arguments || {}, env, keyId));
    } catch (err) {
      return reply(toolError(err.message || String(err)));
    }
  }
  if (method && method.startsWith("notifications/")) return null;
  return fail(-32601, `method not found: ${method}`);
}
__name(handleRpc, "handleRpc");
async function handleMcp(request, env, origin) {
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "GET, POST, OPTIONS",
        "access-control-allow-headers": "authorization, content-type, x-ngs-token",
        "access-control-max-age": "86400"
      }
    });
  }
  if (request.method === "GET") {
    return json({
      name: SERVER_INFO.name,
      version: SERVER_INFO.version,
      status: "ready",
      transport: "streamable-http",
      endpoint: origin + MCP_PATH,
      protocolVersions: PROTOCOL_VERSIONS
    }, 200, {
      "access-control-allow-origin": "*"
    });
  }
  const keyId = await authenticate(request, env);
  if (!keyId) {
    return json({ error: "unauthorized" }, 401, {
      "www-authenticate": `Bearer realm="nougen-fleet", resource_metadata="${origin}/.well-known/oauth-protected-resource"`
    });
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } }, 400);
  }
  const messages = Array.isArray(body) ? body : [body];
  const replies = (await Promise.all(messages.map((m) => handleRpc(m, env, keyId)))).filter((r) => r !== null);
  if (!replies.length) return new Response(null, { status: 202 });
  return json(Array.isArray(body) ? replies : replies[0]);
}
__name(handleMcp, "handleMcp");
var __test__ = { HANDLERS, TOOLS, griotRows, griotEra, griotInEra, griotFlags, griotKey };
function openapiSpec(origin) {
  return {
    openapi: "3.0.1",
    info: {
      title: "NouGen Fleet and Shards API",
      description: "NouGen Intelligence Shards and Fleet Memory Substrate API for ChatGPT, Claude, and Agentic Systems.",
      version: "1.0.0"
    },
    servers: [{ url: origin }],
    paths: {
      "/health": {
        get: {
          summary: "System Health and Coverage",
          description: "Returns health status, active shard count, and substrate mount status.",
          operationId: "getHealth",
          responses: {
            "200": {
              description: "Health status and aggregate metrics",
              content: { "application/json": { schema: { type: "object" } } }
            }
          }
        }
      },
      "/search": {
        post: {
          summary: "Memory Recall and Semantic Search",
          description: "Search across the NouGen Shard vault (200k+ shards) using BM25 and semantic filtering.",
          operationId: "searchShards",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    query: { type: "string", description: "Search query string" },
                    limit: { type: "integer", default: 10, description: "Maximum number of shards to return" },
                    since: { type: "string", description: "ISO date prefix bound (e.g. 2026-01)" },
                    until: { type: "string", description: "ISO date prefix bound" }
                  },
                  required: ["query"]
                }
              }
            }
          },
          responses: {
            "200": {
              description: "Matching shard objects",
              content: { "application/json": { schema: { type: "object" } } }
            }
          }
        }
      },
      "/v1/chat/completions": {
        post: {
          summary: "Fleet Inference / Chat Completions",
          description: "OpenAI-compatible chat completions route calling resident reasoning models.",
          operationId: "chatCompletions",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    model: { type: "string" },
                    messages: {
                      type: "array",
                      items: {
                        type: "object",
                        properties: {
                          role: { type: "string" },
                          content: { type: "string" }
                        }
                      }
                    }
                  },
                  required: ["messages"]
                }
              }
            }
          },
          responses: {
            "200": {
              description: "Chat completion response",
              content: { "application/json": { schema: { type: "object" } } }
            }
          }
        }
      }
    }
  };
}
__name(openapiSpec, "openapiSpec");

var worker_default = {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = url.origin;
    const path = url.pathname.replace(/\/$/, "") || "/";
    switch (path) {
      case "/":
        return new Response(
          "\u{1F6F0}\uFE0F nougen-fleet-mcp \u2014 add " + origin + MCP_PATH + " as a claude.ai custom connector\n",
          { headers: { "content-type": "text/plain; charset=utf-8" } }
        );
      case "/.well-known/oauth-authorization-server":
        return json(oauthMetadata(origin));
      case "/.well-known/oauth-protected-resource":
      case "/.well-known/oauth-protected-resource" + MCP_PATH:
        return json(resourceMetadata(origin));
      case "/register":
        return request.method === "POST" ? handleRegister(request, env) : new Response("POST only", { status: 405 });
      case "/authorize":
        return handleAuthorize(request, env, url);
      case "/google/start":
        return handleGoogleStart(request, env, url);
      case "/google/callback":
        return handleGoogleCallback(request, env, url);
      case "/token":
        return request.method === "POST" ? handleToken(request, env) : new Response("POST only", { status: 405 });
      case MCP_PATH:
        return handleMcp(request, env, origin);
      case "/openapi.json":
        return json(openapiSpec(origin), 200, { "access-control-allow-origin": "*" });
      case "/docs":
      case "/api-docs":
        return new Response(`<!doctype html>
<html><head><meta charset="utf-8"><title>NouGen API Docs</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head><body><div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({ url: '${origin}/openapi.json', dom_id: '#swagger-ui' });</script>
</body></html>`, { headers: { "content-type": "text/html; charset=utf-8", "access-control-allow-origin": "*" } });
      default:
        return new Response("not found", { status: 404 });
    }
  }
};
export {
  __test__,
  worker_default as default
};
//# sourceMappingURL=worker.js.map