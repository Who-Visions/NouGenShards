import { execFile } from "node:child_process"
import { existsSync } from "node:fs"
import { mkdir, mkdtemp, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"

import { MOCK } from "@/lib/mock"
import { parseGates, type GateRun } from "@/lib/gates"

// Where the engine lives. Resolved at runtime, never hard-coded to a machine:
// NGS_ENGINE_DIR wins, else the repo layout (apps/ngs-console -> engine/ngs).
export function engineDir() {
  return process.env.NGS_ENGINE_DIR ?? path.resolve(process.cwd(), "../../engine/ngs")
}

export function cliPath() {
  return process.env.NGS_CLI ?? path.join(engineDir(), "build", "ngs_cli")
}

// The console's own fact log. Kept out of git (.ngs-data/ is ignored).
export function dataDir() {
  return process.env.NGS_DATA_DIR ?? path.resolve(process.cwd(), ".ngs-data", "console")
}

// The console spawns a local binary and writes a local log, so it is a
// workstation tool. A production build (a preview deploy, say) serves the
// recorded mock data unless the operator opts in with NGS_CONSOLE_ENABLE=1.
export function engineLive() {
  if (process.env.NODE_ENV === "production" && process.env.NGS_CONSOLE_ENABLE !== "1") return false
  return existsSync(/*turbopackIgnore: true*/ cliPath())
}

export type CliResult = {
  ok: boolean
  op?: string
  mocked?: boolean
  [key: string]: unknown
}

function run(file: string, args: string[], timeoutMs: number) {
  return new Promise<{ code: number; stdout: string; stderr: string }>((resolve) => {
    execFile(
      file,
      args,
      { timeout: timeoutMs, maxBuffer: 16 * 1024 * 1024 },
      (error, stdout, stderr) => {
        const code =
          error && typeof (error as NodeJS.ErrnoException).code === "number"
            ? ((error as NodeJS.ErrnoException).code as unknown as number)
            : error
              ? 1
              : 0
        resolve({ code, stdout: String(stdout), stderr: String(stderr) })
      }
    )
  })
}

// One CLI call. The CLI always prints one JSON object; anything else is an error.
export async function ngs(args: string[], opts?: { dir?: string; timeoutMs?: number }): Promise<CliResult> {
  const op = args[0] ?? "version"
  if (!engineLive()) {
    return { ...(MOCK[op as keyof typeof MOCK] ?? { ok: false, error: "no mock for " + op }), mocked: true }
  }
  const dir = opts?.dir ?? dataDir()
  await mkdir(/*turbopackIgnore: true*/ dir, { recursive: true })
  const argv = op === "version" ? ["version"] : [dir, ...args]
  const { stdout, stderr } = await run(cliPath(), argv, opts?.timeoutMs ?? 30_000)
  const line = stdout.trim().split("\n").pop() ?? ""
  try {
    return { ...(JSON.parse(line) as CliResult), mocked: false }
  } catch {
    return { ok: false, op, error: (stderr || stdout || "no output").slice(0, 2000), mocked: false }
  }
}

// Bench on a scratch log so the console's own facts stay clean.
export async function bench(n: number): Promise<CliResult> {
  if (!engineLive()) return { ...MOCK.bench, mocked: true }
  const dir = await mkdtemp(path.join(os.tmpdir(), "ngs-bench-"))
  try {
    return await ngs(["bench", String(n)], { dir, timeoutMs: 10 * 60_000 })
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

// The judge gates, run from the engine's own Makefile. Fixed target list only.
export async function gates(): Promise<GateRun> {
  if (!engineLive()) return { ...MOCK.gates, mocked: true }
  const started = Date.now()
  const { code, stdout, stderr } = await run("make", ["-C", engineDir(), "check", "test", "crash"], 5 * 60_000)
  return { ...parseGates(stdout + "\n" + stderr, code), ms: Date.now() - started, mocked: false }
}
