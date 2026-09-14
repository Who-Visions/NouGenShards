"""Tests for destiny store and wake daemon in NouGen."""
from nougen_shards import destiny, wake_daemon


def test_destiny_crud(tmp_path, monkeypatch):
    test_db = tmp_path / "destinies_test.db"
    monkeypatch.setenv("NOUGEN_DESTINY_DB", str(test_db))

    # Create
    d = destiny.create_destiny(
        title="Test Ascension",
        goal="Reach production autonomy",
        branch="U0",
        trigger="When all tests pass",
        status="active",
        actor="test_runner"
    )
    assert "id" in d
    assert d["title"] == "Test Ascension"
    assert d["status"] == "active"

    # Get
    d_get = destiny.get_destiny(d["id"])
    assert d_get["goal"] == "Reach production autonomy"

    # Link
    link_res = destiny.link(d["id"], kind="shard", ref="1:100", role="evidence", note="proof shard")
    assert len(link_res["links"]) == 1
    assert link_res["links"][0]["ref"] == "1:100"

    # Update Status
    up = destiny.update_status(d["id"], "fulfilled", actor="test_runner", evidence="verified")
    assert up["status"] == "fulfilled"

    # Evolve report
    rep = destiny.evolve_report()
    assert rep["status_counts"]["fulfilled"] >= 1


def test_wake_daemon_snapshot():
    files = wake_daemon.get_snapshot()
    assert isinstance(files, dict)
