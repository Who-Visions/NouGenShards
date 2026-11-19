import json
import sqlite3

import pytest

from nougen_shards import vault_unify as vu


def make_vault(path, rows, index=1):
    path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path / f"nougen_shards_{index}.db"))
    conn.execute("CREATE TABLE IF NOT EXISTS shards (id INTEGER PRIMARY KEY, content TEXT)")
    conn.executemany("INSERT INTO shards (content) VALUES (?)", [(f"shard {i}",) for i in range(rows)])
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def vaults(tmp_path, monkeypatch):
    """A fresh tenant: 1,000 shards from the local install, 1 in the node's folder."""
    local = make_vault(tmp_path / "home" / ".nougen" / "shards", 600, index=1)
    make_vault(local, 400, index=2)
    node = make_vault(tmp_path / "account" / "shards", 1)
    monkeypatch.setenv(vu.ENV_LOCAL_VAULT, str(local))
    monkeypatch.setenv(vu.ENV_BACKUP_ROOT, str(tmp_path / "backups"))
    monkeypatch.setenv(vu.ENV_FREE_HEADROOM, "0")
    return node, local, tmp_path


def test_reproduces_the_split_node_sees_one_shard_of_a_thousand(vaults):
    node, local, _ = vaults
    report = vu.inspect(node)
    assert report["state"] == vu.ADOPTABLE
    assert (report["node_count"], report["local_count"]) == (1, 1000)
    assert "VAULT MISMATCH" in vu.describe(report)


def test_apply_points_node_at_existing_vault_and_recall_count_returns(vaults):
    node, local, tmp = vaults
    report = vu.apply(node)
    assert report["changed"] is True and report["state"] == vu.POINTED
    assert vu.resolve(node) == local.resolve()
    assert vu.count_shards(vu.resolve(node)) == 1000
    assert report["resolved_count"] == 1000


def test_apply_backs_up_both_and_deletes_or_overwrites_nothing(vaults):
    node, local, tmp = vaults
    before_local = sorted(p.name for p in local.iterdir())
    report = vu.apply(node)
    backup = tmp / "backups"
    made = list(backup.iterdir())
    assert len(made) == 1
    assert vu.count_shards(made[0] / "node") == 1
    assert vu.count_shards(made[0] / "local") == 1000
    manifest = json.loads((made[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["node_count"] == 1 and manifest["local_count"] == 1000
    # The node's own shard is still in its folder, the local vault is untouched.
    assert vu.count_shards(node) == 1
    assert sorted(p.name for p in local.iterdir()) == before_local
    assert report["backup_dir"] == str(made[0])


def test_apply_is_idempotent(vaults):
    node, _, tmp = vaults
    vu.apply(node)
    again = vu.apply(node)
    assert again["changed"] is False and again["action"] == "none"
    assert len(list((tmp / "backups").iterdir())) == 1


def test_refuses_when_both_vaults_are_populated(vaults, tmp_path):
    _, local, _ = vaults
    busy_node = make_vault(tmp_path / "busy" / "shards", 50)
    assert vu.inspect(busy_node)["state"] == vu.BOTH_POPULATED
    with pytest.raises(vu.VaultUnifyError, match="two vaults are both in use"):
        vu.apply(busy_node)
    assert vu.read_pointer(busy_node) is None
    assert vu.count_shards(busy_node) == 50


def test_populated_node_can_be_pointed_only_when_explicitly_allowed(vaults, tmp_path):
    busy_node = make_vault(tmp_path / "busy" / "shards", 50)
    report = vu.apply(busy_node, allow_populated_node=True)
    assert report["changed"] is True
    assert vu.count_shards(busy_node) == 50          # kept in place, not merged or removed


def test_control_fresh_install_with_no_local_vault_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setenv(vu.ENV_LOCAL_VAULT, str(tmp_path / "nothing-here"))
    node = make_vault(tmp_path / "account" / "shards", 3)
    report = vu.apply(node)
    assert report["state"] == vu.LOCAL_EMPTY and report["changed"] is False
    assert vu.startup_check(node) is None


def test_control_same_folder_is_not_a_mismatch(vaults):
    _, local, _ = vaults
    assert vu.inspect(local)["state"] == vu.SAME
    assert vu.startup_check(local) is None


def test_dry_run_changes_nothing(vaults):
    node, _, tmp = vaults
    report = vu.apply(node, dry_run=True)
    assert report["dry_run"] is True and report["changed"] is False
    assert vu.read_pointer(node) is None and not (tmp / "backups").exists()


def test_refuses_without_room_for_the_backups(vaults, monkeypatch):
    node, _, _ = vaults
    monkeypatch.setenv(vu.ENV_FREE_HEADROOM, str(10 ** 12))
    with pytest.raises(vu.VaultUnifyError, match="not enough free disk"):
        vu.apply(node)
    assert vu.read_pointer(node) is None


def test_pointer_to_missing_folder_or_to_itself_is_ignored(tmp_path):
    node = make_vault(tmp_path / "n", 1)
    (node / vu.POINTER_NAME).write_text(str(tmp_path / "gone"), encoding="utf-8")
    assert vu.read_pointer(node) is None
    (node / vu.POINTER_NAME).write_text(str(node), encoding="utf-8")
    assert vu.read_pointer(node) is None
    (node / vu.POINTER_NAME).write_text("{not json", encoding="utf-8")
    assert vu.read_pointer(node) is None


def test_startup_check_warns_by_default_and_refuses_only_when_asked(vaults, monkeypatch):
    node, _, _ = vaults
    assert "VAULT MISMATCH" in vu.startup_check(node)
    monkeypatch.setenv(vu.ENV_MISMATCH, "refuse")
    with pytest.raises(vu.VaultUnifyError):
        vu.startup_check(node)
    monkeypatch.setenv(vu.ENV_MISMATCH, "off")
    assert vu.startup_check(node) is None


def test_count_never_creates_or_modifies_a_vault(tmp_path):
    missing = tmp_path / "absent"
    assert vu.count_shards(missing) == 0
    assert not missing.exists()


def test_core_resolver_follows_the_pointer(vaults, monkeypatch):
    node, local, _ = vaults
    vu.apply(node)
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(node))
    from nougen_shards import core
    assert core._resolve_vault_dir() == local.resolve()
    assert "VAULT_POINTER" in core.VAULT_SOURCE
