"""The vault-move trap: a stale env var must fail LOUD, never silent-None.

`get_secret` used to trust exactly one path and return None when the key was
not in that file -- and "not in this file" reads exactly like "never
ingested". Measured 2026-08-15: a moved vault left the env var aimed at the
old, empty store, and three provider lanes concluded their keys had never
been ingested. Rule 0.2: probe, don't trust.

These tests pin the fix:

  * resolve_secrets_store() probes every candidate (env, conventional,
    legacy) live -- exists, opens read-only, holds >0 secrets rows.
  * An env var aimed at a dead/empty store logs a WARNING naming both the
    dead path and the live store that was found.
  * A key absent from the active store but present in another LIVE store is
    a divergence, governed by NOUGEN_VAULT_DIVERGENCE = warn (default,
    loud None) | error (raise) | adopt (read-only adoption).
  * The env-configured store stays authoritative: a value is never silently
    served from a store the operator did not point at.

The suite-wide conftest fixture disables the probe chain (it would look
beyond the test isolation boundary by design); every test here re-enables it
against a fabricated home directory so no real store is ever touched.
"""
import logging
import sqlite3
from datetime import datetime

import pytest

from nougen_shards import keymaker


def _make_store(vault_dir, secrets):
    """Create a keymaker-shaped secrets store holding `secrets` (plaintext rows,
    which _unprotect passes through untouched -- keeps the tests cross-platform)."""
    vault_dir.mkdir(parents=True, exist_ok=True)
    db = vault_dir / keymaker.DB_FILENAME
    conn = sqlite3.connect(str(db))
    conn.execute('''
        CREATE TABLE IF NOT EXISTS secrets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            secret_key TEXT UNIQUE NOT NULL,
            secret_value TEXT NOT NULL,
            last_rotated TEXT NOT NULL
        )
    ''')
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for key, value in secrets.items():
        conn.execute(
            "INSERT OR REPLACE INTO secrets (secret_key, secret_value, last_rotated)"
            " VALUES (?, ?, ?)", (key, value, stamp))
    conn.commit()
    conn.close()
    return db


def _row_count(db):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Re-enable the probe chain against a fabricated home, so candidates are
    fully controlled and no real store on this machine can enter the test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv(keymaker.ENV_VAULT_PROBE, "1")
    monkeypatch.setattr(keymaker.Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def trap_world(fake_home, tmp_path, monkeypatch):
    """The exact moved-vault shape: env points at an initialized-but-EMPTY store,
    while the real secrets live in the conventional location."""
    stale = tmp_path / "stale_vault"
    _make_store(stale, {})  # table exists, zero rows: dead by probe rules
    live = _make_store(fake_home / ".nougen" / "secrets", {"OPENAI_API_KEY": "sk-live-value"})
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(stale))
    return {"stale_db": stale / keymaker.DB_FILENAME, "live_db": live}


# --- the trap itself, all three divergence modes ---------------------------

def test_trap_default_warn_is_loud_not_silent(trap_world, monkeypatch, caplog):
    monkeypatch.delenv(keymaker.ENV_VAULT_DIVERGENCE, raising=False)
    with caplog.at_level(logging.INFO, logger=keymaker.__name__):
        assert keymaker.get_secret("OPENAI_API_KEY") is None  # env intent holds
    text = caplog.text
    assert "diverged" in text
    assert str(trap_world["live_db"]) in text            # names the store that has it
    assert keymaker.ENV_SECRETS_VAULT in text            # tells the operator the fix

def test_trap_resolution_warning_names_dead_env_and_live_store(trap_world, caplog):
    with caplog.at_level(logging.INFO, logger=keymaker.__name__):
        keymaker.get_secret("OPENAI_API_KEY")
    text = caplog.text
    assert str(trap_world["stale_db"].parent) in text    # the dead path env points at
    assert str(trap_world["live_db"]) in text            # the live store that won the probe

def test_trap_error_mode_raises(trap_world, monkeypatch):
    monkeypatch.setenv(keymaker.ENV_VAULT_DIVERGENCE, "error")
    with pytest.raises(keymaker.VaultDivergenceError):
        keymaker.get_secret("OPENAI_API_KEY")

def test_trap_adopt_mode_returns_value(trap_world, monkeypatch, caplog):
    monkeypatch.setenv(keymaker.ENV_VAULT_DIVERGENCE, "adopt")
    with caplog.at_level(logging.INFO, logger=keymaker.__name__):
        assert keymaker.get_secret("OPENAI_API_KEY") == "sk-live-value"
    assert "diverged" in caplog.text                     # adoption is still loud

def test_adopt_never_writes_to_any_store(trap_world, monkeypatch):
    """Second-order guard: adoption is READ-ONLY. Nothing is copied into the
    active store, and the donor store is not mutated."""
    monkeypatch.setenv(keymaker.ENV_VAULT_DIVERGENCE, "adopt")
    donor_before = trap_world["live_db"].read_bytes()
    keymaker.get_secret("OPENAI_API_KEY")
    assert _row_count(trap_world["stale_db"]) == 0       # active store still empty
    assert trap_world["live_db"].read_bytes() == donor_before

def test_bogus_divergence_mode_degrades_to_warn(trap_world, monkeypatch, caplog):
    monkeypatch.setenv(keymaker.ENV_VAULT_DIVERGENCE, "yolo")
    with caplog.at_level(logging.INFO, logger=keymaker.__name__):
        assert keymaker.get_secret("OPENAI_API_KEY") is None
    assert "diverged" in caplog.text


# --- probe order -----------------------------------------------------------

def test_live_env_store_wins_over_conventional(fake_home, tmp_path, monkeypatch):
    chosen = tmp_path / "chosen"
    _make_store(chosen, {"K": "from-env-store"})
    _make_store(fake_home / ".nougen" / "secrets", {"K": "from-conventional"})
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(chosen))
    assert keymaker.get_secret("K") == "from-env-store"

def test_conventional_beats_legacy_when_env_unset(fake_home, monkeypatch):
    monkeypatch.delenv(keymaker.ENV_SECRETS_VAULT, raising=False)
    _make_store(fake_home / ".nougen" / "secrets", {"K": "from-conventional"})
    _make_store(fake_home / "old_checkout" / keymaker._LEGACY_VAULT_DIRNAME,
                {"K": "from-legacy"})
    assert keymaker.get_secret("K") == "from-conventional"

def test_dead_default_falls_back_to_live_legacy_store(fake_home, monkeypatch, caplog):
    """No env var, nothing at the conventional path: a live legacy store is
    found by the probe and actually SERVES the key (with the choice logged),
    instead of the old silent None."""
    monkeypatch.delenv(keymaker.ENV_SECRETS_VAULT, raising=False)
    legacy = _make_store(fake_home / "old_checkout" / keymaker._LEGACY_VAULT_DIRNAME,
                         {"K": "from-legacy"})
    with caplog.at_level(logging.INFO, logger=keymaker.__name__):
        assert keymaker.get_secret("K") == "from-legacy"
    assert str(legacy) in caplog.text


# --- nothing anywhere ------------------------------------------------------

def test_no_store_anywhere_fails_loud(fake_home, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(tmp_path / "nowhere"))
    with caplog.at_level(logging.INFO, logger=keymaker.__name__):
        assert keymaker.get_secret("K") is None
    assert "No live secrets store" in caplog.text
    assert str(tmp_path / "nowhere") in caplog.text      # lists what was probed
