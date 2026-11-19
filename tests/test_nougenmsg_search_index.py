import json
import sqlite3

from nougen_shards.nougenmsg import NouGenMsgBus


def _write_message(path, message_id, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "message_id": message_id,
        "sender": "claude",
        "text": text,
        "timestamp": "2026-10-25T18:00:00Z",
    }), encoding="utf-8")


def test_search_incrementally_indexes_all_message_lanes(tmp_path, monkeypatch):
    inboxes = {
        "NOUGEN_CODEX_INBOX": tmp_path / "codex",
        "NOUGEN_GEMINI_INBOX": tmp_path / "gemini",
        "NOUGEN_AGY_INBOX": tmp_path / "agy",
        "NOUGEN_CLAUDE_INBOX": tmp_path / "claude",
        "NOUGEN_ROOT": tmp_path / "nougen-home",
    }
    for name, path in inboxes.items():
        monkeypatch.setenv(name, str(path))

    _write_message(inboxes["NOUGEN_CODEX_INBOX"] / "codex.json", "codex-1", "LearnWithMrsB current work")
    _write_message(inboxes["NOUGEN_GEMINI_INBOX"] / "gemini.json", "gemini-1", "LearnWithMrsB current work")
    _write_message(inboxes["NOUGEN_AGY_INBOX"] / "agy.json", "agy-1", "LearnWithMrsB current work")
    _write_message(inboxes["NOUGEN_CLAUDE_INBOX"] / "claude.json", "claude-1", "LearnWithMrsB current work")

    result = NouGenMsgBus.search_messages("LearnWithMrsB current", target="all", limit=10,
                                          timeout_s=10, as_contract=True)
    assert result["complete"] is True
    assert {message["message_id"] for message in result["results"]} == {
        "codex-1", "gemini-1", "agy-1", "claude-1"
    }
    assert result["timed_out_sources"] == []

    claude_result = NouGenMsgBus.search_messages("LearnWithMrsB", target="claude", limit=10,
                                                 timeout_s=10, as_contract=True)
    assert claude_result["complete"] is True
    assert [message["message_id"] for message in claude_result["results"]] == ["claude-1"]

    db = inboxes["NOUGEN_ROOT"] / "cache" / "nougenmsg_index.db"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages_meta").fetchone()[0] == 4


def test_search_reindexes_changed_messages(tmp_path, monkeypatch):
    inbox = tmp_path / "codex"
    monkeypatch.setenv("NOUGEN_CODEX_INBOX", str(inbox))
    monkeypatch.setenv("NOUGEN_ROOT", str(tmp_path / "nougen-home"))
    message = inbox / "message.json"
    _write_message(message, "mutable-1", "old search phrase")

    first = NouGenMsgBus.search_messages("old search", target="codex", limit=5,
                                         timeout_s=10, as_contract=True)
    assert [item["message_id"] for item in first["results"]] == ["mutable-1"]

    _write_message(message, "mutable-1", "new search phrase")
    stat = message.stat()
    import os
    os.utime(message, (stat.st_atime, stat.st_mtime + 2))
    updated = NouGenMsgBus.search_messages("new search", target="codex", limit=5,
                                           timeout_s=10, as_contract=True)
    assert [item["message_id"] for item in updated["results"]] == ["mutable-1"]
    assert updated["complete"] is True
