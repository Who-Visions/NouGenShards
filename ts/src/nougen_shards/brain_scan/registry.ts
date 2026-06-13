/**
 * Static term sets and root path registry. (TS mimic of brain_scan/registry.py)
 *
 * Python `set` literals -> Set<string>; Python `list` literals -> string[].
 * pathlib Paths under Path.home() -> absolute path strings via path.join(homedir(), ...).
 */
import { homedir } from "node:os";
import * as path from "node:path";

// Known source adapters / tools
export const KNOWN_TOOLS: string[] = [
  "gemini", "claude", "codex", "cursor", "continue", "copilot",
  "openhands", "mem0", "ollama", "qwen", "roo", "vscode", "github",
];

export const GLOBAL_ROOTS: string[] = [
  homedir(),
  path.join(homedir(), ".claude"),
  path.join(homedir(), ".codex"),
  path.join(homedir(), ".gemini"),
  path.join(homedir(), ".cursor"),
  path.join(homedir(), ".continue"),
  path.join(homedir(), ".copilot"),
  path.join(homedir(), ".openhands"),
  path.join(homedir(), ".mem0"),
  path.join(homedir(), ".ollama"),
  path.join(homedir(), ".qwen"),
  path.join(homedir(), ".roo"),
  path.join(homedir(), ".vscode"),
  path.join(homedir(), ".vscode-shared"),
];

export const PROJECT_ROOT_NAMES: string[] = [
  ".agent", ".agents", ".claude", ".codex", ".gemini", ".cursor",
  ".continue", ".openhands", ".roo", ".vscode", ".github", ".logs",
];

export const PROJECT_FILES: string[] = [
  "AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md",
];

export const DANGER_ZONES: Set<string> = new Set([
  ".ssh", ".aws", ".azure", ".config", ".gnupg", ".kube",
  "credentials", "1password", "bitwarden",
]);

export const SKIP_DIRS: Set<string> = new Set([
  "node_modules", ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
  ".cache", ".npm", ".pnpm-store", ".pnpm-cache", ".bun", ".m2", ".nuget",
  ".gradle", ".docker", "dist", "build", "target", "out",
]);

export const SUPPORTED_EXTS: Set<string> = new Set([
  ".json", ".jsonl", ".zst", ".md", ".txt", ".log", ".toml",
  ".yaml", ".yml", ".sqlite", ".db",
]);

export const HIGH_SIGNAL_TERMS: Set<string> = new Set([
  "conversation", "session", "transcript", "chat", "messages",
  "memory", "rules", "agents", "instructions", "checkpoint",
  "rollout", "tool_calls", "tasks", "history",
]);

export const MEDIUM_SIGNAL_TERMS: Set<string> = new Set([
  "settings", "config", "workspace", "launch", "commands",
  "logs", "debug", "workflow",
]);

export const LOW_SIGNAL_TERMS: Set<string> = new Set([
  "cache", "lockfile", "package", "compiled", "binary",
  "image", "video", "audio", "weights",
]);
