// NouGenTube settings page: provider keys, model choice per provider, Auto order, Ollama address.
const $ = id => document.getElementById(id);
const esc = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let prov = {};

async function init() {
  prov = (await chrome.storage.local.get("prov")).prov || {};
  const sync = await chrome.storage.sync.get(["host", "autoOrder", "theme", "keepAwake"]);
  const paint = t => { document.documentElement.dataset.theme = t === "auto" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : t; };
  $("theme").value = sync.theme || "auto"; paint($("theme").value);
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { if ($("theme").value === "auto") paint("auto"); });   // follow the system while this page is open
  $("theme").onchange = () => { chrome.storage.sync.set({ theme: $("theme").value }); paint($("theme").value); };
  $("order").value = sync.autoOrder || "free";
  $("order").onchange = () => chrome.storage.sync.set({ autoOrder: $("order").value });
  $("awake").checked = sync.keepAwake !== false;
  $("awake").onchange = () => chrome.storage.sync.set({ keepAwake: $("awake").checked });
  $("host").value = sync.host || "http://localhost:11434";
  $("saveHost").onclick = async () => {
    const host = $("host").value.trim().replace(/\/+$/, "");
    const ok = await grant(host); if (!ok) return status($("hostSt"), "Permission for that address was not granted", false);
    await chrome.storage.sync.set({ host }); status($("hostSt"), "Saved", true);
  };
  $("provs").innerHTML = NGT_PROVIDERS.map(card).join("");
  NGT_PROVIDERS.forEach(wire);
}

function card(p) {
  const s = prov[p.id] || {};
  return `<div class="card" id="c-${p.id}">
    <div class="row"><span class="name">${esc(p.name)}</span>${p.keyUrl ? `<a href="${p.keyUrl}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">Get a key</a>` : ""}<span class="st ${s.model ? "ok" : ""}" id="st-${p.id}">${s.model ? "Ready: " + esc(s.model) : "Not set up"}</span></div>
    ${p.custom ? `<div class="row" style="margin-top:8px"><input id="b-${p.id}" type="url" placeholder="Base URL, e.g. https://example.com/v1" value="${esc(s.base || "")}"></div>` : ""}
    <div class="row" style="margin-top:8px">
      <input id="k-${p.id}" type="password" autocomplete="off" placeholder="${esc(s.key ? "Key saved. Paste a new one to replace it." : p.keyHint || "API key")}">
      <button class="go" id="t-${p.id}">Test key and load models</button>
    </div>
    <div class="row" style="margin-top:8px" id="mr-${p.id}" ${s.models?.length ? "" : "hidden"}>
      <select id="m-${p.id}">${(s.models || []).map(m => `<option ${m === s.model ? "selected" : ""}>${esc(m)}</option>`).join("")}</select>
      <button id="x-${p.id}">Remove</button>
    </div>
  </div>`;
}

function status(el, text, ok) { el.textContent = text; el.className = "st " + (ok ? "ok" : "bad"); }
const save = () => chrome.storage.local.set({ prov });
// Custom endpoints and non-default Ollama addresses need the browser's permission for that site.
async function grant(url) {
  let origin; try { origin = new URL(url).origin + "/*"; } catch { return false; }
  if (await chrome.permissions.contains({ origins: [origin] })) return true;
  try { return await chrome.permissions.request({ origins: [origin] }); } catch { return false; }
}

function wire(p) {
  const st = $("st-" + p.id), btn = $("t-" + p.id), sel = $("m-" + p.id);
  btn.onclick = async () => {
    const typed = $("k-" + p.id).value.trim(), key = typed || prov[p.id]?.key || "";
    const base = p.custom ? $("b-" + p.id).value.trim().replace(/\/+$/, "") : "";
    if (!key && !p.custom) return status(st, "Paste a key first", false);
    if (p.custom && !base) return status(st, "Enter the base URL first", false);
    if (p.custom && !(await grant(base))) return status(st, "Permission for that address was not granted", false);
    btn.disabled = true; status(st, "Checking…", true);
    const r = await new Promise(res => chrome.runtime.sendMessage({ type: "provModels", id: p.id, key, base }, res));
    btn.disabled = false;
    if (!r?.ok) return status(st, r?.error || "No answer from the provider", false);
    const prev = prov[p.id]?.model;
    const model = (prev && r.models.includes(prev)) ? prev : ((p.prefer || []).find(m => r.models.includes(m)) || (p.preferRe ? r.models.filter(m => new RegExp(p.preferRe).test(m)).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).pop() : "") || r.models[0]);
    prov[p.id] = { key, base, model, models: r.models }; await save();
    sel.innerHTML = r.models.map(m => `<option ${m === model ? "selected" : ""}>${esc(m)}</option>`).join("");
    $("mr-" + p.id).hidden = false; $("k-" + p.id).value = ""; $("k-" + p.id).placeholder = "Key saved. Paste a new one to replace it.";
    status(st, `Ready: ${model} (${r.models.length} models available)`, true);
  };
  sel.onchange = async () => { prov[p.id].model = sel.value; await save(); status(st, "Ready: " + sel.value, true); };
  $("x-" + p.id).onclick = async () => { delete prov[p.id]; await save(); $("c-" + p.id).outerHTML = card(p); wire(p); };
}

init();
