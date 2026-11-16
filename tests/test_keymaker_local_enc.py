"""Regression tests: vault_put on headless Linux (no DPAPI, no OS keyring).

Leg 20261116T165939Z: vault_put failed server-side on the HF Space with
"Error: Error executing tool vault_put" — keymaker._protect() fails closed
with RuntimeError when the `keyring` package is absent and the plaintext
escape hatch is unset. The fix is a machine-local AES-256-GCM fallback
(enc1:) keyed by a file in the vault dir itself, so the write lands
encrypted instead of raising. These tests pin the round-trip on a host
with no keyring at all.
"""
import os
import sqlite3
import stat
import sys

import pytest


@pytest.fixture
def km_no_keyring(monkeypatch, dpapi_stand_in):
    """keymaker with `import keyring` failing and the plaintext hatch OFF.

    Same shape as the HF Space: Linux, no keyring package, no escape hatch.
    """
    monkeypatch.delenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", raising=False)
    monkeypatch.setitem(sys.modules, "keyring", None)
    import nougen_shards.keymaker as keymaker

    dpapi_stand_in(keymaker)
    keymaker._KEYRING_CACHE.clear()
    return keymaker


def _stored_value(km, key):
    conn = sqlite3.connect(str(km.db_path()))
    try:
        row = conn.execute(
            "SELECT secret_value FROM secrets WHERE secret_key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def test_ingest_round_trips_without_keyring(km_no_keyring):
    km = km_no_keyring
    km.ingest_secret("TEST_LOCAL_ENC_KEY", "test-value-36-chars-abcdefghijklmnop")
    assert km.get_secret("TEST_LOCAL_ENC_KEY") == "test-value-36-chars-abcdefghijklmnop"
    stored = _stored_value(km, "TEST_LOCAL_ENC_KEY")
    assert stored.startswith(km._LOCAL_ENC_PREFIX)
    assert km._is_encrypted(stored)
    assert "test-value-36-chars" not in stored


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_enc_key_file_is_owner_only(km_no_keyring):
    km = km_no_keyring
    km.ingest_secret("TEST_LOCAL_ENC_KEY", "test-value")
    key_file = km.vault_dir() / km._LOCAL_ENC_KEY_FILENAME
    assert key_file.is_file()
    assert stat.S_IMODE(os.stat(key_file).st_mode) == 0o600


def test_ingest_round_trips_when_keyring_backend_broken(km_no_keyring, monkeypatch):
    """keyring installed but no backend (headless Linux Secret Service
    absent): set_password raises, the write must still land via enc1."""

    class _BrokenKeyring:
        def set_password(self, service, ref, value):
            raise RuntimeError("No recommended backend was available")

        def get_password(self, service, ref):
            return None

    monkeypatch.setitem(sys.modules, "keyring", _BrokenKeyring())
    km = km_no_keyring
    km.ingest_secret("TEST_LOCAL_ENC_KEY", "test-value-2")
    assert km.get_secret("TEST_LOCAL_ENC_KEY") == "test-value-2"
    assert _stored_value(km, "TEST_LOCAL_ENC_KEY").startswith(km._LOCAL_ENC_PREFIX)


def test_plaintext_hatch_still_wins_when_set(km_no_keyring, monkeypatch):
    """The explicit NOUGEN_ALLOW_PLAINTEXT_VAULT=1 opt-in is preserved:
    with the hatch on, _protect still returns the value unchanged."""
    monkeypatch.setenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", "1")
    km = km_no_keyring
    km.ingest_secret("TEST_LOCAL_ENC_KEY", "plain-value")
    assert _stored_value(km, "TEST_LOCAL_ENC_KEY") == "plain-value"
    assert km.get_secret("TEST_LOCAL_ENC_KEY") == "plain-value"


def test_migrate_plaintext_rows_to_enc1(km_no_keyring):
    km = km_no_keyring
    km.init_vault()
    conn = sqlite3.connect(str(km.db_path()))
    conn.execute(
        "INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)"
        " VALUES ('LEGACY_PLAIN', 'plainvalue', 't')"
    )
    conn.commit()
    conn.close()
    assert km.migrate_to_encrypted() == 1
    stored = _stored_value(km, "LEGACY_PLAIN")
    assert stored.startswith(km._LOCAL_ENC_PREFIX)
    assert km.get_secret("LEGACY_PLAIN") == "plainvalue"


def test_enc1_row_from_another_vault_is_unreadable(km_no_keyring, tmp_path, monkeypatch):
    """A vault's enc1 rows decrypt only under that vault's key file: a row
    copied into a second vault reads as absent, never as a leak."""
    km = km_no_keyring
    km.ingest_secret("TEST_LOCAL_ENC_KEY", "vault-a-value")
    stored = _stored_value(km, "TEST_LOCAL_ENC_KEY")
    assert stored.startswith(km._LOCAL_ENC_PREFIX)

    other = tmp_path / "vault-b"
    monkeypatch.setenv("NOUGEN_SECRETS_VAULT_DIR", str(other))
    monkeypatch.setattr(km, "VAULT_DIR", other, raising=False)
    monkeypatch.setattr(km, "DB_PATH", other / km.DB_FILENAME, raising=False)
    km.init_vault()
    conn = sqlite3.connect(str(km.db_path()))
    conn.execute(
        "INSERT INTO secrets (secret_key, secret_value, last_rotated)"
        " VALUES (?, ?, ?)",
        ("TEST_LOCAL_ENC_KEY", stored, "t"),
    )
    conn.commit()
    conn.close()
    assert km.get_secret("TEST_LOCAL_ENC_KEY") is None


def test_enc_key_differs_per_vault(km_no_keyring, tmp_path, monkeypatch):
    """Two vault dirs mint different local keys (no shared fallback key)."""
    km = km_no_keyring
    km.ingest_secret("TEST_LOCAL_ENC_KEY", "vault-a-value")
    key_a = (km.vault_dir() / km._LOCAL_ENC_KEY_FILENAME).read_bytes()

    other = tmp_path / "vault-b"
    monkeypatch.setenv("NOUGEN_SECRETS_VAULT_DIR", str(other))
    monkeypatch.setattr(km, "VAULT_DIR", other, raising=False)
    monkeypatch.setattr(km, "DB_PATH", other / km.DB_FILENAME, raising=False)
    km.ingest_secret("TEST_LOCAL_ENC_KEY", "vault-b-value")
    key_b = (km.vault_dir() / km._LOCAL_ENC_KEY_FILENAME).read_bytes()
    assert key_a != key_b
