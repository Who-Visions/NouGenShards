import { normalizeEndpoint } from "./capture.js";

const $ = (id) => document.getElementById(id);
const msg = (text, isError = false) => {
  const el = $("msg");
  el.textContent = text;
  el.style.color = isError ? "var(--danger)" : "var(--accent-green)";
};

chrome.storage.local.get(["endpoint", "token"]).then(({ endpoint, token }) => {
  $("endpoint").value = endpoint || "http://127.0.0.1:4444";
  $("token").value = token || "";
  if (token) msg("Connection settings loaded.");
});

$("save").addEventListener("click", async () => {
  const origin = normalizeEndpoint($("endpoint").value);
  if (!origin) return msg("Enter a valid NouGen address.", true);
  const token = $("token").value.trim();
  if (!token) return msg("Enter your NouGen node token.", true);

  const granted = await chrome.permissions.request({ origins: [`${origin}/*`] });
  if (!granted) return msg("Chrome needs permission to connect to your NouGen node.", true);

  const button = $("save");
  button.disabled = true;
  msg("Saving connection…");
  try {
    await chrome.storage.local.set({ endpoint: origin, token });
    msg("Saved. NouGen Capture is ready.");
  } catch (error) {
    msg(`Could not save connection. ${error.message || "Try again."}`, true);
  } finally {
    button.disabled = false;
  }
});
