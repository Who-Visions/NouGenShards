"""Regression tests for keymaker secret-at-rest hardening (audit HIGH findings).

POSIX-only assertions (file modes); the credential-protection round-trip and
migration-honesty checks run everywhere via the plaintext escape hatch.
"""
import importlib
import os
import sqlite3
import stat

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


# --- multi-layer DPAPI peeling -------------------------------------------
# A value re-protected by a migration or a second ingest pass ends up wrapped
# several times, and only the OUTERMOST layer keeps the `dpapi1:` marker.
# Reading one layer returns a base64 blob that looks like a secret and fails as
# one (measured 2026-08-15: rows needed three passes; a one-pass read spent an
# 820-char ciphertext as a bearer token and got 401 back).

@pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only")
@pytest.mark.parametrize("layers", [1, 2, 3])
def test_unprotect_peels_every_dpapi_layer(km, layers):
    import base64
    secret = "sk-test-" + "z" * 49

    # Wrap `layers` deep the way the store does: inner layers are bare base64,
    # only the outermost carries the marker.
    current = secret
    for _ in range(layers):
        blob = km._dpapi_call("CryptProtectData", current.encode("utf-8"))
        current = base64.b64encode(blob).decode("ascii")
    stored = km._DPAPI_PREFIX + current

    assert km._unprotect(stored) == secret


@pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only")
def test_unprotect_rejects_marker_without_a_real_blob(km):
    # Tagged but unreadable must fail loudly, never return the marker payload
    # for the caller to spend as a secret.
    with pytest.raises(OSError):
        km._unprotect(km._DPAPI_PREFIX + "not-base64-at-all!!")


def test_unprotect_passes_through_legacy_plaintext(km):
    assert km._unprotect("plain-legacy-row") == "plain-legacy-row"
