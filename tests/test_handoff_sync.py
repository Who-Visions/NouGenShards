"""Cross-machine transport: records move, and arrivals fire triggers.

These tests run two real handoff directories against a real bare git remote, so
what is exercised is the actual round trip rather than a mocked one.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from nougen_shards import (
    handoff,
    handoff_sync,
    handoff_triggers,
    machine,
    nougen_context,
)


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
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


def test_empty_registry_never_reports_a_push(monkeypatch, fleet):
    """The failure the primary node hit: pushed=True having published nothing."""
    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    report = handoff_sync.sync(remote=fleet["remote"])
    assert report["pushed"] is False
    assert any("empty registry" in e for e in report["errors"])


def test_joining_machine_can_still_receive_on_an_empty_registry(monkeypatch, fleet):
    """Onboarding must keep working — a new box starts with nothing."""
    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    handoff.create_handoff(goal="seed the remote", agent="codex")
    handoff_sync.sync(remote=fleet["remote"])

    _become(monkeypatch, fleet, "newcomer", "cccc3333")
    report = handoff_sync.sync(remote=fleet["remote"])
    assert report["arrived"], report["errors"]
    assert report["pushed"] is True, report["errors"]


def test_sync_refuses_when_another_checkout_holds_the_records(monkeypatch, fleet, tmp_path):
    """Module-derived HANDOFF_DIR vs the checkout you are standing in."""
    directory = _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    monkeypatch.delenv("NOUGEN_HANDOFF_DIR", raising=False)

    # A second checkout, holding the records the operator actually means.
    other = tmp_path / "real-clone"
    (other / ".handoffs" / "claude cli handoffs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(other)], capture_output=True, check=True)
    (other / ".handoffs" / "claude cli handoffs" / "handoff_x.json").write_text("{}")

    monkeypatch.chdir(other)
    monkeypatch.setattr(handoff, "PROJECT_ROOT", directory)
    report = handoff_sync.sync(remote=fleet["remote"])
    assert report["pushed"] is False
    assert any("Registry mismatch" in e for e in report["errors"])


def test_explicit_handoff_dir_is_always_honoured(monkeypatch, fleet, tmp_path):
    """An operator who names the registry is not second-guessed."""
    directory = _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    other = tmp_path / "real-clone"
    (other / ".handoffs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(other)], capture_output=True, check=True)
    (other / ".handoffs" / "handoff_x.json").write_text("{}")

    monkeypatch.chdir(other)
    monkeypatch.setattr(handoff, "PROJECT_ROOT", directory)
    monkeypatch.setenv("NOUGEN_HANDOFF_DIR", str(directory))
    assert handoff.registry_conflict() is None


def test_env_remote_is_written_into_the_repo(monkeypatch, fleet):
    """NOUGEN_HANDOFF_REMOTE must configure git, not just be reported back."""
    directory = _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    monkeypatch.setenv("NOUGEN_HANDOFF_REMOTE", fleet["remote"])
    handoff.create_handoff(goal="env remote", agent="codex")

    report = handoff_sync.sync()
    assert report["pushed"] is True, report["errors"]
    configured = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(directory), capture_output=True, text=True, check=False,
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
        ["git", "ls-files"], cwd=str(directory), capture_output=True, text=True,
        check=False,
    ).stdout.splitlines()
    assert "handoffs.db" not in tracked
    assert "triggers.json" not in tracked
    assert ".gitignore" not in tracked
    assert any(name.endswith(".json") for name in tracked)


def test_merge_leg_records_status_progression():
    """Leg status only advances (open->acked->done), never regresses to an older status."""
    # open + open -> open
    m = handoff_sync.merge_leg_records({"status": "open"}, {"status": "open"})
    assert m["status"] == "open"

    # open + acked -> acked
    m = handoff_sync.merge_leg_records({"status": "open"}, {"status": "acked"})
    assert m["status"] == "acked"

    # acked + open -> acked (local ack survives stale down-sync copy)
    m = handoff_sync.merge_leg_records({"status": "acked"}, {"status": "open"})
    assert m["status"] == "acked"

    # acknowledged + open -> acknowledged
    m = handoff_sync.merge_leg_records({"status": "acknowledged"}, {"status": "open"})
    assert m["status"] == "acknowledged"

    # acked + done -> done
    m = handoff_sync.merge_leg_records({"status": "acked"}, {"status": "done"})
    assert m["status"] == "done"

    # done + open -> done (never regresses to older status)
    m = handoff_sync.merge_leg_records({"status": "done"}, {"status": "open"})
    assert m["status"] == "done"

    # done + acked -> done (never regresses to older status)
    m = handoff_sync.merge_leg_records({"status": "done"}, {"status": "acked"})
    assert m["status"] == "done"

    # complete + acknowledged -> complete
    m = handoff_sync.merge_leg_records({"status": "complete"}, {"status": "acknowledged"})
    assert m["status"] == "complete"


def test_merge_leg_records_unions_events_and_dedupes():
    """Never drop relay events; union events across both copies (dedupe by event+agent+timestamp)."""
    local = {
        "id": "leg-101",
        "status": "acked",
        "events": [
            {"event": "created", "agent": "codex", "timestamp": "2026-08-28T16:00:00Z"},
            {"event": "ack", "agent": "claude-cli", "timestamp": "2026-08-28T16:05:00Z", "note": "on it"},
        ],
    }
    stale_incoming = {
        "id": "leg-101",
        "status": "open",
        "events": [
            {"event": "created", "agent": "codex", "timestamp": "2026-08-28T16:00:00Z"},
            {"event": "comment", "agent": "gateway", "timestamp": "2026-08-28T16:02:00Z", "msg": "queued"},
        ],
    }
    merged = handoff_sync.merge_leg_records(local, stale_incoming)
    assert merged["status"] == "acked"
    assert len(merged["events"]) == 3
    event_names = [e["event"] for e in merged["events"]]
    assert event_names == ["created", "comment", "ack"]
    assert any(e["event"] == "ack" and e["agent"] == "claude-cli" for e in merged["events"])


def test_local_ack_survives_stale_down_synced_copy():
    """An ack made locally survives a stale down-synced copy from the gateway."""
    local_leg = {
        "id": "20260828T160000Z__blade1tb__claude-cli",
        "goal": "fix split-brain",
        "status": "acknowledged",
        "acknowledged_by": "claude-cli",
        "acknowledged_at": "2026-08-28T16:05:00Z",
        "events": [
            {"event": "created", "agent": "codex", "timestamp": "2026-08-28T16:00:00Z"},
            {"event": "ack", "agent": "claude-cli", "timestamp": "2026-08-28T16:05:00Z"},
        ],
    }
    stale_incoming = {
        "id": "20260828T160000Z__blade1tb__claude-cli",
        "goal": "fix split-brain",
        "status": "open",
        "events": [
            {"event": "created", "agent": "codex", "timestamp": "2026-08-28T16:00:00Z"},
        ],
    }
    merged = handoff_sync.merge_leg_records(local_leg, stale_incoming)
    assert merged["status"] == "acknowledged"
    assert merged["acknowledged_by"] == "claude-cli"
    assert merged["acknowledged_at"] == "2026-08-28T16:05:00Z"
    assert len(merged["events"]) == 2
    assert merged["events"][1]["event"] == "ack"


def test_down_sync_file_merges_in_place(tmp_path):
    """down_sync updates an existing file on disk by merging rather than clobbering."""
    target_file = tmp_path / "leg.json"
    local_data = {
        "id": "leg-1",
        "status": "acked",
        "acknowledged_by": "claude-cli",
        "events": [{"event": "ack", "agent": "claude-cli", "timestamp": "2026-08-28T16:05:00Z"}],
    }
    target_file.write_text(json.dumps(local_data, indent=2), encoding="utf-8")

    stale_incoming = {
        "id": "leg-1",
        "status": "open",
        "events": [{"event": "created", "agent": "codex", "timestamp": "2026-08-28T16:00:00Z"}],
    }
    res = handoff_sync.down_sync(target_file, stale_incoming)
    assert res["status"] == "acked"
    assert res["acknowledged_by"] == "claude-cli"
    assert len(res["events"]) == 2

    on_disk = json.loads(target_file.read_text(encoding="utf-8"))
    assert on_disk["status"] == "acked"
    assert on_disk["acknowledged_by"] == "claude-cli"
    assert len(on_disk["events"]) == 2


def test_git_sync_merges_conflicting_leg_files_and_preserves_ack(monkeypatch, fleet):
    """Git sync resolves merge conflict automatically, preserving local ack against stale remote."""
    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    path_pc = handoff.create_handoff(goal="split brain test", agent="codex")
    handoff_sync.sync(remote=fleet["remote"])

    # Machine B pulls and acknowledges locally
    _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    handoff_sync.sync(remote=fleet["remote"])
    handoff.acknowledge_handoff()

    # Machine A makes a concurrent commit to the same record on remote without the ack
    _become(monkeypatch, fleet, "who-pc", "bbbb2222")
    data_pc = json.loads(path_pc.read_text(encoding="utf-8"))
    data_pc["goal"] = "split brain test - updated by gateway"
    data_pc["events"] = [
        {"event": "created", "agent": "codex", "timestamp": "2026-08-28T16:00:00Z"},
        {"event": "comment", "agent": "gateway", "timestamp": "2026-08-28T16:02:00Z"},
    ]
    path_pc.write_text(json.dumps(data_pc, indent=2), encoding="utf-8")
    handoff_sync.sync(remote=fleet["remote"])

    # Machine B pulls from remote - previously this would fail with merge conflict and abort.
    # Now _resolve_merge_conflicts merges them, preserving the local ack!
    _become(monkeypatch, fleet, "who-mac-mini", "aaaa1111")
    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    report = handoff_sync.sync(remote=fleet["remote"])

    assert report["pulled"] is True
    assert not report["errors"]

    # Check that Machine B's handoff file has the ack preserved and events unioned
    files = handoff.get_handoff_files()
    assert files
    target_data = json.loads(files[0].read_text(encoding="utf-8"))
    assert target_data["status"] == "acknowledged"
    assert target_data["acknowledged_by"] == "claude-cli"
    assert target_data["goal"] == "split brain test - updated by gateway"

