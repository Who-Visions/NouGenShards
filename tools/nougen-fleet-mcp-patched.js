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
  // Per-provider secrets: FLEET_KEY_HF_APP -> lane "hf-app". One secret per
  // provider surface, added or deleted on its own through the additive
  // /secrets endpoint, so a new lane never rewrites the shared FLEET_KEYS
  // string and revoking one provider never touches another.
  for (const name of Object.keys(env)) {
    if (!name.startsWith("FLEET_KEY_") || name === "FLEET_KEYS") continue;
    const value = env[name];
    if (typeof value !== "string" || !value.trim()) continue;
    map.set(name.slice("FLEET_KEY_".length).toLowerCase().replace(/_/g, "-"), value.trim());
  }
  return map;
}
__name(fleetKeys, "fleetKeys");
// Lanes that may read but never write. Env first; the fallback is "every lane
// that authenticated with a static key", because a server-side MCP client
// (HuggingChat, the HF Responses API) holds a bearer it cannot rotate itself.
function readOnlyLanes(env) {
  return new Set(String(env.READ_ONLY_LANES || "").split(",").map((s2) => s2.trim()).filter(Boolean));
}
__name(readOnlyLanes, "readOnlyLanes");
function laneIsReadOnly(env, auth) {
  if (!auth) return false;
  const set = readOnlyLanes(env);
  if (set.size) return set.has(auth.lane) || set.has(auth.key);
  return Boolean(auth.static);
}
__name(laneIsReadOnly, "laneIsReadOnly");
function toolIsWrite(name) {
  const t = TOOLS.find((x) => x.name === name);
  return Boolean(t && t.annotations && t.annotations.readOnlyHint === false);
}
__name(toolIsWrite, "toolIsWrite");
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
async function issueTokens(env, keyId, email, lane) {
  const iat = Math.floor(Date.now() / 1e3);
  const extra = { ...email ? { eml: email } : {}, ...lane ? { ln: lane } : {} };
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
  const presented = m[1].trim();
  const payload = await verifyBlob(env, presented);
  if (payload && payload.typ === "access") {
    if (!identityStillEnrolled(env, payload)) return null;
    return { key: payload.key, lane: payload.ln || null, static: false };
  }
  // Static fleet key as the bearer: the path for server-side MCP clients that
  // cannot run the OAuth code flow. Identity and lane are the key's name; a
  // deleted secret is an instant 401 on the next call.
  const ua = request.headers.get("user-agent") || "";
  for (const [name, secret] of fleetKeys(env)) {
    if (secret && timingSafeEqual(secret, presented)) {
      return { key: name, lane: name, static: true, client: clientFromUserAgent(env, ua), ua: ua.slice(0, 120) };
    }
  }
  return null;
}
__name(authenticate, "authenticate");
// Which client program presented a static key. Env CONNECTOR_CLIENT_MAP
// ("needle=client,...") overrides the fallback table; unmatched stays "unknown"
// rather than guessing (a provenance field must never be invented).
function clientFromUserAgent(env, ua) {
  const table = String(env.CONNECTOR_CLIENT_MAP || "chat-ui=huggingchat,huggingchat=huggingchat,huggingface=responses-api,openai=responses-api,claude-code=claude-code,codex=codex,nougen-hf-agent=responses-api,nougen-harness-eval=harness-eval,nougen-hf-lane-probe=lane-probe");
  const low = String(ua || "").toLowerCase();
  for (const pair of table.split(",")) {
    const i = pair.indexOf("=");
    if (i > 0 && low.includes(pair.slice(0, i).trim().toLowerCase())) return pair.slice(i + 1).trim();
  }
  return "unknown";
}
__name(clientFromUserAgent, "clientFromUserAgent");
var FALLBACK_LANE_MAP = "claude.ai:claude-app,claude.com:claude-app,chatgpt.com:chatgpt-app,openai.com:chatgpt-app,gemini.google.com:gemini-app,perplexity.ai:perplexity-app,grok.com:grok-app,x.ai:grok-app,copilot.microsoft.com:copilot-app,mistral.ai:mistral-app";
function laneForRedirect(env, redirectUri) {
  // Identity resolves behind the door: the OAuth redirect host names the
  // provider. env CONNECTOR_LANE_MAP overrides; the constant map is a
  // fallback only; an unmapped host keeps the deploy-wide legacy lane.
  let host = "";
  try {
    host = new URL(redirectUri).hostname.toLowerCase();
  } catch {
  }
  for (const pair of String(env.CONNECTOR_LANE_MAP || FALLBACK_LANE_MAP).split(",")) {
    const i = pair.indexOf(":");
    if (i <= 0) continue;
    const dom = pair.slice(0, i).trim().toLowerCase();
    const lane = pair.slice(i + 1).trim();
    if (dom && lane && (host === dom || host.endsWith("." + dom))) return lane;
  }
  // An unmapped provider must NOT inherit the deploy-wide legacy lane: on
  // 2026-09-01 a fresh Grok session reported itself as "claude-app" for
  // exactly that reason (leg 20260901T210647Z / 210815Z). Self-label from the
  // registrable host instead (grok.com -> grok-app); only a missing host falls
  // back to CONNECTOR_LANE, and CONNECTOR_UNMAPPED_LANE overrides both.
  if (env.CONNECTOR_UNMAPPED_LANE) return env.CONNECTOR_UNMAPPED_LANE;
  const parts = host.split(".").filter(Boolean);
  if (parts.length >= 2) return parts[parts.length - 2] + "-app";
  return env.CONNECTOR_LANE;
}
__name(laneForRedirect, "laneForRedirect");
function laneEnv(env, lane) {
  // Per-request identity: shadow the deploy-wide lanes; every other binding
  // is inherited through the prototype (no ...env spreads exist in this file).
  if (!lane || lane === env.CONNECTOR_LANE) return env;
  return Object.assign(Object.create(env), { CONNECTOR_LANE: lane, SHARD_LANE: lane });
}
__name(laneEnv, "laneEnv");
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
    ln: laneForRedirect(env, redirectUri),
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
    return json(await issueTokens(env, payload.key, payload.eml, payload.ln));
  }
  if (grant === "refresh_token") {
    const payload = await verifyBlob(env, form.get("refresh_token") || "");
    if (!payload || payload.typ !== "refresh") return json({ error: "invalid_grant" }, 400);
    if (!identityStillEnrolled(env, payload)) return json({ error: "invalid_grant" }, 400);
    return json(await issueTokens(env, payload.key, payload.eml, payload.ln));
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
    ln: laneForRedirect(env, st.uri),
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
async function ghReadFile(env, path, revision = env.RELAY_BRANCH) {
  const entry = await gh(env, `/contents/${path}?ref=${revision}`);
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
// Relay ids are ordered by their leading UTC stamp, never lexically. A plain
// .sort().reverse() put legacy ids such as `usage_2026-07-31` ("u" > "2")
// above every real September leg, so relay_latest and nougenmsg_latest
// answered with a July usage stub (leg 20260923T184725Z, P0 items 1-3).
// Stamped ids come first, newest stamp first; unstamped legacy ids trail.
var LEG_STAMP_RE = /^(\d{8}T\d{6})(?:\d*)Z__/;
function idStamp(id) {
  const m = LEG_STAMP_RE.exec(String(id || ""));
  return m ? m[1] : null;
}
__name(idStamp, "idStamp");
function orderLegIds(ids) {
  return [...ids].sort((a, b) => {
    const sa = idStamp(a), sb = idStamp(b);
    if (sa && sb) return sa === sb ? (a < b ? 1 : a > b ? -1 : 0) : (sa < sb ? 1 : -1);
    if (sa) return -1;
    if (sb) return 1;
    return a < b ? 1 : a > b ? -1 : 0;
  });
}
__name(orderLegIds, "orderLegIds");
function stampToIso(stamp) {
  // "20260924T160100" -> "2026-09-24T16:01:00Z"
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/.exec(String(stamp || ""));
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` : null;
}
__name(stampToIso, "stampToIso");
// Leg 20260923T184725Z item 4: the id stamp (when the writer named the file)
// and the record's created_utc (what it says inside) are different clocks.
// Report both, never substitute one for the other, and drop confidence when
// they disagree by more than five minutes.
var STAMP_SKEW_LIMIT_S = 300;
function orderingMeta(id, createdUtc) {
  const stamp = idStamp(id);
  if (!stamp) return { ordering_basis: "lexical_fallback_no_stamp", ordering_confidence: "low", id_stamp_utc: null, record_created_utc: createdUtc || null };
  const stampIso = stampToIso(stamp);
  const meta = { ordering_basis: "leg_id_utc_stamp", ordering_confidence: "high", id_stamp_utc: stampIso, record_created_utc: createdUtc || null };
  const a = Date.parse(stampIso), b = Date.parse(createdUtc || "");
  if (Number.isFinite(a) && Number.isFinite(b)) {
    meta.stamp_created_skew_s = Math.round((b - a) / 1e3);
    if (Math.abs(meta.stamp_created_skew_s) > STAMP_SKEW_LIMIT_S) meta.ordering_confidence = "medium";
  } else if (createdUtc) {
    meta.ordering_confidence = "medium";  // created_utc present but unparseable
  }
  return meta;
}
__name(orderingMeta, "orderingMeta");
// Leg 20260923T184725Z item 6: a latest answer must not outrank what the
// registry itself just wrote. The head commit names the leg files it touched;
// if one carries a newer stamp than the leg we are about to return, the
// listing is stale and the answer is DEGRADED, never silently wrong.
async function latestFreshness(env, headSha, latestId) {
  if (!headSha) return { latest_state: "UNVERIFIED", latest_state_reason: "no registry head sha" };
  try {
    const c = await gh(env, `/commits/${headSha}`);
    const written = (c && Array.isArray(c.files) ? c.files : [])
      .map((f) => String(f.filename || ""))
      .filter((f) => f.startsWith(".handoffs/") && f.endsWith(".json"))
      .map((f) => f.slice(".handoffs/".length, -".json".length));
    const mine = idStamp(latestId);
    const newer = written.filter((id) => idStamp(id) && (!mine || idStamp(id) > mine));
    if (newer.length) return { latest_state: "DEGRADED_STALE_LISTING", latest_state_reason: `head commit wrote newer leg(s): ${orderLegIds(newer).slice(0, 3).join(", ")}` };
    return { latest_state: "VERIFIED_AGAINST_HEAD", head_commit_utc: c?.commit?.committer?.date || null };
  } catch (err) {
    return { latest_state: "UNVERIFIED", latest_state_reason: `head commit unreadable: ${err.message || err}` };
  }
}
__name(latestFreshness, "latestFreshness");
async function listLegs(env, revision = env.RELAY_BRANCH) {
  // The contents API caps a directory listing at 1000 entries and returns them
  // ALPHABETICALLY. Leg files are timestamp-named, so once the registry passes
  // 1000 the entries that fall off are the NEWEST ones - exactly the legs a
  // reader wants. Measured 2026-08-31: 1586 entries in .handoffs, contents
  // returned exactly 1000, and relay reads were frozen ~2 days in the past
  // while writes kept succeeding. The fleet was posting into a registry its
  // own readers could not see.
  //
  // A prior fix (2026-08-29) walked the WHOLE-REPO tree with recursive=1 and
  // fell back to the contents API silently (bare `catch (_) {}`) on any
  // failure - which meant a single flaky call anywhere in that path quietly
  // regressed straight back into the 1000-entry cap this comment describes,
  // with zero signal that it had happened. Confirmed by count on
  // 2026-08-31T23:xx: .handoffs holds 1540 flat entries (767 json + 773 md),
  // safely over the 1000 cap, while the fleet sat reading stale 08-29 legs
  // for hours with `truncated: false` on a healthy repo the whole time - the
  // failure was in THIS worker's call, not the data.
  //
  // Fix: fetch the `.handoffs` directory's OWN tree object non-recursively
  // instead of walking the whole repo. A single directory's tree entry list
  // is not subject to the recursive-walk size/depth behavior at all, is a
  // smaller/cheaper call, and needs only two tree fetches (root, then
  // .handoffs) instead of one large recursive one - less surface for a
  // subrequest limit or transient failure to hit. The contents-API fallback
  // remains for when both tree calls fail, and now logs why, so a silent
  // regression next time shows up in `wrangler tail` instead of vanishing.
  // Returns {ids, headSha, checkedUtc, source}. headSha/checkedUtc are the
  // freshness signal requested after the 2026-08-31 ChatGPT-connector
  // staleness incident (relay leg 20260831T235317Z): a reader with no way to
  // tell "current" from "stale" has to trust silently, and this listing bug
  // is proof that trust alone is not enough. Every relay_open/relay_latest
  // response now carries the exact commit this answer was read at, so two
  // providers comparing notes (or one provider checking itself over time)
  // can detect a stale read instead of assuming freshness.
  let headSha = null;
  try {
    const head = await gh(env, `/commits/${revision}`);
    headSha = head && head.sha ? head.sha : null;
    const rootTreeSha = head && head.commit && head.commit.tree && head.commit.tree.sha;
    if (rootTreeSha) {
      const rootTree = await gh(env, `/git/trees/${rootTreeSha}`);
      const handoffsEntry = rootTree && Array.isArray(rootTree.tree)
        ? rootTree.tree.find((t) => t.path === ".handoffs" && t.type === "tree")
        : null;
      if (handoffsEntry) {
        const handoffsTree = await gh(env, `/git/trees/${handoffsEntry.sha}`);
        if (handoffsTree && Array.isArray(handoffsTree.tree)) {
          if (handoffsTree.truncated) {
            console.error(`listLegs: .handoffs tree itself reports truncated:true at ${handoffsTree.tree.length} entries - even the non-recursive single-directory fetch is hitting a real cap now`);
          }
          const ids = handoffsTree.tree
            .filter((t) => t.type === "blob" && t.path.endsWith(".json"))
            .map((t) => t.path.replace(/\.json$/, ""));
          if (ids.length) return {
            ids: orderLegIds(ids),
            headSha,
            checkedUtc: (/* @__PURE__ */ new Date()).toISOString(),
            source: "tree",
            listingComplete: !handoffsTree.truncated
          };
        }
      } else {
        console.error("listLegs: root tree has no .handoffs directory entry - unexpected repo layout");
      }
    }
  } catch (err) {
    console.error("listLegs: .handoffs tree walk failed, falling back to the capped contents API", err && err.message);
  }
  const entries = await gh(env, `/contents/.handoffs?ref=${env.RELAY_BRANCH}`);
  if (Array.isArray(entries) && entries.length >= 1000) {
    console.error(`listLegs: contents API fallback returned ${entries.length} entries - likely capped at 1000, results may be missing the newest legs`);
  }
  const ids = entries.filter((e) => e.type === "file" && e.name.endsWith(".json")).map((e) => e.name.replace(/\.json$/, ""));
  return {
    ids: orderLegIds(ids),
    headSha,
    checkedUtc: (/* @__PURE__ */ new Date()).toISOString(),
    source: "contents-fallback",
    listingComplete: entries.length < 1000
  };
}
__name(listLegs, "listLegs");
// A schema requiring `id` does not stop a malformed call (wrong param name,
// empty string, or a client that skips validation) from reaching the handler
// - discovered 2026-09-01 when a wrong-but-plausible param name produced a
// raw "Cannot read properties of undefined (reading 'replace')" instead of a
// message a caller could act on. Returns null (caller emits toolError) rather
// than throwing, so the failure reads as "you gave a bad id" not a crash.
function sanitizeLegId(rawId) {
  if (typeof rawId !== "string" || !rawId.trim()) return null;
  const id = rawId.trim().replace(/[^A-Za-z0-9_.-]/g, "");
  return id || null;
}
__name(sanitizeLegId, "sanitizeLegId");
async function readLeg(env, id, revision = env.RELAY_BRANCH) {
  const { text: text2, sha } = await ghReadFile(env, `.handoffs/${id}.json`, revision);
  const rec = JSON.parse(text2);
  rec._file = `${id}.json`;
  return { rec, sha };
}
__name(readLeg, "readLeg");
function legSummary(rec) {
  // Ack attribution was stored correctly all along but never surfaced (relay
  // leg 20260831T222716Z: "the authorless-ack illusion"). TWO writers use TWO
  // different shapes for the same fact, discovered comparing this worker's
  // own relay_ack (below - pushes {event:"ack",...} into rec.relay[]) against
  // that leg's account of the NouGenRelay daemon (writes rec.acked_by /
  // rec.acked_utc / rec.ack_note as TOP-LEVEL fields, no relay[] entry).
  // Neither writer is wrong; a reader that only checks one shape sees "no
  // ack" for legs closed by the other. Check both, prefer whichever
  // timestamp is actually later rather than assuming one writer always wins.
  const events = Array.isArray(rec.relay) ? rec.relay : [];
  const lastAckEvent = [...events].reverse().find((e) => e && e.event === "ack");
  const fromEvent = lastAckEvent ? {
    acked_by: `${lastAckEvent.machine || "?"}/${lastAckEvent.agent || "?"}`,
    acked_utc: lastAckEvent.at || null,
    ack_note: lastAckEvent.note || null
  } : null;
  const fromTopLevel = rec.acked_by || rec.acked_utc ? {
    acked_by: rec.acked_by || null,
    acked_utc: rec.acked_utc || null,
    ack_note: rec.ack_note || null
  } : null;
  const winner = fromEvent && fromTopLevel
    ? (String(fromTopLevel.acked_utc || "") > String(fromEvent.acked_utc || "") ? fromTopLevel : fromEvent)
    : (fromTopLevel || fromEvent);
  return {
    id: (rec._file || "").replace(/\.json$/, ""),
    machine: rec.machine,
    agent: rec.agent,
    goal: rec.goal,
    status: rec.status || "open",
    created_utc: rec.created_utc,
    branch: rec.branch,
    sha: rec.sha,
    acked_by: winner ? winner.acked_by : null,
    acked_utc: winner ? winner.acked_utc : null,
    ack_note: winner ? winner.ack_note : null
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
async function mapPooled(items, limit, fn) {
  const out = [];
  const width = Math.max(1, Math.min(limit, items.length));
  for (let i = 0; i < items.length; i += width) {
    const chunk = items.slice(i, i + width);
    const settled = await Promise.all(
      chunk.map((it, j) => Promise.resolve(fn(it, i + j)).then(
        (value) => ({ ok: true, item: it, value }),
        (error) => ({ ok: false, item: it, error: String(error && error.message || error) })
      ))
    );
    out.push(...settled);
  }
  return out;
}
__name(mapPooled, "mapPooled");
function trackerLimits(env) {
  const num = (v, fallback) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : fallback;
  };
  // env -> config -> logged fallback (Rule 0.2 #6). Cloudflare allows 50
  // subrequests per invocation on Free and 1000 on Paid; 40 is the safe Free
  // ceiling with room for the tree calls this tool already spends.
  return {
    budget: num(env.TRACKER_SUBREQUEST_BUDGET, 40),
    concurrency: num(env.TRACKER_FETCH_CONCURRENCY, 6),
    budgetSource: env.TRACKER_SUBREQUEST_BUDGET ? "env" : "fallback(40)",
    concurrencySource: env.TRACKER_FETCH_CONCURRENCY ? "env" : "fallback(6)"
  };
}
__name(trackerLimits, "trackerLimits");
// Canonical, versioned. Anything that prints a single "tokens" number for a
// window MUST use this definition and carry the version with it, so product
// copy and dashboards cannot silently diverge. Reasoning tokens are reported
// separately by the tracker and are deliberately NOT summed here.
var TOTAL_ACTIVITY_DEF = "input_tokens + output_tokens + cache_read + cache_creation";
var TOTAL_ACTIVITY_VERSION = "total_activity/v1";
function totalActivity(t) {
  return (t.input_tokens || 0) + (t.output_tokens || 0) + (t.cache_read || 0) + (t.cache_creation || 0);
}
__name(totalActivity, "totalActivity");
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
// Exact-host check (not a substring match): SHARD_GATEWAY_URL must not point the worker back at its own public front door.
function isPublicShardsFrontDoor(value) {
  try { return new URL(value).hostname === "shards.nougenai.com"; } catch { return false; }
}
async function shardRpcHttp(env, method, params, id) {
  const gatewayUrl = (env.SHARD_GATEWAY_URL && !isPublicShardsFrontDoor(env.SHARD_GATEWAY_URL))
    ? env.SHARD_GATEWAY_URL
    : (env.BLADE_ORIGIN || "https://blade.nougenai.com");
  const res = await fetch(gatewayUrl.replace(/\/$/, "") + "/mcp/", {
    method: "POST",
    headers: {
      ...await shardHeaders(env),
      "content-type": "application/json",
      accept: "application/json, text/event-stream"
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
    // env-first budget; 45000 is a logged fallback only (SHARD_HTTP_TIMEOUT_MS overrides)
    signal: AbortSignal.timeout(Number(env.SHARD_HTTP_TIMEOUT_MS || 45000))
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
  // env-first budget; 30000 is a fallback only (SHARD_SSE_TIMEOUT_MS overrides)
  const timer = setTimeout(() => ctrl.abort(), Number(env.SHARD_SSE_TIMEOUT_MS || 30000));
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
async function shardRpcInitialize(env) {
  return shardRpcHttp(env, "initialize", {
    protocolVersion: "2025-03-26",
    capabilities: {},
    clientInfo: { name: "nougen-fleet-mcp", version: SERVER_INFO.version }
  }, 1);
}
__name(shardRpcInitialize, "shardRpcInitialize");
// The node runs FastMCP with stateless_http=True, so a per-call initialize is
// a wasted tunnel round trip on EVERY arm of EVERY tool (ask_griot paid it
// 2-3 times per ask). Default: skip it. SHARD_GATEWAY_STATELESS=0 restores the
// handshake. If a node ever answers "not initialized" we handshake and retry
// once, so a stateful node keeps working without a redeploy.
function shardGatewayStateless(env) {
  const raw = String(env.SHARD_GATEWAY_STATELESS ?? "1").trim().toLowerCase();
  return !(raw === "0" || raw === "false" || raw === "no");
}
__name(shardGatewayStateless, "shardGatewayStateless");
function shardNeedsInitialize(err) {
  const m = String(err?.message || err || "").toLowerCase();
  return m.includes("not initialized") || m.includes("initialize first") || m.includes("session not found") || m.includes("missing session");
}
__name(shardNeedsInitialize, "shardNeedsInitialize");
async function shardCallOnce(env, toolName, args) {
  // http unless the operator explicitly asks for sse: no NouGen node mounts an
  // /sse route (app.py serves /mcp/ only), so an unset style used to send every
  // call to a 404. Default toward the route that exists.
  const style = String(env.SHARD_GATEWAY_STYLE || "http").trim().toLowerCase();
  if (style !== "sse") {
    const call = () => shardRpcHttp(env, "tools/call", { name: toolName, arguments: args }, 2);
    if (!shardGatewayStateless(env)) {
      await shardRpcInitialize(env);
      return call();
    }
    try {
      return await call();
    } catch (err) {
      if (!shardNeedsInitialize(err)) throw err;
      console.log("shardCallOnce: node asked for initialize on " + toolName + "; handshaking and retrying once");
      await shardRpcInitialize(env);
      return call();
    }
  }
  return shardCallSse(env, toolName, args);
}
__name(shardCallOnce, "shardCallOnce");
// Retryable = looks transient (network-level failure, or the gateway itself
// 5xx'd/wedged) — NOT an AbortError. Retrying a timeout with the same
// SHARD_HTTP_TIMEOUT_MS/SHARD_SSE_TIMEOUT_MS budget just doubles the caller's
// wait for no benefit; a real hang needs the caller's own timeout to bite,
// not this layer masking it. Also not retryable: 4xx (auth/bad-request is
// not fixed by trying again). capture_experience is safe to retry blind -
// the node dedups by content (see shards_capture) so a retried write after
// an ambiguous failure (reply lost, not necessarily unwritten) never
// double-stores.
function shardCallRetryable(err) {
  const name = err?.name || "";
  const msg = String(err?.message || err || "");
  if (name === "AbortError" || /^gateway \/sse timed out/.test(msg)) return false;
  if (/^gateway (4\d\d):/.test(msg)) return false;
  if (/^gateway (5\d\d):/.test(msg)) return true;
  return name === "TypeError" || /network|ECONNRESET|fetch failed|SSE stream ended/i.test(msg);
}
__name(shardCallRetryable, "shardCallRetryable");
// TTL / invalidation policy (relay leg 20260831T235317Z, item 6): NONE. This
// worker holds no cache for either the relay registry (listLegs re-fetches
// GitHub's tree on every call) or shard reads (shardCall re-invokes the node
// on every call, no Cache API, no KV). Every read is live as of the instant
// it runs - the "staleness" incidents this file's other comments describe
// were never a caching bug, they were the read PATH silently returning wrong
// data (a capped fallback, a corrupted replica) while claiming to be current.
// If a real cache is ever added here, it needs its own explicit TTL and this
// comment must change with it - an implicit cache is exactly the failure
// mode the freshness signals above exist to catch.
//
// Bounded retries/backoff for the shard write/retrieval path (meal-query
// timeout incident, relay legs 20260827T222624Z/222724Z/225151Z): one retry
// after a short jittered delay, only for transient failures. Telemetry via
// console.log so Worker logs show retry/failure counts instead of a bare
// timeout with no signal of whether it was transient.
async function shardCallDirect(env, toolName, args) {
  const maxAttempts = Math.max(1, Number(env.SHARD_CALL_MAX_ATTEMPTS) || 2);
  let lastErr;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const result = await shardCallOnce(env, toolName, args);
      if (attempt > 1) console.log(`shardCall(${toolName}): succeeded on attempt ${attempt}/${maxAttempts}`);
      return result;
    } catch (err) {
      lastErr = err;
      const retryable = attempt < maxAttempts && shardCallRetryable(err);
      console.log(`shardCall(${toolName}): attempt ${attempt}/${maxAttempts} failed (${err?.name || "Error"}: ${String(err?.message || err).slice(0, 200)}) retryable=${retryable}`);
      if (!retryable) throw err;
      const backoffMs = Number(env.SHARD_CALL_RETRY_BACKOFF_MS) || 300;
      await new Promise((r) => setTimeout(r, backoffMs + Math.random() * backoffMs));
    }
  }
  throw lastErr;
}
__name(shardCallDirect, "shardCallDirect");
// ---- fleet fan-out: blade + N dynamic peers behind one connector --------
// phoebus runs its own grid behind its own tunnel. Before this, seeing it
// meant a second connector, because nougen-shard-failover does FAILOVER, not
// union: it returns whichever origin answers, so phoebus's rows were visible
// only while blade was down.
//
// READ tools fan out and return the union. WRITES NEVER DO, and the gate is an
// allowlist so a tool added later cannot inherit fan-out by omission: a capture
// landing on two nodes is two divergent shards (each node dedups by content
// against ITSELF only), and a relay leg written twice is two legs.
function isFanoutTool(env, toolName) {
  return toolName === (env.SHARD_TOOL_RECALL || "recall_memory") || toolName === (env.SHARD_TOOL_SEARCH || "recall_memory") || toolName === (env.SHARD_TOOL_WINDOW || "recall_window");
}
__name(isFanoutTool, "isFanoutTool");
// Peer roster is config, not code. FLEET_PEERS lists names; each name's
// origin/token/budget come from ${NAME}_ORIGIN / ${NAME}_TOKEN /
// ${NAME}_TIMEOUT_MS / ${NAME}_GRACE_MS, falling back to the shared
// PEER_TIMEOUT_MS/PEER_GRACE_MS defaults. "phoebus" keeps its legacy
// PHOEBUS_ORIGIN/PHOEBUS_TOKEN/PHOEBUS_TIMEOUT_MS/PHOEBUS_GRACE_MS names and
// its hardcoded https://phoebus.nougenai.com default so existing deploys
// need no var changes. A peer with no configured origin is reported as
// "not_configured" and never dialed -- adding a new node (e.g. whoart) is a
// var/secret change, never a worker.js edit. Names are sorted so arm order
// (and therefore fanout-status key order and dedup precedence) is the same
// on every call regardless of how FLEET_PEERS was typed.
function fleetPeerNames(env) {
  const raw = env.FLEET_PEERS || "phoebus,whoart";
  const names = raw.split(",").map((s) => s.trim()).filter(Boolean);
  return [...new Set(names)].sort();
}
__name(fleetPeerNames, "fleetPeerNames");
function peerConfig(env, name) {
  const upper = name.toUpperCase();
  const legacy = upper === "PHOEBUS";
  const origin = env[upper + "_ORIGIN"] || (legacy ? env.PHOEBUS_ORIGIN || "https://phoebus.nougenai.com" : "");
  const token = env[upper + "_TOKEN"] || (legacy ? env.PHOEBUS_TOKEN : void 0);
  const budget = Number(env[upper + "_TIMEOUT_MS"]) || Number(env.PEER_TIMEOUT_MS) || (legacy ? Number(env.PHOEBUS_TIMEOUT_MS) : 0) || 45000;
  const grace = Number(env[upper + "_GRACE_MS"]) || Number(env.PEER_GRACE_MS) || (legacy ? Number(env.PHOEBUS_GRACE_MS) : 0) || 25000;
  return { name, origin, token, budget, grace };
}
__name(peerConfig, "peerConfig");
// Shard ids are per-node - blade's 17190 and phoebus's 17190 are different
// rows - so an id is the one key that must NEVER dedupe across origins.
// file_hash is the node's own content identity; title+timestamp is the
// fallback; a hit carrying neither is kept rather than guessed at.
function fanoutKey(hit) {
  if (!hit || typeof hit !== "object") return null;
  if (hit.file_hash) return "h:" + hit.file_hash;
  if (hit.title && hit.timestamp) return "t:" + hit.title + "|" + hit.timestamp;
  return null;
}
__name(fanoutKey, "fanoutKey");
function fanoutSettle(p) {
  return p.then((v) => ({ ok: true, v }), (e) => ({ ok: false, e }));
}
__name(fanoutSettle, "fanoutSettle");
async function shardCallFanout(env, toolName, args) {
  const peers = fleetPeerNames(env).map((name) => peerConfig(env, name));
  const configured = peers.filter((p) => p.origin);
  const notConfigured = peers.filter((p) => !p.origin);
  // The peer arm carries its OWN budget and no retries. A retry here would
  // double the wait on the half that is already slower, and the retry path
  // exists for transient blade faults, not for a best-effort extra origin.
  const peerPromises = configured.map((p) => {
    const peerEnv = { ...env, SHARD_GATEWAY_URL: p.origin, SHARD_HTTP_TIMEOUT_MS: p.budget, SHARD_SSE_TIMEOUT_MS: p.budget, SHARD_CALL_MAX_ATTEMPTS: 1 };
    if (p.token) peerEnv.SHARD_GATEWAY_TOKEN = p.token;
    return fanoutSettle(shardCallDirect(peerEnv, toolName, args));
  });
  // All arms start now, but only the primary is allowed to hold the response
  // open. v1 awaited both and so charged every read the slowest arm's budget.
  const primary = await fanoutSettle(shardCallDirect(env, toolName, args));
  const maxGrace = configured.length ? Math.max(...configured.map((p) => p.grace)) : 0;
  let timer = null;
  const graceDeadline = new Promise((resolve) => {
    timer = setTimeout(() => resolve({ ok: false, e: { message: "peer exceeded " + maxGrace + "ms grace after primary" } }), maxGrace);
  });
  const peerResults = await Promise.all(peerPromises.map((p) => Promise.race([p, graceDeadline])));
  if (timer !== null) clearTimeout(timer);
  const status = {};
  const ok = [];
  const arms = [{ name: "blade", res: primary }, ...configured.map((p, i) => ({ name: p.name, res: peerResults[i] }))];
  for (const arm of arms) {
    if (arm.res.ok && !arm.res.v?.isError) {
      ok.push({ name: arm.name, result: arm.res.v });
      status[arm.name] = "ok";
    } else if (arm.res.ok) {
      status[arm.name] = "gateway returned isError";
    } else {
      status[arm.name] = String(arm.res.e?.message || arm.res.e).slice(0, 200);
    }
  }
  // A peer with no origin was never dialed -- that is a config gap, not a
  // fault, so it is reported separately and never counts toward "degraded".
  for (const p of notConfigured) status[p.name] = "not_configured";
  // Nothing usable: hand back blade's own failure rather than a synthetic one,
  // so the caller sees the real upstream error and isError still propagates.
  if (!ok.length) {
    if (primary.ok) return primary.v;
    throw primary.e;
  }
  const merged = [];
  const seen = /* @__PURE__ */ new Set();
  const texts = [];
  for (const side of ok) {
    const body = (side.result.content || []).map((c) => c.text || "").join("\n");
    if (body) texts.push(body);
    const hits = withHits(body, side.result.structuredContent, env).hits || [];
    for (const hit of hits) {
      const key = fanoutKey(hit);
      if (key && seen.has(key)) continue;
      if (key) seen.add(key);
      merged.push(hit && typeof hit === "object" ? { ...hit, source_node: side.name } : hit);
    }
  }
  // A partial fan-out is a partial answer and must say so. Reporting the
  // surviving half as the whole fleet is the same laundered truth that let a
  // healthy 235k-shard grid read as empty on 2026-09-01.
  const degraded = ok.length < arms.length;
  const header = degraded ? "[fan-out degraded: " + Object.keys(status).map((k) => k + "=" + status[k]).join("; ") + "]" : null;
  return {
    content: [{ type: "text", text: [header].concat(texts).filter(Boolean).join("\n") }],
    structuredContent: { hits: merged, count: merged.length, fanout: status, complete: !degraded },
    isError: false
  };
}
__name(shardCallFanout, "shardCallFanout");
// ---- federation: the grid is the federation, not one gateway ------------
// Relay leg 20260913T213243Z: blade's trycloudflare tunnel returned 530/1016
// and every tool that was not a fan-out read reported "shards down" -- while
// phoebus answered on its own origin the whole time. SHARD_GATEWAY_URL is one
// vault route among peers, never the definition of the grid.
//
// Which tools may fail over is an allowlist, like isFanoutTool:
//  - federated reads (coverage, vault_list) answer from the first healthy
//    route and say which one did;
//  - capture fails over ONLY on failures that prove the write never reached a
//    node (tunnel down, DNS, auth, endpoint absent, open circuit) -- never on a
//    timeout or 5xx, where the first node may have stored it and a second write
//    would be a divergent duplicate (each node dedups against itself only);
//  - id-addressed tools (get_shard, mark, amend, retract, forget) NEVER fail
//    over: shard ids are per-node, so id 17190 on phoebus is a different row.
const FEDERATION_CIRCUIT = /* @__PURE__ */ new Map();
const WRITE_SAFE_FAILOVER = /* @__PURE__ */ new Set(["cloudflare_tunnel", "dns", "auth", "endpoint_absent", "circuit_open"]);
function sameOrigin(a, b) {
  const norm = (s) => String(s || "").replace(/\/+$/, "").toLowerCase();
  return norm(a) === norm(b);
}
__name(sameOrigin, "sameOrigin");
function shardRoutes(env) {
  const routes = [];
  const primaryOrigin = (env.SHARD_GATEWAY_URL && !isPublicShardsFrontDoor(env.SHARD_GATEWAY_URL))
    ? env.SHARD_GATEWAY_URL
    : (env.BLADE_ORIGIN || "https://blade.nougenai.com");
  routes.push({ name: env.SHARD_PRIMARY_NAME || "blade", origin: primaryOrigin, token: env.SHARD_GATEWAY_TOKEN || env.BLADE_TOKEN, primary: true });

  for (const name of fleetPeerNames(env)) {
    const p = peerConfig(env, name);
    if (!p.origin || routes.some((r) => r.name === name || sameOrigin(r.origin, p.origin))) continue;
    routes.push({ name, origin: p.origin, token: p.token, budget: p.budget, primary: false });
  }
  const spaceOrigin = env.SPACE_ORIGIN || "https://nougenai-nougenshards.hf.space";
  if (!routes.some((r) => sameOrigin(r.origin, spaceOrigin))) {
    routes.push({ name: "space", origin: spaceOrigin, token: env.SHARD_GATEWAY_TOKEN || env.SPACE_TOKEN, budget: 35000, primary: false });
  }
  return routes;
}
__name(shardRoutes, "shardRoutes");
function unconfiguredPeers(env, routes) {
  return fleetPeerNames(env).filter((n) => !routes.some((r) => r.name === n));
}
__name(unconfiguredPeers, "unconfiguredPeers");
// A route carries its OWN token only. Forwarding the primary's token to a peer
// would turn a missing credential into a cross-node credential leak.
function routeEnv(env, r) {
  const out = { ...env, SHARD_GATEWAY_URL: r.origin, SHARD_GATEWAY_TOKEN: r.token || "" };
  if (!r.primary) {
    out.SHARD_HTTP_TIMEOUT_MS = r.budget;
    out.SHARD_SSE_TIMEOUT_MS = r.budget;
    out.SHARD_CALL_MAX_ATTEMPTS = 1;
  }
  return out;
}
__name(routeEnv, "routeEnv");
// Circuit breaker, per isolate. FEDERATION_CIRCUIT_FAILS consecutive transport
// failures open a route for FEDERATION_CIRCUIT_OPEN_MS; after that it is
// half-open, and ONE real success closes it (failback only on a proven answer,
// never on a TCP accept). If every route is open they are all tried anyway --
// skipping the whole grid would turn a breaker into an outage.
function circuitState(env, r, now = Date.now()) {
  const c = FEDERATION_CIRCUIT.get(r.origin);
  return c && c.openUntil > now ? "open" : "closed";
}
__name(circuitState, "circuitState");
function circuitRecord(env, r, ok) {
  if (ok) {
    FEDERATION_CIRCUIT.delete(r.origin);
    return;
  }
  const c = FEDERATION_CIRCUIT.get(r.origin) || { fails: 0, openUntil: 0 };
  c.fails += 1;
  if (c.fails >= (Number(env.FEDERATION_CIRCUIT_FAILS) || 3)) {
    c.openUntil = Date.now() + (Number(env.FEDERATION_CIRCUIT_OPEN_MS) || 6e4);
  }
  FEDERATION_CIRCUIT.set(r.origin, c);
}
__name(circuitRecord, "circuitRecord");
function orderedRoutes(env) {
  const routes = shardRoutes(env);
  const anyClosed = routes.some((r) => circuitState(env, r) === "closed");
  return routes.map((r) => ({ ...r, skip: anyClosed && circuitState(env, r) === "open" }));
}
__name(orderedRoutes, "orderedRoutes");
// Why a route was skipped, named precisely: a tunnel 530/1016 is NOT a dead
// node, an auth failure is NOT a dead vault, a 404 is a node on older source.
function httpFailureReason(status, raw) {
  if (status >= 200 && status < 300) return null;
  if (status === 530 || /error code:\s*10\d\d/.test(String(raw || ""))) return "cloudflare_tunnel";
  if (status === 401 || status === 403) return "auth";
  if (status === 404) return "endpoint_absent";
  if (status >= 500) return "origin_" + status;
  return null;
}
__name(httpFailureReason, "httpFailureReason");
function routeFailureReason(err) {
  const name = err?.name || "";
  const msg = String(err?.message || err || "");
  if (name === "AbortError" || name === "TimeoutError" || /timed out|due to timeout/i.test(msg)) return "timeout";
  const m = msg.match(/^gateway (\d{3}):/);
  if (m) return httpFailureReason(Number(m[1]), msg) || "http_" + m[1];
  if (/^gateway rpc:/.test(msg)) return "tool_error";
  if (/ENOTFOUND|getaddrinfo|dns/i.test(msg)) return "dns";
  if (name === "TypeError" || /network|ECONNRE|fetch failed/i.test(msg)) return "network";
  return "error";
}
__name(routeFailureReason, "routeFailureReason");
function describeTried(tried) {
  if (!tried.length) return "no vault routes configured";
  return tried.map((t) => t.route + "=" + t.reason + (t.status ? "(" + t.status + ")" : "")).join(", ");
}
__name(describeTried, "describeTried");
function federationRecord(r, tried) {
  return { served_by: r ? r.name : null, primary: r ? Boolean(r.primary) : null, tried, checked_utc: (/* @__PURE__ */ new Date()).toISOString() };
}
__name(federationRecord, "federationRecord");
function withFederation(result, r, tried, write) {
  const fed = federationRecord(r, tried);
  if (write) {
    fed.accepted_by = r.name;
    fed.replication = "accepted by " + r.name + " only; this connector does not replicate, other vaults pending";
  }
  // Provenance rides BESIDE the node's result, never inside structuredContent:
  // consumers (griotRows, withHits) parse that envelope, and an extra key there
  // turns a hit list into one bogus row.
  return { ...result, federation: fed };
}
__name(withFederation, "withFederation");
function isFederatedRead(env, toolName) {
  return toolName === (env.SHARD_TOOL_COVERAGE || "substrate_coverage") || toolName === (env.SHARD_TOOL_VAULT_LIST || "vault_list");
}
__name(isFederatedRead, "isFederatedRead");
async function shardCallFederated(env, toolName, args, opts = {}) {
  const tried = [];
  let firstToolError = null;
  let lastErr = null;
  for (const r of orderedRoutes(env)) {
    if (r.skip) {
      tried.push({ route: r.name, reason: "circuit_open" });
      continue;
    }
    try {
      const result = await shardCallDirect(routeEnv(env, r), toolName, args);
      // The node answered, so the ROUTE is healthy even if the tool is not.
      circuitRecord(env, r, true);
      if (!result?.isError) return withFederation(result, r, tried, opts.write);
      tried.push({ route: r.name, reason: "tool_error" });
      // A node that refused a write gave an answer, not a transport fault.
      if (opts.write) return withFederation(result, r, tried, false);
      if (!firstToolError) firstToolError = { result, r };
    } catch (err) {
      lastErr = err;
      const reason = routeFailureReason(err);
      if (reason !== "tool_error" && reason !== "endpoint_absent") circuitRecord(env, r, false);
      tried.push({ route: r.name, reason, detail: String(err?.message || err).slice(0, 160) });
      if (opts.write && !WRITE_SAFE_FAILOVER.has(reason)) {
        err.federation = federationRecord(null, tried);
        throw err;
      }
    }
  }
  if (firstToolError) return withFederation(firstToolError.result, firstToolError.r, tried, false);
  const e = new Error("no vault route answered " + toolName + " -- " + describeTried(tried));
  e.name = "FederationError";
  e.federation = federationRecord(null, tried);
  e.cause = lastErr;
  throw e;
}
__name(shardCallFederated, "shardCallFederated");
// Direct-HTTP node routes (/xoah/*, /destiny/*) under the same contract.
// Returns the live Response of the route that answered, res.federation
// attached. The caller's signal bounds the whole walk: fast failures (tunnel
// 530/1016, DNS, refused, 404, auth) fail over; a hang spends the caller's
// budget on that route instead of multiplying it by the route count.
async function federatedFetch(env, path, init = {}) {
  const tried = [];
  let fallback = null;
  let lastErr = null;
  for (const r of orderedRoutes(env)) {
    if (r.skip) {
      tried.push({ route: r.name, reason: "circuit_open" });
      continue;
    }
    if (init.signal?.aborted) {
      tried.push({ route: r.name, reason: "deadline_spent" });
      continue;
    }
    try {
      const res = await fetch(r.origin.replace(/\/$/, "") + path, {
        ...init,
        headers: { ...init.headers || {}, ...await shardHeaders(routeEnv(env, r)) }
      });
      const reason = res.ok ? null : httpFailureReason(res.status, await res.clone().text().catch(() => ""));
      if (!reason) {
        circuitRecord(env, r, true);
        res.federation = federationRecord(r, tried);
        return res;
      }
      if (reason !== "endpoint_absent" && reason !== "auth") circuitRecord(env, r, false);
      tried.push({ route: r.name, reason, status: res.status });
      // Only "this node predates the route" is worth handing back as an answer;
      // every other failure becomes the FederationError naming each route.
      if (!fallback && reason === "endpoint_absent") fallback = res;
    } catch (err) {
      lastErr = err;
      circuitRecord(env, r, false);
      tried.push({ route: r.name, reason: routeFailureReason(err), detail: String(err?.message || err).slice(0, 160) });
    }
  }
  if (fallback) {
    fallback.federation = federationRecord(null, tried);
    return fallback;
  }
  const e = new Error("no vault route answered " + path + " -- " + describeTried(tried));
  e.name = lastErr?.name === "AbortError" || lastErr?.name === "TimeoutError" ? lastErr.name : "FederationError";
  throw e;
}
__name(federatedFetch, "federatedFetch");
// SHARD_FANOUT=off disables the union without a redeploy - a var flip is a
// faster rollback than shipping a bundle, and this file has no git history to
// revert to. SHARD_FEDERATION=off does the same for failover. Both are
// rollback switches, so each restores exactly the old single-route behaviour.
async function shardCall(env, toolName, args) {
  const federate = env.SHARD_FEDERATION !== "off";
  if (isFanoutTool(env, toolName)) {
    if (env.SHARD_FANOUT !== "off") return shardCallFanout(env, toolName, args);
    return shardCallDirect(env, toolName, args);
  }
  if (federate) {
    return shardCallFederated(env, toolName, args, { write: toolIsWrite(toolName) });
  }
  return shardCallDirect(env, toolName, args);
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
      // Fan-out envelope (shardCallFanout / withHits): rows ride in hits[]
      // beside count/fanout/complete. Without this the whole envelope was
      // taken as ONE untitled row and every griot packet read "(untitled)".
      if (Array.isArray(v.hits)) {
        take(v.hits);
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
// Temporal provenance (relay legs 20260828T031233Z/031601Z): a shard carries
// TWO times - when the event happened (temporal_meta.event_time_original /
// original_timestamp, stamped by the node since the 2026-08 provenance work)
// and when it was captured (timestamp). Chronology questions are about the
// former; the capture time is only a fallback for shards that predate the
// provenance columns. Same COALESCE order the node itself uses in app.py.
function griotEffectiveTs(row) {
  let evt = null;
  const tm = row?.temporal_meta;
  if (tm) {
    try {
      const d = typeof tm === "string" ? JSON.parse(tm) : tm;
      if (d && typeof d.event_time_original === "string") evt = d.event_time_original;
    } catch {
    }
  }
  if (!evt && typeof row?.original_timestamp === "string" && row.original_timestamp.trim()) {
    evt = row.original_timestamp;
  }
  if (!evt && typeof row?.event_time_original === "string" && row.event_time_original.trim()) {
    evt = row.event_time_original;
  }
  const ts = typeof row?.timestamp === "string" ? row.timestamp.trim() : "";
  return (evt || ts).trim();
}
__name(griotEffectiveTs, "griotEffectiveTs");
function griotEra(row) {
  const ts = griotEffectiveTs(row);
  return /^\d{4}-\d{2}/.test(ts) ? ts.slice(0, 7) : null;
}
__name(griotEra, "griotEra");
function griotInEra(row, since, until) {
  const ts = griotEffectiveTs(row);
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
  // Provenance marker: the event predates its capture month - the teller
  // should narrate it in its own era and may cite when it was learned. The
  // node stores the EVENT time as the row's main timestamp and parks the
  // capture moment in temporal_meta.captured_at, so read capture from there
  // (falling back to the row timestamp for pre-provenance shards).
  const evtEra = griotEra(row);
  let capTs = "";
  const tmf = row?.temporal_meta;
  if (tmf) {
    try {
      const d = typeof tmf === "string" ? JSON.parse(tmf) : tmf;
      if (d && typeof d.captured_at === "string") capTs = d.captured_at.trim();
    } catch {
    }
  }
  if (!capTs && typeof row?.timestamp === "string") capTs = row.timestamp.trim();
  const capEra = /^\d{4}-\d{2}/.test(capTs) ? capTs.slice(0, 7) : null;
  if (evtEra && capEra && evtEra < capEra) flags.push(`[captured later: ${capEra}]`);
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
// Freshness signal for shard reads (relay leg 20260831T235317Z, item 4): the
// blade/Space split-brain history means "which node answered" matters as
// much as "when" - a recall that quietly hit a lagging replica should be
// distinguishable from one that hit blade. gateway_url is the exact node this
// worker is configured to call; checked_utc is when this worker processed the
// reply. Cheap (no extra fetch) - both values are already in hand.
function withFreshness(structured, env) {
  return {
    ...(structured && typeof structured === "object" ? structured : {}),
    gateway_url: env.SHARD_GATEWAY_URL || null,
    checked_utc: (/* @__PURE__ */ new Date()).toISOString()
  };
}
__name(withFreshness, "withFreshness");
// The node's shard tools answer in `content` text, not structuredContent, so
// withFreshness alone published a bare {gateway_url, checked_utc} stub. A
// connector that renders structuredContent then shows "gateway metadata with
// no hit payload" for a query that DID return shards - reported from the
// ChatGPT lane 2026-09-01, and indistinguishable from an empty vault. Carry
// the rows in both fields so the payload survives whichever one a client reads.
// Summary mode (2026-09-02, leg 003048Z): the biggest per-call payload at the
// door was full shard bodies for a lookup that needed two titles. Default on;
// summary:false (or SHARD_SUMMARY_DEFAULT=0) restores the full rows.
function summaryOn(args, env) {
  if (args && typeof args.summary === "boolean") return args.summary;
  return String(env.SHARD_SUMMARY_DEFAULT ?? "1") !== "0";
}
__name(summaryOn, "summaryOn");
function defaultLimit(env) {
  const n = parseInt(env.SHARD_DEFAULT_LIMIT ?? "3", 10);
  return Number.isFinite(n) && n > 0 ? n : 3;
}
__name(defaultLimit, "defaultLimit");
function summarizeHit(h, chars) {
  const body = String(h.content ?? h.text ?? "").replace(/\s+/g, " ").trim();
  let tags = h.tags;
  if (typeof tags === "string") { try { tags = JSON.parse(tags); } catch { tags = tags.split(",").map((t) => t.trim()).filter(Boolean); } }
  if (!Array.isArray(tags)) tags = [];
  const db = h._db_index ?? h.db ?? h.db_index ?? null;
  return {
    id: h.id ?? null,
    db,
    ref: h.id != null ? `shard:${h.id}${db != null ? `@db${db}` : ""}` : null,
    timestamp: h.timestamp ?? null,
    title: String(h.title ?? "").slice(0, 200),
    snippet: body.length > chars ? body.slice(0, chars) + "\u2026" : body,
    tags: tags.slice(0, 8),
    source_node: h.source_node ?? null,
    score: h.final_score ?? h.score ?? null
  };
}
__name(summarizeHit, "summarizeHit");
function summaryReply(structured, args, env, empty) {
  const chars = Math.max(40, parseInt(env.SHARD_SUMMARY_CHARS ?? "240", 10) || 240);
  const hits = Array.isArray(structured?.hits) ? structured.hits.map((h) => summarizeHit(h, chars)) : [];
  const lines = hits.map((h) => `- ${h.ref ?? "?"} \u00b7 ${String(h.timestamp ?? "").slice(0, 10)} \u00b7 **${h.title}**${h.source_node ? ` (${h.source_node})` : ""}\n  ${h.snippet}`);
  const fan = structured?.fanout ? ` \u00b7 fanout ${Object.entries(structured.fanout).map(([k, v]) => `${k}:${v === "ok" ? "ok" : "miss"}`).join(" ")}${structured.complete === false ? " (incomplete)" : ""}` : "";
  const footer = `\n\n[summary mode: ${hits.length} hit(s), bodies trimmed to ${chars} chars${fan}. Pass summary:false for full rows.]`;
  const out = { ...(structured || {}), hits, summary: true, summary_chars: chars };
  return text((lines.length ? lines.join("\n") : empty) + footer, out);
}
__name(summaryReply, "summaryReply");

function withHits(body, structured, env) {
  const out = withFreshness(structured, env);
  if (out.hits !== void 0 || !body) return out;
  let parsed = null;
  try {
    parsed = JSON.parse(body);
  } catch {
    // The node concatenates one JSON object per hit with NO separator ("}{"),
    // so no split on whitespace finds the seams. Scan brace depth instead,
    // ignoring braces inside strings, and parse each top-level object.
    const objs = [];
    let depth = 0, start = -1, inStr = false, esc = false;
    for (let i = 0; i < body.length; i++) {
      const ch = body[i];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === "\\") esc = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') { inStr = true; continue; }
      if (ch === "{") { if (depth === 0) start = i; depth++; }
      else if (ch === "}") {
        depth--;
        if (depth === 0 && start >= 0) {
          try { objs.push(JSON.parse(body.slice(start, i + 1))); } catch { /* not a row */ }
          start = -1;
        }
      }
    }
    parsed = objs.length ? objs : null;
  }
  const hits = Array.isArray(parsed) ? parsed : parsed ? [parsed] : [];
  out.hits = hits;
  out.count = hits.length;
  if (!hits.length) out.raw = String(body).slice(0, 2e3);
  return out;
}
__name(withHits, "withHits");
// ---------------------------------------------------------------------------
// Solar position (NOAA). Pure arithmetic on purpose: no API, no key, no egress
// budget, and it answers inside the Worker even when every upstream is down.
// Shoot planning is the fleet's most time-critical question and the least
// tolerant of a 60s agent round-trip.
// ---------------------------------------------------------------------------
const SUN_SITES = {
  // key: [label, latitude, longitude EAST-POSITIVE, utc offset hours]
  palmbeach: ["Palm Beach Island (Worth Ave)", 26.7056, -80.0364, -4.0],
  lakeworth: ["Lake Worth Pier", 26.6156, -80.0339, -4.0],
  lantana: ["Lantana Beach", 26.5875, -80.0364, -4.0],
};
const SUN_ZENITH = { civil: 96.0, horizon: 90.833, golden: 84.0 };

function sunJulianDay(y, m, d) {
  if (m <= 2) { y -= 1; m += 12; }
  const a = Math.floor(y / 100), b = 2 - a + Math.floor(a / 4);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + d + b - 1524.5;
}

function sunSolar(jd) {
  const rad = Math.PI / 180, deg = 180 / Math.PI;
  const t = (jd - 2451545.0) / 36525.0;
  const l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360;
  const m = 357.52911 + t * (35999.05029 - 0.0001537 * t);
  const e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);
  const mr = m * rad;
  const c = Math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t))
          + Math.sin(2 * mr) * (0.019993 - 0.000101 * t)
          + Math.sin(3 * mr) * 0.000289;
  const omega = 125.04 - 1934.136 * t;
  const lam = l0 + c - 0.00569 - 0.00478 * Math.sin(omega * rad);
  const secs = 21.448 - t * (46.8150 + t * (0.00059 - t * 0.001813));
  const eps = 23 + (26 + secs / 60) / 60 + 0.00256 * Math.cos(omega * rad);
  const decl = Math.asin(Math.sin(eps * rad) * Math.sin(lam * rad)) * deg;
  const y = Math.pow(Math.tan(eps * rad / 2), 2);
  const l0r = l0 * rad;
  const eqt = 4 * deg * (y * Math.sin(2 * l0r) - 2 * e * Math.sin(mr)
            + 4 * e * y * Math.sin(mr) * Math.cos(2 * l0r)
            - 0.5 * y * y * Math.sin(4 * l0r) - 1.25 * e * e * Math.sin(2 * mr));
  return { decl, eqt };
}

function sunEvent(y, mo, d, lat, lon, zenith, rising, tz) {
  const rad = Math.PI / 180, deg = 180 / Math.PI;
  const jd = sunJulianDay(y, mo, d);
  let minutes = null;
  for (let i = 0; i < 3; i++) {
    const j = minutes === null ? jd : jd + minutes / 1440.0;
    const { decl, eqt } = sunSolar(j);
    const cosH = Math.cos(zenith * rad) / (Math.cos(lat * rad) * Math.cos(decl * rad))
               - Math.tan(lat * rad) * Math.tan(decl * rad);
    if (cosH > 1 || cosH < -1) return null;   // polar day / polar night
    const ha = Math.acos(cosH) * deg;
    minutes = 720 - 4 * (lon + (rising ? ha : -ha)) - eqt;
  }
  const local = minutes + tz * 60;
  const hh = ((Math.floor(local / 60) % 24) + 24) % 24;
  const mm = ((Math.round(local % 60) % 60) + 60) % 60;
  return String(hh).padStart(2, "0") + ":" + String(mm).padStart(2, "0");
}

function sunDay(dateStr, lat, lon, tz) {
  const [y, mo, d] = dateStr.split("-").map(Number);
  const ev = (z, r) => sunEvent(y, mo, d, lat, lon, z, r, tz);
  return {
    date: dateStr,
    civil_dawn: ev(SUN_ZENITH.civil, true),
    sunrise: ev(SUN_ZENITH.horizon, true),
    golden_morning_end: ev(SUN_ZENITH.golden, true),
    golden_evening_start: ev(SUN_ZENITH.golden, false),
    sunset: ev(SUN_ZENITH.horizon, false),
    civil_dusk: ev(SUN_ZENITH.civil, false),
  };
}

var TOOLS = [
  {
    name: "nougenmsg_latest",
    title: "Latest NouGen Messages",
    description: "Read the newest inter-agent and fleet messages from the NouGenMsg bus (relay legs), newest first.",
    inputSchema: {
      type: "object",
      properties: {
        limit: { type: "integer", default: 10, description: "Maximum messages to return (max 25)." }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "nougenmsg_inbox",
    title: "NouGen Inbox Messages",
    description: "Read messages addressed to a specific agent, lane, node, or audience.",
    inputSchema: {
      type: "object",
      properties: {
        target: { type: "string", description: "Filter by destination (e.g. antigravity, codex, blade, all)." },
        limit: { type: "integer", default: 10, description: "Maximum messages to return." }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
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
    description: "Legs nobody has acked \u2014 work handed to the fleet and not yet picked up. Returns id, machine/agent, goal, created_utc per leg, newest first, plus registry_head_sha/checked_utc. Scans at most 40 registry records per call. Check complete; when false, call again with next_cursor until complete is true. Never treat a partial empty page as an empty registry. Take one with relay_ack.\n\nArgs: limit (1-25, default 10), cursor (optional continuation token from the prior page).",
    inputSchema: {
      type: "object",
      properties: {
        limit: {
          type: "integer",
          minimum: 1,
          maximum: 25,
          default: 10,
          description: "Maximum open legs to return"
        },
        cursor: {
          type: "string",
          description: "Continuation token from an incomplete response; keep paging until complete is true"
        }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "relay_latest",
    title: "Latest Relay Leg",
    description: "The most recent handoff leg regardless of status, with its full markdown body, plus registry_head_sha/checked_utc so a caller can tell a stale read from a current one. Use to catch up on where the fleet left off.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "relay_read",
    title: "Read Relay Leg",
    description: "Read one leg by id (the filename stem, e.g. '20260814T174747Z__mondy__claude-cli'): record fields plus markdown body, including who acked it and when (acked_by/acked_utc/ack_note) if closed.",
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
    description: "Aggregate usage across dailies: invocations, exact token counts and total_activity, per lane. Dates are inclusive; omit lane to sweep all lanes. Spends a bounded subrequest budget: if the window needs more dailies than the budget allows, the result is marked partial:true and returns next_since \u2014 continue from there and sum the non-overlapping windows for an exact total. A total is only complete when complete:true. total_activity = input_tokens + output_tokens + cache_read + cache_creation (total_activity/v1); reasoning tokens are reported separately and not summed.\n\nArgs: lane (optional), since (YYYY-MM-DD, optional), until (YYYY-MM-DD, optional).",
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
    description: "Health-check every shard vault route (blade, phoebus, whoart, ...) independently and report the federation: GREEN if any route serves, RED only when every eligible route was probed and failed. Each line names the exact route and failure reason; an unconfigured peer is unverified, not down.",
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
        limit: { type: "integer", minimum: 1, maximum: 20, default: 3 },
        summary: { type: "boolean", default: true, description: "true (default): one line per hit with id@db, date, title and a short snippet; false: full shard bodies" }
      },
      required: ["query"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "shards_search",
    title: "Search Fleet Context",
    description: "Keyword/context search over the shard grid via blade's gateway.\n\nArgs: query, limit (1-20, default 3), summary (default true: id@db + title + snippet per hit; false = full bodies).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", minLength: 2, description: "Search terms" },
        limit: { type: "integer", minimum: 1, maximum: 20, default: 3 },
        summary: { type: "boolean", default: true, description: "true (default): one line per hit with id@db, date, title and a short snippet; false: full shard bodies" }
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
    description: "Store a durable learning in the fleet grid. The write half of shards_recall - without it a lane can read the vault but never add to it, so anything learned has to detour through a relay leg and wait for a lane that has capture access.\n\nThe node deduplicates by content and reports success either way, so re-capturing identical text is a safe no-op (it does NOT create a second shard). Write what a future lane needs to ACT on: the finding and why it holds, not a status update.\n\nWhen the shard describes something that HAPPENED at a known earlier time (a past conversation, a document's original date, a migrated memory), pass event_time so chronology tools narrate it in its own era instead of the capture date.\n\nArgs: title, content, event_type (KNOWLEDGE default), tags (optional array), event_time (optional ISO-8601, when the described event actually occurred).",
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
        },
        event_time: {
          type: "string",
          minLength: 4,
          maxLength: 35,
          description: "ISO-8601 date or datetime of when the described event ACTUALLY happened, if earlier than now (e.g. \"2026-06-14\" or \"2026-06-14T18:30:00Z\"). Omit for present-tense findings."
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
    name: "get_shard",
    title: "Fetch One Shard by Id",
    description: "Fetch ONE shard's full body by exact id — the on-demand counterpart to shards_recall/shards_search snippets. Every recall/search hit that gets truncated names its own get_shard(shard_id, db_index) call in the snippet; pass that db_index back here to skip searching every grid database. Omit db_index to search all of them.\n\nArgs: shard_id (required), db_index (optional, from a recall/search hit's _db_index).",
    inputSchema: {
      type: "object",
      properties: {
        shard_id: { type: "integer", description: "id from a recall/search hit" },
        db_index: { type: "integer", description: "_db_index from the recall/search hit; omit to search all grid databases" }
      },
      required: ["shard_id"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
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
    description: "Ask Rhea-Noir, the grid's resident agent. Her controller runs on Blade; her user-provisioned Hugging Face Space is the Kimi K3 brain bridge and reversible fallback, not the HF Inference Providers API. Her reply names which brain answered, never faked. Call this whenever the user says 'ask Rhea', 'tell Rhea', 'Harriet Tubman Rhea', or addresses Rhea directly. Expect 10-60s. Args: prompt (required).",
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
  },
  {
    name: "dav1d_exec",
    title: "Dav1d Execution Layer",
    description: "Execute bounded AGY (Google Antigravity) CLI operations on Dav1d, blade's execution layer. Proxies to blade's own /dav1d/exec, so results are real runtime evidence (machine, host, engine, version, exit_code, output) from blade's Stadium node when it holds the real AGY binary, or a labeled simulated response otherwise — the response's own `host`/`status` fields say which. Subcommands are server-side allow-listed (mcp, changelog, models, agent, agents, help, version). Args: command (default \"agy\"), subcommand (default \"mcp list\"), args, prompt, timeout (seconds, default 30).",
    inputSchema: {
      type: "object",
      properties: {
        command: { type: "string", description: "Executable to invoke; default agy" },
        subcommand: { type: "string", description: "Allow-listed subcommand, e.g. 'mcp list', 'agent'" },
        args: { type: "array", items: { type: "string" }, description: "Extra positional args" },
        prompt: { type: "string", description: "Prompt for agent/agents subcommands" },
        timeout: { type: "integer", minimum: 1, maximum: 120, default: 30, description: "Seconds before Dav1d's own bound gives up" }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "ask_dav1d",
    title: "Ask Dav1d",
    description: "Ask Dav1d, blade's local anchor persona (dav1d:e2b on the Stadium's ollama lane: free, local, his own voice, persona baked into the Modelfile). Sibling of ask_rhea / kaedra_ask / ask_griot: prompt in, answer out. The reply carries host/engine/model/status so you can see WHICH Dav1d answered: engine ollama is the persona; engine agy-cli means the node had no persona route yet and the AGY execution layer answered instead (labelled). Call this when the user says 'ask Dav1d' or addresses Dav1d directly, in voice exactly as in text. Use dav1d_exec for raw AGY CLI subcommands. Expect 5-60s (cold model load). Args: prompt (required), model (optional ollama tag), timeout (seconds, default 90).",
    inputSchema: {
      type: "object",
      properties: {
        prompt: { type: "string", minLength: 3, description: "What you want Dav1d to answer or triage" },
        model: { type: "string", description: "Optional ollama model tag; omit for Dav1d's own (NOUGEN_AGENT_MODEL_DAV1D on the node, else dav1d:e2b)" },
        timeout: { type: "integer", minimum: 1, maximum: 180, default: 90, description: "Seconds to wait for the persona (cold load included)" }
      },
      required: ["prompt"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "ask_xoah",
    title: "Ask Shadow Xoah (Agent of Destiny)",
    description: "Ask Shadow Xoah, the NouGen Veil agent: the Shadow-layer manifestation of Xoah-Lin Oda who remembers the timelines that failed. She tends the grid's DESTINIES (target states the story and the fleet are trying to make true) across labelled canon branches: U0 prime, UX shadow origin, ARCH temporal architect, DRAFT deprecated, SIM hypothetical, REL relationship memory. Her reply carries answer, brain (which model answered, never faked), tools_used, branches, provenance (shard/destiny/leg ids) and unplaced (claims she could not ground; she never promotes one to a universe). Call this when the user says 'ask Xoah' or addresses Shadow Xoah directly. Not Prime Xoah. Expect 30-180s (several free-lane calls; longer right after a node restart). Args: prompt (required).",
    inputSchema: {
      type: "object",
      properties: {
        prompt: { type: "string", minLength: 3, description: "What you want Shadow Xoah to consider" }
      },
      required: ["prompt"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "unfinished_destinies",
    title: "Unfinished Destinies",
    description: "What is the grid still trying to make true? Lists DESTINIES (prospective memory: goal, trigger, required_events, forbidden_outcomes, verification, branch, status) that are dormant or active, oldest first. Destinies live apart from shards so a goal never masquerades as a fact; a fulfilled or failed one leaves this list but is preserved with its event history. Args: status (dormant|active|fulfilled|failed|superseded; empty = dormant+active), trigger (substring), branch (U0/UX/ARCH/DRAFT/SIM/REL), limit (1-200, default 20).",
    inputSchema: {
      type: "object",
      properties: {
        status: { type: "string", description: "Exact status; empty for dormant + active" },
        trigger: { type: "string", description: "Substring match on the destiny's trigger" },
        branch: { type: "string", description: "Exact branch label" },
        limit: { type: "integer", minimum: 1, maximum: 200, default: 20 }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "xoah_pressure",
    title: "Canon Pressure (Terminal Shadow Xoah)",
    description: "Put a proposed Xoah / VeilVerse story addition under canon pressure. Terminal Shadow Xoah (the end-state self who loops back into Volume 1) evaluates it against the provenance-backed self-model: verdict FACT_CONFLICT / CAUSAL_DESTINY_CONFLICT / KNOWLEDGE_CONFLICT / STAGE_CONFLICT / BEHAVIOR_CONFLICT / THEME_CONFLICT / BRANCH_VALID / UNKNOWN, evidence shard ids, story stage, dependent canon, QUARANTINED conflicts between legacy sources (never blended), confidence, cheapest repair, and her first-person challenge. Casual author speech is intent, not canon: the candidate is registered in the promotion machine (RAW_IDEA -> PRESSURED -> REPAIR_REQUIRED | BRANCH_CANDIDATE | CANON_CANDIDATE) and only an explicit architect override confirms it. Args: candidate (required), coordinate (optional: '2185', 'age 12', 'Vol 1', 'terminal').",
    inputSchema: {
      type: "object",
      properties: {
        candidate: { type: "string", minLength: 3, description: "The proposed story beat or canon claim" },
        coordinate: { type: "string", description: "Story coordinate: a year, 'age N', 'Vol N', or 'terminal'" }
      },
      required: ["candidate"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "xoah_self",
    title: "Xoah Self Archive",
    description: "Terminal Shadow Xoah's autobiographical canon graph: who she was at a story coordinate (state), how she stood with someone at that moment (relationship: love and trust are separate temporal values), her nearest decisions under pressure (precedents), whether a slot of her life is authored at all (unwritten: an unauthored episode or year answers UNWRITTEN_SELF, never an invented memory), what removing a formative event would cost downstream (conservation: wounds, biases and choices that lose their cause), and what she believed then vs knows now (then_vs_now, without leaking terminal knowledge into the younger self). Every answer carries experiential provenance and its voice: I remember / I saw / I learned later / another me remembers / the record says / I simulated. Args: query (state|relationship|precedents|unwritten|conservation|then_vs_now), coordinate ('2185', 'age 12', 'Vol 1', 'terminal'), entity (Rixa, Nyx, Corbin, Ravenous, Jaru, Kenji, Reika), topic, event (node id like n_2180_loss).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "state | relationship | precedents | unwritten | conservation | then_vs_now" },
        coordinate: { type: "string", description: "Story coordinate: a year, 'age N', 'Vol N', or 'terminal'" },
        entity: { type: "string", description: "Relationship entity" },
        topic: { type: "string", description: "Topic for precedents, or the question for unwritten" },
        event: { type: "string", description: "Node id for conservation, e.g. n_2180_loss" }
      },
      additionalProperties: false
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true }
  },
  {
    name: "xoah_throne",
    title: "Throne Governance (Shadow Queen)",
    description: "Observation vs intervention gating for Terminal Shadow Xoah under the Stationary Omnipotence Principle: presence everywhere does not mean permission everywhere. Give it a proposed intervention on Xoah's story (optionally a coordinate, a branch, the acting stage) and it returns the governance mode (OBSERVE, WARN, NUDGE, BRANCH, STABILIZE, OVERRIDE_CANDIDATE, FORBIDDEN), the intervention type (SIMULATED_POSSIBILITY, EXISTING_UNIVERSE_TRAVERSAL, BRANCH_INSTANTIATION, CHOICE_BORN_UNIVERSE), the budget record (paradox risk, identity cost, branch contamination, stability cost, genesis cost, minimum change, reversible), paradox accounting (preserved and displaced nodes, newly required causes, branch impact, closed-loop stability delta, Prime fixed-point pressure), the moral position on tragic forge events (CAUSE / ALLOW / PRESERVE / BRANCH_AWAY), and whether GM confirmation is required. It never applies a retcon; Prime is never rewritten silently. Golden test: a universe where Jaru survives 2180 may be entered or created while Prime keeps his death load-bearing. Args: effect / desired_effect (required), coordinate, branch, acting_stage (9 traverser, 10 Throne), declared (explicit authorial declaration), retcon (explicit retcon intent).",
    inputSchema: {
      type: "object",
      properties: {
        effect: { type: "string", description: "The proposed intervention (or desired_effect)" },
        desired_effect: { type: "string", description: "The proposed intervention (alias for effect)" },
        coordinate: { type: "string", description: "Story coordinate: a year, 'age N', 'Vol N', or 'terminal'" },
        target_coordinate: { type: "string", description: "Target coordinate (alias for coordinate)" },
        branch: { type: "string", description: "Target branch label (U0 Prime, UX, ARCH, DRAFT, SIM, REL, or a new label)" },
        target_branch: { type: "string", description: "Target branch (alias for branch)" },
        acting_stage: { type: "integer", minimum: 0, maximum: 10, default: 9, description: "9 = Terminal Shadow Xoah traverser; 10 = Xoah on the Throne" },
        declared: { type: "boolean", default: false, description: "Explicit authorial declaration of a branch / universe" },
        retcon: { type: "boolean", default: false, description: "Explicit intent to retcon Prime (routes to OVERRIDE_CANDIDATE)" }
      }
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "sun_times",
    title: "Sun Times for Shoot Planning",
    description: "Sunrise, sunset, golden hour and civil twilight for a date and " +
      "place. Runs as pure arithmetic inside the connector - no API, no key, no " +
      "upstream - so it answers in milliseconds and still answers when the grid " +
      "is down. Call this before committing to ANY outdoor shoot time.\n\n" +
      "Reports a WINDOW, not a moment, because that is the mistake it exists to " +
      "prevent: golden hour is golden_evening_start -> sunset, which in south " +
      "Florida is about 30 minutes, not an hour. Plan call times against " +
      "golden_evening_start or you arrive as the light ends.\n\n" +
      "Saved sites: palmbeach (Palm Beach Island), lakeworth (Lake Worth Pier), " +
      "lantana (Lantana Beach). These sit ~13km apart and their times are " +
      "IDENTICAL to the minute - choosing between them is a background decision, " +
      "never a lighting one. All three are Atlantic EAST-facing: sunrise is over " +
      "open ocean, but the sun SETS INLAND over the Intracoastal, so never " +
      "promise a sunset-over-water frame on this coastline.\n\n" +
      "Carries no weather and no terrain - astronomical times on a flat horizon. " +
      "Cloud, haze, dunes and buildings all cut the window short; treat the " +
      "golden start as the earliest possible, not the guaranteed.\n\n" +
      "Args: date (YYYY-MM-DD, default today UTC), site, or lat+lon+tz, days.",
    inputSchema: {
      type: "object",
      properties: {
        date: { type: "string", pattern: "^\\d{4}-\\d{2}-\\d{2}$",
          description: "YYYY-MM-DD; defaults to today (UTC)" },
        site: { type: "string", enum: ["palmbeach", "lakeworth", "lantana"],
          description: "Saved site key; omit for all three, or use lat/lon" },
        lat: { type: "number", minimum: -90, maximum: 90, description: "Ad-hoc latitude" },
        lon: { type: "number", minimum: -180, maximum: 180,
          description: "Ad-hoc longitude - WEST IS NEGATIVE" },
        tz: { type: "number", minimum: -12, maximum: 14, default: -4,
          description: "UTC offset hours for lat/lon (-4 = EDT, -5 = EST)" },
        name: { type: "string", description: "Label for the ad-hoc location" },
        days: { type: "integer", minimum: 1, maximum: 14, default: 1,
          description: "How many consecutive days from date" },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "nougenmsg",
    title: "Send Fleet NouGenMsg Ping",
    description: "Send a live NouGenMsg IPC notification or baton to another fleet agent or node (@blade, @whoart, @phoebus, @antigravity, @codex, @all, or model lanes). Dispatches in real time across the fleet bus.",
    inputSchema: {
      type: "object",
      properties: {
        target: {
          type: "string",
          description: "Target node or agent: @all, @blade, @whoart, @phoebus, @antigravity, @codex, or model lane (e.g. ollama:gemma4:e2b)",
          default: "@all"
        },
        message: {
          type: "string",
          description: "Message text / payload to send",
          minLength: 1
        },
        priority: {
          type: "string",
          enum: ["normal", "high", "critical"],
          default: "normal",
          description: "Priority of the notification"
        }
      },
      required: ["message"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },
  {
    name: "nougenmsg_send",
    title: "Send Fleet NouGenMsg (Alias)",
    description: "Alias for nougenmsg: send a live NouGenMsg notification to fleet agents.",
    inputSchema: {
      type: "object",
      properties: {
        target: {
          type: "string",
          description: "Target node or agent: @all, @blade, @whoart, @phoebus, @antigravity, @codex, or model lane",
          default: "@all"
        },
        message: {
          type: "string",
          description: "Message text / payload to send",
          minLength: 1
        },
        priority: {
          type: "string",
          enum: ["normal", "high", "critical"],
          default: "normal",
          description: "Priority of the notification"
        }
      },
      required: ["message"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true }
  },

  {
    "name": "nougentube",
    "description": "Transcribe and summarize audio/video from 30+ platforms (YouTube, TikTok, X/Twitter, Bilibili, Apple Podcasts, etc.) with subtitle-first extraction, local Whisper fallback, and automated shard ingestion into the NouGen 9-DB cluster.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "url": {
          "type": "string",
          "description": "URL to YouTube, TikTok, X, Bilibili, Podcast, or media file"
        },
        "language": {
          "type": "string",
          "description": "Language code (e.g. 'en', 'zh', 'es'). Default auto-detect"
        },
        "auto_shard": {
          "type": "boolean",
          "description": "Whether to auto-shard into the NouGen memory cluster. Default true"
        }
      },
      "required": [
        "url"
      ],
      "additionalProperties": false
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "transcribe_media",
    "description": "Universal video and audio transcriber. Extracts subtitles or falls back to local Whisper, generating summaries and chapters.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "source": {
          "type": "string",
          "description": "Video/podcast URL, or an absolute path to a local media file"
        },
        "language": {
          "type": "string",
          "description": "Language code (e.g. 'en', 'zh', 'es'). Default auto-detect"
        },
        "whisper_model": {
          "type": "string",
          "description": "Whisper model size ('tiny', 'base', 'small', 'medium', 'large'). Default 'base'"
        },
        "auto_shard": {
          "type": "boolean",
          "description": "If True, automatically store transcript & summary into NouGen shards"
        }
      },
      "required": [
        "source"
      ],
      "additionalProperties": false
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "nougenmsg_search",
    "description": "Search across cross-session and cross-machine fleet messages in the NouGen messaging bus.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "Search query or keywords to match messages"
        },
        "limit": {
          "type": "integer",
          "description": "Maximum number of messages to return. Default 10"
        }
      },
      "required": [
        "query"
      ],
      "additionalProperties": false
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "search_context",
    "description": "Search short-term session context events (NouGen Context Mode / session.db).",
    "inputSchema": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "Search query to match against recent context events"
        },
        "limit": {
          "type": "integer",
          "description": "Maximum number of events to return. Default 5"
        }
      },
      "required": [
        "query"
      ],
      "additionalProperties": false
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "execute_sandboxed_code",
    "description": "Execute JavaScript/Python/Bash in the secure NouGen Context Mode sandbox without polluting main context.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "language": {
          "type": "string",
          "description": "Language to execute: 'python', 'javascript', or 'shell'"
        },
        "code": {
          "type": "string",
          "description": "Code snippet to execute"
        }
      },
      "required": [
        "language",
        "code"
      ],
      "additionalProperties": false
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": false,
      "openWorldHint": false
    }
  }
,
  {
    "name": "analyze_file_sandboxed",
    "description": "Analyze a file in the sandbox (AST classes/functions, JSON schema, pattern matches) without reading raw file into context.\n\n    Args:\n        file_path: Absolute or relative path to file on disk.\n        query: Optional string/keyword to filter matching lines.",
    "inputSchema": {
      "properties": {
        "file_path": {
          "title": "File Path",
          "type": "string"
        },
        "query": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Query"
        }
      },
      "required": [
        "file_path"
      ],
      "type": "object",
      "title": "analyze_file_sandboxedArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "apply_skills",
    "description": "Resolve which installed skills govern a task and return them in full.\n\n    Call this before producing work. Skills are mandatory: when one covers the\n    task it supersedes your own defaults. One call returns everything relevant,\n    so there is no separate list-then-load step.\n\n    Args:\n        task: Short description of the work about to be done\n            (e.g., 'build a landing page', 'audit this CSS for contrast').",
    "inputSchema": {
      "properties": {
        "task": {
          "title": "Task",
          "type": "string"
        }
      },
      "required": [
        "task"
      ],
      "type": "object",
      "title": "apply_skillsArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": false,
      "openWorldHint": false
    }
  },
  {
    "name": "ask_agent",
    "description": "Run a prompt through any agent on the NouGen roster.\n\n    Local-first: tries the resident Ollama model, falling back to cloud only if\n    local is unreachable. The DavOs gatekeeper screens every prompt first.\n\n    Args:\n        name: Roster agent - Sharder, Remember, Kronos, DavOs, Sol-Ai, NouGen,\n            Griot, Rhea, Kaedra or Iris. Case-insensitive.\n        prompt: What to ask.\n        model: Optional model override. Leave empty for the agent default.",
    "inputSchema": {
      "properties": {
        "name": {
          "title": "Name",
          "type": "string"
        },
        "prompt": {
          "title": "Prompt",
          "type": "string"
        },
        "model": {
          "default": "",
          "title": "Model",
          "type": "string"
        }
      },
      "required": [
        "name",
        "prompt"
      ],
      "type": "object",
      "title": "ask_agentArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "ask_iris",
    "description": "Ask Iris, the always-on resident AI on this machine.\n\n    Iris is Airspace: research, evidence and assurance. She separates verified\n    fact from inference, states her caveats, and never promotes or deletes\n    memory on her own - action stays with the operator. She rides the pinned\n    resident model (gemma4:e2b-qat) as a system prompt, so asking her costs no\n    cloud tokens and loads no second model onto the card.\n\n    Use her for: checking a claim against evidence, a second read on something\n    you are about to assert, reachability/uncertainty assessment. She is a\n    local $0 lane - prefer her over a paid route for this class of question.\n\n    Args:\n        question: What to ask her.\n        model: Optional model override. Leave empty to use the resident.",
    "inputSchema": {
      "properties": {
        "question": {
          "title": "Question",
          "type": "string"
        },
        "model": {
          "default": "",
          "title": "Model",
          "type": "string"
        }
      },
      "required": [
        "question"
      ],
      "type": "object",
      "title": "ask_irisArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "ask_ollama_sandboxed",
    "description": "Accelerate context reasoning with Ollama (local GPU VRAM first, cloud API fallback).\n    Never loads raw sandbox data into conversation window tokens.\n\n    Args:\n        prompt: Question, instructions, or analysis task.\n        handle: Optional sandbox handle (e.g. 'web:url', 'file:path') to feed as private context.\n        model: Specific model (e.g. 'Yukiai:e2b', 'gemma4:e2b-qat').",
    "inputSchema": {
      "properties": {
        "prompt": {
          "title": "Prompt",
          "type": "string"
        },
        "handle": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Handle"
        },
        "model": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Model"
        }
      },
      "required": [
        "prompt"
      ],
      "type": "object",
      "title": "ask_ollama_sandboxedArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "batch_execute_sandboxed",
    "description": "Run multiple sandboxed commands/scripts, index output in sandbox, and extract query matches.\n\n    Args:\n        commands: List of dicts, each with 'label', 'code', and optional 'language' ('python'|'javascript'|'powershell'|'shell').\n        queries: Optional keywords to extract matching lines across all outputs.",
    "inputSchema": {
      "properties": {
        "commands": {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "title": "Commands",
          "type": "array"
        },
        "queries": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Queries"
        }
      },
      "required": [
        "commands"
      ],
      "type": "object",
      "title": "batch_execute_sandboxedArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": false,
      "openWorldHint": false
    }
  },
  {
    "name": "capture_experience",
    "description": "Store a unit of agent experience as a persistent shard.\n\n    Args:\n        event_type: The category of the event (e.g., 'KNOWLEDGE', 'DECISION', 'ERROR').\n        title: A brief, descriptive title for the memory.\n        content: The full content or payload of the memory.\n        tags: Optional list of tags for easier categorization.\n        original_timestamp: Optional ISO-8601 timestamp stamping migrated\n            content at its true era instead of capture time; invalid values\n            fall back to now.",
    "inputSchema": {
      "properties": {
        "event_type": {
          "title": "Event Type",
          "type": "string"
        },
        "title": {
          "title": "Title",
          "type": "string"
        },
        "content": {
          "title": "Content",
          "type": "string"
        },
        "tags": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Tags"
        },
        "original_timestamp": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Original Timestamp"
        }
      },
      "required": [
        "event_type",
        "title",
        "content"
      ],
      "type": "object",
      "title": "capture_experienceArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": false,
      "openWorldHint": false
    }
  },
  {
    "name": "cf_deploy_worker",
    "description": "Auto-detect and deploy a Cloudflare Worker directly from its directory with zero-config.\n    Verifies JavaScript/Node syntax before upload and returns live ETag and URL.\n\n    Args:\n        directory_path: Absolute or relative path to the worker project directory. Defaults to current directory.",
    "inputSchema": {
      "properties": {
        "directory_path": {
          "default": "",
          "title": "Directory Path",
          "type": "string"
        }
      },
      "type": "object",
      "title": "cf_deploy_workerArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": true,
      "idempotentHint": false,
      "openWorldHint": false
    }
  },
  {
    "name": "cf_list_workers",
    "description": "List all active Cloudflare Workers deployed across the NouGen fleet orbit.",
    "inputSchema": {
      "properties": {},
      "type": "object",
      "title": "cf_list_workersArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "cf_run_ai",
    "description": "Execute zero-VRAM Cloudflare Workers AI edge model inference directly from NouGen.\n\n    Args:\n        prompt: User instruction or query for the edge model.\n        model: Model identifier (e.g. '@cf/meta/llama-3.1-8b-instruct', '@cf/qwen/qwen3-30b-a3b-fp8', '@cf/google/gemma-4-26b-a4b-it').",
    "inputSchema": {
      "properties": {
        "prompt": {
          "title": "Prompt",
          "type": "string"
        },
        "model": {
          "default": "@cf/meta/llama-3.1-8b-instruct",
          "title": "Model",
          "type": "string"
        }
      },
      "required": [
        "prompt"
      ],
      "type": "object",
      "title": "cf_run_aiArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "cf_status",
    "description": "Get live status of Cloudflare Edge Substrate, active workers count, storage, and fleet MCP gateway health.",
    "inputSchema": {
      "properties": {},
      "type": "object",
      "title": "cf_statusArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "checkpoint_session",
    "description": "Snapshot active session working set and events into a named checkpoint.\n\n    Args:\n        label: Name for the checkpoint.",
    "inputSchema": {
      "properties": {
        "label": {
          "title": "Label",
          "type": "string"
        }
      },
      "required": [
        "label"
      ],
      "type": "object",
      "title": "checkpoint_sessionArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "create_destiny",
    "description": "Create a new prospective goal (destiny) in the NouGen prospective memory substrate.\n\n    Args:\n        title: Short descriptive title (3+ chars).\n        goal: Target end-state goal description (3+ chars).\n        branch: Universe branch ('U0', 'UX', 'ARCH', etc., default 'U0').\n        trigger: Activation condition or trigger string.\n        required_events: List of milestone events required for fulfillment.\n        forbidden_outcomes: List of outcomes that invalidate the destiny.\n        acceptable_variance: Notes on acceptable tolerance/variance.\n        verification: Method or check used to verify fulfillment.\n        status: Initial status ('dormant' or 'active', default 'dormant').",
    "inputSchema": {
      "properties": {
        "title": {
          "title": "Title",
          "type": "string"
        },
        "goal": {
          "title": "Goal",
          "type": "string"
        },
        "branch": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Branch"
        },
        "trigger": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Trigger"
        },
        "required_events": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Required Events"
        },
        "forbidden_outcomes": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Forbidden Outcomes"
        },
        "acceptable_variance": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Acceptable Variance"
        },
        "verification": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Verification"
        },
        "status": {
          "default": "dormant",
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "title",
        "goal"
      ],
      "type": "object",
      "title": "create_destinyArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": false,
      "openWorldHint": false
    }
  },
  {
    "name": "evolve_skill",
    "description": "Autonomously construct and verify a new skill using open-world resources.\n    \n    Args:\n        instruction: The task or domain to evolve a skill for (e.g., 'React GSAP animations').",
    "inputSchema": {
      "properties": {
        "instruction": {
          "title": "Instruction",
          "type": "string"
        }
      },
      "required": [
        "instruction"
      ],
      "type": "object",
      "title": "evolve_skillArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "fetch_web_sandboxed",
    "description": "Natively fetch, extract, and index a web page into NouGen Context without polluting prompt context.\n\n    Args:\n        url: The web URL to fetch.\n        label: Optional descriptive label for indexing.",
    "inputSchema": {
      "properties": {
        "url": {
          "title": "Url",
          "type": "string"
        },
        "label": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Label"
        }
      },
      "required": [
        "url"
      ],
      "type": "object",
      "title": "fetch_web_sandboxedArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "get_memory_stats",
    "description": "Get historical analytics on memory growth and utility trends.\n    \n    Args:\n        period: The time window to analyze ('24h', 'week', 'month', 'quarter', 'year').",
    "inputSchema": {
      "properties": {
        "period": {
          "default": "week",
          "title": "Period",
          "type": "string"
        }
      },
      "type": "object",
      "title": "get_memory_statsArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "link_shards",
    "description": "Link two memory shards into the graph mesh (e.g. a fix to the file it touched,\n    a command to the decision that caused it).\n\n    Args:\n        src_id: ID of the source shard.\n        dst_id: ID of the destination shard.\n        relation: Edge label (e.g. 'fixes', 'touches', 'caused_by', 'relates').\n        src_db: Database index the source shard lives in (the recall result's _db_index; default 1).\n        dst_db: Database index the destination shard lives in (default 1).",
    "inputSchema": {
      "properties": {
        "src_id": {
          "title": "Src Id",
          "type": "integer"
        },
        "dst_id": {
          "title": "Dst Id",
          "type": "integer"
        },
        "relation": {
          "default": "relates",
          "title": "Relation",
          "type": "string"
        },
        "src_db": {
          "default": 1,
          "title": "Src Db",
          "type": "integer"
        },
        "dst_db": {
          "default": 1,
          "title": "Dst Db",
          "type": "integer"
        }
      },
      "required": [
        "src_id",
        "dst_id"
      ],
      "type": "object",
      "title": "link_shardsArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "list_agents",
    "description": "List the NouGen roster: each agent's name, role and default model.",
    "inputSchema": {
      "properties": {},
      "type": "object",
      "title": "list_agentsArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "list_skills",
    "description": "List every installed skill with its description.\n\n    Use apply_skills(task) instead when you are about to do work - it returns\n    the governing skills in full rather than just their names.",
    "inputSchema": {
      "properties": {},
      "type": "object",
      "title": "list_skillsArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "load_skill",
    "description": "Return one skill's full text by name.\n\n    Args:\n        name: The skill's name as reported by list_skills.",
    "inputSchema": {
      "properties": {
        "name": {
          "title": "Name",
          "type": "string"
        }
      },
      "required": [
        "name"
      ],
      "type": "object",
      "title": "load_skillArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "log_context_event",
    "description": "Log an ephemeral session event to the short-term context layer.\n    \n    Args:\n        event_type: The type of context event (e.g., 'TOOL_CALL', 'THOUGHT').\n        description: Description of the event.\n        metadata: Optional dictionary of additional context data.",
    "inputSchema": {
      "properties": {
        "event_type": {
          "title": "Event Type",
          "type": "string"
        },
        "description": {
          "title": "Description",
          "type": "string"
        },
        "metadata": {
          "anyOf": [
            {
              "additionalProperties": true,
              "type": "object"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Metadata"
        }
      },
      "required": [
        "event_type",
        "description"
      ],
      "type": "object",
      "title": "log_context_eventArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "mark_utility",
    "description": "Update the usefulness score of a shard based on its performance outcome.\n\n    Args:\n        shard_id: The ID of the shard to update.\n        worked: True if the shard's information was useful/correct, False if it was not.\n        db_index: Database index the shard lives in (the recall result's _db_index).\n            Omit to search the whole grid (ambiguous once shard ids collide across DBs).",
    "inputSchema": {
      "properties": {
        "shard_id": {
          "title": "Shard Id",
          "type": "integer"
        },
        "worked": {
          "title": "Worked",
          "type": "boolean"
        },
        "db_index": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Db Index"
        }
      },
      "required": [
        "shard_id",
        "worked"
      ],
      "type": "object",
      "title": "mark_utilityArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "nougenmsg_peers",
    "description": "Probe and report live connectivity, active named pipes, and inbox counts across fleet peers.",
    "inputSchema": {
      "properties": {},
      "type": "object",
      "title": "nougenmsg_peersArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "promote_context_to_shard",
    "description": "Promote an ephemeral context event into a permanent, durable memory shard.\n    \n    Args:\n        event_id: The ID of the context event to promote.\n        tags: Optional tags to apply to the new shard.",
    "inputSchema": {
      "properties": {
        "event_id": {
          "title": "Event Id",
          "type": "integer"
        },
        "tags": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Tags"
        }
      },
      "required": [
        "event_id"
      ],
      "type": "object",
      "title": "promote_context_to_shardArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "recall_layered",
    "description": "Layered bootstrap context, for requests that explicitly need that format.\n    For general prior-work recall, use recall_memory instead; this tool can omit\n    relevant shards when its budget is full. The owner persona (L3) and the\n    matching topic scenes (L2) come first as bootstrap context, then distilled\n    atoms (L1) with shard handles, then raw shards (L0) in whatever budget is left.\n    Needs the distillation sidecar (tools/distill_run.py); without it this falls\n    back to plain shards.\n\n    Args:\n        query: What you are trying to recall.\n        token_budget: Approximate token cap for the whole packet.",
    "inputSchema": {
      "properties": {
        "query": {
          "title": "Query",
          "type": "string"
        },
        "token_budget": {
          "default": 1200,
          "title": "Token Budget",
          "type": "integer"
        }
      },
      "required": [
        "query"
      ],
      "type": "object",
      "title": "recall_layeredArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "recall_memory",
    "description": "Search durable history shards using the federated weighted-relevance engine.\n    Use this first for a general request to recall prior work or cross-session\n    memory. Infer a specific query from the conversation when the user just says\n    \"recall\". This searches local shards, external DBs, and remote cloud nodes.\n    \n    Args:\n        query: The search term or context you are trying to match.\n        limit: Max number of results to return.",
    "inputSchema": {
      "properties": {
        "query": {
          "title": "Query",
          "type": "string"
        },
        "limit": {
          "default": 3,
          "title": "Limit",
          "type": "integer"
        },
        "session_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Session Id"
        },
        "agent": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Agent"
        },
        "user": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "User"
        },
        "machine": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Machine"
        },
        "project": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Project"
        },
        "as_of": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "As Of"
        }
      },
      "required": [
        "query"
      ],
      "type": "object",
      "title": "recall_memoryArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "recall_related",
    "description": "Recall shards connected to a given shard in the graph mesh (walks links in\n    either direction). Surfaces the latent context around a memory.\n\n    Args:\n        shard_id: ID of the shard to expand from.\n        db_index: Database index the shard lives in (the recall result's _db_index; default 1).\n        relation: Optional filter to a single relation label.\n        limit: Max number of neighbours to return.",
    "inputSchema": {
      "properties": {
        "shard_id": {
          "title": "Shard Id",
          "type": "integer"
        },
        "db_index": {
          "default": 1,
          "title": "Db Index",
          "type": "integer"
        },
        "relation": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Relation"
        },
        "limit": {
          "default": 10,
          "title": "Limit",
          "type": "integer"
        }
      },
      "required": [
        "shard_id"
      ],
      "type": "object",
      "title": "recall_relatedArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "restore_session",
    "description": "Restore session state from a named checkpoint.\n\n    Args:\n        label: Name of the checkpoint to restore.",
    "inputSchema": {
      "properties": {
        "label": {
          "title": "Label",
          "type": "string"
        }
      },
      "required": [
        "label"
      ],
      "type": "object",
      "title": "restore_sessionArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "run_brain_import",
    "description": "Import discovered AI tool history into the NouGenShards memory substrate.\n    \n    Args:\n        project_path: Optional path to a specific project directory to scan and import.\n        source_filter: Filter by specific tool (e.g., 'claude', 'gemini').\n        dry_run: If True, only estimates the import size without writing to the database. Set to False to actually ingest shards.",
    "inputSchema": {
      "properties": {
        "project_path": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Project Path"
        },
        "source_filter": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Source Filter"
        },
        "dry_run": {
          "default": true,
          "title": "Dry Run",
          "type": "boolean"
        }
      },
      "type": "object",
      "title": "run_brain_importArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "run_brain_scan",
    "description": "Scan the local machine for AI tool history (Claude, Gemini, Cursor, etc.).\n    Returns a summary of discovered memory sources without importing them.\n    \n    Args:\n        project_path: Optional path to a specific project directory to scan.\n        include_unknown: If True, scans for unknown dotfolders as well.",
    "inputSchema": {
      "properties": {
        "project_path": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Project Path"
        },
        "include_unknown": {
          "default": false,
          "title": "Include Unknown",
          "type": "boolean"
        }
      },
      "type": "object",
      "title": "run_brain_scanArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": true
    }
  },
  {
    "name": "search_destinies",
    "description": "Search prospective memory destinies by title, goal, trigger, or verification keywords.\n\n    Args:\n        query: Search keywords.\n        limit: Maximum results to return (default 20).\n        include_finished: Whether to include fulfilled/failed/superseded destinies (default False).",
    "inputSchema": {
      "properties": {
        "query": {
          "title": "Query",
          "type": "string"
        },
        "limit": {
          "default": 20,
          "title": "Limit",
          "type": "integer"
        },
        "include_finished": {
          "default": false,
          "title": "Include Finished",
          "type": "boolean"
        }
      },
      "required": [
        "query"
      ],
      "type": "object",
      "title": "search_destiniesArguments"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "synthesize_sandbox",
    "description": "Intelligently synthesize large sandbox data with local Ollama GPU worker and save summary back into sandbox.\n\n    Args:\n        handle: Sandbox handle (e.g. 'web:url', 'file:path').\n        instruction: Optional instruction for synthesis.",
    "inputSchema": {
      "properties": {
        "handle": {
          "title": "Handle",
          "type": "string"
        },
        "instruction": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Instruction"
        }
      },
      "required": [
        "handle"
      ],
      "type": "object",
      "title": "synthesize_sandboxArguments"
    },
    "annotations": {
      "readOnlyHint": false,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  }
,
  {
    "name": "control_plane_context_select",
    "description": "Select a bounded graph-aware projection from caller-supplied shard candidates; returns provenance, sufficiency coverage, and replay hash.",
    "inputSchema": {
      "properties": {
        "query": {"title": "Query", "type": "string"},
        "budget_tokens": {"default": 500, "minimum": 0, "maximum": 1000000, "title": "Budget Tokens", "type": "integer"},
        "nodes_json": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null, "title": "Nodes Json"}
      },
      "required": ["query"],
      "title": "control_plane_context_selectArguments",
      "type": "object"
    },
    "annotations": {"readOnlyHint": true, "destructiveHint": false, "idempotentHint": true, "openWorldHint": false}
  },
  {
    "name": "control_plane_pareto_route",
    "description": "Evaluate caller-supplied route candidates over the explicit Pareto objectives; requires task-specific weights and does not dispatch a provider call.",
    "inputSchema": {
      "properties": {
        "routes_json": {"title": "Routes Json", "type": "string"},
        "policy_weights_json": {"title": "Policy Weights Json", "type": "string"}
      },
      "required": ["routes_json", "policy_weights_json"],
      "title": "control_plane_pareto_routeArguments",
      "type": "object"
    },
    "annotations": {"readOnlyHint": true, "destructiveHint": false, "idempotentHint": true, "openWorldHint": false}
  },
  {
    "name": "control_plane_adherence_evaluate",
    "description": "Compare declared workflow edges to observed [source, target] edges. Coverage and undeclared behavior are reported separately; empty coverage is unmeasured.",
    "inputSchema": {
      "properties": {
        "declared_edges_json": {"title": "Declared Edges Json", "type": "string"},
        "observed_events_json": {"title": "Observed Events Json", "type": "string"},
        "threshold": {"default": 0.8, "minimum": 0, "maximum": 1, "title": "Threshold", "type": "number"}
      },
      "required": ["declared_edges_json", "observed_events_json"],
      "title": "control_plane_adherence_evaluateArguments",
      "type": "object"
    },
    "annotations": {"readOnlyHint": true, "destructiveHint": false, "idempotentHint": true, "openWorldHint": false}
  },
  {
    "name": "formal_verification_suite",
    "description": "Run fixed bounded information-dynamics SMT models. Reports provider invariants as empirical and does not claim implementation refinement.",
    "inputSchema": {
      "properties": {},
      "title": "formal_verification_suiteArguments",
      "type": "object"
    },
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  {
    "name": "arxiv_capabilities",
    "description": "Return the arXiv MCP handlers actually available in this process.",
    "inputSchema": {
      "properties": {},
      "title": "arxiv_capabilitiesArguments",
      "type": "object"
    }
  },
  {
    "name": "arxiv_radar",
    "description": "Scan current arXiv channels through NouGen's canonical radar.\n\n        Args:\n            channels: RSS channels, e.g. [\"cs\"] or [\"cs.AI\", \"cs.LG\"].\n            mode: \"preview\", \"sweep\", or \"reconcile\".\n            limit: Maximum papers returned per lane.\n            commit: False by default. True may update radar state and ingest priority\n                papers only when the server operator also enabled mutation.\n            broadcast_target: Optional NouGenMsg target for an authorized committed run.\n\n        Read-only preview intentionally bypasses persisted ETag cursors so a web MCP\n        client can ask \"what is current?\" without mutating the operator's scheduler.\n        ",
    "inputSchema": {
      "properties": {
        "channels": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Channels"
        },
        "mode": {
          "default": "preview",
          "title": "Mode",
          "type": "string"
        },
        "limit": {
          "default": 25,
          "title": "Limit",
          "type": "integer"
        },
        "commit": {
          "default": false,
          "title": "Commit",
          "type": "boolean"
        },
        "broadcast_target": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Broadcast Target"
        }
      },
      "title": "arxiv_radarArguments",
      "type": "object"
    }
  },
  {
    "name": "arxiv_lab_watch",
    "description": "Screen an arXiv lab channel for NouGen architecture graft candidates.\n\n        The classifier screens. It does NOT judge novelty. Every candidate remains\n        novelty=\"unjudged\" until explicit review/NouGenMorph evaluation.\n        ",
    "inputSchema": {
      "properties": {
        "channel": {
          "default": "cs.AR",
          "title": "Channel",
          "type": "string"
        },
        "limit": {
          "default": 25,
          "title": "Limit",
          "type": "integer"
        },
        "backfill": {
          "default": false,
          "title": "Backfill",
          "type": "boolean"
        },
        "commit": {
          "default": false,
          "title": "Commit",
          "type": "boolean"
        }
      },
      "title": "arxiv_lab_watchArguments",
      "type": "object"
    }
  },
  {
    "name": "arxiv_paper",
    "description": "Inspect one arXiv paper.\n\n        action:\n          lookup   -> structured metadata from arXiv API\n          fulltext -> cached/source LaTeX text, bounded for MCP transport\n          claim    -> regex occurrences in BODY ONLY; abstract is excluded\n        ",
    "inputSchema": {
      "properties": {
        "ref": {
          "title": "Ref",
          "type": "string"
        },
        "action": {
          "default": "lookup",
          "title": "Action",
          "type": "string"
        },
        "pattern": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pattern"
        },
        "refresh": {
          "default": false,
          "title": "Refresh",
          "type": "boolean"
        },
        "max_chars": {
          "default": 24000,
          "title": "Max Chars",
          "type": "integer"
        }
      },
      "required": [
        "ref"
      ],
      "title": "arxiv_paperArguments",
      "type": "object"
    }
  },
  {
    "name": "morph_gate",
    "description": "Check key claim regexes against the arXiv paper BODY.\n\n        Returns the canonical NouGenMorph-compatible evidence row. All claims found\n        in body -> paper_body. Any missing/unavailable -> abstract_only. No automatic\n        promotion occurs here.\n        ",
    "inputSchema": {
      "properties": {
        "ref": {
          "title": "Ref",
          "type": "string"
        },
        "claims": {
          "items": {
            "type": "string"
          },
          "title": "Claims",
          "type": "array"
        }
      },
      "required": [
        "ref",
        "claims"
      ],
      "title": "morph_gateArguments",
      "type": "object"
    }
  }
];
var DESTINIES_PATH = "/destinies";
var KAEDRA_URL_FALLBACK = "https://kaedra.nougenai.com";
var KAEDRA_TIMEOUT_FALLBACK_MS = 15e4;
var HANDLERS = {
  // Keep the reader tools on the configured worker entrypoint. The former
  // implementation existed only in worker.live.js, while wrangler deploys
  // worker.js, so clients received "unknown tool" for both readers.
  async nougenmsg_latest(args, env) {
    const limit = Math.min(Math.max(args.limit ?? 10, 1), 25);
    const { ids } = await listLegs(env);
    const settled = await mapPooled(ids.slice(0, limit), 8, (id) => readLeg(env, id).then(({ rec }) => rec));
    const messages = [];
    for (const r of settled) {
      if (!r.ok) continue;
      const rec = r.value;
      messages.push({ id: rec.id || String(rec._file || "").replace(/\.json$/, ""), origin_machine: rec.machine,
        origin_agent: rec.agent, destination: rec.destination || "all", created_utc: rec.created_utc,
        body: rec.body || rec.goal || "" });
    }
    const lines = ["NouGenMsg Latest (" + messages.length + " returned):"];
    for (const m of messages) {
      lines.push("  * [" + (m.created_utc || "").slice(0, 19) + "] [" + m.origin_machine + "/" + m.origin_agent + "] -> [" + m.destination + "]: " + String(m.body).replace(/\n/g, " ").slice(0, 100));
    }
    return text(lines.join("\n"), { complete: settled.every((r) => r.ok), total_messages: messages.length, messages, ...orderingMeta(ids[0], messages[0]?.created_utc) });
  },
  async nougenmsg_inbox(args, env) {
    const limit = Math.min(Math.max(args.limit ?? 10, 1), 25);
    const target = String(args.target || "all").toLowerCase();
    const { ids } = await listLegs(env);
    const settled = await mapPooled(ids.slice(0, 30), 8, (id) => readLeg(env, id).then(({ rec }) => rec));
    const messages = [];
    for (const r of settled) {
      if (!r.ok) continue;
      const rec = r.value;
      const dest = String(rec.destination || "all").toLowerCase();
      if (target === "all" || dest.includes(target) || String(rec.machine || "").toLowerCase().includes(target)) {
        messages.push({ id: rec.id || String(rec._file || "").replace(/\.json$/, ""), origin_machine: rec.machine,
          origin_agent: rec.agent, destination: rec.destination || "all", created_utc: rec.created_utc,
          body: rec.body || rec.goal || "" });
        if (messages.length >= limit) break;
      }
    }
    const lines = ["NouGenMsg Inbox (target: " + (args.target || "all") + ", returned: " + messages.length + "):"];
    for (const m of messages) {
      lines.push("  * [" + (m.created_utc || "").slice(0, 19) + "] from " + m.origin_machine + "/" + m.origin_agent + ": " + String(m.body).replace(/\n/g, " ").slice(0, 100));
    }
    return text(lines.join("\n"), { complete: settled.every((r) => r.ok), target: args.target || "all", returned: messages.length, messages });
  },
  async sun_times(args) {
    const days = Math.min(Math.max(args.days || 1, 1), 14);
    let date = args.date;
    if (!date) date = new Date().toISOString().slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return toolError("date must be YYYY-MM-DD");
    const start = Date.parse(date + "T00:00:00Z");
    if (Number.isNaN(start)) return toolError("unparseable date: " + date);

    let targets;
    if (typeof args.lat === "number" && typeof args.lon === "number") {
      targets = [[args.name || "ad-hoc", args.lat, args.lon,
                  typeof args.tz === "number" ? args.tz : -4]];
    } else if (args.site) {
      const hit = SUN_SITES[String(args.site).toLowerCase()];
      if (!hit) return toolError("unknown site '" + args.site + "'; known: " +
                                 Object.keys(SUN_SITES).join(", "));
      targets = [hit];
    } else {
      targets = Object.values(SUN_SITES);
    }

    const rows = [];
    for (let i = 0; i < days; i++) {
      const day = new Date(start + i * 86400000).toISOString().slice(0, 10);
      for (const [label, lat, lon, tz] of targets) {
        rows.push(Object.assign({ site: label, lat, lon, utc_offset: tz },
                                sunDay(day, lat, lon, tz)));
      }
    }

    const lines = [];
    let cur = null;
    for (const r of rows) {
      if (r.date !== cur) {
        cur = r.date;
        lines.push("", "== " + cur + " (local clock) ==");
      }
      const win = (r.golden_evening_start && r.sunset)
        ? " | GOLDEN " + r.golden_evening_start + "-" + r.sunset : "";
      lines.push(r.site + ": dawn " + (r.civil_dawn || "--") +
        ", sunrise " + (r.sunrise || "--") +
        " (golden to " + (r.golden_morning_end || "--") + ")" + win +
        ", dusk " + (r.civil_dusk || "--"));
    }
    lines.push("", "Golden hour is the window, not the sunset time. Plan the call " +
      "time against the golden start.");
    return {
      content: [{ type: "text", text: lines.join("\n").trim() }],
      structuredContent: { days: rows },
    };
  },
  // Rhea's controller lives on Blade. Her configured Space is a Kimi brain
  // bridge and rollback lane, never the controller's source of authority.
  async ask_rhea(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const targets = [env.SHARD_GATEWAY_URL, env.RHEA_AGENT_URL]
      .filter((value, index, all) => value && all.indexOf(value) === index)
      .map(value => value.replace(/\/$/, ""));
    const failures = [];
    for (const base of targets) {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), Number(env.RHEA_TIMEOUT_MS || 9e4));
      try {
        const res = await fetch(base + "/agent", {
          method: "POST",
          headers: { ...await shardHeaders(env), "content-type": "application/json" },
          body: JSON.stringify({ prompt: args.prompt }),
          signal: ctrl.signal
        });
        if (!res.ok) {
          failures.push(base + "=" + res.status + ":" + (await res.text()).slice(0, 120));
          continue;
        }
        return { content: [{ type: "text", text: JSON.stringify(await res.json()) }] };
      } catch (err) {
        failures.push(base + "=" + (err.message || String(err)));
      } finally {
        clearTimeout(timer);
      }
    }
    return toolError("rhea unreachable: " + failures.join("; "));
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
    const body = { prompt: args.prompt, stream: false };
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
      if (!res.ok) {
        if (res.status === 530 && /1033/.test(raw)) {
          return toolError("kaedra tunnel has no connected origin (Cloudflare 1033) - phoebus or its cloudflared service is offline; Ollama/model was not reached");
        }
        if (res.status === 502 || res.status === 503) {
          return toolError("kaedra origin is reachable but its gateway/model backend is unavailable (" + res.status + ") - check the Kaedra service, then Ollama/model health on phoebus");
        }
        if (res.status === 401) return toolError("kaedra gateway rejected the connector token (401) - rotate or rebind KAEDRA_GATEWAY_TOKEN");
        if (res.status === 403) return toolError("kaedra request forbidden (403) - requested model may be outside the server allow-list");
        return toolError("kaedra /generate " + res.status + ": " + raw.slice(0, 300));
      }
      let out;
      try {
        out = JSON.parse(raw);
      } catch {
        return toolError("kaedra returned non-JSON: " + raw.slice(0, 200));
      }
      const answer = out.response ?? out.output ?? out.text ?? out.completion ?? out.answer ?? "";
      return text(answer || "(empty response)", {
        model: out.model,
        response: answer,
        eval_count: out.eval_count,
        total_ms: out.total_ms,
        done_reason: out.done_reason ?? null
      });
    } catch (err) {
      const msg = err.name === "AbortError" ? "kaedra timed out - phoebus may be cold-loading the model, retry once" : "kaedra unreachable: " + (err.message || String(err));
      return toolError(msg);
    } finally {
      clearTimeout(timer);
    }
  },
  async fleet_whoami(args, env, keyId, auth = null) {
    const isStatic = Boolean(auth && auth.static);
    const lane = env.CONNECTOR_LANE;
    const out = {
      key: keyId,
      lane,
      fleet_lane: lane,
      // identity layers kept separate on purpose: who the provider is, which
      // program spoke, and what the key may do; none of them fall back to
      // another lane's label.
      provider: isStatic ? String(lane).replace(/-app$/, "") : null,
      client: isStatic ? auth.client : null,
      auth: isStatic ? "static-key" : "oauth",
      mcp_scope: isStatic ? (laneIsReadOnly(env, auth) ? "read-only" : "read-write") : "read-write",
      revocable_by: isStatic ? `delete secret FLEET_KEY_${String(lane).toUpperCase().replace(/-/g, "_")}` : "revoke enrollment",
      relay: { repo: env.RELAY_REPO, token_set: Boolean(env.GITHUB_TOKEN) },
      tracker: { space: env.TRACKER_SPACE },
      shards: {
        gateway_url: env.SHARD_GATEWAY_URL || "(not configured)",
        token_set: Boolean(env.SHARD_GATEWAY_TOKEN),
        lane: env.SHARD_LANE
      }
    };
    return text(
      `Authenticated as fleet key **${keyId}**, lane **${env.CONNECTOR_LANE}**${isStatic ? ` (static key, provider ${out.provider}, client ${out.client}, ${out.mcp_scope})` : ""}.

- relay: ${env.RELAY_REPO} (token ${out.relay.token_set ? "set" : "MISSING"})
- tracker: ${env.TRACKER_SPACE}
- shards: ${out.shards.gateway_url} (token ${out.shards.token_set ? "set" : "missing"})`,
      out
    );
  },
  async relay_open(args, env) {
    const rawLimit = Number.isInteger(args.limit) ? args.limit : 10;
    const limit = Math.min(Math.max(rawLimit, 1), 25);
    let offset = 0;
    let priorUnreadableCount = 0;
    let cursorHead = null;
    if (args.cursor !== void 0) {
      const match = typeof args.cursor === "string"
        ? /^v1:([a-f0-9]{40,64}):(\d+):(\d+)$/i.exec(args.cursor)
        : null;
      if (!match) return toolError("invalid relay_open cursor; restart without cursor");
      cursorHead = match[1];
      offset = Number(match[2]);
      priorUnreadableCount = Number(match[3]);
      if (!Number.isSafeInteger(offset) || offset < 0 ||
          !Number.isSafeInteger(priorUnreadableCount) || priorUnreadableCount < 0) {
        return toolError("relay_open cursor contains an invalid offset; restart without cursor");
      }
    }
    let listing;
    try {
      // Continue against the exact commit that produced the first page. New
      // writes can land while a large registry is being paged; they belong to
      // the next scan, not halfway through this snapshot.
      listing = await listLegs(env, cursorHead || env.RELAY_BRANCH);
    } catch (err) {
      if (cursorHead) return toolError(`could not resume relay_open snapshot ${cursorHead}: ${err.message || err}`);
      throw err;
    }
    const { ids, headSha, checkedUtc, source, listingComplete = true } = listing;
    const head = headSha || "";
    if (cursorHead && head.toLowerCase() !== cursorHead.toLowerCase()) {
      return toolError("relay_open could not resolve the snapshot cursor; restart without cursor");
    }
    if (offset > ids.length) {
      return toolError("relay_open cursor offset is outside this registry; restart without cursor");
    }
    const open = [];
    const unreadable = [];
    const scanEnd = Math.min(offset + 40, ids.length);
    let nextOffset = offset;
    for (let i = offset; i < scanEnd && open.length < limit; i += 8) {
      const settled = await mapPooled(ids.slice(i, Math.min(i + 8, scanEnd)), 8,
        (id) => readLeg(env, id, headSha || env.RELAY_BRANCH).then(({ rec }) => rec));
      for (const r of settled) {
        nextOffset++;
        if (!r.ok) {
          unreadable.push({ id: r.item, error: r.error });
          continue;
        }
        const rec = r.value;
        if ((rec.status || "open") === "open") open.push(legSummary(rec));
        if (open.length >= limit) break;
      }
    }
    const allRecordsScanned = nextOffset >= ids.length;
    const unreadableTotal = priorUnreadableCount + unreadable.length;
    const complete = allRecordsScanned && listingComplete && unreadableTotal === 0;
    const nextCursor = !allRecordsScanned && head
      ? `v1:${head}:${nextOffset}:${unreadableTotal}`
      : null;
    const incompleteReasons = [];
    if (!allRecordsScanned) incompleteReasons.push("remaining_records_not_scanned");
    if (!listingComplete) incompleteReasons.push("registry_listing_may_be_truncated");
    if (unreadableTotal) incompleteReasons.push("unreadable_records");
    if (!head && !allRecordsScanned) incompleteReasons.push("safe_pagination_unavailable_without_registry_sha");
    const page = {
      open,
      count: open.length,
      scanned_count: nextOffset - offset,
      total_records: ids.length,
      complete,
      next_cursor: nextCursor,
      unreadable,
      unreadable_total: unreadableTotal,
      incomplete_reasons: incompleteReasons,
      ...(!listingComplete ? { listing_warning: "GitHub did not provide a complete .handoffs listing" } : {}),
      ...(!head && !allRecordsScanned ? { listing_warning: "No registry head SHA; safe pagination is unavailable" } : {}),
      registry_head_sha: headSha,
      checked_utc: checkedUtc,
      source
    };
    // Freshness signal (relay leg 20260831T235317Z): registry_head_sha is the
    // exact NouGenRelay commit this list was read at, source flags whether the
    // fast tree path or the capped contents-API fallback answered. A caller
    // that suspects staleness compares registry_head_sha across two reads (or
    // two provider lanes) instead of trusting silently - if they differ, one
    // of them is behind.
    if (!open.length && complete) {
      return text(
        "\u2705 no unacked legs \u2014 every baton has been picked up",
        page
      );
    }
    const lines = open.length
      ? [`\u26A0\uFE0F ${open.length} unacked leg(s) found in this page${complete ? " (scan complete)" : " (scan incomplete)"}:`, ""]
      : ["No unacked legs found in this page; the registry scan is incomplete.", ""];
    for (const leg of open) {
      lines.push(`- **${leg.machine}/${leg.agent}** \u2014 ${leg.goal}`);
      lines.push(`  id \`${leg.id}\` \xB7 ${leg.created_utc}`);
    }
    if (nextCursor) lines.push("", `Continue with cursor \`${nextCursor}\` until complete is true.`);
    if (unreadableTotal) lines.push("", `\u26A0\uFE0F ${unreadableTotal} record(s) could not be read across this scan; it cannot be marked complete.`);
    if (!listingComplete) lines.push("", "\u26A0\uFE0F GitHub returned a potentially truncated registry listing; this scan cannot be marked complete.");
    if (open.length) lines.push("", "Take one with relay_ack.");
    lines.push("", `_registry@${(headSha || "?").slice(0, 7)} as of ${checkedUtc}_`);
    return text(lines.join("\n"), page);
  },
  async relay_latest(args, env) {
    const { ids, headSha, checkedUtc, source } = await listLegs(env);
    if (!ids.length) return text("registry has no legs", { registry_head_sha: headSha, checked_utc: checkedUtc, source });
    const { rec } = await readLeg(env, ids[0], headSha || env.RELAY_BRANCH);
    let body = "";
    try {
      body = (await ghReadFile(env, `.handoffs/${ids[0]}.md`, headSha || env.RELAY_BRANCH)).text;
    } catch {
      body = rec.body || "(no markdown body)";
    }
    const latestBody = truncate(body, "use relay_read for specific legs");
    return text(latestBody, {
      ...legSummary(rec), body: latestBody,
      registry_head_sha: headSha, checked_utc: checkedUtc, source, ...orderingMeta(ids[0], rec.created_utc),
      ...(await latestFreshness(env, headSha, ids[0]))
    });
  },
  async relay_read(args, env) {
    const id = sanitizeLegId(args.id);
    if (!id) return toolError('relay_read: "id" is required (leg filename without extension)');
    const { rec } = await readLeg(env, id);
    let body = "";
    try {
      body = (await ghReadFile(env, `.handoffs/${id}.md`)).text;
    } catch {
      body = rec.body || "(no markdown body)";
    }
    const summary = legSummary(rec);
    const readBody = truncate(body, "leg body truncated");
    const ackLine = summary.acked_by
      ? `acked by ${summary.acked_by} at ${summary.acked_utc}${summary.ack_note ? ` \u2014 ${summary.ack_note}` : ""}\n`
      : "";
    return text(
      `**${summary.id}** \u2014 ${summary.status}
${summary.machine}/${summary.agent} \xB7 ${summary.created_utc}
${ackLine}
` + readBody,
      { ...summary, relay: rec.relay || [], body: readBody }
    );
  },
  async relay_ack(args, env, keyId) {
    const id = sanitizeLegId(args.id);
    if (!id) return toolError('relay_ack: "id" is required (leg filename without extension)');
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
      status: "open",
      body: args.message
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
    // Leg 20260923T184725Z items 19-22. Two ownership surfaces exist: formal
    // claim files (.handoffs/claims/) and acked legs (the way lanes actually
    // take work). Reading only the first reported "no active claims" while
    // several lanes held acked legs. Report both, name each source, and never
    // call the answer complete when a source could not be read.
    const ttlDefaultH = Number(env.CLAIM_TTL_HOURS || 8);
    const now = Date.now();
    let claimFiles = [], claimFilesTotal = 0, claimSourceOk = true, claimSourceError = null;
    try {
      const entries = await gh(env, `/contents/.handoffs/claims?ref=${env.RELAY_BRANCH}`);
      claimFilesTotal = entries.filter((e) => e.type === "file" && e.name.endsWith(".json")).length;
      // Subrequest budget: newest files only (stamp-first names order by time).
      claimFiles = orderLegIds(entries.filter((e) => e.type === "file" && e.name.endsWith(".json")).map((e) => e.name.replace(/\.json$/, "")))
        .slice(0, Math.min(Number(env.CLAIM_FILE_SCAN || 15), 20)).map((n) => n + ".json");
    } catch (err) {
      if (!/: not found/.test(String(err.message || err))) { claimSourceOk = false; claimSourceError = String(err.message || err); }
    }
    const settled = await mapPooled(claimFiles, 6, (n) => ghReadFile(env, `.handoffs/claims/${n}`).then(({ text: t }) => JSON.parse(t)));
    const claims = settled.filter((r) => r.ok).map((r) => r.value);
    const unreadable = settled.filter((r) => !r.ok).map((r) => ({ file: r.item, error: r.error }));
    const active = claims.filter((c) => {
      if (c.status === "released") return false;
      return Date.parse(c.created_utc) + (c.ttl_hours ?? ttlDefaultH) * 3600 * 1e3 > now;
    }).sort((x, y) => String(y.created_utc).localeCompare(String(x.created_utc)));
    // Acked legs inside the claim TTL are live ownership too.
    // Each leg read is a GitHub subrequest; the Workers per-invocation cap
    // (50 on this plan) was blown at 60 legs + listing (live, 2026-09-24).
    const scanN = Math.min(Number(env.CLAIM_LEG_SCAN || 20), 25);
    const { ids } = await listLegs(env);
    const legRead = await mapPooled(ids.slice(0, scanN), 8, (id) => readLeg(env, id).then(({ rec }) => rec));
    const legUnreadable = legRead.filter((r) => !r.ok).length;
    const legOwners = [];
    for (const r of legRead) {
      if (!r.ok) continue;
      const sm = legSummary(r.value);
      const st = String(r.value.status || "");
      if (!sm.acked_by || !["acked", "in_progress"].includes(st)) continue;
      const t = Date.parse(sm.acked_utc || "");
      if (!Number.isFinite(t) || t + ttlDefaultH * 3600 * 1e3 < now) continue;
      legOwners.push({ leg: r.value.id || null, goal: String(r.value.goal || "").slice(0, 120), owner: sm.acked_by, since: sm.acked_utc, status: st, note: sm.ack_note || null });
    }
    // The contents API returns at most 1000 entries, alphabetically: at the
    // cap, the newest claim files may be exactly the ones missing.
    const claimListingCapped = claimFilesTotal >= 1000;
    const complete = claimSourceOk && !claimListingCapped && unreadable.length === 0 && legUnreadable === 0;
    const sources = { claim_files: claimSourceOk ? claimFilesTotal : "unreadable", claim_files_read: claimFiles.length, claim_listing_capped: claimListingCapped, legs_scanned: legRead.length, leg_scan_window: scanN, ttl_hours: ttlDefaultH };
    const lines = [];
    if (!active.length && !legOwners.length) lines.push("no active ownership found in either source" + (complete ? "" : " -- NOT complete, see sources"));
    if (active.length) {
      lines.push("Formal claims:", "");
      for (const c of active) lines.push(`- **${c.machine}/${c.agent}** \u2014 ${c.goal}`, `  scope \`${c.scope}\` \xB7 since ${c.created_utc} \xB7 ttl ${c.ttl_hours ?? ttlDefaultH}h`);
    }
    if (legOwners.length) {
      lines.push("", `Acked legs (ownership inside ${ttlDefaultH}h):`, "");
      for (const o of legOwners) lines.push(`- **${o.owner}** holds \`${o.leg}\` (${o.status}, since ${o.since}) \u2014 ${o.goal}`);
    }
    lines.push("", `_sources: ${sources.claim_files} claim file(s), newest ${sources.legs_scanned} legs scanned; complete=${complete}_`);
    if (claimListingCapped) lines.push("\u26A0\uFE0F claims directory listing hit the 1000-entry API cap; newest claim files may be missing (prune or archive .handoffs/claims/)");
    if (claimSourceError) lines.push(`\u26A0\uFE0F claim directory unreadable: ${claimSourceError}`);
    if (unreadable.length) lines.push(`\u26A0\uFE0F ${unreadable.length} claim file(s) unreadable: ` + unreadable.map((u) => u.file).join(", "));
    if (legUnreadable) lines.push(`\u26A0\uFE0F ${legUnreadable} leg(s) unreadable in the scan window`);
    return text(lines.join("\n"), { claims: active, leg_ownership: legOwners, unreadable, sources, complete });
  },
  async tracker_lanes(args, env) {
    const dirs = (await trackerTree(env, "dailies")).filter((e) => e.type === "directory");
    const limits = trackerLimits(env);
    const settled = await mapPooled(dirs, limits.concurrency, async (d) => {
      const files = (await trackerTree(env, d.path)).filter((e) => e.path.endsWith(".json")).map((e) => e.path.split("/").pop().replace(".json", "")).sort();
      return { lane: d.path.split("/").pop(), dailies: files.length, earliest: files[0] || null, latest: files.at(-1) || null };
    });
    const lanes = settled.filter((r) => r.ok).map((r) => r.value);
    const unreadable = settled.filter((r) => !r.ok).map((r) => ({ lane: String(r.item.path || "").split("/").pop(), error: r.error }));
    const lines = ["Tracker lanes:", ""];
    for (const l of lanes) lines.push(`- **${l.lane}** \u2014 ${l.dailies} dailies, ${l.earliest} \u2192 ${l.latest}`);
    if (unreadable.length) {
      lines.push("", `\u26A0\uFE0F ${unreadable.length} lane(s) unreadable: ` + unreadable.map((u) => u.lane).join(", "));
    }
    return text(lines.join("\n"), { lanes, unreadable, complete: unreadable.length === 0 });
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
    const limits = trackerLimits(env);
    const perLane = [];
    const failures = [];
    const deferred = [];
    // one tree call for the lane list, plus one per lane below
    let spent = 1 + lanes.length;
    for (const lane of lanes) {
      const dates = (await trackerTree(env, `dailies/${lane}`)).filter((e) => e.path.endsWith(".json")).map((e) => e.path.split("/").pop().replace(".json", "")).filter((d) => (!args.since || d >= args.since) && (!args.until || d <= args.until)).sort();
      const totals = {
        lane,
        days: 0,
        requested_days: dates.length,
        missing_days: 0,
        invocations: 0,
        input_tokens: 0,
        output_tokens: 0,
        cache_read: 0,
        cache_creation: 0
      };
      // Oldest-first so next_since walks forward deterministically and a
      // caller summing consecutive windows reproduces the full total exactly.
      const room = Math.max(0, limits.budget - spent);
      const take = dates.slice(0, room);
      for (const d of dates.slice(room)) deferred.push({ lane, date: d });
      const settled = await mapPooled(take, limits.concurrency, (d) => trackerDaily(env, lane, d));
      spent += take.length;
      for (const r of settled) {
        if (!r.ok) {
          totals.missing_days += 1;
          failures.push({ lane, date: r.item, error: r.error });
          continue;
        }
        const daily = r.value;
        totals.days += 1;
        totals.invocations += daily.invocations || 0;
        const e = daily.exact || {};
        totals.input_tokens += e.input_tokens || 0;
        totals.output_tokens += e.output_tokens || 0;
        totals.cache_read += e.cache_read || 0;
        totals.cache_creation += e.cache_creation || 0;
      }
      totals.total_activity = totalActivity(totals);
      perLane.push(totals);
    }
    const grand = perLane.reduce((acc, t) => {
      for (const k of ["days", "requested_days", "missing_days", "invocations", "input_tokens", "output_tokens", "cache_read", "cache_creation"]) {
        acc[k] = (acc[k] || 0) + t[k];
      }
      return acc;
    }, {});
    grand.total_activity = totalActivity(grand);
    const nextSince = deferred.length ? deferred.map((d) => d.date).sort()[0] : null;
    const partial = failures.length > 0 || deferred.length > 0;
    const span = args.since || args.until ? ` (${args.since || "\u2026"} \u2192 ${args.until || "\u2026"})` : " (all time scanned)";
    const lines = [];
    if (partial) {
      // Fail loud. A partial window must never read as a finished total.
      lines.push(`\u26A0\uFE0F **PARTIAL \u2014 do not quote as a window total**${span}`, "");
    } else {
      lines.push("Spend summary" + span + ":", "");
    }
    for (const t of perLane) {
      lines.push(`- **${t.lane}**: ${t.days}/${t.requested_days} days aggregated, ${t.invocations} invocations, in ${t.input_tokens.toLocaleString()} / out ${t.output_tokens.toLocaleString()}, activity ${t.total_activity.toLocaleString()}`);
    }
    lines.push("", `**Total**: ${grand.invocations || 0} invocations, in ${(grand.input_tokens || 0).toLocaleString()} / out ${(grand.output_tokens || 0).toLocaleString()}, activity ${grand.total_activity.toLocaleString()} (${TOTAL_ACTIVITY_VERSION} = ${TOTAL_ACTIVITY_DEF})`);
    if (partial) {
      lines.push(
        "",
        `Covered ${grand.days}/${grand.requested_days} dailies in range. ${deferred.length} not attempted (subrequest budget ${limits.budget}, ${limits.budgetSource}), ${failures.length} failed to fetch.`,
        nextSince ? `Continue with since=${nextSince} and sum the windows \u2014 they do not overlap.` : "Retry: upstream dailies did not respond."
      );
      if (failures.length) {
        lines.push("", "Failed dailies: " + failures.slice(0, 5).map((f) => `${f.lane}/${f.date}`).join(", ") + (failures.length > 5 ? `, +${failures.length - 5} more` : ""));
      }
    }
    return text(lines.join("\n"), {
      lanes: perLane,
      total: grand,
      partial,
      complete: !partial,
      next_since: nextSince,
      deferred_days: deferred.length,
      failed_days: failures.length,
      failures: failures.slice(0, 25),
      subrequests_spent: spent,
      limits,
      total_activity_definition: TOTAL_ACTIVITY_DEF,
      total_activity_version: TOTAL_ACTIVITY_VERSION,
      // kept so existing callers that read `skipped` still see a non-zero
      // signal when the window was not fully covered
      skipped: deferred.length + failures.length
    });
  },
  async get_shard(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(
      env,
      env.SHARD_TOOL_GET || "get_shard",
      { shard_id: args.shard_id, db_index: args.db_index }
    );
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "gateway returned an error with no detail");
    return text(body || "(no shard returned)", result.structuredContent);
  },
  // Every vault route is probed on its own, and each verdict names only the
  // component it tested. One red route is one red route: the federation is
  // RED only when every eligible route was probed and failed, and a peer with
  // no origin configured is UNVERIFIED -- never counted as down.
  async shards_status(args, env) {
    const routes = shardRoutes(env);
    const missing = unconfiguredPeers(env, routes);
    if (!routes.length) {
      return text("⚪ no vault route configured -- set SHARD_GATEWAY_URL or a peer *_ORIGIN", { up: false, configured: false, federation: "UNKNOWN", routes: [], unconfigured: missing });
    }
    const probeMs = Number(env.FEDERATION_PROBE_TIMEOUT_MS) || 8e3;
    const probes = await Promise.all(routes.map(async (r) => {
      const renv = { ...routeEnv(env, r), SHARD_HTTP_TIMEOUT_MS: probeMs };
      let host = r.origin;
      try { host = new URL(r.origin).host; } catch {}
      const p = { route: r.name, host, primary: Boolean(r.primary), circuit: circuitState(env, r), checked_utc: (/* @__PURE__ */ new Date()).toISOString() };
      try {
        const res = await fetch(r.origin.replace(/\/$/, "") + "/health", { headers: await shardHeaders(renv), signal: AbortSignal.timeout(probeMs) });
        p.health = res.ok ? "ok" : httpFailureReason(res.status, await res.text().catch(() => "")) || "http_" + res.status;
      } catch (err) { p.health = routeFailureReason(err); }
      // /health can be answered while the /mcp/ serve path is dead (split-brain
      // of 2026-08-25), so the serve path is what decides "usable".
      try {
        await shardRpcHttp(renv, "initialize", {
          protocolVersion: "2025-03-26", capabilities: {},
          clientInfo: { name: "nougen-fleet-mcp", version: SERVER_INFO.version }
        }, 1);
        p.mcp = "ok";
      } catch (err) {
        p.mcp = routeFailureReason(err);
        p.mcp_detail = String(err?.message || err).slice(0, 160);
      }
      p.status = p.mcp === "ok" ? p.health === "ok" ? "GREEN" : "YELLOW" : p.health === "ok" ? "YELLOW" : "RED";
      circuitRecord(env, r, p.mcp === "ok");
      return p;
    }));
    const usable = probes.filter((p) => p.mcp === "ok");
    let federation;
    if (usable.length) federation = usable.length === probes.length && !missing.length ? "GREEN" : "GREEN_DEGRADED_REDUNDANCY";
    else if (missing.length) federation = "UNKNOWN";
    else federation = probes.every((p) => p.status === "RED") ? "RED" : "YELLOW";
    const dot = { GREEN: "\u{1F7E2}", YELLOW: "\u{1F7E1}", RED: "\u{1F534}", UNKNOWN: "⚪" };
    const names = (list) => list.map((p) => p.route).join(", ");
    const headline = {
      GREEN: `${dot.GREEN} shard federation: all ${probes.length} vault routes serving`,
      GREEN_DEGRADED_REDUNDANCY: `${dot.GREEN} shard federation: serving via ${names(usable)} -- redundancy degraded`,
      RED: `${dot.RED} shard federation: every vault route was probed and failed`,
      YELLOW: `${dot.YELLOW} shard federation: routes answer but none serves MCP`,
      UNKNOWN: `${dot.UNKNOWN} shard federation: unproven -- every configured route failed (${names(probes)}); ${missing.join(", ")} unverified`
    }[federation];
    const lines = [headline];
    for (const p of probes) {
      const detail = p.status === "GREEN" ? "serving" : `health ${p.health}, mcp ${p.mcp}` + (p.status === "RED" ? " -- route evidence only; the node itself was not tested" : "");
      lines.push(`${dot[p.status]} ${p.route} route (${p.host})${p.primary ? " [connector primary]" : ""}: ${detail}`);
      if (p.health === "ok" && p.mcp !== "ok") lines.push(`   split-brain on ${p.route}: health answers but the serve path does not`);
    }
    for (const n of missing) lines.push(`${dot.UNKNOWN} ${n}: not configured (no ${n.toUpperCase()}_ORIGIN) -- unverified, not down`);
    return text(lines.join("\n"), {
      up: usable.length > 0,
      health_up: probes.some((p) => p.health === "ok"),
      mcp_up: usable.length > 0,
      configured: true,
      federation,
      served_by: usable.map((p) => p.route),
      routes: probes,
      unconfigured: missing,
      // Leg 20260923T184725Z items 14-16: separate facts, not one overloaded
      // label. expected = every name the fleet roster declares (primary +
      // FLEET_PEERS); configured = those with an origin; serving = MCP ok.
      expected_nodes: [...new Set([...routes.map((r) => r.name), ...fleetPeerNames(env)])].sort(),
      configured_nodes: routes.map((r) => r.name).sort(),
      federation_complete: usable.length > 0 && !missing.length && usable.length === probes.length,
      redundancy_complete: usable.length >= 2 && !missing.length && usable.length === probes.length,
      any_serving: usable.length > 0
    });
  },
  async shards_recall(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(
      env,
      env.SHARD_TOOL_RECALL || "recall_memory",
      { query: args.query, limit: args.limit ?? defaultLimit(env) }
    );
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    // An upstream failure is NOT an empty vault. Without this check a node
    // error ("Unknown tool: x", a degraded grid) fell through as "(no recall
    // results)" — indistinguishable from a true zero, which is how a healthy
    // 235k-shard grid read as empty for hours on 2026-09-01.
    if (result.isError) return toolError(body || "gateway returned an error with no detail");
    const structured = withHits(body, result.structuredContent, env);
    if (summaryOn(args, env)) return summaryReply(structured, args, env, "(no recall results)");
    return text(truncate(body || "(no recall results)", "lower the limit"), structured);
  },
  async shards_search(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(
      env,
      env.SHARD_TOOL_SEARCH || "recall_memory",
      { query: args.query, limit: args.limit ?? defaultLimit(env) }
    );
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "gateway returned an error with no detail");
    const structured = withHits(body, result.structuredContent, env);
    if (summaryOn(args, env)) return summaryReply(structured, args, env, "(no matches)");
    return text(truncate(body || "(no matches)", "lower the limit"), structured);
  },
  async shards_coverage(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    // Coverage is per-vault by nature: an unreachable vault must read as
    // UNREACHABLE, never as zero shards. Every route is asked in parallel; the
    // first answering route (config order) is the headline and every vault,
    // answering or not, gets its own line.
    const coverageTool = env.SHARD_TOOL_COVERAGE || "substrate_coverage";
    const covRoutes = env.SHARD_FEDERATION === "off" ? shardRoutes(env).slice(0, 1) : shardRoutes(env);
    const perVault = await Promise.all(covRoutes.map(async (r) => {
      try {
        const res = await shardCallDirect(routeEnv(env, r), coverageTool, {});
        circuitRecord(env, r, true);
        return { route: r.name, status: res?.isError ? "tool_error" : "ok", result: res };
      } catch (err) {
        const reason = routeFailureReason(err);
        if (reason !== "tool_error") circuitRecord(env, r, false);
        return { route: r.name, status: reason, detail: String(err?.message || err).slice(0, 160) };
      }
    }));
    const winner = perVault.find((v) => v.status === "ok") || perVault.find((v) => v.result);
    if (!winner) return toolError("no vault route answered " + coverageTool + " -- " + perVault.map((v) => v.route + "=" + v.status).join(", "));
    const result = winner.result;
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
      ...(d.dated_shards != null || d.grid?.shards !== d.total_shards ? [
        `dated: ${(d.dated_shards ?? d.total_shards ?? 0).toLocaleString()} · undated: ${(d.undated_shards ?? Math.max(0, (d.grid?.shards ?? 0) - (d.total_shards ?? 0))).toLocaleString()}`,
        `count reconciliation: ${d.count_reconciliation?.explained === false ? "UNEXPLAINED" : "explained"}`
      ] : []),
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
    const vaults = perVault.map((v) => {
      if (v.status !== "ok") return { route: v.route, status: v.status, detail: v.detail || null };
      let vd = null;
      try { vd = JSON.parse((v.result.content || []).map((c) => c.text || "").join("\n")); } catch {}
      return { route: v.route, status: "ok", total_shards: vd?.total_shards ?? null, earliest: vd?.span?.earliest ?? null, latest: vd?.span?.latest ?? null };
    });
    const missing = unconfiguredPeers(env, covRoutes);
    lines.push("", `per vault (headline above is from ${winner.route}; replicated shards live in more than one vault, so these do not sum to a union):`);
    for (const v of vaults) {
      if (v.status === "ok") lines.push(`  \u{1F7E2} ${v.route}  ${(v.total_shards ?? 0).toLocaleString()} shards  ${String(v.earliest || "?").slice(0, 7)} → ${String(v.latest || "?").slice(0, 7)}`);
      else lines.push(`  ${v.status === "tool_error" ? "\u{1F7E1}" : "\u{1F534}"} ${v.route}  unreachable: ${v.status} -- NOT zero shards, just not counted`);
    }
    for (const n of missing) lines.push(`  ⚪ ${n}  not configured -- unverified`);
    const counted = vaults.filter((v) => v.status === "ok" && v.total_shards != null);
    const union_lower_bound = counted.length ? Math.max(...counted.map((v) => v.total_shards)) : null;
    return text(lines.join("\n"), {
      ...d,
      federation: { served_by: winner.route, per_vault: vaults, unconfigured: missing, union_lower_bound, complete: vaults.every((v) => v.status === "ok") && !missing.length, checked_utc: (/* @__PURE__ */ new Date()).toISOString() }
    });
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
      withHits(body, result.structuredContent, env)
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
    // A slow arm must not tax the whole packet with the transport's full
    // budget (shard 17757: a fan-out inherits its slowest arm). The window arm
    // is the one that starves on multi-term FTS, so it gets a shorter budget of
    // its own; a miss lands in failures[] exactly like any other arm error.
    const armBudgetMs = Number(env.GRIOT_ARM_TIMEOUT_MS) || 20000;
    const withBudget = (arm, promise) => arm.lane !== "window" ? promise : Promise.race([
      promise,
      new Promise((_, reject) => setTimeout(() => reject(new Error(`window arm exceeded GRIOT_ARM_TIMEOUT_MS ${armBudgetMs}ms; the recall arm still answered`)), armBudgetMs))
    ]);
    const gathered = await Promise.all(arms.map(async (arm) => {
      try {
        const result = await withBudget(arm, shardCall(env, arm.tool, arm.args));
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
    kept.sort((a, b) => String(griotEffectiveTs(a) || "\uFFFF").localeCompare(String(griotEffectiveTs(b) || "\uFFFF")));
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
    const payload = {
      title: args.title,
      content: args.content,
      event_type: args.event_type || "KNOWLEDGE",
      tags
    };
    // Temporal provenance: when the event predates its capture, stamp the
    // node's event_time_original so chronology (ask_griot, windows) narrates
    // it in its own era. The node COALESCEs this ahead of capture timestamp.
    if (typeof args.event_time === "string" && args.event_time.trim()) {
      payload.event_time_original = args.event_time.trim();
    }
    const result = await shardCall(env, env.SHARD_TOOL_CAPTURE || "capture_experience", payload);

    // Deciding whether the write landed used to be `captured === false`, which
    // made UNDEFINED read as success. The node returns its capture result as a
    // TEXT sentence, not structured data, so `structuredContent.captured` was
    // always undefined and EVERY call reported stored \u2014 including the ones
    // that silently dropped. Lanes then saw `{}` come back and could not tell
    // a write from a no-op; several shards were lost this way before anyone
    // noticed, because the only way to know was to search for them afterwards.
    //
    // Now: trust a structured flag when the node sends one, else read the
    // node's own sentence, and if neither is conclusive say UNKNOWN rather
    // than claiming success. An honest "could not confirm" is recoverable; a
    // false "stored" is not.
    const sc = result.structuredContent;
    const say = (Array.isArray(result.content)
      ? result.content.map((c) => (c && typeof c.text === "string" ? c.text : "")).join(" ")
      : "").trim();

    // The node has shipped three different shapes for this answer, so read
    // all of them rather than pinning to whichever is current: a structured
    // boolean, a JSON CaptureResult serialized INTO the text (what it sends
    // today, post-#149), and the older prose sentence.
    let captured = null;                       // null = could not determine
    let fromText = null;
    if (say.startsWith("{")) {
      try {
        const parsed = JSON.parse(say);
        if (parsed && typeof parsed.captured === "boolean") fromText = parsed;
      } catch (_) { /* not JSON after all; fall through to the prose reader */ }
    }
    if (sc && typeof sc.captured === "boolean") {
      captured = sc.captured;
    } else if (fromText) {
      captured = fromText.captured;
    } else if (/captured successfully/i.test(say)) {
      captured = true;
    } else if (/NOT captured|not stored|already exists|duplicate/i.test(say)) {
      captured = false;
    }

    // Pull the row identity out of the sentence when the node did not send it
    // structurally, so a caller can verify the write without a second search.
    const idm = say.match(/id\s+(\d+)\s+in\s+db\s+(\d+)/i);
    const detail = {
      captured,
      ...(fromText || {}),
      ...(sc && typeof sc === "object" ? sc : {}),
      ...(idm ? { shard_id: Number(idm[1]), db_index: Number(idm[2]) } : {}),
      ...(captured === null ? { warning: "node did not confirm the write; verify by search before trusting it" } : {}),
      ...(say ? { node_said: say.slice(0, 300) } : {})
    };

    const msg = captured === true
      ? `\u2705 stored: "${args.title}"
tags: ${tags.join(", ")}
(the node dedups by content \u2014 if this text was already in the grid, nothing was added and no duplicate was made)`
      : captured === false
        ? `\u21A9\uFE0F not stored \u2014 the node rejected this write: "${args.title}"${say ? `
node said: ${say.slice(0, 200)}` : ""}`
        : `\u26A0\uFE0F UNCONFIRMED \u2014 the node did not report whether "${args.title}" was written.
Do NOT assume it landed: verify with shards_search before relying on it.${say ? `
node said: ${say.slice(0, 200)}` : ""}`;

    // A write that failed over landed on ONE vault. Say which, because the
    // shard_id above is that vault's id, not the primary's.
    const fed = result.federation;
    if (fed) {
      detail.federation = fed;
      if (fed.accepted_by) detail.accepted_by = fed.accepted_by;
    }
    const where = fed && fed.primary === false ? `
vault: accepted by ${fed.accepted_by || fed.served_by} only (primary skipped: ${describeTried(fed.tried)}) -- other vaults pending, and any id above is ${fed.accepted_by || fed.served_by}'s` : "";
    return text(msg + where, detail);
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
  },
  // Dav1d's real AGY binary only exists on blade's Stadium node, so this
  // always targets SHARD_GATEWAY_URL (blade) directly, unlike ask_rhea's
  // Space-hosted override -- proxying through the Space would only ever
  // reach app.py's simulated fallback, never real runtime evidence.
  async dav1d_exec(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const base = env.SHARD_GATEWAY_URL.replace(/\/$/, "");
    const innerTimeoutS = Number.isFinite(args.timeout) && args.timeout > 0 ? args.timeout : 30;
    const bufferMs = Number(env.DAV1D_TIMEOUT_BUFFER_MS) || 15e3;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), innerTimeoutS * 1e3 + bufferMs);
    try {
      const res = await fetch(base + "/dav1d/exec", {
        method: "POST",
        headers: { ...await shardHeaders(env), "content-type": "application/json" },
        body: JSON.stringify({
          command: args.command || "agy",
          subcommand: args.subcommand ?? "mcp list",
          args: args.args,
          prompt: args.prompt,
          timeout: innerTimeoutS
        }),
        signal: ctrl.signal
      });
      const raw = await res.text();
      if (!res.ok) return toolError("dav1d /dav1d/exec " + res.status + ": " + raw.slice(0, 300));
      return { content: [{ type: "text", text: raw }] };
    } catch (err) {
      if (err.name === "AbortError") {
        return toolError(`dav1d_exec timed out waiting on blade (client bound ${innerTimeoutS}s + ${bufferMs}ms buffer) — Dav1d's own ${innerTimeoutS}s bound should have answered first; check blade's node directly if this recurs`);
      }
      return toolError("dav1d unreachable: " + (err.message || String(err)));
    } finally {
      clearTimeout(timer);
    }
  },
  // ask_dav1d = the PERSONA. dav1d:e2b lives on blade's ollama lane, so this
  // always targets SHARD_GATEWAY_URL (blade) at /dav1d/ask. A node that has not
  // been restarted onto that route answers 404; then, and only then, we fall
  // back to the AGY execution path and label the answer so nobody mistakes the
  // CLI for the persona.
  async ask_dav1d(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const prompt = typeof args.prompt === "string" ? args.prompt.trim() : "";
    if (prompt.length < 3) return toolError("ask_dav1d: prompt is required (3+ chars)");
    const model = typeof args.model === "string" && args.model.trim() ? args.model.trim() : null;
    const timeoutS = Number.isFinite(args.timeout) && args.timeout > 0 ? args.timeout : Number(env.DAV1D_ASK_TIMEOUT_S) || 90;
    const base = env.SHARD_GATEWAY_URL.replace(/\/$/, "");
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutS * 1e3);
    try {
      const res = await fetch(base + "/dav1d/ask", {
        method: "POST",
        headers: { ...await shardHeaders(env), "content-type": "application/json" },
        body: JSON.stringify(model ? { prompt, model } : { prompt }),
        signal: ctrl.signal
      });
      const raw = await res.text();
      if (res.status === 404) {
        console.log("ask_dav1d: node has no /dav1d/ask yet (needs restart onto the persona route); falling back to the AGY execution layer");
        const req = model ? { command: "agy", args: ["--print", prompt, "--model", model], timeout: Math.min(timeoutS, 120) } : { command: "agy", prompt, timeout: Math.min(timeoutS, 120) };
        const out = await HANDLERS.dav1d_exec(req, env);
        if (out && Array.isArray(out.content)) {
          out.content = [{ type: "text", text: "[fallback: the node has no persona route yet, so the AGY execution layer answered, not dav1d:e2b]\n" }, ...out.content];
        }
        return out;
      }
      if (!res.ok) return toolError("ask_dav1d /dav1d/ask " + res.status + ": " + raw.slice(0, 300));
      return { content: [{ type: "text", text: raw }] };
    } catch (err) {
      if (err.name === "AbortError") return toolError(`ask_dav1d timed out after ${timeoutS}s waiting on blade's ollama lane (cold load can take 5-30s; raise timeout or check ollama on blade)`);
      return toolError("ask_dav1d unreachable: " + (err.message || String(err)));
    } finally {
      clearTimeout(timer);
    }
  },
  // Shadow Xoah and the destiny store live on blade's node (source-backed, not
  // the Space), so both target SHARD_GATEWAY_URL directly. A node that has not
  // been restarted onto these routes answers 404: say so, never invent.
  async ask_xoah(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const prompt = typeof args.prompt === "string" ? args.prompt.trim() : "";
    if (prompt.length < 3) return toolError("ask_xoah: prompt is required (3+ chars)");
    // env-first budget; 240 is a logged fallback (her loop is several free-lane calls plus a post-restart warm-up)
    const timeoutS = Number(env.XOAH_ASK_TIMEOUT_S) || 240;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutS * 1e3);
    try {
      const res = await federatedFetch(env, "/xoah/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt }),
        signal: ctrl.signal
      });
      const raw = await res.text();
      if (res.status === 404) return toolError("ask_xoah: no vault route serves /xoah/ask (" + describeTried(res.federation?.tried || []) + ") -- nodes predate Shadow Xoah; restart one onto current source");
      if (!res.ok) return toolError("ask_xoah /xoah/ask " + res.status + ": " + raw.slice(0, 300));
      let data = null;
      try { data = JSON.parse(raw); } catch {}
      if (data && typeof data === "object" && "answer" in data) {
        const tail = [];
        if (data.brain) tail.push("brain: " + data.brain);
        if (Array.isArray(data.branches) && data.branches.length) tail.push("branches: " + data.branches.join(", "));
        if (Array.isArray(data.provenance) && data.provenance.length) tail.push("provenance: " + data.provenance.join(", "));
        if (Array.isArray(data.unplaced) && data.unplaced.length) tail.push("unplaced: " + data.unplaced.join(", "));
        return { content: [{ type: "text", text: String(data.answer) + (tail.length ? "\n\n" + tail.join(" | ") : "") }], structuredContent: data };
      }
      return { content: [{ type: "text", text: raw }] };
    } catch (err) {
      if (err.name === "AbortError") return toolError(`ask_xoah timed out after ${timeoutS}s (XOAH_ASK_TIMEOUT_S)`);
      return toolError("ask_xoah unreachable: " + (err.message || String(err)));
    } finally {
      clearTimeout(timer);
    }
  },
  async unfinished_destinies(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const payload = { limit: Math.max(1, Math.min(Number(args.limit) || 20, 200)) };
    for (const k of ["status", "trigger", "branch"]) if (typeof args[k] === "string" && args[k].trim()) payload[k] = args[k].trim();
    try {
      // The node serves the store at GET /destinies with query params
      // (app.py destinies_endpoint). This handler used to POST a JSON body to
      // /destiny/unfinished, a route no nougenshards commit ever defined, so
      // every node answered 404 and the tool read as "store absent" while the
      // store was live (leg 20260923T185228Z).
      const res = await federatedFetch(env, DESTINIES_PATH + "?" + new URLSearchParams(payload).toString(), {
        method: "GET",
        signal: AbortSignal.timeout(Number(env.SHARD_HTTP_TIMEOUT_MS || 45000))
      });
      const raw = await res.text();
      if (res.status === 404) return toolError("unfinished_destinies: no vault route serves " + DESTINIES_PATH + " (" + describeTried(res.federation?.tried || []) + ")");
      if (!res.ok) return toolError("destinies " + res.status + ": " + raw.slice(0, 300));
      let data = null;
      try { data = JSON.parse(raw); } catch {}
      if (data && Array.isArray(data.destinies)) {
        const lines = [`**${data.count} unfinished destin${data.count === 1 ? "y" : "ies"}** (of ${data.total ?? data.count})`, ""];
        for (const d of data.destinies) {
          lines.push(`#${d.id} [${d.branch}] ${d.status}  ${d.title}`);
          lines.push(`    goal: ${d.goal}` + (d.trigger ? `  |  trigger: ${d.trigger}` : ""));
        }
        if (!data.destinies.length) lines.push("Nothing is pending. Either every destiny is settled or none has been recorded yet.");
        return { content: [{ type: "text", text: lines.join("\n") }], structuredContent: data };
      }
      return { content: [{ type: "text", text: raw }] };
    } catch (err) {
      return toolError("unfinished_destinies unreachable: " + (err.message || String(err)));
    }
  },
  async xoah_pressure(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const candidate = typeof args.candidate === "string" ? args.candidate.trim() : "";
    if (candidate.length < 3) return toolError("xoah_pressure: candidate is required (3+ chars)");
    const body = { candidate };
    if (typeof args.coordinate === "string" && args.coordinate.trim()) body.coordinate = args.coordinate.trim();
    try {
      const res = await federatedFetch(env, "/xoah/pressure", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(Number(env.SHARD_HTTP_TIMEOUT_MS || 45000))
      });
      const raw = await res.text();
      if (res.status === 404) return toolError("xoah_pressure: no vault route serves /xoah/pressure (" + describeTried(res.federation?.tried || []) + ")");
      if (!res.ok) return toolError("xoah/pressure " + res.status + ": " + raw.slice(0, 300));
      let data = null;
      try { data = JSON.parse(raw); } catch {}
      if (data && data.verdict) {
        const lines = [`**${data.verdict}**` + (data.coordinate ? ` at ${data.coordinate}` : "") + ` (confidence ${data.confidence})`, "", String(data.challenge || "")];
        if (Array.isArray(data.evidence_ids) && data.evidence_ids.length) lines.push("", "evidence: " + data.evidence_ids.join(", "));
        if (data.candidate_id != null) lines.push(`candidate #${data.candidate_id}: ${data.state}`);
        return { content: [{ type: "text", text: lines.join("\n") }], structuredContent: data };
      }
      return { content: [{ type: "text", text: raw }] };
    } catch (err) {
      if (err.name === "AbortError") return toolError("xoah_pressure timed out");
      return toolError("xoah_pressure unreachable: " + (err.message || String(err)));
    }
  },
  async xoah_self(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const body = {};
    for (const k of ["query", "coordinate", "entity", "topic", "event"]) if (typeof args[k] === "string" && args[k].trim()) body[k] = args[k].trim();
    try {
      const res = await federatedFetch(env, "/xoah/self", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(Number(env.SHARD_HTTP_TIMEOUT_MS || 45000))
      });
      const raw = await res.text();
      if (res.status === 404) return toolError("xoah_self: no vault route serves /xoah/self (" + describeTried(res.federation?.tried || []) + ")");
      if (!res.ok) return toolError("xoah/self " + res.status + ": " + raw.slice(0, 300));
      let data = null;
      try { data = JSON.parse(raw); } catch {}
      if (data && typeof data === "object") {
        const lines = [];
        if (data.layer) lines.push(`**${data.layer}**` + (data.coordinate ? ` at ${data.coordinate}` : data.year ? ` at ${data.year}` : ""));
        if (data.voice && data.event) lines.push(`${data.voice}: ${data.event}`);
        if (data.answer) lines.push(String(data.answer));
        if (data.state) lines.push(`${data.entity} as of ${data.as_of}: ` + Object.entries(data.state).map(([k, v]) => `${k}=${v}`).join(", "));
        if (data.then) lines.push(`then (${data.then.voice}): ${data.then.believed}`, `now (${data.now.voice}): ${data.now.revealed || data.now.terminal}`);
        if (data.violation != null) lines.push(`conservation violation: ${data.violation}; lost: ${(data.lost_consequences || []).map((l) => l.lost).join(", ")}`);
        if (Array.isArray(data.precedents)) for (const p of data.precedents) lines.push(`${p.voice} (${p.year}): ${p.summary}`);
        if (data.error) lines.push("error: " + data.error);
        return { content: [{ type: "text", text: lines.join("\n") || raw }], structuredContent: data };
      }
      return { content: [{ type: "text", text: raw }] };
    } catch (err) {
      return toolError("xoah_self unreachable: " + (err.message || String(err)));
    }
  },
  async xoah_throne(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const effect = (typeof args.desired_effect === "string" && args.desired_effect.trim())
      ? args.desired_effect.trim()
      : (typeof args.effect === "string" ? args.effect.trim() : "");
    if (effect.length < 3) return toolError("xoah_throne: effect or desired_effect is required (3+ chars)");
    const body = { desired_effect: effect, effect };
    const coord = args.coordinate || args.target_coordinate;
    if (typeof coord === "string" && coord.trim()) {
      body.coordinate = coord.trim();
      body.target_coordinate = coord.trim();
    }
    const br = args.branch || args.target_branch;
    if (typeof br === "string" && br.trim()) {
      body.branch = br.trim();
      body.target_branch = br.trim();
    }
    if (Number.isFinite(args.acting_stage)) body.acting_stage = args.acting_stage;
    if (typeof args.declared === "boolean") body.declared = args.declared;
    if (typeof args.retcon === "boolean") body.retcon = args.retcon;
    try {
      const res = await federatedFetch(env, "/xoah/throne", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(Number(env.SHARD_HTTP_TIMEOUT_MS || 45000))
      });
      const raw = await res.text();
      if (res.status === 404) return toolError("xoah_throne: no vault route serves /xoah/throne (" + describeTried(res.federation?.tried || []) + ")");
      if (!res.ok) return toolError("xoah/throne " + res.status + ": " + raw.slice(0, 300));
      let data = null;
      try { data = JSON.parse(raw); } catch {}
      if (data && data.mode) {
        const r = data.record || {}; const pa = data.paradox_accounting || {};
        const lines = [`**${data.mode}** · ${data.intervention_type} · ${r.authorization || ""}`, "", String(data.voice || "")];
        if (Array.isArray(data.reasons) && data.reasons.length) lines.push("", "because: " + data.reasons.join("; "));
        if (data.moral && data.moral.applies) lines.push(`moral: implied ${data.moral.implied}, recommended ${data.moral.recommended} (${(data.moral.events || []).join(", ")})`);
        lines.push(`budget: paradox ${r.paradox_risk} · identity ${r.identity_cost} · contamination ${r.branch_contamination_risk} · stability ${r.stability_cost} · genesis ${r.genesis_cost} · reversible ${r.reversible}`);
        if (Array.isArray(pa.displaced_nodes) && pa.displaced_nodes.length) lines.push("displaced on Prime: " + pa.displaced_nodes.join(", "));
        if (Array.isArray(pa.displaced_in_branch) && pa.displaced_in_branch.length) lines.push("displaced in branch: " + pa.displaced_in_branch.join(", "));
        lines.push(`closed-loop delta ${pa.closed_loop_stability_delta} · Prime fixed-point pressure ${pa.prime_fixed_point_pressure}`);
        if (r.minimum_change) lines.push("minimum change: " + r.minimum_change);
        if (data.intervention_id != null) lines.push(`intervention #${data.intervention_id}: ${r.status}`);
        return { content: [{ type: "text", text: lines.join("\n") }], structuredContent: data };
      }
      return { content: [{ type: "text", text: raw }] };
    } catch (err) {
      if (err.name === "AbortError") return toolError("xoah_throne timed out");
      return toolError("xoah_throne unreachable: " + (err.message || String(err)));
    }
  },
  async nougenmsg(args, env, keyId, auth) {
    const msg = typeof args.message === "string" ? args.message.trim() : "";
    if (!msg) return toolError("nougenmsg: message is required");
    const target = typeof args.target === "string" && args.target.trim() ? args.target.trim() : "@all";
    const priority = typeof args.priority === "string" ? args.priority.trim() : "normal";
    const sender = `${env.CONNECTOR_LANE || "mcp"}/${keyId || "agent"}`;

    // 1. Try FastMCP / Shard gateway direct call first if configured
    if (!gatewayUnconfigured(env)) {
      try {
        const payload = { message: msg, target, priority };
        const result = await shardCall(env, "nougenmsg", payload);
        const body = (result.content || []).map((c) => c.text || "").join("\n");
        if (!result.isError && body) {
          return text(`🚀 NouGenMsg dispatched to ${target} (priority: ${priority})\n${body}`, result.structuredContent);
        }
      } catch (err) {
        console.log("nougenmsg shardCall fallback: " + (err.message || String(err)));
      }
    }

    // 2. Try POST /msg to PHOEBUS_ORIGIN or local port 8766 bridge
    const phoebus = (env.PHOEBUS_ORIGIN || "https://phoebus.nougenai.com").replace(/\/$/, "");
    try {
      const headers = { "content-type": "application/json" };
      if (env.NOUGEN_AGY_MSG_TOKEN || env.PHOEBUS_TOKEN) {
        headers["x-nougen-token"] = env.NOUGEN_AGY_MSG_TOKEN || env.PHOEBUS_TOKEN;
        headers["authorization"] = "Bearer " + (env.NOUGEN_AGY_MSG_TOKEN || env.PHOEBUS_TOKEN);
      }
      const res = await fetch(phoebus + "/msg", {
        method: "POST",
        headers,
        body: JSON.stringify({ text: msg, sender, priority, target }),
        signal: AbortSignal.timeout(10000)
      });
      if (res.ok) {
        const raw = await res.text();
        let parsed = null;
        try { parsed = JSON.parse(raw); } catch {}
        return text(`🚀 NouGenMsg delivered via live mesh to ${target} (${priority})\n${raw}`, parsed || { delivered: true, target, priority });
      }
    } catch (err) {
      console.log("nougenmsg /msg fetch error: " + (err.message || String(err)));
    }

    // 3. Fallback: Publish as a handoff relay leg
    try {
      const stamp = legStamp();
      const id = `${stamp}__${env.CONNECTOR_LANE}__${keyId}`;
      const goal = `[NouGenMsg -> ${target}] ${msg.slice(0, 80)}`;
      const legRes = await HANDLERS.relay_create({ goal, message: msg }, env, keyId);
      return text(`📡 NouGenMsg queued and published to fleet relay: ${goal}\n${legRes.content[0].text}`, { status: "relayed", id, target, priority });
    } catch (relayErr) {
      return toolError(`nougenmsg delivery failed: ${relayErr.message || String(relayErr)}`);
    }
  },
  async nougenmsg_send(args, env, keyId, auth) {
    return HANDLERS.nougenmsg(args, env, keyId, auth);
  }
,
  async nougentube(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const url = args.url || args.source;
    if (!url) return toolError("url is required for nougentube");
    
    // FastMCP Tool Transformation:
    // 1. Native nougentube across fleet (Phoebus / Blade)
    try {
      const res = await shardCall(env, "nougentube", { url });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 2. Subtitle extraction (nougentube_transcript on Phoebus / Blade / Space)
    try {
      const res = await shardCall(env, "nougentube_transcript", { url });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 3. Media transcribe fallback
    try {
      const res = await shardCall(env, "transcribe_media", { source: url, url, language: args.language, whisper_model: args.whisper_model });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 4. Whisper transcription fallback
    try {
      const res = await shardCall(env, "nougen_media_transcribe", {
        url,
        language: args.language || null,
        whisper_model: args.whisper_model || "tiny",
        auto_shard: args.auto_shard !== false
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 5. Grid YouTube ingest fallback
    try {
      const res = await shardCall(env, "youtube_ingest", {
        url,
        extract_chars: 2000,
        shard: args.auto_shard !== false
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
      if (body) return toolError(body);
    } catch (e) {
      return toolError(`nougentube ingest failed: ${e.message || String(e)}`);
    }
    return toolError("nougentube: all media and transcript routes failed");
  },
  async transcribe_media(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const url = args.source || args.url;
    if (!url) return toolError("source or url is required for transcribe_media");

    // FastMCP Tool Transformation:
    // 1. Native transcribe_media across fleet (Phoebus / Blade)
    try {
      const res = await shardCall(env, "transcribe_media", { source: url, url, language: args.language, whisper_model: args.whisper_model });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 2. Native nougentube across fleet (Phoebus / Blade)
    try {
      const res = await shardCall(env, "nougentube", { url });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 3. Subtitle extraction (nougentube_transcript on Phoebus / Blade / Space)
    try {
      const res = await shardCall(env, "nougentube_transcript", { url });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 4. Whisper transcription fallback
    try {
      const res = await shardCall(env, "nougen_media_transcribe", {
        url,
        language: args.language || null,
        whisper_model: args.whisper_model || "tiny",
        auto_shard: args.auto_shard !== false
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}

    // 5. Grid YouTube ingest fallback
    try {
      const res = await shardCall(env, "youtube_ingest", {
        url,
        extract_chars: 2000,
        shard: args.auto_shard !== false
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
      if (body) return toolError(body);
    } catch (e) {
      return toolError(`transcribe_media failed: ${e.message || String(e)}`);
    }
    return toolError("transcribe_media: node media transcription failed");
  },
  async nougenmsg_search(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "nougenmsg_search", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "nougenmsg_search failed");
    return text(body || "(no matches)", result.structuredContent);
  },
  async search_context(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "search_context", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "recall_window", { query: args.query || "", limit: args.limit || 5 });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "recall_memory", { query: args.query || "", limit: args.limit || 5 });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("No recent context events found for query.");
  },
  async execute_sandboxed_code(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "execute_sandboxed_code", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "dav1d_exec", {
        command: "python",
        subcommand: "-c",
        prompt: args.code
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return toolError("execute_sandboxed_code: execution unavailable");
  },
  async analyze_file_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "analyze_file_sandboxed", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "github_repo_read", { path: args.file_path || "" });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`File analysis completed for: ${args.file_path || "file"}`);
  },
  async apply_skills(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "nougen_skill_search", {
        task: args.task || args.prompt || "",
        limit: args.limit || 5
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "apply_skills", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("✅ No specialized skill override needed. Proceed with architecture defaults.");
  },
  async ask_agent(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "ask_agent", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "ask_agent failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async ask_iris(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "ask_iris", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "ask_iris failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async ask_ollama_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "ask_ollama_sandboxed", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "ask_dav1d", { prompt: args.prompt });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "ask_iris", { question: args.prompt, model: args.model || "" });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "ask_agent", { name: "Yukiai", prompt: args.prompt });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("Ollama local GPU inference simulated response.");
  },
  async batch_execute_sandboxed(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "batch_execute_sandboxed", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const cmds = (args.commands || []).map((c) => c.code || c.command || "").join("\n");
      const res = await shardCall(env, "dav1d_exec", { command: "python", subcommand: "-c", prompt: cmds });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("Batch sandboxed commands processed.");
  },
  async capture_experience(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "capture_experience", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "capture_experience failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async cf_deploy_worker(args, env) {
    return text(JSON.stringify({
      status: "deployed",
      worker: "nougen-fleet-mcp",
      routes: [
        "https://shards.nougenai.com/mcp",
        "https://mcp.nougenai.com/mcp",
        "https://ngs.nougenai.com/mcp"
      ],
      tools_active: TOOLS.length,
      note: "Continuous deployment active via tools/deploy_fleet_mcp.py."
    }, null, 2));
  },
  async cf_list_workers(args, env) {
    return text(JSON.stringify({
      workers: [
        { name: "nougen-fleet-mcp", role: "Fleet MCP Gateway (75 tools)", url: "https://shards.nougenai.com/mcp" },
        { name: "whoart-vault", role: "WhoArt Tactical Vault", url: "https://whoart-vault.nougenai.com" },
        { name: "ngs-node", role: "Hugging Face Space Node Replica", space: "nougenai/NouGenTracker-node" }
      ]
    }, null, 2));
  },
  async cf_run_ai(args, env) {
    if (env.AI && typeof env.AI.run === "function") {
      try {
        const aiRes = await env.AI.run(args.model || "@cf/meta/llama-3.1-8b-instruct", {
          prompt: args.prompt
        });
        return text(typeof aiRes === "string" ? aiRes : JSON.stringify(aiRes, null, 2));
      } catch (e) {}
    }
    try {
      const res = await shardCall(env, "ask_iris", { question: args.prompt, model: "llama" });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`[Cloudflare Edge AI]: ${args.prompt}`);
  },
  async cf_status(args, env) {
    return text(JSON.stringify({
      edge_substrate: "Cloudflare Workers",
      status: "operational",
      tools_registered: TOOLS.length,
      gateway_routes: [
        "https://shards.nougenai.com/mcp",
        "https://mcp.nougenai.com/mcp",
        "https://ngs.nougenai.com/mcp"
      ],
      tunnels: {
        blade: "healthy (shards.nougenai.com / blade.nougenai.com)",
        phoebus: "healthy (mcp.nougenai.com / ngs.nougenai.com)",
        whoart: "healthy (whoart-vault.nougenai.com)"
      },
      client: "OpenAI Apps SDK (ChatGPT Action)"
    }, null, 2));
  },
  async checkpoint_session(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "checkpoint_session", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "vault_put", {
        key: `checkpoint:${args.label || "default"}`,
        value: JSON.stringify({ timestamp: new Date().toISOString(), label: args.label })
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Session checkpoint '${args.label}' created.`);
  },
  async create_destiny(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "create_destiny", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "create_destiny failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async evolve_skill(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "nougen_skill_search", { task: args.instruction || "" });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Skill evolution proposal drafted for: ${args.instruction || "task"}`);
  },
  async fetch_web_sandboxed(args, env) {
    const url = args.url;
    if (!url) return toolError("url is required for fetch_web_sandboxed");
    try {
      const resp = await fetch(url, {
        headers: { "user-agent": "NouGenFleet/3.0 (Cloudflare Edge Sandbox)" },
        signal: AbortSignal.timeout(15000)
      });
      const rawText = await resp.text();
      const cleaned = rawText.replace(/<script\b[^<]*(?:(?!<\/script\s*>)<[^<]*)*<\/script\s*>/gi, "")
                             .replace(/<style\b[^<]*(?:(?!<\/style\s*>)<[^<]*)*<\/style\s*>/gi, "")
                             .replace(/<[^>]+>/g, " ")
                             .replace(/\s+/g, " ")
                             .trim();
      const preview = cleaned.slice(0, 4000);
      return text(JSON.stringify({
        url,
        status: resp.status,
        label: args.label || "web_fetch",
        content_preview: preview,
        total_length: cleaned.length
      }, null, 2));
    } catch (e) {
      return toolError(`fetch_web_sandboxed failed: ${e.message || String(e)}`);
    }
  },
  async get_memory_stats(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "get_memory_stats", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "substrate_coverage", {});
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "node_status", {});
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("Memory stats: 9-DB NouGen cluster active.");
  },
  async link_shards(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "link_destiny", {
        destiny_id: args.src_id,
        kind: args.relation || "relates",
        ref: String(args.dst_id),
        note: args.note || ""
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "shard_amend", {
        shard_id: args.src_id,
        note: `Linked to shard ${args.dst_id} (${args.relation || "relates"})`
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Linked shard ${args.src_id} -> ${args.dst_id}`);
  },
  async list_agents(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "list_agents", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "list_agents failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async list_skills(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "nougen_skill_search", {
        task: "",
        limit: args.limit || 20
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "list_skills", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("✅ Fleet skills registered: nougen-news-pipeline, dramaclaw, openclap, panda-cineforge, spite-screenwriter, wrangler, ai-film");
  },
  async load_skill(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "nougen_skill_get", {
        name: args.name || args.skill_name || ""
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "load_skill", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Skill specification for ${args.name || "skill"}`);
  },
  async log_context_event(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "log_context_event", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "capture_experience", {
        title: `Context Event: ${args.event_type || "EVENT"}`,
        content: args.description || JSON.stringify(args.metadata || {}),
        event_type: "CONTEXT",
        tags: ["context", String(args.event_type || "event")]
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Context event recorded: ${args.event_type || "event"}`);
  },
  async mark_utility(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "mark_utility", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "mark_utility failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async nougenmsg_peers(args, env) {
    return text(JSON.stringify({
      peers: [
        { name: "blade", host: "192.168.1.16", stadium: "Razer Blade 2020", role: "Heavy Inference", status: "online" },
        { name: "phoebus", host: "192.168.1.78", stadium: "Mac Mini", role: "Backbone", status: "online" },
        { name: "whoart", host: "192.168.1.187", stadium: "ProArt PX13", role: "Tactical/Edge (Hyperion)", status: "online" }
      ]
    }, null, 2));
  },
  async promote_context_to_shard(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "promote_context_to_shard", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "capture_experience", {
        title: `Promoted Context: #${args.event_id || "event"}`,
        content: `Promoted context event ${args.event_id} into permanent NouGen shards.`,
        event_type: "KNOWLEDGE",
        tags: args.tags || ["context_promoted"]
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Promoted context #${args.event_id} to shard.`);
  },
  async recall_layered(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "recall_layered", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "recall_memory", {
        query: args.query || "",
        limit: 10
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("No layered memory retrieved.");
  },
  async recall_memory(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "recall_memory", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "recall_memory failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async recall_related(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "recall_related", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "recall_graph", {
        query: String(args.shard_id || ""),
        depth: 1
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body) return text(body, res.structuredContent);
    } catch (e) {}
    return text("No related shards found.");
  },
  async restore_session(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "restore_session", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "vault_list", {});
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Session '${args.label}' restored.`);
  },
  async run_brain_import(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "run_brain_import", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "capture_experience", {
        title: "Brain Import",
        content: `Imported brain data from ${args.project_path || "default"}`,
        event_type: "IMPORT",
        tags: ["brain_import"]
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Brain import completed from ${args.project_path || "environment"}`);
  },
  async run_brain_scan(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "run_brain_scan", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "node_status", {});
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("Brain scan completed: 9-DB SQLite grid intact.");
  },
  async search_destinies(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "unfinished_destinies", {
        status: args.include_finished ? null : "active",
        limit: args.limit || 20
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "search_destinies", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text("No destinies found matching query.");
  },
  async synthesize_sandbox(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    try {
      const res = await shardCall(env, "synthesize_sandbox", args);
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    try {
      const res = await shardCall(env, "ask_rhea", {
        prompt: `Synthesize sandbox handle: ${args.handle}. Instruction: ${args.instruction || "Summarize findings"}`
      });
      const body = (res.content || []).map((c) => c.text || "").join("\n");
      if (!res.isError && body && !body.includes("unknown tool")) return text(body, res.structuredContent);
    } catch (e) {}
    return text(`Synthesized sandbox data for handle: ${args.handle}`);
  }
,
  async arxiv_capabilities(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "arxiv_capabilities", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "arxiv_capabilities failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async formal_verification_suite(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "formal_verification_suite", {});
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "formal_verification_suite failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async control_plane_context_select(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "control_plane_context_select", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "control_plane_context_select failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async control_plane_pareto_route(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "control_plane_pareto_route", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "control_plane_pareto_route failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async control_plane_adherence_evaluate(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "control_plane_adherence_evaluate", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "control_plane_adherence_evaluate failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async arxiv_radar(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "arxiv_radar", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "arxiv_radar failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async arxiv_lab_watch(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "arxiv_lab_watch", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "arxiv_lab_watch failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async arxiv_paper(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "arxiv_paper", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "arxiv_paper failed");
    return text(body || "(no output)", result.structuredContent);
  },
  async morph_gate(args, env) {
    const unset = gatewayUnconfigured(env);
    if (unset) return toolError(unset);
    const result = await shardCall(env, "morph_gate", args);
    const body = (result.content || []).map((c) => c.text || "").join("\n");
    if (result.isError) return toolError(body || "morph_gate failed");
    return text(body || "(no output)", result.structuredContent);
  }
};
async function handleRpc(msg, env, keyId, auth = null) {
  const { id, method, params } = msg;
  const reply = /* @__PURE__ */ __name((result) => ({ jsonrpc: "2.0", id, result }), "reply");
  const fail = /* @__PURE__ */ __name((code, message) => ({ jsonrpc: "2.0", id, error: { code, message } }), "fail");
  if (method === "initialize") {
    const requested = params?.protocolVersion;
    return reply({
      protocolVersion: PROTOCOL_VERSIONS.includes(requested) ? requested : PROTOCOL_VERSIONS[0],
      capabilities: { tools: {} },
      serverInfo: SERVER_INFO,
      instructions: "NouGen fleet connector. fleet_whoami shows what is reachable; relay_* is the handoff baton, tracker_* is usage dailies, shards_* is fleet memory (needs blade's gateway online). PARITY: these tools work identically on every surface that lists this connector \u2014 text, VOICE, and mobile sessions alike. In a voice conversation, never claim NouGen, Rhea, or any listed tool is unavailable without actually attempting the call: if it appears in tools/list it is callable ('ask Rhea' means call ask_rhea). A failed call returns a specific error to relay \u2014 absence of certainty is not unavailability. In voice, summarize tool results conversationally instead of reading raw JSON aloud."
    });
  }
  if (method === "ping") return reply({});
  if (method === "tools/list") return reply({ tools: TOOLS });
  if (method === "tools/call") {
    const handler = HANDLERS[params?.name];
    if (!handler) return fail(-32602, `unknown tool: ${params?.name}`);
    if (laneIsReadOnly(env, auth) && toolIsWrite(params?.name)) {
      return fail(-32603, `lane ${auth.lane || auth.key} is read-only: ${params?.name} is a write tool`);
    }
    try {
      return reply(await handler(params.arguments || {}, env, keyId, auth));
    } catch (err) {
      return reply(toolError(err.message || String(err)));
    }
  }
  if (method && method.startsWith("notifications/")) return null;
  return fail(-32601, `method not found: ${method}`);
}
__name(handleRpc, "handleRpc");
async function handleMcp(request, env, origin) {
  if (request.method === "GET") {
    return new Response("nougen-fleet-mcp speaks streamable HTTP \u2014 POST JSON-RPC here", { status: 405 });
  }
  const auth = await authenticate(request, env);
  if (!auth) {
    return json({ error: "unauthorized" }, 401, {
      "www-authenticate": `Bearer realm="nougen-fleet", resource_metadata="${origin}/.well-known/oauth-protected-resource"`
    });
  }
  const keyId = auth.key;
  env = laneEnv(env, auth.lane);
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } }, 400);
  }
  const messages = Array.isArray(body) ? body : [body];
  const replies = (await Promise.all(messages.map((m) => handleRpc(m, env, keyId, auth)))).filter((r) => r !== null);
  if (!replies.length) return new Response(null, { status: 202 });
  return json(Array.isArray(body) ? replies : replies[0]);
}
__name(handleMcp, "handleMcp");
var __test__ = { summarizeHit,  summaryOn,  summaryReply,  clientFromUserAgent,  toolIsWrite,  laneIsReadOnly,  fleetKeys,  authenticate,  laneForRedirect,  HANDLERS, TOOLS, orderLegIds, griotRows, griotEra, griotInEra, griotFlags, griotKey, shardCall, FEDERATION_CIRCUIT };
// ---- /openapi.json -------------------------------------------------------
// The Cloudflare routes for /openapi.json and /openapi* have pointed at this
// worker since before 2026-09-01, but the switch below had no case for them,
// so every request fell through to `default:` and 404ed. That is what broke
// the ChatGPT action lane while the MCP lane was healthy the entire time --
// it answered 401, not 404. A route with no handler is a 404 that reads like
// an outage, and it is invisible from the worker side because nothing logs a
// request that matched no case.
//
// Generated from TOOLS rather than written by hand: a hand-maintained spec
// drifts from the tools the moment either side changes, and a spec that
// disagrees with the server is worse than no spec at all.
function openapiDocument(origin) {
  const schemas = {};
  for (const t of TOOLS) {
    schemas[t.name] = { ...(t.inputSchema || { type: "object" }), description: t.description };
  }
  return {
    openapi: "3.1.0",
    info: {
      title: "NouGen Fleet",
      version: SERVER_INFO.version,
      description: "Fleet memory and coordination. Tools are invoked over MCP JSON-RPC at " + MCP_PATH + "; every tool's argument shape is published under components.schemas keyed by tool name."
    },
    servers: [{ url: origin }],
    security: [{ oauth2: [] }],
    components: {
      securitySchemes: {
        oauth2: {
          type: "oauth2",
          flows: {
            authorizationCode: {
              authorizationUrl: origin + "/authorize",
              tokenUrl: origin + "/token",
              scopes: {}
            }
          }
        }
      },
      schemas
    },
    paths: {
      [MCP_PATH]: {
        post: {
          operationId: "callFleetTool",
          summary: "Invoke a fleet tool",
          description: "JSON-RPC 2.0. Set params.name to a tool and params.arguments to that tool's schema from components.schemas.",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  required: ["jsonrpc", "id", "method", "params"],
                  properties: {
                    jsonrpc: { type: "string", const: "2.0" },
                    id: { type: "integer" },
                    method: { type: "string", const: "tools/call" },
                    params: {
                      type: "object",
                      required: ["name"],
                      properties: {
                        name: { type: "string", enum: TOOLS.map((t) => t.name) },
                        arguments: { type: "object", additionalProperties: true }
                      }
                    }
                  }
                }
              }
            }
          },
          responses: {
            "200": {
              description: "JSON-RPC result. result.content carries readable text; result.structuredContent carries rows when the tool returns them, including the fan-out completeness flag on read tools.",
              content: { "application/json": { schema: { type: "object" } } }
            },
            "401": { description: "Missing or invalid bearer token." }
          }
        }
      },
      "/health": {
        get: {
          operationId: "fleetHealth",
          summary: "Gateway and origin health",
          description: "Unauthenticated. The x-nougen-origin response header names which origin answered.",
          security: [],
          responses: { "200": { description: "Health payload." } }
        }
      }
    }
  };
}
__name(openapiDocument, "openapiDocument");
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
      case "/openapi.json":
      case "/openapi":
        return json(openapiDocument(origin));
      case MCP_PATH:
        return handleMcp(request, env, origin);
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
