"""Encryption at rest for personal-scope shards.

The threat model is narrow and concrete: personal financial and identity
records are being captured as shards. Before this lane existed the bodies
landed as plaintext in a multi-hundred-MB SQLite cluster and a plaintext FTS
index.

Every fixture below is synthetic. Real account numbers, balances, and
addresses must never appear in this repository -- that is the whole point of
the module under test.
These tests pin the properties that make that safe:

  1. ciphertext round-trips, and a tampered byte is REJECTED, not silently
     decoded into garbage;
  2. a private shard's body is not readable with raw sqlite3 against the DB file;
  3. the plaintext body is absent from the shards_fts index;
  4. normal shards are untouched â€” no re-encryption, no behaviour change;
  5. file encryption never deletes an original it could not verify.
"""
import base64
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards
from nougen_shards import private_vault as pv
from nougen_shards import schema


# A fixed test key keeps the suite hermetic and off DPAPI, so it runs on CI and
# non-Windows lanes. Production resolves the key via DPAPI or the recovery file.
TEST_KEY_B64 = base64.b64encode(b"\x11" * 32).decode("ascii")


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv(pv.ENV_KEY, TEST_KEY_B64)
    pv.reset_key_cache()
    yield
    pv.reset_key_cache()


# --- primitives -------------------------------------------------------------

def test_round_trip_preserves_unicode():
    secret = "Placeholder Bank ending 0000 â€” balance $1.23 Â· cafÃ©"
    blob = pv.encrypt_text(secret)
    assert blob.startswith(pv.ENC_PREFIX)
    assert secret not in blob
    assert pv.decrypt_text(blob) == secret


def test_nonce_is_fresh_per_call():
    a = pv.encrypt_text("same input")
    b = pv.encrypt_text("same input")
    assert a != b, "a reused nonce would leak equality between shards"
    assert pv.decrypt_text(a) == pv.decrypt_text(b) == "same input"


def test_tampered_ciphertext_is_rejected():
    from cryptography.exceptions import InvalidTag
    blob = pv.encrypt_text("tax return 2024")
    raw = bytearray(base64.b64decode(blob[len(pv.ENC_PREFIX):]))
    raw[-1] ^= 0x01
    tampered = pv.ENC_PREFIX + base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(InvalidTag):
        pv.decrypt_text(tampered)


def test_plaintext_passes_through_both_ways():
    """A mixed corpus must keep working: the old plaintext shards still read."""
    assert pv.decrypt_text("just a normal shard") == "just a normal shard"
    assert not pv.is_encrypted("just a normal shard")


def test_encrypt_is_idempotent():
    once = pv.encrypt_text("statement")
    assert pv.encrypt_text(once) == once


def test_wrong_key_cannot_decrypt():
    from cryptography.exceptions import InvalidTag
    blob = pv.encrypt_text("100 Example Street")
    other = b"\x22" * 32
    with pytest.raises(InvalidTag):
        pv.decrypt_text(blob, key=other)


# --- sensitivity contract ---------------------------------------------------

def test_sensitivity_levels():
    assert pv.normalize_sensitivity(None) == "normal"
    assert pv.normalize_sensitivity("PRIVATE") == "private"
    assert not pv.should_encrypt(None)
    assert not pv.should_encrypt("normal")
    assert pv.should_encrypt("private")
    assert pv.should_encrypt("secret")
    with pytest.raises(ValueError):
        pv.normalize_sensitivity("kinda-secret")


# --- shard integration ------------------------------------------------------

@pytest.fixture
def vault(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)
        monkeypatch.setattr(shards, "get_db_path",
                            lambda index: temp_path / f"test_shards_{index}.db")
        monkeypatch.setenv("NOUGEN_EMBED_MODEL", "")
        shards.init_db(1)
        yield temp_path


BODY = "Example Bank checking ending 0000 cleared $12.34 on 2026-01-01."


def _raw_rows(db_path, sql):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _locate(vault):
    """capture() shards by domain, so the target DB index is chosen at write
    time. Find whichever cluster DB actually took the row."""
    for path in sorted(vault.glob("test_shards_*.db")):
        conn = sqlite3.connect(path)
        try:
            row = conn.execute("SELECT id FROM shards LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            continue
        finally:
            # Windows will not remove the temp dir while a handle is open.
            conn.close()
        if row:
            index = int(path.stem.rsplit("_", 1)[1])
            return path, row[0], index
    raise AssertionError("no cluster DB holds the captured shard")


def test_private_shard_is_ciphertext_on_disk(vault):
    assert shards.capture("FINANCE", "Aug payment", BODY, sensitivity="private")
    db, _id, _idx = _locate(vault)

    rows = _raw_rows(db, "SELECT content, sensitivity, enc FROM shards")
    assert len(rows) == 1
    content, sensitivity, enc = rows[0]
    assert sensitivity == "private" and enc == 1
    assert content.startswith(pv.ENC_PREFIX)
    assert BODY not in content

    # And not anywhere in the raw file bytes, which is the property that matters
    # if the DB is ever copied off the machine.
    assert BODY.encode("utf-8") not in db.read_bytes()


def test_private_body_absent_from_fts_index(vault):
    shards.capture("FINANCE", "Aug payment", BODY, sensitivity="private")
    db, _id, _idx = _locate(vault)
    indexed = _raw_rows(db, "SELECT content FROM shards_fts")
    assert indexed, "the FTS trigger should still fire â€” only the body is opaque"
    assert all(BODY not in (r[0] or "") for r in indexed)


def test_private_shard_decrypts_on_read(vault):
    shards.capture("FINANCE", "Aug payment", BODY, sensitivity="private")
    _db, shard_id, index = _locate(vault)
    got = shards.get_shard_by_id(shard_id, index)
    assert got["content"] == BODY
    assert got["sensitivity"] == "private"


def test_missing_key_degrades_to_placeholder_not_crash(vault, monkeypatch):
    shards.capture("FINANCE", "Aug payment", BODY, sensitivity="private")
    _db, shard_id, index = _locate(vault)
    monkeypatch.delenv(pv.ENV_KEY, raising=False)
    monkeypatch.setenv(pv.ENV_KEY_FILE, str(vault / "absent.bin"))
    monkeypatch.setenv(pv.ENV_KEY_SEARCH_PATH, str(vault / "nowhere"))
    pv.reset_key_cache()
    got = shards.get_shard_by_id(shard_id, index)
    assert "unavailable" in got["content"]  # one bad shard must not kill recall


def test_normal_shards_stay_plaintext(vault):
    body = "ordinary engineering note about retries"
    assert shards.capture("KNOWLEDGE", "Retries", body)
    db, _id, _idx = _locate(vault)
    rows = _raw_rows(db, "SELECT content, sensitivity, enc FROM shards")
    content, sensitivity, enc = rows[0]
    assert content == body
    assert sensitivity == "normal" and enc == 0


# --- file lane --------------------------------------------------------------

def test_file_round_trip_and_original_removed_after_verification(tmp_path):
    src = tmp_path / "statement.csv"
    payload = b"date,amount\n2026-01-01,-12.34\n"
    src.write_bytes(payload)

    out = pv.encrypt_file(str(src))
    assert out.endswith(pv.FILE_SUFFIX)
    assert not src.exists(), "original is removed only after a verified round trip"
    assert payload not in Path(out).read_bytes()

    back = pv.decrypt_file(out)
    assert Path(back).read_bytes() == payload


def test_keep_original_leaves_source_in_place(tmp_path):
    src = tmp_path / "keep.txt"
    src.write_bytes(b"hold onto this")
    pv.encrypt_file(str(src), keep_original=True)
    assert src.exists()


def test_failed_verification_never_deletes_the_original(tmp_path, monkeypatch):
    """The whole point of the verify step: irreplaceable records survive a bug."""
    src = tmp_path / "taxes.csv"
    src.write_bytes(b"irreplaceable")
    monkeypatch.setattr(pv, "decrypt_file_bytes", lambda _p: b"corrupted")
    with pytest.raises(pv.PrivateVaultError):
        pv.encrypt_file(str(src))
    assert src.exists(), "original must survive a failed verification"
    assert not (tmp_path / ("taxes.csv" + pv.FILE_SUFFIX)).exists()


def test_non_nougen_file_is_rejected(tmp_path):
    stray = tmp_path / "not-ours.bin"
    stray.write_bytes(b"random bytes")
    with pytest.raises(pv.PrivateVaultError):
        pv.decrypt_file_bytes(str(stray))


# --- key custody ------------------------------------------------------------

def test_key_generation_always_writes_a_recovery_file(tmp_path, monkeypatch):
    monkeypatch.delenv(pv.ENV_KEY, raising=False)
    monkeypatch.setenv(pv.ENV_KEY_FILE, str(tmp_path / "vault" / "private_key.bin"))
    monkeypatch.setenv(pv.ENV_KEY_SEARCH_PATH, str(tmp_path / "vault"))
    pv.reset_key_cache()
    try:
        key = pv.load_key(create=True)
    except pv.PrivateVaultError:
        pytest.skip("no DPAPI or OS keyring available on this lane")
    assert len(key) == 32
    recovery = Path(pv.recovery_path())
    assert recovery.exists(), "a key must never exist without a recovery path"
    assert pv.ENV_KEY in recovery.read_text(encoding="utf-8")


def test_bad_env_key_is_rejected_loudly(monkeypatch):
    monkeypatch.setenv(pv.ENV_KEY, base64.b64encode(b"tooshort").decode())
    pv.reset_key_cache()
    with pytest.raises(pv.PrivateVaultError):
        pv.load_key()


# --- migration --------------------------------------------------------------

def test_migration_adds_sensitivity_columns_and_is_idempotent(tmp_path):
    db = tmp_path / "nougen_shards_1.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE shards (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event_type TEXT,
        title TEXT, content TEXT, tags TEXT, file_hash TEXT UNIQUE,
        utility_score REAL DEFAULT 1.0, access_count INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()

    assert any("sensitivity" in op for op in schema.plan_db(str(db)).pending)

    schema.apply_db(str(db), backup=False)
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(shards)")}
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert {"sensitivity", "enc"} <= cols
    assert version == schema.TARGET_SCHEMA_VERSION

    # Re-running is a no-op, not a second round of ALTERs.
    assert schema.plan_db(str(db)).pending == []


def test_existing_key_is_found_before_a_new_one_is_minted(tmp_path, monkeypatch):
    """Silent key divergence is data loss.

    A deployment can have more than one configured vault directory. If
    NOUGEN_VAULT_DIR points somewhere without a key, load_key must sweep the
    other configured locations before generating â€” otherwise a second key gets
    minted and every shard encrypted under the first becomes unreadable.
    """
    home = tmp_path / "home"
    (home / "workspace" / "vault").mkdir(parents=True)
    monkeypatch.delenv(pv.ENV_KEY, raising=False)
    monkeypatch.setenv(pv.ENV_KEY_SEARCH_PATH, str(home / "workspace" / "vault"))
    monkeypatch.setenv(pv.ENV_KEY_FILE, str(tmp_path / "elsewhere" / "private_key.bin"))
    pv.reset_key_cache()

    planted = home / "workspace" / "vault" / pv.KEY_FILENAME
    try:
        from nougen_shards.keymaker import _protect
        planted.write_text(_protect(TEST_KEY_B64), encoding="utf-8")
    except Exception:
        pytest.skip("no DPAPI or OS keyring available on this lane")

    found = pv.load_key(create=True)
    assert base64.b64encode(found).decode() == TEST_KEY_B64
    assert not (tmp_path / "elsewhere").exists(), "must not mint a competing key"


# --- migration coverage across a heterogeneous vault -------------------------

def _make_shard_db(path, with_utility=True):
    extra = ", utility_score REAL DEFAULT 1.0" if with_utility else ""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE shards (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,"
        f" event_type TEXT, title TEXT, content TEXT, tags TEXT, file_hash TEXT UNIQUE{extra})")
    conn.commit()
    conn.close()


def test_migration_covers_domain_vaults_not_just_the_numbered_cluster(tmp_path):
    """A vault can hold brain_scan `*_vault.db` files alongside the cluster.

    A filename-only glob left them a schema version behind, which stays invisible
    until a write carrying a newer column lands on one and fails.
    """
    _make_shard_db(tmp_path / "nougen_shards_1.db")
    _make_shard_db(tmp_path / "who_visions_vault.db", with_utility=False)
    # A DB with no shards table at all must be ignored, not crashed on.
    sqlite3.connect(tmp_path / "history.db").execute("CREATE TABLE events (id INTEGER)")

    found = {Path(p).name for p in schema._vault_dbs(str(tmp_path))}
    assert found == {"nougen_shards_1.db", "who_visions_vault.db"}


def test_missing_column_skips_one_index_not_the_whole_migration(tmp_path):
    """A domain vault has no utility_score. That must cost one index, not v2."""
    db = tmp_path / "who_visions_vault.db"
    _make_shard_db(db, with_utility=False)
    schema.SKIPPED_INDEXES.clear()

    schema.apply_db(str(db), backup=False)

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(shards)")}
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert {"sensitivity", "enc"} <= cols
    assert version == schema.TARGET_SCHEMA_VERSION, "the DB must still reach v2"
    assert any("utility_score" in note for note in schema.SKIPPED_INDEXES), \
        "the skip must be reported, never silently swallowed"


def test_db_glob_override_is_honoured(tmp_path, monkeypatch):
    _make_shard_db(tmp_path / "nougen_shards_1.db")
    _make_shard_db(tmp_path / "who_visions_vault.db", with_utility=False)
    monkeypatch.setenv(schema.ENV_DB_GLOBS, "who_*_vault.db")
    found = {Path(p).name for p in schema._vault_dbs(str(tmp_path))}
    assert found == {"who_visions_vault.db"}
