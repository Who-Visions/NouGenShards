import { normalizeEndpoint } from "./capture.js";
const $ = (id) => document.getElementById(id);
const msg = (t) => { $("msg").textContent = t; };

chrome.storage.local.get(["endpoint", "token"]).then(({ endpoint, token }) => {
  $("endpoint").value = endpoint || "";
  // Never echo the saved token back into the page.
  $("token").placeholder = token ? "Saved (hidden). Type to replace." : "";
});

$("save").addEventListener("click", async () => {
  const origin = normalizeEndpoint($("endpoint").value);
  const typed = $("token").value.trim();
  const token = typed || (await chrome.storage.local.get("token")).token || "";
  if (!origin) return msg("Endpoint must be https (or http on localhost).");
  if (!token) return msg("Token is required.");
  // Host access is requested for exactly this origin, not all sites.
  const ok = await chrome.permissions.request({ origins: [`${origin}/*`] });
  if (!ok) return msg("Permission to reach that endpoint was declined.");
  await chrome.storage.local.set({ endpoint: origin, token });
  $("token").value = "";
  msg("Saved.");
});
