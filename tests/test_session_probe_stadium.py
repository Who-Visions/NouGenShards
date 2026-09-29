import sqlite3

import pytest

from nougen_shards import session_probe


@pytest.mark.parametrize("raw,expected", [
    ("", "http://127.0.0.1:11434"),
    ("0.0.0.0", "http://127.0.0.1:11434"),
    ("0.0.0.0:11434", "http://127.0.0.1:11434"),
    ("localhost:11434", "http://localhost:11434"),
    ("http://10.0.0.5:9999", "http://10.0.0.5:9999"),
    ("https://ollama.example", "https://ollama.example:11434"),
])
def test_ollama_url_dials_bind_addresses(monkeypatch, raw, expected):
    monkeypatch.setenv("OLLAMA_HOST", raw)
    assert session_probe._ollama_url() == expected


def test_stadium_check_counts_shards_and_survives_dead_ollama(monkeypatch, tmp_path):
    for i, rows in ((1, 3), (2, 2)):
        conn = sqlite3.connect(tmp_path / f"nougen_shards_{i}.db")
        conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO shards DEFAULT VALUES", [()] * rows)
        conn.commit()
        conn.close()
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(session_probe, "OLLAMA_URL", "http://127.0.0.1:1")

    out = session_probe.stadium_check()

    assert out["coach_box_tokens"] == session_probe.COACH_BOX_TOKENS
    assert out["vault"] == {"path": str(tmp_path), "dbs": 2, "shards": 5, "errors": []}
    assert out["ollama"]["up"] is False and out["ollama"]["error"]
