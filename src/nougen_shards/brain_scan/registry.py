from pathlib import Path

# Known source adapters / tools
KNOWN_TOOLS = [
    "gemini", "claude", "codex", "cursor", "continue", "copilot",
    "openhands", "mem0", "ollama", "qwen", "roo", "vscode", "github"
]

GLOBAL_ROOTS = [
    Path.home(),
    Path.home() / ".claude",
    Path.home() / ".codex",
    Path.home() / ".gemini",
    Path.home() / ".cursor",
    Path.home() / ".continue",
    Path.home() / ".copilot",
    Path.home() / ".openhands",
    Path.home() / ".mem0",
    Path.home() / ".ollama",
    Path.home() / ".qwen",
    Path.home() / ".roo",
    Path.home() / ".vscode",
    Path.home() / ".vscode-shared"
]

# Agent memory stores that do not live under a dot-directory named after their
# tool, so the original GLOBAL_ROOTS never reached them. Appended to
# GLOBAL_ROOTS rather than kept as a separate list so that anything patching
# GLOBAL_ROOTS (the test suite pins it to a temp dir) still controls every root
# that gets walked — a second, unpatched root list would silently escape that
# isolation and reach the real home directory.
EXTRA_DB_ROOTS = [
    Path.home() / "Watchtower",
    Path.home() / ".iris",
]

GLOBAL_ROOTS.extend(EXTRA_DB_ROOTS)

# SQLite is read via query, not by slurping the file, so these extensions are
# exempt from the byte-size ceiling that applies to text candidates.
SQLITE_EXTS = {".db", ".sqlite", ".sqlite3"}

# NouGenShards' own substrate. Ingesting it would re-import every shard as the
# body of a new shard on each run.
SELF_EXCLUDE_DIRS = {".nougen"}

PROJECT_ROOT_NAMES = [
    ".agent", ".agents", ".claude", ".codex", ".gemini", ".cursor",
    ".continue", ".openhands", ".roo", ".vscode", ".github", ".logs"
]

PROJECT_FILES = [
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md"
]

DANGER_ZONES = {
    ".ssh", ".aws", ".azure", ".config", ".gnupg", ".kube", 
    "credentials", "1password", "bitwarden"
}

SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".cache", ".npm", ".pnpm-store", ".pnpm-cache", ".bun", ".m2", ".nuget",
    ".gradle", ".docker", "dist", "build", "target", "out",
    "antigravity", "antigravity-backup", "antigravity-ide", "antigravity-browser-profile",
    "extensions", "cacheddata", "cachedextensions", "bin", "locales", "packages", "usr", "lib"
}

SUPPORTED_EXTS = {
    ".json", ".jsonl", ".md", ".txt", ".log", ".toml", 
    ".yaml", ".yml"
}

HIGH_SIGNAL_TERMS = {
    "conversation", "session", "transcript", "chat", "messages", 
    "memory", "rules", "agents", "instructions", "checkpoint", 
    "rollout", "tool_calls", "tasks", "history"
}

MEDIUM_SIGNAL_TERMS = {
    "settings", "config", "workspace", "launch", "commands", 
    "logs", "debug", "workflow"
}

LOW_SIGNAL_TERMS = {
    "cache", "lockfile", "package", "compiled", "binary", 
    "image", "video", "audio", "weights"
}
