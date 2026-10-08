import { normalizeEndpoint } from "./capture.js";

const $ = (id) => document.getElementById(id);
const msg = (text, isError = false) => {
  const el = $("msg");
  el.textContent = text;
  el.style.color = isError ? "var(--danger)" : "var(--accent-green)";
};

chrome.storage.local.get(["endpoint", "token"]).then(({ endpoint, token }) => {
  $("endpoint").value = endpoint || "http://127.0.0.1:4444";
  if (token) msg("Already connected. You can reconnect any time.");
});

$("connect").addEventListener("click", async () => {
  const origin = normalizeEndpoint($("endpoint").value);
  if (!origin) return msg("Enter a valid NouGen address.", true);
  let parsed;
  try { parsed = new URL(origin); } catch { return msg("Enter a valid NouGen address.", true); }
  if (parsed.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(parsed.hostname)) {
    return msg("One-click connect works with NouGen on this computer. Remote nodes need a different setup.", true);
  }

  const granted = await chrome.permissions.request({ origins: [`${origin}/*`] });
  if (!granted) return msg("Chrome needs permission to connect to your NouGen node.", true);

  const button = $("connect");
  button.disabled = true;
  msg("Connecting…");
  try {
    const response = await fetch(`${origin}/extension/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.token) throw new Error(data.detail || `NouGen returned ${response.status}.`);
    await chrome.storage.local.set({ endpoint: origin, token: data.token });
    msg("Connected. You’re ready to capture pages.");
  } catch (error) {
    msg(`Could not connect. ${error.message || "Check that NouGen is running."}`, true);
  } finally {
    button.disabled = false;
  }
});
