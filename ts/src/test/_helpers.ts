/**
 * Shared test helpers for the NouGenShards TS suite (node:test based).
 *
 * The substrate resolves its vault + history paths from env at module-load time,
 * so a test file must call `isolateEnv()` BEFORE dynamically importing the module
 * under test. node:test runs each file in its own process, so this gives clean
 * per-file isolation — the TS equivalent of the Python `monkeypatch`/`tmp_path`
 * fixtures.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";

/**
 * Point the vault, NOUGEN_HOME, and the OS home dir (history.db lives under
 * homedir/.nougen) at fresh temp dirs. Returns the root temp dir.
 * Call at the very top of a test file, before any `await import(...)`.
 */
export function isolateEnv(prefix = "ngs-test-"): string {
  const root = mkdtempSync(path.join(tmpdir(), prefix));
  process.env.NOUGEN_VAULT_DIR = path.join(root, "vault");
  process.env.NOUGEN_HOME = path.join(root, "home");
  // history.ts / brain_scan resolve homedir() — steer it at the temp root so
  // the real ~/.nougen is never touched during tests.
  process.env.USERPROFILE = root; // Windows homedir source
  process.env.HOME = root; // POSIX homedir source
  return root;
}

/** Capture everything written to stdout while `fn` runs (the `capsys` analogue). */
export async function captureStdout(fn: () => unknown | Promise<unknown>): Promise<string> {
  const chunks: string[] = [];
  const orig = process.stdout.write.bind(process.stdout);
  process.stdout.write = (chunk: any) => {
    chunks.push(typeof chunk === "string" ? chunk : String(chunk));
    return true;
  };
  try {
    await fn();
  } finally {
    process.stdout.write = orig;
  }
  return chunks.join("");
}

/** Install a fake global fetch returning `responder(url, init)`; returns a restore fn. */
export function mockFetch(
  responder: (url: string, init?: any) => { status?: number; json?: any; text?: string },
): () => void {
  const orig = globalThis.fetch;
  globalThis.fetch = async (url: any, init?: any) => {
    const r = responder(String(url), init);
    const status = r.status ?? 200;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => r.json,
      text: async () => r.text ?? JSON.stringify(r.json ?? ""),
      body: null,
    } as any;
  };
  return () => {
    globalThis.fetch = orig;
  };
}
