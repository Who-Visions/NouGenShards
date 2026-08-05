"""The credential vault must resolve absolutely and stay out of the shard substrate."""
import importlib
from pathlib import Path

import pytest

from nougen_shards import keymaker


@pytest.fixture
def reloaded(monkeypatch):
    """Reimport keymaker so module-level path constants are recomputed."""
    def _reload(cwd: Path, **env):
        for var in ("NOUGEN_SECRETS_DIR", "NOUGEN_VAULT_DIR"):
            monkeypatch.delenv(var, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.chdir(cwd)
        return importlib.reload(keymaker)

    yield _reload
    importlib.reload(keymaker)


def test_default_vault_is_absolute_and_cwd_independent(reloaded, tmp_path):
    """Keys stored from one directory must be visible from another."""
    nested = tmp_path / "nested"
    nested.mkdir()

    first = reloaded(tmp_path).DB_PATH
    second = reloaded(nested).DB_PATH

    assert first.is_absolute()
    assert first == second
    assert first == Path.home() / ".nougen" / "vault" / "shards_secrets.db"


def test_shard_substrate_var_does_not_capture_secrets(reloaded, tmp_path):
    """NOUGEN_VAULT_DIR points at the shard substrate; secrets must not land there."""
    substrate = tmp_path / "shards"
    module = reloaded(tmp_path, NOUGEN_VAULT_DIR=str(substrate))

    assert substrate not in module.DB_PATH.parents


def test_explicit_secrets_dir_wins(reloaded, tmp_path):
    module = reloaded(tmp_path, NOUGEN_SECRETS_DIR=str(tmp_path / "creds"))

    assert module.DB_PATH == (tmp_path / "creds" / "shards_secrets.db").resolve()


def test_existing_local_vault_is_not_orphaned(reloaded, tmp_path):
    """An upgrade must keep using a project-local vault that already holds keys."""
    (tmp_path / ".nougen_vault").mkdir()
    module = reloaded(tmp_path)

    assert module.DB_PATH == (tmp_path / ".nougen_vault" / "shards_secrets.db").resolve()


def test_derived_paths_share_the_vault_dir(reloaded, tmp_path):
    module = reloaded(tmp_path, NOUGEN_SECRETS_DIR=str(tmp_path / "creds"))

    assert module.DB_PATH.parent == module.VAULT_DIR
    assert module.CSV_PATH.parent == module.VAULT_DIR
    assert module.SECRETS_JSON_DIR.parent == module.VAULT_DIR
    assert module.VAULT_DIR.is_absolute()
