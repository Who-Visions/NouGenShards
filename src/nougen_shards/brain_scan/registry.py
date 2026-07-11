from pathlib import Path
from typing import List

# Known source adapters / tools
KNOWN_TOOLS: List[str] = [
    "gemini", "claude", "codex", "cursor", "continue", "copilot",
    "openhands", "mem0", "ollama", "qwen", "roo", "vscode", "github"
]

GLOBAL_ROOTS: List[Path] = [
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
    ".gradle", ".docker", "dist", "build", "target", "out"
}

SUPPORTED_EXTS = {
    ".json", ".jsonl", ".zst", ".md", ".txt", ".log", ".toml", 
    ".yaml", ".yml", ".sqlite", ".db"
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
