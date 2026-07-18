#!/usr/bin/env python
"""
ALWAYS-SHARD enforcement guard (Claude Code hooks; companion to handoff_guard.py).

GM standing order (2026-07-17): every artifact an agent touches or produces must
be captured to the vault IN THE SAME SESSION. Precedent: 50 receipt PDFs saved
to NouGenBuilds\\5321 on 07-13 were never sharded; recall returned nothing four
days later and the GM had to re-supply evidence he'd already delivered.
Disk-without-shard = invisible = failure. This guard makes the rule structural
instead of relying on agent discipline:

  --mode stop       : NON-blocking nudge. If this session produced artifacts
                      (Write/Edit tool calls or large pasted payloads) and no
                      vault capture has been made yet, remind the agent to
                      shard before yielding. (Stop fires every turn — never block.)
  --mode sessionend : safety net. If artifacts exist and the session never
                      captured, AUTO-WRITE a pointer shard into the vault
                      listing every file path the session wrote, so nothing
                      is ever unrecallable even when the agent forgets.

Reads the hook event JSON on stdin (Claude Code protocol). All failures are
swallowed — a hook must never wedge the session. Everything environment-shaped
resolves env -> config -> derived, constants are logged fallbacks only.
"""
import sys, os, json, glob, re, datetime
from pathlib import Path

REPO = Path(os.environ.get("NOUGEN_REPO", str(Path(__file__).resolve().parents[1])))
AGENT = os.environ.get("NOUGEN_AGENT", "claude-cli")
# Payload size that counts a pasted user message as an artifact needing capture.
PASTE_MIN = int(os.environ.get("NOUGEN_SHARDGUARD_PASTE_MIN", "4000"))

# Tool-name markers that count as a vault capture.
CAPTURE_MARKERS = tuple(
    os.environ.get(
        "NOUGEN_SHARDGUARD_CAPTURE_MARKERS",
        "capture_experience,write_memory,write_intelligence_shard,"
        "write_distilled_shard,promote_context_to_shard",
    ).split(",")
)
# Tool names whose use means the session produced on-disk artifacts.
ARTIFACT_TOOLS = tuple(
    os.environ.get("NOUGEN_SHARDGUARD_ARTIFACT_TOOLS", "Write,NotebookEdit").split(",")
)


def _resolve_vault_dir():
    """Mirror handoff_guard: NOUGEN_VAULT_DIR -> ~/.nougen/config.json ->
    repo-local .vault -> per-user default."""
    env = os.environ.get("NOUGEN_VAULT_DIR")
    if env:
        return Path(env)
    try:
        cfg = json.loads((Path.home() / ".nougen" / "config.json").read_text(encoding="utf-8"))
        if cfg.get("vault_dir"):
            return Path(cfg["vault_dir"])
    except Exception:
        pass
    local = REPO / ".vault"
    if local.is_dir():
        return local
    return Path.home() / ".nougen" / "shards"


VAULT_DIR = _resolve_vault_dir()


def _arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _scan_transcript(path):
    """One pass over the session transcript JSONL.

    Returns (captures, artifact_files, paste_count). Line-level substring
    prefilter keeps this cheap even on multi-MB transcripts."""
    captures, paste_count = 0, 0
    artifact_files = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if any(m and m in line for m in CAPTURE_MARKERS):
                    captures += 1
                    continue
                if '"tool_use"' not in line and '"type":"user"' not in line and '"type": "user"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                msg = d.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    if d.get("type") == "user" and isinstance(content, str) and len(content) >= PASTE_MIN:
                        paste_count += 1
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use" and c.get("name") in ARTIFACT_TOOLS:
                        fp = (c.get("input") or {}).get("file_path") or (c.get("input") or {}).get("notebook_path")
                        if fp:
                            artifact_files.append(fp)
                    elif c.get("type") == "text" and d.get("type") == "user" and len(c.get("text", "")) >= PASTE_MIN:
                        paste_count += 1
    except Exception:
        pass
    return captures, artifact_files, paste_count


def _emit_context(event, text):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event, "additionalContext": text}}))


def _auto_pointer_shard(sid, artifact_files, paste_count):
    """Write a pointer shard so session artifacts are never unrecallable."""
    try:
        sid8 = str(sid)[:8]
        existing = glob.glob(str(VAULT_DIR / "intelligence_shard_*.md"))
        if any(f"_shardguard_{sid8}" in os.path.basename(f) for f in existing):
            return
        max_id = 0
        pat = re.compile(r"intelligence_shard_(\d+)_")
        for f in existing:
            m = pat.search(os.path.basename(f))
            if m:
                max_id = max(max_id, int(m.group(1)))
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Scratchpad/temp writes are noise; everything else is a real artifact.
        keep = [f for f in dict.fromkeys(artifact_files)
                if "\\Temp\\" not in f and "/Temp/" not in f and "scratchpad" not in f.lower()]
        listing = "\n".join(f"- `{f}`" for f in keep) or "(no durable file writes; pasted payloads only)"
        body = (f"# 🌑 SHARDGUARD {max_id + 1}: Unsharded Session Artifacts\n\n"
                f"**Agent:** {AGENT}\n**Session ID:** `{sid}`\n**Captured:** {ts}\n\n"
                f"This session ended WITHOUT a manual vault capture despite producing "
                f"artifacts ({len(keep)} durable file writes, {paste_count} large pasted payloads). "
                f"Auto-pointer per GM ALWAYS-SHARD order — follow up and distill properly.\n\n"
                f"## Files written\n{listing}\n\n"
                f"> Auto-captured by shard_guard sessionend lane.\n")
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        (VAULT_DIR / f"intelligence_shard_{max_id + 1}_shardguard_{sid8}_{ts}.md").write_text(
            body, encoding="utf-8")
    except Exception:
        pass


def main():
    try:
        evt = json.load(sys.stdin)
    except Exception:
        evt = {}
    mode = _arg("--mode", "stop")
    sid = evt.get("session_id", "unknown")
    transcript = evt.get("transcript_path", "")
    if not transcript or not os.path.exists(transcript):
        return
    captures, artifact_files, paste_count = _scan_transcript(transcript)
    has_artifacts = bool(artifact_files) or paste_count > 0

    if mode == "stop":
        if has_artifacts and captures == 0:
            _emit_context("Stop",
                          "🌑 ALWAYS SHARD (GM standing order): this session produced "
                          f"{len(artifact_files)} file write(s) and {paste_count} pasted payload(s) "
                          "but has made ZERO vault captures. Before yielding, capture_experience "
                          "every artifact (files, receipts, findings, decisions). "
                          "Disk-without-shard = invisible = failure.")
        return

    if mode == "sessionend":
        if has_artifacts and captures == 0:
            _auto_pointer_shard(sid, artifact_files, paste_count)
        return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a hook must never wedge the session
