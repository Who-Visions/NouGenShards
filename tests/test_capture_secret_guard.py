"""HARDENING invariant 8: secrets must be redacted at every shard write.

Doctrine (Atibon/Keymaker): shards may reference key *names* and fingerprints,
never plaintext values. The bulk brain_scan importer already redacts; this
guards the structural path — a plain core.capture() (as used by the MCP
capture_experience tool, hooks, and fleet writes) must not land raw secrets in
the substrate.
"""
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path",
                            lambda index: temp_path / f"test_shards_{index}.db")
        # Keep the test hermetic: never reach for a live embed model.
        monkeypatch.setenv("NOUGEN_EMBED_MODEL", "")
        shards.init_db(1)
        yield temp_path


# Live-shaped but fake — long enough to trip the pattern length floors.
FAKE_HF = "hf_" + "A1b2C3d4E5f6G7h8I9j0KLMNOP"
FAKE_OPENAI = "sk-" + "abcdef0123456789abcdef␟".replace("␟", "") + "ABCDEF0123"
FAKE_GOOGLE = "AIza" + "B" * 34


def _capture_and_read(title, content):
    ok = shards.capture("KNOWLEDGE", title, content)
    assert ok, "capture should succeed"
    res = shards.retrieve(content[:40], limit=3) or shards.retrieve("credential", limit=3)
    assert res, "expected the shard to be retrievable"
    row = shards.get_shard_by_id(res[0]["id"], res[0]["_db_index"])
    assert row is not None
    return row


def test_secret_in_content_is_redacted_at_write():
    row = _capture_and_read(
        "HF credential note",
        f"The huggingface token is {FAKE_HF} — keep it in the keymaker.")
    assert FAKE_HF not in row["content"], "raw HF token round-tripped into the vault"
    assert "<REDACTED_HF_KEY>" in row["content"]


def test_secret_in_title_is_redacted_at_write():
    row = _capture_and_read(
        f"Google key {FAKE_GOOGLE} rotation",
        "Routine rotation note for the google cloud credential.")
    assert FAKE_GOOGLE not in row["title"], "raw Google key round-tripped in the title"
    assert "<REDACTED_GOOGLE_KEY>" in row["title"]


def test_clean_content_passes_through_untouched():
    body = "A perfectly ordinary shard about retrieval pipelines and MMR."
    row = _capture_and_read("Clean note", body)
    assert row["content"] == body
    assert "REDACTED" not in row["content"]
