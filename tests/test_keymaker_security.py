"""Regression tests for keymaker secret-at-rest hardening (audit HIGH findings).

POSIX-only assertions (file modes); the credential-protection round-trip and
migration-honesty checks run everywhere via the plaintext escape hatch.
"""
import importlib
import os
import sqlite3
import stat
import sys

import pytest


@pytest.fixture
def km(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", "1")
    import nougen_shards.keymaker as keymaker
    importlib.reload(keymaker)
    yield keymaker


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_vault_dirs_are_owner_only(km):
    km.init_vault()
    assert stat.S_IMODE(os.stat(km.VAULT_DIR).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(km.SECRETS_JSON_DIR).st_mode) == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_service_account_json_is_owner_only(km):
    km.ingest_service_account('{"project_id":"p","client_email":"a@b.com","private_key":"K"}')
    saf = km.SECRETS_JSON_DIR / "p_service_account.json"
    assert saf.exists()
    assert stat.S_IMODE(os.stat(saf).st_mode) == 0o600


def test_external_db_uri_round_trips(km):
    km.register_external_db("postgres://u:pass@host:5432/db", "tbl", "t", "c")
    dbs = km.list_external_dbs()
    assert dbs and dbs[0]["uri"] == "postgres://u:pass@host:5432/db"


def test_migration_does_not_count_plaintext_escape_hatch(km):
    km.init_vault()
    conn = sqlite3.connect(str(km.DB_PATH))
    conn.execute("INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)"
                 " VALUES ('LEG','plainvalue','t')")
    conn.commit()
    conn.close()
    # With the plaintext escape hatch active, _protect can't encrypt, so nothing
    # should be reported as migrated (the old code falsely counted it).
    assert km.migrate_to_encrypted() == 0
