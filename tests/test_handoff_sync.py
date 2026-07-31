"""Cross-machine transport: records move, and arrivals fire triggers.

These tests run two real handoff directories against a real bare git remote, so
what is exercised is the actual round trip rather than a mocked one.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from nougen_shards import handoff, handoff_sync, handoff_triggers, machine, nougen_context


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git not on PATH")


@pytest.fixture
def fleet(monkeypatch):
    """A bare remote plus two handoff directories standing in for two computers."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        remote = root / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", "-b", "handoffs", str(remote)],
            capture_output=True, check=True,
        )
        monkeypatch.setattr(
            nougen_context, "SESSION_DB_PATH", str(root / "context_session.db")
        )
        monkeypatch.delenv("NOUGEN_TRIGGERS", raising=False)
        monkeypatch.delenv("NOUGEN_HANDOFF_REMOTE", raising=False)
        yield {"root": root, "remote": str(remote)}
        machine.host_label.cache_clear()
        machine.machine_id.cache_clear()


def _become(monkeypatch, fleet, host, machine_id):
    """Switch the process to one of the two machines, with its own handoff dir."""
    directory = fleet["root"] / host
    directory.mkdir(exist_ok=True)
    monkeypatch.setattr(handoff, "HANDOFF_DIR", directory)
    monkeypatch.setenv("NOUGEN_MACHINE", host)
    monkeypatch.setenv("NOUGEN_MACHINE_ID", machine_id)
    machine.host_label.cache_clear()
    machine.machine_id.cache_clear()
    return directory


def test_record_travels_between_two_machines(monkeypatch, fleet):
    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    path = handoff.create_handoff(goal="windows build", agent="codex")
    origin_id = json.loads(path.read_text(encoding="utf-8"))["handoff_id"]
    report = handoff_sync.sync(remote=fleet["remote"])
    assert report["pushed"] is True, report["errors"]

    _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    report = handoff_sync.sync(remote=fleet["remote"])
    assert report["pulled"] is True, report["errors"]
    assert origin_id in report["arrived"]

    # The record reads as remote on the receiving box, with the writer intact.
    files = handoff.get_handoff_files()
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["machine"]["host"] == "who-pc"
    assert machine.record_origin(data) == "remote"


def test_arriving_record_fires_triggers_on_the_receiving_machine(monkeypatch, fleet):
    receipt = fleet["root"] / "reacted.txt"

    _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    handoff_triggers.add_trigger(
        trigger_id="react-to-remote",
        run=f'echo "$NOUGEN_HANDOFF_HOST $NOUGEN_HANDOFF_GOAL" > "{receipt}"',
        events=["created"],
        origin="remote",
    )
    handoff_sync.sync(remote=fleet["remote"])

    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    handoff.create_handoff(goal="needs signing", agent="codex")
    handoff_sync.sync(remote=fleet["remote"])
    assert not receipt.exists(), "the writing machine must not react to its own record"

    _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    report = handoff_sync.sync(remote=fleet["remote"])
    assert report["arrived"], report["errors"]
    assert receipt.exists(), "arrival should have fired the remote-origin trigger"
    assert receipt.read_text().strip() == "who-pc needs signing"


def test_arrivals_replay_only_once(monkeypatch, fleet):
    counter = fleet["root"] / "count.txt"

    _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    handoff_triggers.add_trigger(
        trigger_id="count",
        run=f'echo x >> "{counter}"',
        events=["created"],
        origin="remote",
    )
    handoff_sync.sync(remote=fleet["remote"])

    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    handoff.create_handoff(goal="once only", agent="codex")
    handoff_sync.sync(remote=fleet["remote"])

    _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    handoff_sync.sync(remote=fleet["remote"])
    handoff_sync.sync(remote=fleet["remote"])
    handoff_sync.sync(remote=fleet["remote"])
    assert counter.read_text().split() == ["x"], "a record must not re-fire every sync"


def test_triggers_do_not_travel_by_default(monkeypatch, fleet):
    """Executable config must not arrive from another machine unasked."""
    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    handoff_triggers.add_trigger(trigger_id="pc-local", run="true", events=["created"])
    handoff.create_handoff(goal="carry me", agent="codex")
    handoff_sync.sync(remote=fleet["remote"])

    mac_dir = _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    handoff_sync.sync(remote=fleet["remote"])
    assert handoff.get_handoff_files(), "records should still have arrived"
    assert not (mac_dir / "triggers.json").exists()
    assert handoff_triggers.load_triggers() == []


def test_ack_travels_back_to_the_originating_machine(monkeypatch, fleet):
    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    path = handoff.create_handoff(goal="round trip", agent="codex")
    handoff_sync.sync(remote=fleet["remote"])

    _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    handoff_sync.sync(remote=fleet["remote"])
    handoff.acknowledge_handoff()
    handoff_sync.sync(remote=fleet["remote"])

    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    handoff_sync.sync(remote=fleet["remote"])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "acknowledged"
    assert data["acknowledged_on"]["host"] == "who-mac-mini"


def test_env_remote_is_written_into_the_repo(monkeypatch, fleet):
    """NOUGEN_HANDOFF_REMOTE must configure git, not just be reported back."""
    directory = _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    monkeypatch.setenv("NOUGEN_HANDOFF_REMOTE", fleet["remote"])
    handoff.create_handoff(goal="env remote", agent="codex")

    report = handoff_sync.sync()
    assert report["pushed"] is True, report["errors"]
    configured = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(directory), capture_output=True, text=True,
    ).stdout.strip()
    assert configured == fleet["remote"]


def test_sync_without_remote_reports_instead_of_failing(monkeypatch, fleet):
    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    handoff.create_handoff(goal="no remote", agent="codex")
    report = handoff_sync.sync()
    assert report["committed"] is True
    assert report["pushed"] is False
    assert any("No sync remote" in e for e in report["errors"])


def test_index_and_registry_stay_local(monkeypatch, fleet):
    directory = _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    handoff.create_handoff(goal="ignore check", agent="codex")
    handoff_sync.sync(remote=fleet["remote"])
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=str(directory), capture_output=True, text=True
    ).stdout.splitlines()
    assert "handoffs.db" not in tracked
    assert "triggers.json" not in tracked
    assert ".gitignore" not in tracked
    assert any(name.endswith(".json") for name in tracked)
