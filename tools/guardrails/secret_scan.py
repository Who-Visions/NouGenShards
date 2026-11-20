#!/usr/bin/env python3
"""Local secret scan for staged changes. Free, offline, no CI minutes.

Reads `git diff --cached`, looks only at added lines, and exits 2 when one
carries a credential shape. Wired into hooks/pre-commit, so the key is
stopped before it enters history, which is the only point where it is cheap.

Patterns come from nougen_shards.credential_patterns when it imports. In a
repo without that package the built-in fallback set is used and said so.

Config (env, all optional):
  NOUGEN_SECRET_SCAN        "off" disables the scan
  NOUGEN_SECRET_SCAN_ALLOW  comma list of path globs to skip
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_ALLOW_FILE = os.path.join(_HERE, "secret_scan_allow.txt")

# Fallback shapes, used only when the shared pattern set cannot be imported.
_FALLBACK = [re.compile(p) for p in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bAIza[0-9A-Za-z_\-]{35}\b",
    r"\bgh[pousr]_[0-9A-Za-z]{36,}\b",
    r"\bgithub_pat_[0-9A-Za-z_]{40,}\b",
    r"\bsk-(proj-|ant-)?[0-9A-Za-z_\-]{24,}\b",
    r"\bxox[abprs]-[0-9A-Za-z\-]{20,}\b",
    r"\bhf_[0-9A-Za-z]{30,}\b",
    r"\beyJ[0-9A-Za-z_\-]{10,}\.eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\b",
)]


def load_detector():
    """(detector, redactor, source label)."""
    src = os.path.join(_REPO, "src")
    if os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)
    try:
        from nougen_shards.credential_patterns import contains_credential, redact
        return contains_credential, redact, "nougen_shards.credential_patterns"
    except Exception:  # noqa: BLE001 - any import failure means fallback
        def detect(text: str) -> bool:
            return any(p.search(text) for p in _FALLBACK)

        def redact(text: str) -> str:
            for p in _FALLBACK:
                text = p.sub("[REDACTED]", text)
            return text
        return detect, redact, "built-in fallback"


def allowed_globs() -> list[str]:
    globs = [g.strip() for g in (os.environ.get("NOUGEN_SECRET_SCAN_ALLOW") or "").split(",")
             if g.strip()]
    if os.path.isfile(_ALLOW_FILE):
        with open(_ALLOW_FILE, encoding="utf-8") as fh:
            globs += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    return globs


def added_lines(diff: str):
    """Yield (path, line number, text) for every added line in a unified diff."""
    path, lineno = None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            path = path[2:] if path.startswith("b/") else path
            path = None if path == "/dev/null" else path
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            lineno = int(m.group(1)) if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            if path:
                yield path, lineno, raw[1:]
            lineno += 1
        elif raw.startswith(" "):
            lineno += 1


def scan(diff: str, detect=None, globs=None):
    detect = detect or load_detector()[0]
    globs = allowed_globs() if globs is None else globs
    hits = []
    for path, lineno, text in added_lines(diff):
        if any(fnmatch.fnmatch(path, g) for g in globs):
            continue
        if detect(text):
            hits.append((path, lineno, text))
    return hits


def main() -> int:
    if (os.environ.get("NOUGEN_SECRET_SCAN") or "").lower() == "off":
        return 0
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--no-color", "--no-ext-diff"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"[guardrails] secret scan could not read the staged diff: {exc}\n")
        return 2
    detect, redact, source = load_detector()
    hits = scan(proc.stdout, detect)
    if not hits:
        return 0
    sys.stderr.write(f"[guardrails] secret scan ({source}) found {len(hits)} staged line(s):\n")
    for path, lineno, text in hits:
        shown = redact(text).strip()[:120]
        sys.stderr.write(f"  {path}:{lineno}: {shown}\n")
    sys.stderr.write("Unstage the value, move it to the secret store, and commit again. "
                     "A false positive goes in tools/guardrails/secret_scan_allow.txt.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
