/**
 * NouGenContext sandbox execution logic (Node/Bun). (TS mimic of nougen_sandbox.py)
 * Process-level isolation: no parent env, no shell, timeout. NOT a full security sandbox.
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

/** Whether arbitrary code execution is opted-in via NOUGEN_ENABLE_SANDBOX. */
export function sandbox_enabled(): boolean {
  const v = (process.env.NOUGEN_ENABLE_SANDBOX ?? "").trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(v);
}

/** Checks if a command-line tool is available (mirrors shutil.which). */
export function _is_tool_available(name: string): boolean {
  return _which(name) !== null;
}

/** Resolves an executable on PATH, honoring PATHEXT on Windows (mirrors shutil.which). */
function _which(name: string): string | null {
  // Absolute / path-qualified name: test directly.
  if (path.isAbsolute(name) || name.includes(path.sep) || name.includes("/")) {
    return _has_exec(name) ?? null;
  }
  const pathEnv = process.env.PATH ?? "";
  const dirs = pathEnv.split(path.delimiter).filter((d) => d.length > 0);
  const isWin = os.platform() === "win32";
  const exts = isWin
    ? (process.env.PATHEXT ?? ".COM;.EXE;.BAT;.CMD").split(";").filter((e) => e.length > 0)
    : [""];
  for (const dir of dirs) {
    const base = path.join(dir, name);
    // On Windows try name as-is and with each PATHEXT extension.
    const candidates = isWin
      ? [base, ...exts.map((e) => base + e.toLowerCase()), ...exts.map((e) => base + e)]
      : [base];
    for (const c of candidates) {
      const hit = _has_exec(c);
      if (hit) return hit;
    }
  }
  return null;
}

function _has_exec(p: string): string | null {
  try {
    return existsSync(p) ? p : null;
  } catch {
    return null;
  }
}

/**
 * Executes code in a sandboxed subprocess.
 * Only stdout is returned; network is disabled if possible.
 *
 * Note: this is process-level isolation (no parent env, no shell), NOT a full
 * security sandbox. Untrusted callers (MCP tools, `nougen ctx execute`) are
 * refused unless the operator opts in with NOUGEN_ENABLE_SANDBOX=1. Internal
 * callers running their own generated code may pass trusted=True.
 */
export function execute_sandboxed(
  code: string,
  language: string = "javascript",
  timeout: number = 10,
  trusted: boolean = false,
): string {
  if (!trusted && !sandbox_enabled()) {
    return (
      "Error: Sandboxed code execution is disabled by default for safety. " +
      "It allows arbitrary code to run on this machine. " +
      "Set NOUGEN_ENABLE_SANDBOX=1 to enable it."
    );
  }

  // Create temp file for code
  const suffix = ["javascript", "typescript"].includes(language) ? ".js" : ".py";
  const tempDir = mkdtempSync(path.join(os.tmpdir(), "nougen-sbx-"));
  const temp_path = path.join(tempDir, `code${suffix}`);
  writeFileSync(temp_path, code, { encoding: "utf-8" });

  try {
    // Determine runtime
    let runtime: string | null;
    if (["javascript", "typescript"].includes(language)) {
      // Prefer Bun if available, fallback to Node
      const runtime_name = _is_tool_available("bun") ? "bun" : "node";
      runtime = _which(runtime_name);
      if (!runtime) {
        return `Error: Runtime '${runtime_name}' not found.`;
      }
    } else if (language === "python") {
      // No sys.executable equivalent in Node; resolve a python interpreter on PATH.
      runtime = _which("python") ?? _which("python3");
      if (!runtime) {
        return "Error: Runtime 'python' not found.";
      }
    } else {
      return `Error: Unsupported language '${language}'`;
    }

    // Minimal environment: do NOT inherit the parent env (it carries API keys and
    // tokens that untrusted code could exfiltrate). Pass only what runtimes need.
    const _ALLOWED_ENV = [
      "SystemRoot",
      "SystemDrive",
      "PATH",
      "PATHEXT",
      "COMSPEC",
      "WINDIR",
      "USERPROFILE",
      "HOME",
      "LANG",
      "PROCESSOR_ARCHITECTURE",
      "NUMBER_OF_PROCESSORS",
    ];
    const env: Record<string, string> = {};
    for (const k of _ALLOWED_ENV) {
      const val = process.env[k];
      if (val !== undefined) env[k] = val;
    }
    const tmp = os.tmpdir();
    env.TEMP = tmp;
    env.TMP = tmp;
    if (os.platform() === "win32") {
      if (!("SystemRoot" in env)) env.SystemRoot = "C:\\Windows";
      if (!("SystemDrive" in env)) env.SystemDrive = "C:";
    }

    try {
      // Execute with shell disabled (runtime is an absolute path; shell adds injection surface)
      const stdout = execFileSync(runtime, [temp_path], {
        timeout: timeout * 1000,
        env,
        shell: false,
        encoding: "utf-8",
        stdio: ["ignore", "pipe", "pipe"],
      });
      return (stdout ?? "").trim();
    } catch (exc: any) {
      // Timeout: execFileSync surfaces ETIMEDOUT / signal kill.
      if (exc && (exc.code === "ETIMEDOUT" || exc.signal === "SIGTERM" || exc.killed === true)) {
        return `Error: Execution timed out after ${timeout}s`;
      }
      // Non-zero exit: the spawned process ran but failed.
      if (exc && typeof exc.status === "number") {
        const stderr = exc.stderr ? String(exc.stderr) : "";
        return `Execution failed (Exit ${exc.status}):\n${stderr}`;
      }
      // Spawn failure (OSError / SubprocessError equivalent).
      return `Error: Sandbox execution failed: ${exc?.message ?? exc}`;
    }
  } finally {
    try {
      if (existsSync(temp_path)) {
        rmSync(temp_path, { force: true });
      }
      rmSync(tempDir, { force: true, recursive: true });
    } catch {
      /* mirror OSError pass */
    }
  }
}
