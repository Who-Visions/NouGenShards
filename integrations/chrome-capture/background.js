import { buildPayload, normalizeEndpoint } from "./capture.js";
import { buildMorph } from "./morph.js";
import { isYouTube, mcpCall, shardRef } from "./nougen.js";

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
  if (cmd !== "capture-selection") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) void act("capture", tab, { selection: null });
});

// Popup sends {type, goal}; work runs here so it survives the popup closing.
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && ["capture", "morph", "tube"].includes(msg?.type)) void act(msg.type, tab, { selection: null, goal: msg.goal });
  })();
  reply({ started: true });
});

async function config() {
  const { endpoint, token } = await chrome.storage.local.get(["endpoint", "token"]);
  const origin = normalizeEndpoint(endpoint);
  return origin && token ? { origin, token } : null;
}

async function readPage(tabId, wantSelection) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      const root = document.querySelector("article, main, [role=main]") || document.body;
      const clone = root.cloneNode(true);
      clone.querySelectorAll("script,style,nav,footer,aside,header,noscript,form").forEach((n) => n.remove());
      return { selection: sel ? String(getSelection() || "") : "", text: (clone.innerText || clone.textContent || "").slice(0, 200000) };
    },
    args: [wantSelection],
  });
  return res?.result || { selection: "", text: "" };
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
    if (!cfg) return notify("Not configured", "Open the extension options and set the endpoint and token.");
    if (kind === "capture") return await doCapture(cfg, tab, opts.selection);
    if (kind === "tube") return await doTube(cfg, tab);
    if (kind === "morph") return await doMorph(cfg, tab, opts.goal);
  } catch (e) {
    notify("NouGen failed", String((e && e.message) || e));
  }
}

async function doCapture(cfg, tab, selection) {
  let sel = selection, pageText = "";
  if (sel === null || sel === "") {
    const got = await readPage(tab.id, sel === null);
    if (sel === null) sel = got.selection;
    pageText = got.text;
  }
  const payload = buildPayload({ selection: sel, pageText, url: tab.url, title: tab.title });
  if (!payload) return notify("Nothing to capture", "No selection or readable page text.");
  const r = await postCapture(cfg, payload);
  // HTTP 200 + status "ok" does not mean written: read `captured`.
  if (r.ok) return notify("Captured", `shard ${r.data.shard_id ?? "?"}`);
  notify("Not captured", r.data.error || r.data.reason || `HTTP ${r.http}`);
}

async function doTube(cfg, tab) {
  if (!isYouTube(tab.url)) return notify("Not a YouTube page", "NouGenTube takes YouTube video or playlist URLs.");
  notify("NouGenTube", "Transcribing; this can take a minute.");
  const out = await mcpCall(cfg.origin, cfg.token, "nougentube_ingest", { url: tab.url, limit: 1 });
  const counts = out.counts ? Object.entries(out.counts).map(([k, v]) => `${k}: ${v}`).join(", ") : "done";
  notify("NouGenTube", `${out.processed ?? "?"} processed (${counts})`);
}

async function doMorph(cfg, tab, goal) {
  const page = await readPage(tab.id, false);
  const plan = buildMorph({ url: tab.url, title: tab.title, text: page.text, goal });
  if (!plan) return notify("Nothing to morph", "No readable prose on this page.");
  const refs = [];
  let failed = 0;
  for (const shard of plan.shards) {
    const r = await postCapture(cfg, shard);
    const ref = r.ok ? shardRef(r.data) : null;
    if (ref) refs.push(ref); else failed += 1;
  }
  if (!refs.length) return notify("Morph failed", "No shard was captured.");
  let tail = "";
  if (plan.destiny) {
    try {
      const d = await mcpCall(cfg.origin, cfg.token, "create_destiny", plan.destiny);
      if (d.id == null) throw new Error(d.error || "no destiny id returned");
      for (const ref of refs) await mcpCall(cfg.origin, cfg.token, "link_destiny", { destiny_id: d.id, kind: "shard", ref, role: "evidence" });
      tail = `; destiny #${d.id}`;
    } catch (e) {
      tail = `; destiny FAILED (${String((e && e.message) || e)})`;
    }
  }
  notify("Morphed", `${refs.length} shards${failed ? `, ${failed} not captured` : ""}${tail}`);
}

function notify(title, message) {
  chrome.notifications.create({ type: "basic", iconUrl: "icon128.png", title, message });
}
