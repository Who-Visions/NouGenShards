import { buildPayload, normalizeEndpoint } from "./capture.js";
import { buildMorph } from "./morph.js";
import { isYouTube, mcpCall, shardRef, checkNodeHealth, searchShards } from "./nougen.js";

const MENU = { sel: "nougen-capture-selection", page: "nougen-capture-page", morph: "nougen-morph-page", tube: "nougen-tube" };

// Listeners are registered at top level: the service worker is killed after 30s idle.
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: MENU.sel, title: "Capture selection to shards", contexts: ["selection"] });
  chrome.contextMenus.create({ id: MENU.page, title: "Capture page to shards", contexts: ["page"] });
  chrome.contextMenus.create({ id: MENU.morph, title: "Morph page into distilled shards", contexts: ["page"] });
  chrome.contextMenus.create({ id: MENU.tube, title: "Send video to NouGenTube", contexts: ["page"],
    documentUrlPatterns: ["https://www.youtube.com/*", "https://m.youtube.com/*", "https://music.youtube.com/*", "https://youtu.be/*"] });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const id = info.menuItemId;
  if (id === MENU.sel) void act("capture", tab, { selection: info.selectionText });
  else if (id === MENU.page) void act("capture", tab, { selection: "" });
  else if (id === MENU.morph) void act("morph", tab, {});
  else if (id === MENU.tube) void act("tube", tab, {});
});

chrome.commands.onCommand.addListener(async (cmd) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  if (cmd === "capture-selection") void act("capture", tab, { selection: null });
  else if (cmd === "morph-page") void act("morph", tab, {});
  else if (cmd === "tube-page") void act("tube", tab, {});
});

// Message listener handles requests from popup, sidepanel, and options
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "check_health") {
    (async () => {
      const cfg = await config();
      if (!cfg) return reply({ ok: false, error: "Not configured" });
      const res = await checkNodeHealth(cfg.origin, cfg.token);
      reply(res);
    })();
    return true; // Keep reply channel open for async response
  }

  if (msg?.type === "search_shards") {
    (async () => {
      const cfg = await config();
      if (!cfg) return reply({ ok: false, error: "Not configured" });
      try {
        const results = await searchShards(cfg.origin, cfg.token, msg.query);
        reply({ ok: true, results });
      } catch (err) {
        reply({ ok: false, error: String((err && err.message) || err) });
      }
    })();
    return true;
  }

  if (msg?.type === "get_active_tab") {
    (async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab) return reply({ tab: null });
      const page = await readPage(tab.id, true).catch(() => ({ selection: "", text: "", author: "", description: "" }));
      reply({
        tab: {
          id: tab.id,
          url: tab.url,
          title: tab.title,
          isYouTube: isYouTube(tab.url),
          selection: page.selection,
          author: page.author,
          description: page.description,
        }
      });
    })();
    return true;
  }

  if (["capture", "morph", "tube"].includes(msg?.type)) {
    (async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) {
        await act(msg.type, tab, { selection: msg.selection || null, goal: msg.goal, tags: msg.tags });
      }
    })();
    reply({ started: true });
    return false;
  }
});

function emitProgress(step, percent, detail = "") {
  const payload = { step, percent, detail, timestamp: Date.now() };
  chrome.storage.local.set({ last_progress: payload }).catch(() => {});
  chrome.runtime.sendMessage({ type: "progress_update", ...payload }).catch(() => {});
}

async function config() {
  const { endpoint, token } = await chrome.storage.local.get(["endpoint", "token"]);
  const origin = normalizeEndpoint(endpoint);
  return origin && token ? { origin, token } : null;
}

async function readPage(tabId, wantSelection) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      const authorMeta = document.querySelector('meta[name="author"], meta[property="article:author"], meta[name="twitter:creator"]');
      const descMeta = document.querySelector('meta[name="description"], meta[property="og:description"]');
      const root = document.querySelector("article, main, [role=main]") || document.body;
      const clone = root.cloneNode(true);
      clone.querySelectorAll("script,style,nav,footer,aside,header,noscript,form").forEach((n) => n.remove());
      return {
        selection: sel ? String(getSelection() || "") : "",
        text: (clone.innerText || clone.textContent || "").slice(0, 200000),
        author: authorMeta ? authorMeta.getAttribute("content") || "" : "",
        description: descMeta ? descMeta.getAttribute("content") || "" : ""
      };
    },
    args: [wantSelection],
  });
  return res?.result || { selection: "", text: "", author: "", description: "" };
}

async function postCapture(cfg, payload) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 25000);
  try {
    const resp = await fetch(`${cfg.origin}/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-NGS-Token": cfg.token },
      body: JSON.stringify(payload),
      signal: ctl.signal,
    });
    const data = await resp.json().catch(() => ({}));
    return { ok: resp.ok && data.captured === true, data, http: resp.status };
  } finally { clearTimeout(timer); }
}

async function act(kind, tab, opts) {
  try {
    const cfg = await config();
    if (!cfg) {
      emitProgress("error", 0, "Not configured. Set endpoint & token in Options.");
      return notify("Not configured", "Open the extension options and set the endpoint and token.");
    }
    if (kind === "capture") return await doCapture(cfg, tab, opts.selection, opts.tags);
    if (kind === "tube") return await doTube(cfg, tab);
    if (kind === "morph") return await doMorph(cfg, tab, opts.goal);
  } catch (e) {
    const errStr = String((e && e.message) || e);
    emitProgress("error", 0, errStr);
    notify("NouGen failed", errStr);
  }
}

async function doCapture(cfg, tab, selection, extraTags = []) {
  emitProgress("reading", 25, "Reading page DOM...");
  let sel = selection, pageText = "", author = "";
  if (sel === null || sel === "") {
    const got = await readPage(tab.id, sel === null);
    if (sel === null) sel = got.selection;
    pageText = got.text;
    author = got.author;
  }
  emitProgress("packaging", 50, "Packaging knowledge payload...");
  const payload = buildPayload({ selection: sel, pageText, url: tab.url, title: tab.title, extraTags, author });
  if (!payload) {
    emitProgress("error", 0, "Nothing to capture");
    return notify("Nothing to capture", "No selection or readable page text.");
  }
  emitProgress("transmitting", 75, "Transmitting to shard vault...");
  const r = await postCapture(cfg, payload);
  // HTTP 200 + status "ok" does not mean written: read `captured`.
  if (r.ok) {
    emitProgress("done", 100, `Captured shard #${r.data.shard_id ?? "?"}`);
    return notify("Captured", `shard ${r.data.shard_id ?? "?"}`);
  }
  emitProgress("error", 0, r.data.error || r.data.reason || `HTTP ${r.http}`);
  notify("Not captured", r.data.error || r.data.reason || `HTTP ${r.http}`);
}

async function doTube(cfg, tab) {
  if (!isYouTube(tab.url)) {
    emitProgress("error", 0, "Not a YouTube page");
    return notify("Not a YouTube page", "NouGenTube takes YouTube video or playlist URLs.");
  }
  emitProgress("transcribing", 30, "Ingesting video audio & transcribing...");
  notify("NouGenTube", "Transcribing; this can take a minute.");
  try {
    const out = await mcpCall(cfg.origin, cfg.token, "nougentube_ingest", { url: tab.url, limit: 1 });
    const counts = out.counts ? Object.entries(out.counts).map(([k, v]) => `${k}: ${v}`).join(", ") : "done";
    emitProgress("done", 100, `Transcribed: ${out.processed ?? "?"} processed (${counts})`);
    notify("NouGenTube", `${out.processed ?? "?"} processed (${counts})`);
  } catch (err) {
    emitProgress("error", 0, String((err && err.message) || err));
    throw err;
  }
}

async function doMorph(cfg, tab, goal) {
  emitProgress("analyzing", 20, "Extracting page prose...");
  const page = await readPage(tab.id, false);
  emitProgress("distilling", 40, "Distilling key concepts & destiny...");
  const plan = buildMorph({ url: tab.url, title: tab.title, text: page.text, goal });
  if (!plan) {
    emitProgress("error", 0, "No readable prose");
    return notify("Nothing to morph", "No readable prose on this page.");
  }
  const refs = [];
  let failed = 0;
  const total = plan.shards.length;
  for (let i = 0; i < total; i++) {
    const shard = plan.shards[i];
    emitProgress("storing", 40 + Math.round(((i + 1) / total) * 40), `Writing shard ${i + 1}/${total}...`);
    const r = await postCapture(cfg, shard);
    const ref = r.ok ? shardRef(r.data) : null;
    if (ref) refs.push(ref); else failed += 1;
  }
  if (!refs.length) {
    emitProgress("error", 0, "No shard was captured");
    return notify("Morph failed", "No shard was captured.");
  }
  let tail = "";
  if (plan.destiny) {
    emitProgress("linking", 90, "Linking destiny chain...");
    try {
      const d = await mcpCall(cfg.origin, cfg.token, "create_destiny", plan.destiny);
      if (d.id == null) throw new Error(d.error || "no destiny id returned");
      for (const ref of refs) await mcpCall(cfg.origin, cfg.token, "link_destiny", { destiny_id: d.id, kind: "shard", ref, role: "evidence" });
      tail = `; destiny #${d.id}`;
    } catch (e) {
      tail = `; destiny FAILED (${String((e && e.message) || e)})`;
    }
  }
  emitProgress("done", 100, `Morphed ${refs.length} shards${tail}`);
  notify("Morphed", `${refs.length} shards${failed ? `, ${failed} not captured` : ""}${tail}`);
}

function notify(title, message) {
  chrome.notifications.create({ type: "basic", iconUrl: "icon128.png", title, message });
}
