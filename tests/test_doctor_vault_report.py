"""`nougen doctor` must not report a healthy box as broken.

The doctor's vault section checks the Keymaker SECRETS vault, but its output
said only "[Vault] ❌ Vault not found" — printed directly under nine healthy
shard databases. Read as the memory vault, that is a contradiction, and it was
reported as one (phoebus, 2026-08-04: "vault path check still unresolved").
A box with no stored secrets is a normal configuration, not a failure.
"""
from pathlib import Path

from nougen_shards import cli, keymaker


def test_missing_secrets_vault_is_information_not_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(keymaker, "DB_PATH", tmp_path / "nowhere" / "shards_secrets.db")
    lines = cli.keymaker_vault_report()
    text = "\n".join(lines)
    assert "❌" not in text
    assert "keymaker" in text.lower()
    # It must say WHERE it looked and HOW to fix it, not just that it failed.
    assert str((tmp_path / "nowhere" / "shards_secrets.db").absolute()) in text
    assert keymaker.ENV_SECRETS_VAULT in text
    # And it must disarm the contradiction with the healthy substrate above.
    assert "substrate" in text


def test_present_vault_reports_path_and_providers(monkeypatch, tmp_path):
    db = tmp_path / "shards_secrets.db"
    db.write_bytes(b"")
    monkeypatch.setattr(keymaker, "DB_PATH", db)
    monkeypatch.setattr(keymaker, "list_providers", lambda: ["anthropic"])
    lines = cli.keymaker_vault_report()
    text = "\n".join(lines)
    assert str(db.absolute()) in text
    assert "anthropic" in text
    assert "ℹ️" not in text
