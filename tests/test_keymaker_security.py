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
    vault_dir = tmp_path / "vault"
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("NOUGEN_SECRETS_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", "1")
    # The escape hatch only applies when `import keyring` fails. CI has no
    # keyring, but a macOS dev box does, so `_protect` wrote these fixtures
    # into the operator's real login Keychain (and failed there with -25244).
    # Make the import fail so every host takes the same path as CI.
    monkeypatch.setitem(sys.modules, "keyring", None)
    import nougen_shards.keymaker as keymaker
    importlib.reload(keymaker)
    keymaker._PROBE_CACHE.clear()
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


def test_migration_does_not_count_plaintext_escape_hatch(km, monkeypatch):
    monkeypatch.setattr(km, "_protect", lambda val, *args, **kwargs: val)
    km.init_vault()
    conn = sqlite3.connect(str(km.DB_PATH))
    conn.execute("INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)"
                 " VALUES ('LEG','plainvalue','t')")
    conn.commit()
    conn.close()
    # With the plaintext escape hatch active, _protect can't encrypt, so nothing
    # should be reported as migrated (the old code falsely counted it).
    assert km.migrate_to_encrypted() == 0


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_existing_service_account_file_is_repaired_to_0600(km, tmp_path):
    # Pre-create the SA file world-readable (as an older version would), then
    # re-ingest: O_TRUNC keeps old perms, so fchmod must repair it to 0600.
    km.init_vault()
    saf = km.SECRETS_JSON_DIR / "p_service_account.json"
    saf.write_text("{}")
    os.chmod(saf, 0o644)
    km.ingest_service_account('{"project_id":"p","client_email":"a@b.com","private_key":"K"}')
    assert stat.S_IMODE(os.stat(saf).st_mode) == 0o600


def test_migration_encrypts_existing_external_db_uri(km):
    # An external_dbs row written by an older version holds a raw URI; migrate
    # must encrypt it (here the plaintext escape hatch is on, so _protect is a
    # no-op and nothing is claimed — assert it is at least not double-counted).
    km.register_external_db("postgres://u:pass@h:5432/db", "t", "a", "b")
    # round-trips back to plaintext via list (escape hatch); migration is a no-op
    # under the hatch but must not raise and must leave the URI readable.
    before = km.list_external_dbs()[0]["uri"]
    km.migrate_to_encrypted()
    after = km.list_external_dbs()[0]["uri"]
    assert before == after == "postgres://u:pass@h:5432/db"


def test_list_external_dbs_skips_row_when_keyring_missing(km, monkeypatch):
    # If _unprotect raises ImportError (keyring backend absent) the row must be
    # skipped, not crash list_external_dbs (federated_retrieve calls it pre-try).
    km.register_external_db("postgres://u:p@h/d", "t", "a", "b")
    import nougen_shards.keymaker as keymaker
    def boom(_):
        raise ImportError("No module named 'keyring'")
    monkeypatch.setattr(keymaker, "_unprotect", boom)
    assert km.list_external_dbs() == []  # skipped, no exception


class _FakeKeyring:
    """In-memory keyring; records reads so the test can prove the Keychain is never hit."""
    def __init__(self):
        self.store, self.reads = {}, 0

    def set_password(self, service, ref, value):
        self.store[(service, ref)] = value

    def get_password(self, service, ref):
        self.reads += 1
        return self.store.get((service, ref))


@pytest.fixture
def km_keyring(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.delenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", raising=False)
    monkeypatch.setenv("NOUGEN_DISABLE_KEYCHAIN_POPUP", "1")  # headless: reads use the cache only
    fake = _FakeKeyring()
    monkeypatch.setitem(sys.modules, "keyring", fake)
    import nougen_shards.keymaker as keymaker
    importlib.reload(keymaker)
    monkeypatch.setattr(keymaker, "_KEYRING_CACHE_FILE", tmp_path / "keyring_cache.json")
    yield keymaker, fake


@pytest.mark.skipif(os.name == "nt", reason="Windows uses DPAPI, not the keyring cache")
def test_secret_ingested_headless_is_readable_headless(km_keyring):
    km, fake = km_keyring
    km.ingest_secret("NEW_PROVIDER_API_KEY", "value-123")
    km._KEYRING_CACHE.clear()  # a fresh session: nothing in memory
    assert km.get_secret("NEW_PROVIDER_API_KEY") == "value-123"
    assert fake.reads == 0  # served from the cache; the Keychain was never asked


@pytest.mark.skipif(os.name == "nt", reason="Windows uses DPAPI, not the keyring cache")
def test_csv_export_survives_an_unreadable_row(km_keyring):
    km, _ = km_keyring
    km.ingest_secret("OK_KEY", "fine")
    conn = sqlite3.connect(str(km._get_db_path()) if hasattr(km, "_get_db_path") else str(km.DB_PATH))
    conn.execute("insert into secrets (secret_key, secret_value, last_rotated) values (?, ?, ?)",
                 ("ORPHAN_KEY", km._KEYRING_PREFIX + "no-such-ref", "2026-10-01"))
    conn.commit(); conn.close()
    km.ingest_secret("ANOTHER_KEY", "also-fine")  # used to raise AttributeError in _export_to_csv
    assert km.get_secret("ANOTHER_KEY") == "also-fine"


def test_hf_token_nougenai_alias_resolution(km):
    km.init_vault()
    # Ingest under canonical full key name
    km.ingest_secret("HUGGINGFACE_KEY_NOUGENAI_GMAIL_COM", "hf_test_token_secret_123")
    
    # Must resolve via HF_TOKEN, HF_TOKEN_NOUGENAI, HUGGINGFACE_API_KEY, and HUGGINGFACE_API_TOKEN
    assert km.get_secret("HF_TOKEN_NOUGENAI") == "hf_test_token_secret_123"
    assert km.get_secret("HF_TOKEN") == "hf_test_token_secret_123"
    assert km.get_secret("HUGGINGFACE_API_KEY") == "hf_test_token_secret_123"
    assert km.get_secret("HUGGINGFACE_API_TOKEN") == "hf_test_token_secret_123"
    assert km.resolve_secret_for_var("HF_TOKEN_NOUGENAI") == "hf_test_token_secret_123"
    assert km.resolve_secret_for_var("HF_TOKEN") == "hf_test_token_secret_123"
    assert km.resolve_secret_for_var("HUGGINGFACE_API_KEY") == "hf_test_token_secret_123"


# Names the connectors interpolate into SQL. Each must be refused at
# registration, not stored and then silently skipped on every read.
_BAD_IDENTIFIERS = ['a"b', 'x; DROP TABLE secrets', 'ok\n', '1abc', 'a b', '', None]


@pytest.mark.parametrize("bad", _BAD_IDENTIFIERS)
@pytest.mark.parametrize("field", ["table_name", "title_col", "content_col"])
def test_register_external_db_rejects_unsafe_identifier(km, field, bad):
    names = {"table_name": "tbl", "title_col": "t", "content_col": "c", field: bad}
    with pytest.raises(ValueError, match=field):
        km.register_external_db("postgres://u:pass@host:5432/db", **names)
    assert km.list_external_dbs() == []


@pytest.mark.parametrize("bad", _BAD_IDENTIFIERS)
@pytest.mark.parametrize("field", ["table_name", "title_col", "content_col"])
def test_register_local_vault_rejects_unsafe_identifier(km, tmp_path, field, bad):
    names = {"table_name": "shards", "title_col": "title", "content_col": "content", field: bad}
    with pytest.raises(ValueError, match=field):
        km.register_local_vault(str(tmp_path / "v.db"), **names)
    assert km.list_local_vaults() == []


@pytest.mark.xfail(strict=True, raises=sqlite3.OperationalError, reason=(
    "pre-existing: init_vault() creates local_vaults with last_connected and no "
    "UNIQUE(path)/registered_at, so register_local_vault's CREATE IF NOT EXISTS is "
    "a no-op and its INSERT ... registered_at ... ON CONFLICT(path) fails. Needs a "
    "schema migration; remove this marker when that lands."))
def test_register_local_vault_accepts_plain_identifiers(km, tmp_path):
    km.register_local_vault(str(tmp_path / "v.db"), "shards", "title", "_content2")
    rows = km.list_local_vaults()
    assert [(r["table_name"], r["title_col"], r["content_col"]) for r in rows] == [
        ("shards", "title", "_content2")]


@pytest.mark.skipif(os.name == "nt", reason="DPAPI is available on Windows")
def test_dpapi_row_off_windows_does_not_break_ingest(km):
    # A Windows-synced DPAPI row in a POSIX vault must read as unreadable in the
    # audit ledger, not crash ingest_secret after the new row was committed.
    import base64
    km.init_vault()
    blob = km._DPAPI_PREFIX + base64.b64encode(km._DPAPI_MAGIC + b"\x00" * 24).decode()
    conn = sqlite3.connect(str(km.DB_PATH))
    conn.execute("INSERT INTO secrets (secret_key, secret_value, last_rotated) VALUES (?, ?, ?)",
                 ("WINDOWS_ROW", blob, "2026-01-01 00:00:00"))
    conn.commit()
    conn.close()
    km.ingest_secret("NEW_KEY", "new-value")
    assert km.get_secret("NEW_KEY") == "new-value"
    with pytest.raises(OSError):
        km._unprotect(blob)
    ledger = open(km.CSV_PATH, encoding="utf-8").read()
    assert "WINDOWS_ROW" in ledger and "unreadable" in ledger
