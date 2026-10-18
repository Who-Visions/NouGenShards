import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (f) => readFileSync(join(root, f), "utf8");

// Every file the extension names must ship. (#738 shipped without icon.png: it was
// gitignored via *.png, and notifications silently failed.)
export function referencedFiles() {
  const m = JSON.parse(read("manifest.json"));
  const out = new Set(Object.values(m.icons || {}));
  out.add(m.background.service_worker);
  out.add(m.action.default_popup); out.add(m.options_ui.page);
  if (m.side_panel?.default_path) out.add(m.side_panel.default_path);
  Object.values(m.action.default_icon || {}).forEach((f) => out.add(f));
  for (const f of [m.background.service_worker]) for (const x of read(f).matchAll(/from "\.\/([^"]+)"/g)) out.add(x[1]);
  const htmlFiles = [m.action.default_popup, m.options_ui.page];
  if (m.side_panel?.default_path) htmlFiles.push(m.side_panel.default_path);
  for (const f of htmlFiles)
    for (const x of read(f).matchAll(/(?:src|href)="([^"#]+\.(?:js|css))"/g)) out.add(x[1]);
  for (const x of read("background.js").matchAll(/iconUrl: "([^"]+)"/g)) out.add(x[1]);
  return [...out];
}
test("every referenced file exists", () => {
  const missing = referencedFiles().filter((f) => !existsSync(join(root, f)));
  assert.deepEqual(missing, []);
});
test("detector flags a missing file (negative control)", () => {
  assert.ok(!existsSync(join(root, "definitely-missing.png")));
});
test("manifest version and permissions are sane", () => {
  const m = JSON.parse(read("manifest.json"));
  assert.equal(m.manifest_version, 3);
  assert.ok(!m.permissions.includes("<all_urls>") && !(m.host_permissions || []).length);
});
