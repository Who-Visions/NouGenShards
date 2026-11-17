"""Regression tests: vault_put on headless Linux (no DPAPI, no OS keyring).

Leg 20261116T165939Z: vault_put failed server-side on the HF Space with
"Error: Error executing tool vault_put" — keymaker._protect() fails closed
with RuntimeError when the `keyring` package is absent and the plaintext
escape hatch is unset. The fix is a machine-local AES-256-GCM fallback
(enc1:) keyed by a file in the vault dir itself, so the write lands
encrypted instead of raising. These tests pin the round-trip on a host
with no keyring at all.
"""
import base64
import os
import secrets
import sqlite3
import stat
import sys
import threading
import time

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


def test_read_secret_row_uses_source_vault_key(km_no_keyring, tmp_path, monkeypatch):
    """Codex P2 (finding 1): an enc1: row read from a foreign store decrypts
    under that store's key file, not the active vault's. Before the fix the
    read used the active vault's key, so the row failed authentication
    against the wrong key and came back None."""
    km = km_no_keyring
    # Vault B mints its own key and holds the secret under it.
    vault_b = tmp_path / "vault-b"
    monkeypatch.setenv("NOUGEN_SECRETS_VAULT_DIR", str(vault_b))
    monkeypatch.setattr(km, "VAULT_DIR", vault_b, raising=False)
    monkeypatch.setattr(km, "DB_PATH", vault_b / km.DB_FILENAME, raising=False)
    km.ingest_secret("TEST_FOREIGN_KEY", "vault-b-value")
    assert km.get_secret("TEST_FOREIGN_KEY") == "vault-b-value"

    # Active vault is now a fresh vault A with its own key: the same row,
    # read from B's store by path, must still decrypt — under B's key.
    vault_a = tmp_path / "vault-a"
    monkeypatch.setenv("NOUGEN_SECRETS_VAULT_DIR", str(vault_a))
    monkeypatch.setattr(km, "VAULT_DIR", vault_a, raising=False)
    monkeypatch.setattr(km, "DB_PATH", vault_a / km.DB_FILENAME, raising=False)
    km.ingest_secret("TEST_OTHER_KEY", "vault-a-value")
    assert km.get_secret("TEST_OTHER_KEY") == "vault-a-value"
    assert (
        km._read_secret_row(vault_b / km.DB_FILENAME, "TEST_FOREIGN_KEY")
        == "vault-b-value"
    )

    # And the reverse: with B active again, A's row still reads by path.
    monkeypatch.setenv("NOUGEN_SECRETS_VAULT_DIR", str(vault_b))
    monkeypatch.setattr(km, "VAULT_DIR", vault_b, raising=False)
    monkeypatch.setattr(km, "DB_PATH", vault_b / km.DB_FILENAME, raising=False)
    assert (
        km._read_secret_row(vault_a / km.DB_FILENAME, "TEST_OTHER_KEY")
        == "vault-a-value"
    )


def test_concurrent_first_key_creation(km_no_keyring, tmp_path, monkeypatch):
    """Codex P2 (finding 2): concurrent first writes to a fresh vault must
    not fail vault_put — exactly one key is published, atomically, and every
    caller ends up with the same key."""
    km = km_no_keyring
    vault = tmp_path / "vault-race"
    monkeypatch.setenv("NOUGEN_SECRETS_VAULT_DIR", str(vault))
    monkeypatch.setattr(km, "VAULT_DIR", vault, raising=False)
    monkeypatch.setattr(km, "DB_PATH", vault / km.DB_FILENAME, raising=False)

    barrier = threading.Barrier(8)
    results, errors = [], []

    def _mint():
        try:
            barrier.wait(timeout=10)
            results.append(km._local_enc_key(create=True))
        except Exception as exc:  # noqa: BLE001 - collected for the assert
            errors.append(exc)

    threads = [threading.Thread(target=_mint) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors
    assert len(results) == 8
    assert len(set(results)) == 1  # one key, shared by every caller
    km.ingest_secret("TEST_RACE_KEY", "race-value")
    assert km.get_secret("TEST_RACE_KEY") == "race-value"


def test_local_enc_key_retries_not_yet_populated_file(
    km_no_keyring, tmp_path, monkeypatch
):
    """Codex P2 (finding 2), read side: a key file that is momentarily empty
    because a concurrent writer is mid-publish is retried, not raised."""
    km = km_no_keyring
    vault = tmp_path / "vault-retry"
    monkeypatch.setenv("NOUGEN_SECRETS_VAULT_DIR", str(vault))
    monkeypatch.setattr(km, "VAULT_DIR", vault, raising=False)
    monkeypatch.setattr(km, "DB_PATH", vault / km.DB_FILENAME, raising=False)
    vault.mkdir(parents=True, exist_ok=True)
    key_file = vault / km._LOCAL_ENC_KEY_FILENAME
    key_file.write_text("", "utf-8")  # empty: a writer is mid-publish
    real = base64.b64encode(secrets.token_bytes(km._LOCAL_ENC_KEY_BYTES)).decode("ascii")

    def _finish_publish():
        time.sleep(0.01)
        key_file.write_text(real, "utf-8")

    publisher = threading.Thread(target=_finish_publish)
    publisher.start()
    try:
        assert km._local_enc_key(create=False) == base64.b64decode(real)
    finally:
        publisher.join(timeout=10)
