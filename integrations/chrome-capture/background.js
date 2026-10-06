import { buildPayload, normalizeEndpoint } from "./capture.js";

const MENU_SEL = "nougen-capture-selection";
const MENU_PAGE = "nougen-capture-page";

// Listeners are registered at top level: the service worker is killed after 30s idle.
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: MENU_SEL, title: "Capture selection to shards", contexts: ["selection"] });
  chrome.contextMenus.create({ id: MENU_PAGE, title: "Capture page to shards", contexts: ["page"] });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  void run(tab, info.menuItemId === MENU_SEL ? info.selectionText : "");
});

chrome.commands.onCommand.addListener(async (cmd) => {
  if (cmd !== "capture-selection") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) void run(tab, null);
});

async function readPage(tabId, wantSelection) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => ({
      selection: sel ? String(getSelection() || "") : "",
      text: document.body ? document.body.innerText : "",
    }),
    args: [wantSelection],
  });
  return res?.result || { selection: "", text: "" };
}

async function run(tab, selection) {
  try {
    const { endpoint, token } = await chrome.storage.local.get(["endpoint", "token"]);
    const origin = normalizeEndpoint(endpoint);
    if (!origin || !token) return notify("Not configured", "Open the extension options and set the endpoint and token.");
    let sel = selection;
    let pageText = "";
    if (sel === null || sel === "") {
      const got = await readPage(tab.id, sel === null);
      if (sel === null) sel = got.selection;
      pageText = got.text;
    }
    const payload = buildPayload({ selection: sel, pageText, url: tab.url, title: tab.title });
    if (!payload) return notify("Nothing to capture", "No selection or readable page text.");
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 25000);
    const resp = await fetch(`${origin}/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-NGS-Token": token },
      body: JSON.stringify(payload),
      signal: ctl.signal,
    }).finally(() => clearTimeout(timer));
    const data = await resp.json().catch(() => ({}));
    // HTTP 200 + status "ok" does not mean written: read `captured`.
    if (resp.ok && data.captured === true) return notify("Captured", `shard ${data.shard_id ?? "?"}`);
    notify("Not captured", data.error || data.reason || `HTTP ${resp.status}`);
  } catch (e) {
    notify("Capture failed", String(e && e.message || e));
  }
}

function notify(title, message) {
  chrome.notifications.create({ type: "basic", iconUrl: "icon.png", title, message });
}
