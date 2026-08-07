"""The secrets vault must resolve to ONE place, deterministically.

Before this was fixed, `VAULT_DIR` was `Path(os.getenv("NOUGEN_VAULT_DIR",
".nougen_vault"))`, which failed two ways at once:

  * `.nougen_vault` is CWD-relative, so the store moved with the working
    directory. Measured on a real deployment: 44 secrets spread across FOUR
    stores, and `get_secret` returning None looked exactly like "never
    ingested" rather than "you are pointed at the wrong file".
  * NOUGEN_VAULT_DIR is the MEMORY vault. Sharing it aimed the secrets DB at a
    directory of 40+ shard databases, and `init_vault()` then tried to icacls
    that whole tree -- which timed out and made vault init fail outright.

These tests pin the fix: two possible answers, neither influenced by CWD or by
the memory-vault variable.
"""
from nougen_shards import keymaker


def test_explicit_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(tmp_path / "chosen"))
    assert keymaker.resolve_secrets_vault_dir() == tmp_path / "chosen"


def test_default_is_user_anchored_not_cwd_relative(monkeypatch, tmp_path):
    monkeypatch.delenv(keymaker.ENV_SECRETS_VAULT, raising=False)
    expected = keymaker.Path.home() / ".nougen" / "secrets"
    assert keymaker.resolve_secrets_vault_dir() == expected
    assert keymaker.resolve_secrets_vault_dir().is_absolute()


def test_resolution_does_not_move_with_the_working_directory(monkeypatch, tmp_path):
    """The regression that fragmented the vault across four stores."""
    monkeypatch.delenv(keymaker.ENV_SECRETS_VAULT, raising=False)
    before = keymaker.resolve_secrets_vault_dir()

    elsewhere = tmp_path / "some" / "other" / "checkout"
    elsewhere.mkdir(parents=True)
    # Plant exactly the bait the old resolver would have taken.
    legacy = elsewhere / ".nougen_vault"
    legacy.mkdir()
    (legacy / keymaker.DB_FILENAME).write_bytes(b"")

    monkeypatch.chdir(elsewhere)
    assert keymaker.resolve_secrets_vault_dir() == before


def test_memory_vault_env_is_not_consulted(monkeypatch, tmp_path):
    """NOUGEN_VAULT_DIR points at the shard cluster; secrets must ignore it.

    Honouring it is what aimed init_vault's icacls at a hundreds-of-MB tree.
    """
    monkeypatch.delenv(keymaker.ENV_SECRETS_VAULT, raising=False)
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path / "memory_vault"))
    assert keymaker.resolve_secrets_vault_dir() != tmp_path / "memory_vault"


def test_explicit_env_beats_memory_vault_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path / "memory_vault"))
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(tmp_path / "secrets"))
    assert keymaker.resolve_secrets_vault_dir() == tmp_path / "secrets"


# --- drift detection --------------------------------------------------------

def test_find_legacy_stores_reports_stores_outside_the_canonical_vault(monkeypatch, tmp_path):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(canonical))

    stray = tmp_path / "checkout" / ".nougen_vault"
    stray.mkdir(parents=True)
    (stray / keymaker.DB_FILENAME).write_bytes(b"")

    found = keymaker.find_legacy_stores(roots=[tmp_path])
    assert (stray / keymaker.DB_FILENAME).resolve() in found


def test_find_legacy_stores_excludes_the_canonical_vault(monkeypatch, tmp_path):
    """The canonical store is not drift; reporting it would cry wolf forever."""
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / keymaker.DB_FILENAME).write_bytes(b"")
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(canonical))

    found = keymaker.find_legacy_stores(roots=[tmp_path])
    assert (canonical / keymaker.DB_FILENAME).resolve() not in found


def test_find_legacy_stores_survives_an_unreadable_root(monkeypatch, tmp_path):
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(tmp_path / "canonical"))
    assert keymaker.find_legacy_stores(roots=[tmp_path / "does" / "not" / "exist"]) == []


def test_derived_paths_hang_off_the_resolved_dir():
    assert keymaker.DB_PATH.parent == keymaker.VAULT_DIR
    assert keymaker.CSV_PATH.parent == keymaker.VAULT_DIR
    assert keymaker.SECRETS_JSON_DIR.parent == keymaker.VAULT_DIR
    assert keymaker.DB_PATH.name == keymaker.DB_FILENAME
