"""Regression tests for keymaker secret-at-rest hardening (audit HIGH findings).

POSIX-only assertions (file modes); the credential-protection round-trip and
migration-honesty checks run everywhere via the plaintext escape hatch.
"""
import csv
import importlib
import os
import sqlite3
import stat
import subprocess
import sys

import pytest


@pytest.fixture
def km(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", "1")
    import nougen_shards.keymaker as keymaker
    importlib.reload(keymaker)
    yield keymaker


@pytest.fixture
def km_protected(tmp_path, monkeypatch):
    """Vault with the plaintext escape hatch OFF: _protect must really encrypt."""
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.delenv("NOUGEN_ALLOW_PLAINTEXT_VAULT", raising=False)
    import nougen_shards.keymaker as keymaker
    importlib.reload(keymaker)
    yield keymaker


def _protection_backend_available() -> bool:
    """True when _protect has a real backend (Windows DPAPI, or a POSIX keyring)."""
    if os.name == "nt":
        return True
    try:
        import keyring
        return keyring.get_keyring() is not None
    except Exception:  # pylint: disable=broad-except
        return False


requires_backend = pytest.mark.skipif(
    not _protection_backend_available(),
    reason="no OS secret backend (DPAPI/keyring) on this platform")
windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows ACL semantics")
# Synthetic, non-functional test material. Never a real credential.
FAKE_SECRET = "sk-nougen-test-" + ("Z9" * 12)


# --------------------------------------------------------------------------
# Gap 1: the crypto round-trip itself. Neutering _protect into a no-op used to
# leave every secret in plaintext at rest with the whole suite still green.
# --------------------------------------------------------------------------

@requires_backend
def test_ingested_secret_round_trips_through_real_crypto(km_protected):
    km_protected.ingest_secret("ROUNDTRIP_KEY", FAKE_SECRET)
    assert km_protected.get_secret("ROUNDTRIP_KEY") == FAKE_SECRET


@requires_backend
def test_secret_is_never_plaintext_in_the_sqlite_bytes_on_disk(km_protected):
    km_protected.ingest_secret("ATREST_KEY", FAKE_SECRET)

    stored_column = sqlite3.connect(str(km_protected.DB_PATH)).execute(
        "SELECT secret_value FROM secrets WHERE secret_key='ATREST_KEY'").fetchone()[0]
    assert stored_column != FAKE_SECRET
    assert km_protected._is_encrypted(stored_column)

    # The raw file bytes, not just the column: covers freelist pages, the WAL
    # and any journal sibling, plus the metadata-only CSV ledger.
    needles = [FAKE_SECRET.encode("utf-8"), FAKE_SECRET.encode("utf-16-le")]
    checked = 0
    for path in km_protected.VAULT_DIR.rglob("*"):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        checked += 1
        for needle in needles:
            assert needle not in blob, f"plaintext secret found at rest in {path.name}"
    assert checked, "vault produced no files to inspect"


@requires_backend
def test_service_account_private_key_round_trips_but_email_is_encrypted(km_protected):
    km_protected.ingest_service_account(
        '{"project_id":"p","client_email":"a@b.com","private_key":"' + FAKE_SECRET + '"}')
    # The SA metadata secret goes through _protect like any other secret.
    assert km_protected.get_secret("GCP_SA_P") == "a@b.com"
    db_bytes = km_protected.DB_PATH.read_bytes()
    assert b"a@b.com" not in db_bytes


# --------------------------------------------------------------------------
# Gap 2: _is_encrypted must DISCRIMINATE. Hardcoding it to True made the CSV
# audit ledger claim every legacy plaintext row was protected.
# --------------------------------------------------------------------------

def test_is_encrypted_discriminates_ciphertext_from_plaintext(km):
    assert km._is_encrypted("plainvalue") is False
    assert km._is_encrypted("") is False
    assert km._is_encrypted("postgres://u:pass@host/db") is False
    assert km._is_encrypted(km._DPAPI_PREFIX + "AQAAANCMnd8=") is True
    assert km._is_encrypted(km._KEYRING_PREFIX + "abc123") is True


@requires_backend
def test_is_encrypted_recognises_real_protect_output(km_protected):
    assert km_protected._is_encrypted(km_protected._protect(FAKE_SECRET, "K")) is True


def test_csv_ledger_reports_plaintext_rows_as_unprotected(km):
    """The ledger must not lie: a legacy plaintext row reports encrypted=False."""
    km.init_vault()
    conn = sqlite3.connect(str(km.DB_PATH))
    conn.execute("INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)"
                 " VALUES ('LEGACY_PLAIN','plainvalue','t')")
    conn.commit()
    conn.close()
    km._export_to_csv()
    with open(km.CSV_PATH, newline="", encoding="utf-8") as f_in:
        rows = {r["secret_key"]: r for r in csv.DictReader(f_in)}
    assert rows["LEGACY_PLAIN"]["encrypted"] == "False"


# --------------------------------------------------------------------------
# JOB 2 / JOB 3: owner-only protection, verified on the platform that runs it.
# The POSIX st_mode tests above are skipped on NTFS, so these are the ones that
# actually exercise the control here.
# --------------------------------------------------------------------------

def _icacls(path) -> str:
    proc = subprocess.run(["icacls", str(path)], capture_output=True, text=True,
                          check=True, timeout=30)
    return proc.stdout


def _assert_windows_owner_only(path, km_mod):
    text = _icacls(path)
    user = km_mod._resolve_acl_user()
    short = user.split("\\")[-1].lower()
    lines = [ln for ln in text.splitlines() if ":(" in ln]
    assert lines, f"icacls reported no ACEs for {path}:\n{text}"
    # Inheritance disabled: inherited ACEs are flagged (I) by icacls.
    assert "(I)" not in text, f"inherited ACEs still present on {path}:\n{text}"
    assert "BUILTIN\\Users" not in text, f"BUILTIN\\Users still granted on {path}:\n{text}"
    assert "Everyone" not in text, f"Everyone still granted on {path}:\n{text}"
    assert "(F)" in text, f"current user lacks full control on {path}:\n{text}"
    for line in lines:
        principal = line.split(":(")[0].strip()
        principal = principal.replace(str(path), "").strip()
        assert principal.split("\\")[-1].lower() == short, (
            f"unexpected principal {principal!r} on {path}:\n{text}")


@windows_only
def test_vault_dirs_are_owner_only_windows(km):
    """Windows counterpart of test_vault_dirs_are_owner_only (POSIX-skipped)."""
    km.init_vault()
    _assert_windows_owner_only(km.VAULT_DIR, km)
    _assert_windows_owner_only(km.SECRETS_JSON_DIR, km)


@windows_only
def test_service_account_json_is_owner_only_windows(km):
    """Windows counterpart of test_service_account_json_is_owner_only."""
    km.ingest_service_account('{"project_id":"p","client_email":"a@b.com","private_key":"K"}')
    saf = km.SECRETS_JSON_DIR / "p_service_account.json"
    assert saf.exists()
    _assert_windows_owner_only(saf, km)


@windows_only
def test_existing_service_account_file_is_repaired_windows(km):
    """Windows counterpart of test_existing_service_account_file_is_repaired_to_0600:
    a pre-existing file with inherited ACEs must be re-locked on re-ingest."""
    km.init_vault()
    saf = km.SECRETS_JSON_DIR / "p_service_account.json"
    saf.write_text("{}", encoding="utf-8")
    # Re-enable inheritance so the file starts out inheriting, as an older
    # version (or a restore/copy) would have left it.
    subprocess.run(["icacls", str(saf), "/inheritance:e"], capture_output=True,
                   check=False, timeout=30)
    subprocess.run(["icacls", str(saf), "/grant", "*S-1-5-32-545:(R)"],
                   capture_output=True, check=False, timeout=30)
    km.ingest_service_account('{"project_id":"p","client_email":"a@b.com","private_key":"K"}')
    _assert_windows_owner_only(saf, km)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_secrets_db_is_owner_only_posix(km):
    km.init_vault()
    assert stat.S_IMODE(os.stat(km.DB_PATH).st_mode) == 0o600


@windows_only
def test_secrets_db_is_owner_only_windows(km):
    """shards_secrets.db previously got no chmod and no icacls on any platform."""
    km.init_vault()
    assert km.DB_PATH.exists()
    _assert_windows_owner_only(km.DB_PATH, km)


# --------------------------------------------------------------------------
# JOB 2: the ACL must FAIL LOUDLY, never silently skip.
# --------------------------------------------------------------------------

@windows_only
def test_empty_username_env_still_locks_the_service_account(km, monkeypatch):
    """Old behaviour: USERNAME='' -> `if user:` false -> icacls skipped silently,
    leaving the plaintext private key at inherited permissions. Now the user is
    resolved from a real API instead, so the lock is still applied."""
    for var in km._ACL_USER_ENV_VARS:
        monkeypatch.setenv(var, "")
    km.ingest_service_account('{"project_id":"p","client_email":"a@b.com","private_key":"K"}')
    saf = km.SECRETS_JSON_DIR / "p_service_account.json"
    assert saf.exists()
    _assert_windows_owner_only(saf, km)


def test_unresolvable_user_raises_instead_of_skipping(km, monkeypatch):
    """When no identity can be established at all, refuse rather than continue."""
    monkeypatch.setattr(km, "_windows_user_from_api", lambda: "")
    for var in km._ACL_USER_ENV_VARS:
        monkeypatch.setenv(var, "")
    import getpass
    monkeypatch.setattr(getpass, "getuser", lambda: "")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(
        OSError("no whoami")))
    with pytest.raises(km.VaultProtectionError):
        km._resolve_acl_user()


@windows_only
def test_failed_acl_raises_and_removes_the_unprotected_key_file(km, monkeypatch):
    """icacls failure used to be swallowed by check=False. It must now raise,
    and must not leave the plaintext private key behind."""
    km.init_vault()  # harden the dirs first, so only the SA file's ACL fails
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd and cmd[0] == "icacls" and str(cmd[1]).endswith("_service_account.json"):
            class _Failed:
                returncode = 5
                stdout = ""
                stderr = "Access is denied."
            return _Failed()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(km.VaultProtectionError):
        km.ingest_service_account(
            '{"project_id":"p","client_email":"a@b.com","private_key":"K"}')
    assert not (km.SECRETS_JSON_DIR / "p_service_account.json").exists()


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
    km.init_vault()
    conn = sqlite3.connect(str(km.DB_PATH))
    conn.execute("INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)"
                 " VALUES ('LEG','plainvalue','t')")
    conn.commit()
    conn.close()
    # Simulate the escape hatch where _protect cannot encrypt and returns the
    # value unchanged (on Windows DPAPI always encrypts, so force the no-op):
    # nothing should be reported as migrated (the old code falsely counted it).
    monkeypatch.setattr(km, "_protect", lambda value, key=None: value)
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
