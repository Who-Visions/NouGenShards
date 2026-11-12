"""Tests for tools/shard_electron_docs.py domain_key routing and idempotent re-runs."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nougen_shards import core
from tools import shard_electron_docs


def test_shard_electron_docs_domain_and_idempotent_rerun(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(vault))
    monkeypatch.setattr(core, "GLOBAL_DIR", vault)

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ipc.md").write_text("# IPC Main and Renderer\n\nElectron IPC bridge overview.\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["shard_electron_docs.py", str(docs)])
    assert shard_electron_docs.main() == 0

    # Re-run on unchanged page must succeed (duplicate treated as already present, exit 0)
    monkeypatch.setattr(sys, "argv", ["shard_electron_docs.py", str(docs)])
    assert shard_electron_docs.main() == 0

    found_domains = []
    for idx in range(1, core.MAX_DB_COUNT + 1):
        db = core.get_db_path(idx)
        if db.exists():
            with sqlite3.connect(db) as con:
                rows = con.execute("SELECT event_type, domain_key, title FROM shards").fetchall()
                found_domains.extend(rows)

    assert len(found_domains) == 1
    event_type, domain_key, title = found_domains[0]
    assert event_type == "doc"
    assert domain_key == "electron-docs"
    assert title == "IPC Main and Renderer"
