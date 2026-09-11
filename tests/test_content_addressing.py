"""Tests for content-addressed shard lookup and 'nougen get' command."""
import pytest
from unittest.mock import patch
from nougen_shards import core as shards
from nougen_shards.cli import main as cli_main


@pytest.fixture
def bound_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    tokens = shards.bind_active_vault(tmp_path, "owner")
    shards._INITIALIZED_DBS.clear()
    for i in range(1, 10):
        shards.init_db(i)
    yield tmp_path
    shards._INITIALIZED_DBS.clear()
    shards.reset_active_vault(tokens)


def test_get_shard_by_hash_exact_and_prefix(bound_vault):
    # Capture two distinct shards
    res_a = shards.capture("LOG", "Alpha Title", "Deterministic Shard Alpha for Testing Content Addressing", tags=["alpha", "test"])
    assert res_a.get("captured") is True
    target_id = res_a["shard_id"]
    target_db = res_a["db_index"]

    shard_a = shards.get_shard_by_id(target_id, target_db)
    assert shard_a is not None
    hash_a = shard_a["file_hash"]
    assert len(hash_a) == 32

    # 1. Exact hash lookup
    found_exact = shards.get_shard_by_hash(hash_a)
    assert found_exact is not None
    assert found_exact["id"] == target_id
    assert "Alpha" in found_exact["content"]
    assert found_exact["__db_index__"] == target_db

    # 2. sha: prefix syntax lookup (e.g. 12 chars)
    found_prefix = shards.get_shard_by_hash(f"sha:{hash_a[:12]}")
    assert found_prefix is not None
    assert found_prefix["id"] == target_id

    # 3. 8-char minimum prefix lookup
    found_8 = shards.get_shard_by_hash(hash_a[:8])
    assert found_8 is not None
    assert found_8["id"] == target_id

    # 4. Non-existent hash returns None (loud miss)
    missing = shards.get_shard_by_hash("ffffffffffffffffffffffffffffffff")
    assert missing is None

    # 5. Missing prefix returns None
    missing_prefix = shards.get_shard_by_hash("sha:ffffffffffff")
    assert missing_prefix is None


def test_cli_get_command(bound_vault, capsys):
    res = shards.capture("LOG", "Gamma Title", "Shard Gamma for CLI Testing", tags=["gamma"])
    assert res.get("captured") is True
    target_id = res["shard_id"]
    target_db = res["db_index"]
    shard_gamma = shards.get_shard_by_id(target_id, target_db)
    target_hash = shard_gamma["file_hash"]

    # Test CLI get by hash prefix
    with patch("sys.argv", ["nougen", "get", target_hash[:10]]):
        cli_main()
    captured = capsys.readouterr().out
    assert "Shard Gamma for CLI Testing" in captured
    assert f"sha:{target_hash[:12]}" in captured

    # Test CLI get by locator id@dbN
    with patch("sys.argv", ["nougen", "get", f"{target_id}@db{target_db}"]):
        cli_main()
    captured = capsys.readouterr().out
    assert "Shard Gamma for CLI Testing" in captured

    # Test CLI get missing hash returns exit code 1
    with patch("sys.argv", ["nougen", "get", "sha:000000000000"]):
        with pytest.raises(SystemExit) as exc:
            cli_main()
        assert exc.value.code == 1
