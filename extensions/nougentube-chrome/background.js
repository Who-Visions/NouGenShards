// NouGenTube background page. Every model route lives here: the NouGenOpen free-fleet bridge,
// local Ollama, and any provider the user has added a key for (Claude, OpenAI, Gemini,
// DeepSeek, OpenRouter, NVIDIA, or a custom OpenAI-compatible endpoint). "Auto" walks the
// routes in order and moves to the next one when a route fails or stays silent.
importScripts("providers.js", "power-core.js");

const DEF = { host: "http://localhost:11434", model: "auto", localModel: "gemma4:e2b-qat", autoOrder: "free" };
// nougen-open serve. 8765 is the default; a machine where 8765 is taken (Phoebus runs
// mesh_registry there) serves the bridge on 8767. Find the one that is really the bridge
// (its /health lists "lanes"), remember it, and look again whenever a call fails.
let NGO = "http://127.0.0.1:8765";
const NGO_CANDIDATES = ["http://127.0.0.1:8765", "http://127.0.0.1:8767"];
async function findBridge() {
  for (const c of NGO_CANDIDATES) {
    try {
      const r = await fetch(c + "/health", { signal: AbortSignal.timeout(1500) });
      const j = await r.json();
      if (r.ok && j && Array.isArray(j.lanes)) { NGO = c; chrome.storage.local.set({ ngo: c }); return c; }
    } catch {}
  }
  return null;
}
// One bridge call that survives a wrong port: if the request fails outright, or the port
// answers 404/405 (another service holds it, e.g. mesh_registry on Phoebus 8765), look for
// the real bridge and retry once there.
async function bridgeFetch(path, init) {
  let r;
  try { r = await fetch(NGO + path, init); if (r.status !== 404 && r.status !== 405) return r; } catch (e) { if (init && init.signal && init.signal.aborted) throw e; }
  const before = NGO;
  if (!(await findBridge()) || (NGO === before && r)) { if (r) return r; throw new Error("bridge not found"); }
  return fetch(NGO + path, init);
}
chrome.storage.local.get("ngo").then(v => { if (v && NGO_CANDIDATES.includes(v.ngo)) NGO = v.ngo; }).catch(() => {});
const IDLE_MS = globalThis.NG_IDLE_MS ?? 90000;   // max silence between chunks once text has started
// Long jobs in the panel (a batch, a Morph, a translation, audio transcription) keep the computer awake, never the screen.
const blocker = createPowerBlocker(chrome.power);
blocker.reset();   // a worker that starts holds nothing, so let go of anything a dead one left in the system
// While a job holds, the worker keeps itself alive from its own side. A hidden tab's timers are throttled (Electron's
// backgroundThrottling), so a worker that lives on the page's pings can die mid-job. Any extension API call restarts its idle timer.
const jobs = new Map();   // awake port -> { id: blocker id or null, text: progress shown on the toolbar button }
let selfPing = null;
function syncJobs() {
  const holding = [...jobs.values()].some(j => j.id !== null);
  if (holding && !selfPing) selfPing = setInterval(() => { try { chrome.runtime.getPlatformInfo(); } catch { /* worker is going away anyway */ } }, 20000);
  if (!holding && selfPing) { clearInterval(selfPing); selfPing = null; }
}
// Progress of the long jobs on the toolbar button, like a taskbar progress bar; it clears when the last job ends.
function paintBadge() {
  if (!chrome.action) return;
  let text = "";
  for (const j of jobs.values()) if (j.text) text = j.text;
  try { chrome.action.setBadgeText({ text }); if (text) chrome.action.setBadgeBackgroundColor({ color: "#a47bff" }); } catch { /* no toolbar button */ }
}
// The toolbar button brings the panel forward in the current tab; on a tab with no panel it opens settings.
if (chrome.action) chrome.action.onClicked.addListener(async tab => {
  try { const r = await chrome.tabs.sendMessage(tab.id, { type: "focus-panel" }); if (!r || !r.ok) throw new Error("no panel"); } catch { chrome.runtime.openOptionsPage(); }
});

async function cfg() {
  const sync = await chrome.storage.sync.get(["host", "model", "localModel", "autoOrder"]);
  const local = await chrome.storage.local.get(["prov", "nvKey"]);
  const prov = local.prov || {};
  // One-time carry-over of the key saved by earlier versions (⚙ prompt).
  if (local.nvKey && !prov.nvidia) { prov.nvidia = { key: local.nvKey, model: "google/gemma-4-31b-it" }; chrome.storage.local.set({ prov }); }
  if (local.nvKey) chrome.storage.local.remove("nvKey");   // migrated (or superseded); deleting the provider must not resurrect it
  const c = { ...DEF, ...sync, prov };
  if (String(c.model).startsWith("nvidia:")) c.model = "prov:nvidia";   // old picker value
  return c;
}
const provBase = (p, saved) => (p.custom ? (saved.base || "") : p.base).replace(/\/+$/, "");
const ready = c => NGT_PROVIDERS.filter(p => c.prov[p.id]?.model && (c.prov[p.id].key || p.custom) && provBase(p, c.prov[p.id]));
const bridgeUp = async () => { try { return (await fetch(NGO + "/health", { signal: AbortSignal.timeout(1500) })).ok; } catch { return false; } };
const localModels = async c => { try { return (await (await fetch(c.host + "/api/tags", { signal: AbortSignal.timeout(2500) })).json()).models.map(m => m.name); } catch { return []; } };

function authHeaders(p, key) {
  if (p.kind === "anthropic") return { "x-api-key": key, "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true" };
  return key ? { authorization: "Bearer " + key } : {};
}
async function listModels(id, key, base) {
  const p = NGT_BY_ID[id]; if (!p) throw new Error("unknown provider");
  const b = (p.custom ? base || "" : p.base).replace(/\/+$/, ""); if (!b) throw new Error("enter the endpoint's base URL");
  const r = await fetch(b + "/models" + (p.kind === "anthropic" ? "?limit=200" : ""), { headers: authHeaders(p, key), signal: AbortSignal.timeout(20000) });
  const t = await r.text();
  if (!r.ok) throw new Error(`${p.name} said ${r.status}: ${t.slice(0, 160)}`);
  const j = JSON.parse(t), all = (j.data || j.models || []).map(m => String(m.id || m.name || "").replace(/^models\//, "")).filter(Boolean);
  if (!all.length) throw new Error(p.name + " returned no models for this key");
  // A provider's list mixes in models that cannot hold a chat (embeddings, moderation, speech, images). Offer only chat models,
  // unless that would leave nothing (a custom endpoint may name its models anything).
  const chat = all.filter(m => !/embed|moderation|whisper|tts|transcri|dall-e|image|imagen|veo|sora|audio|realtime|live|rerank|guard|robotics|aqa|nano-banana|computer-use/i.test(m));
  return chat.length ? chat : all;
}

chrome.runtime.onMessage.addListener((msg, _s, reply) => {
  if (msg.type === "models") {
    cfg().then(async c => {
      const [ngo, local] = await Promise.all([bridgeUp(), localModels(c)]);
      const keyed = ready(c), labels = { auto: "Auto: best available route" };
      keyed.forEach(p => labels["prov:" + p.id] = `${p.name.replace(/ \(.+\)/, "")} · ${c.prov[p.id].model}`);
      reply({ ok: true, models: ["auto", ...(ngo ? ["nougenopen:auto"] : []), ...keyed.map(p => "prov:" + p.id), ...local],
        labels, nougenopen: ngo, current: c.model, localModel: c.localModel, keyed: keyed.length, ollamaErr: local.length ? null : "Ollama is not running" });
    });
    return true;
  }
  if (msg.type === "provModels") { listModels(msg.id, msg.key, msg.base).then(models => reply({ ok: true, models }), e => reply({ ok: false, error: String(e.message || e) })); return true; }
  if (msg.type === "openOptions") { chrome.runtime.openOptionsPage(); reply({ ok: true }); return; }
  if (msg.type === "shard") {
    bridgeFetch("/v1/nougen/shard", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(msg.doc) })
      .then(async r => { const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch {}
        if (!r.ok) reply({ ok: false, error: j?.error?.message || ("bridge said " + r.status) });
        else if (!j || typeof j !== "object") reply({ ok: false, error: "the bridge answered " + r.status + " but not with JSON" });
        else reply({ ok: !!j.ok, parts: j.parts || [] }); },
        () => reply({ ok: false, error: "the NouGenOpen bridge is not running (nougen-open serve)" }));
    return true;
  }
});

async function* lines(r) {
  const rd = r.body.getReader(), dec = new TextDecoder(); let buf = "";
  for (;;) { const { done, value } = await rd.read(); if (done) break; buf += dec.decode(value, { stream: true });
    const ls = buf.split("\n"); buf = ls.pop(); for (const l of ls) if (l.trim()) yield l.trim(); }
  if (buf.trim()) yield buf.trim();
}

// ---- one function per wire format; each streams text through emit() and returns a receipt ----
async function runBridge(messages, emit, signal) {
  const r = await fetch(NGO + "/v1/chat/completions", { method: "POST", signal, headers: { "content-type": "application/json" },
    body: JSON.stringify({ model: "nougenopen/auto", messages, max_tokens: 4500, temperature: 0.3 }) });
  const j = await r.json(); if (!r.ok) throw new Error("NouGenOpen " + r.status + " " + (j.error?.message || "").slice(0, 200));
  const text = j.choices?.[0]?.message?.content || ""; if (!text.trim()) throw new Error("NouGenOpen returned an empty answer");
  emit(text);
  return { model: j.model, tokens: j.usage?.completion_tokens || "?", where: "NouGenOpen free fleet via " + (j.nougen?.provider || "?") };
}
async function runOllama(c, model, messages, emit, signal) {
  const body = think => JSON.stringify({ model, messages, stream: true, ...(think === false ? { think: false } : {}), options: { num_ctx: 16384, temperature: 0.3 } });
  let r = await fetch(c.host + "/api/chat", { method: "POST", body: body(false), signal });
  if (!r.ok) r = await fetch(c.host + "/api/chat", { method: "POST", body: body(), signal });
  if (!r.ok) throw new Error("Ollama " + r.status + " " + (await r.text()).slice(0, 200));
  let rec = null, got = false;
  for await (const l of lines(r)) { const j = JSON.parse(l); if (j.error) throw new Error("Ollama: " + j.error);
    if (j.message?.content) { got = true; emit(j.message.content); } if (j.done) rec = { model: j.model, tokens: j.eval_count, where: "local" }; }
  if (!got) throw new Error("Ollama returned an empty answer");
  return rec || { model, tokens: "?", where: "local" };
}
async function runOpenAI(p, saved, messages, emit, signal) {
  const r = await fetch(provBase(p, saved) + "/chat/completions", { method: "POST", signal,
    headers: { "content-type": "application/json", accept: "text/event-stream", ...authHeaders(p, saved.key) },
    body: JSON.stringify({ model: saved.model, messages, stream: true }) });
  if (!r.ok) throw new Error(`${p.name} ${r.status} ${(await r.text()).slice(0, 200)}`);
  let toks = 0, got = false;
  for await (const l of lines(r)) { if (!l.startsWith("data:")) continue; const d = l.slice(5).trim(); if (d === "[DONE]") break;
    let j; try { j = JSON.parse(d); } catch { continue; }
    if (j.error) throw new Error(`${p.name}: ${j.error.message || JSON.stringify(j.error).slice(0, 160)}`);
    const t = j.choices?.[0]?.delta?.content; if (t) { got = true; emit(t); } if (j.usage) toks = j.usage.completion_tokens || toks; }
  if (!got) throw new Error(p.name + " returned an empty answer");
  return { model: saved.model, tokens: toks || "?", where: p.name.replace(/ \(.+\)/, "") };
}
// Claude Messages API, called directly with the user's own key (no SDK: this extension has no
// build step). No sampling parameters: current Claude models reject them. Thinking stays at
// its default. The refusal fallback is requested where the model supports it.
async function runAnthropic(p, saved, messages, emit, signal) {
  const system = messages.filter(m => m.role === "system").map(m => m.content).join("\n\n");
  const turns = messages.filter(m => m.role !== "system").map(m => ({ role: m.role, content: m.content }));
  const call = withFallback => fetch(p.base + "/messages", { method: "POST", signal,
    headers: { "content-type": "application/json", ...authHeaders(p, saved.key), ...(withFallback ? { "anthropic-beta": "server-side-fallback-2026-07-01" } : {}) },
    body: JSON.stringify({ model: saved.model, max_tokens: 16000, stream: true, ...(system ? { system } : {}), messages: turns, ...(withFallback ? { fallbacks: "default" } : {}) }) });
  let r = await call(NGT_ANTHROPIC_FALLBACK.test(saved.model));
  if (r.status === 400 && NGT_ANTHROPIC_FALLBACK.test(saved.model)) { const t = await r.text(); if (/fallback|beta/i.test(t)) r = await call(false); else throw new Error("Claude 400 " + t.slice(0, 200)); }
  if (!r.ok) throw new Error(`Claude ${r.status} ${(await r.text()).slice(0, 200)}`);
  let toks = 0, got = false, stop = "", model = saved.model;
  for await (const l of lines(r)) { if (!l.startsWith("data:")) continue; let j; try { j = JSON.parse(l.slice(5)); } catch { continue; }
    if (j.type === "error") throw new Error("Claude: " + (j.error?.message || "stream error"));
    if (j.type === "message_start" && j.message?.model) model = j.message.model;
    if (j.type === "content_block_delta" && j.delta?.type === "text_delta") { got = true; emit(j.delta.text); }
    if (j.type === "message_delta") { toks = j.usage?.output_tokens || toks; stop = j.delta?.stop_reason || stop; } }
  if (stop === "refusal") throw new Error("Claude declined this request");
  if (!got) throw new Error("Claude returned an empty answer" + (stop ? ` (${stop})` : ""));
  return { model, tokens: toks || "?", where: "Claude" + (stop === "max_tokens" ? " (cut off at the length limit)" : "") };
}

// A route = { label, firstMs, run(emit, signal) }. firstMs is how long it may stay silent.
function routeFor(c, id) {
  if (id === "nougenopen:auto") return { label: "NouGenOpen free fleet", firstMs: 240000, run: (m, e, s) => runBridge(m, e, s) };
  if (id.startsWith("prov:")) { const p = NGT_BY_ID[id.slice(5)], saved = c.prov[p?.id];
    if (!p || !saved?.model) return { label: id, firstMs: 1, run: async () => { throw new Error("no key saved for this provider (open ⚙ settings)"); } };
    return { label: p.name.replace(/ \(.+\)/, ""), firstMs: 75000, run: (m, e, s) => (p.kind === "anthropic" ? runAnthropic : runOpenAI)(p, saved, m, e, s) }; }
  return { label: "local " + id, firstMs: 200000, run: (m, e, s) => runOllama(c, id, m, e, s) };
}
async function autoRoutes(c) {
  const [ngo, local] = await Promise.all([bridgeUp(), localModels(c)]);
  const free = [...(ngo ? ["nougenopen:auto"] : []), ...(local.length ? [local.includes(c.localModel) ? c.localModel : local[0]] : [])];
  const keyed = ready(c).map(p => "prov:" + p.id);
  return (c.autoOrder === "keys" ? [...keyed, ...free] : [...free, ...keyed]).map(id => routeFor(c, id));
}

chrome.runtime.onConnect.addListener(port => {
  if (port.name === "awake") {   // one open port = one long job: a hold, a progress badge, and a worker that stays alive
    const job = { id: null, text: "" };
    jobs.set(port, job);
    port.onMessage.addListener(msg => {
      if (!msg) return;
      if (msg.start && job.id === null) { try { job.id = blocker.start(msg.start); } catch { /* unknown type: hold nothing */ } syncJobs(); }
      if (typeof msg.progress === "string") { job.text = msg.progress.slice(0, 4); paintBadge(); }   // a badge has room for four characters
    });
    port.onDisconnect.addListener(() => { if (job.id !== null) blocker.stop(job.id); jobs.delete(port); syncJobs(); paintBadge(); });
    return;
  }
  // Request/response ports to the bridge. As in Electron's MessagePorts model, a closed port is a signal to settle:
  // when the panel goes away (closed, or navigated to another video) the request is aborted and nothing is posted back.
  const BRIDGE = {
    map: { path: () => "map", timeout: 300000, body: m => ({ prompts: m.prompts, system: m.system, max_tokens: 1500 }), ok: j => ({ ok: true, results: j.results }) },
    recall: { path: () => "recall", timeout: 60000, body: m => m.body, ok: j => ({ ok: true, shards: j.shards || [], failed: j.failed || [] }) },
    tube: { path: m => (m.kind === "playlist" ? "playlist" : "transcript"), timeout: 0, timeoutOf: m => (m.kind === "playlist" ? 120000 : 1500000), body: m => m.body, ok: j => ({ ...j, ok: true }) },
    web: { path: () => "web", timeout: 110000, body: m => m.body, ok: j => ({ ok: true, results: j.results || [], providers: j.providers || [], failed: j.failed || [] }) },
    shard: { path: () => "shard", timeout: 180000, body: m => m.doc, ok: j => ({ ok: !!j.ok, parts: j.parts || [] }) },
  };
  const bridge = BRIDGE[port.name];
  if (bridge) {
    let closed = false, ctrl = null;
    port.onDisconnect.addListener(() => { closed = true; if (ctrl) ctrl.abort(); });
    const send = m => { if (!closed) try { port.postMessage(m); } catch {} };
    port.onMessage.addListener(async msg => {
      if (msg.ping) return;   // keepalive: each message resets the service worker idle timer
      const c = ctrl = new AbortController(), ms = bridge.timeoutOf ? bridge.timeoutOf(msg) : bridge.timeout;
      let timedOut = false;
      const timer = ms ? setTimeout(() => { timedOut = true; c.abort(); }, ms) : null;
      try {
        const r = await bridgeFetch("/v1/nougen/" + bridge.path(msg), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(bridge.body(msg)), signal: c.signal });
        // Read text and parse safely: a reachable bridge that answers with HTML or an empty body is reported as
        // what it is, never as "not running" (that message is only for fetch itself failing).
        const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch {}
        if (!r.ok) send({ ok: false, error: j?.error?.message || ("bridge said " + r.status), code: r.status });
        else if (!j || typeof j !== "object") send({ ok: false, error: "the bridge answered " + r.status + " but not with JSON", code: r.status });
        else send(bridge.ok(j));
      } catch (e) {
        if (closed) return;
        if (!timedOut) findBridge();
        send({ ok: false, error: timedOut ? "the bridge took too long" : "the NouGenOpen bridge is not running (nougen-open serve)" });
      } finally { clearTimeout(timer); }
    });
    return;
  }
  if (port.name !== "chat") return;
  let closed = false, current = null;
  port.onDisconnect.addListener(() => { closed = true; current && current.abort(); });
  const send = m => { if (!closed) try { port.postMessage(m); } catch {} };
  port.onMessage.addListener(async ({ messages, ping }) => {
    if (ping) return;   // keepalive only
    const c = await cfg();
    const routes = c.model === "auto" ? await autoRoutes(c) : [routeFor(c, c.model)];
    if (!routes.length) return send({ error: "No model route is available. Start Ollama or the NouGenOpen bridge, or add a provider key in ⚙ settings." });
    const failed = [];
    for (let i = 0; i < routes.length && !closed; i++) {
      const rt = routes[i], ctrl = current = new AbortController(); let first = false, silent = false, stalled = false, timer;
      // firstMs bounds the wait for the first text; after that every chunk restarts an idle deadline,
      // so a stream that stops mid-answer is aborted instead of hanging the panel.
      const arm = (ms, why) => { clearTimeout(timer); timer = setTimeout(() => { why(); ctrl.abort(); }, ms); };
      arm(rt.firstMs, () => { silent = true; });
      if (routes.length > 1) send({ stage: (i ? "Trying " : "Asking ") + rt.label + (i ? ` (route ${i + 1} of ${routes.length})` : "") });
      try {
        const rec = await rt.run(messages, t => { first = true; arm(IDLE_MS, () => { stalled = true; }); send({ delta: t }); }, ctrl.signal);
        return send({ done: true, ...rec, failed });
      } catch (e) {
        if (closed) return;
        failed.push(rt.label + ": " + (silent ? `no answer within ${Math.round(rt.firstMs / 1000)}s`
          : stalled ? `went quiet for ${Math.round(IDLE_MS / 1000)}s mid-answer` : String(e.message || e).slice(0, 160)));
        if (first) send({ reset: true });   // drop the partial text before the next route writes
      } finally { clearTimeout(timer); }
    }
    send({ error: (routes.length > 1 ? "Every route failed. " : "") + failed.join(" · ") });
  });
});
