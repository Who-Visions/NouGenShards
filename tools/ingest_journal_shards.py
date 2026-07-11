"""Ingest codex_memory_journal.jsonl records as first-class DB shards.

Closes the H4 coverage gap from wargames/retrieval-quality.md: operational
doctrine written via fleet-registry write_memory lands only in the journal
file, invisible to semantic recall. Idempotent — capture() dedupes.
Dynamic per Rule 0.2: journal path env-resolved.
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("NOUGEN_VAULT_DIR", r"C:/Users/super/Watchtower/vault")

from nougen_shards.core import capture, GLOBAL_DIR

JOURNAL = os.environ.get("NOUGEN_JOURNAL_PATH", str(GLOBAL_DIR / "codex_memory_journal.jsonl"))
EVENT_TYPE = os.environ.get("NOUGEN_JOURNAL_EVENT_TYPE", "DOCTRINE")


def main():
    if not os.path.isfile(JOURNAL):
        print(json.dumps({"error": f"journal missing: {JOURNAL}"}))
        return 1
    written, dupes, bad = 0, 0, 0
    with open(JOURNAL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            title = (rec.get("title") or "").strip()
            content = (rec.get("content") or "").strip()
            if not title or not content:
                bad += 1
                continue
            tags = rec.get("tags") or []
            if isinstance(tags, str):
                tags = [t for t in tags.split(",") if t]
            ok = capture(EVENT_TYPE, title, content, tags)
            if ok:
                written += 1
            else:
                dupes += 1
    print(json.dumps({"journal": JOURNAL, "ingested": written,
                      "already_present": dupes, "skipped_bad": bad}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
