"""Machine identity and cross-computer triggers."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from nougen_shards import handoff, handoff_triggers, machine, nougen_context


@pytest.fixture(autouse=True)
def setup_handoff_env(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(handoff, "HANDOFF_DIR", temp_path)
        monkeypatch.setattr(
            nougen_context, "SESSION_DB_PATH", str(temp_path / "context_session.db")
        )
        # Identity is cached per-process; clear it so env overrides take effect.
        machine.host_label.cache_clear()
        machine.machine_id.cache_clear()
        machine.hostname.cache_clear()
        monkeypatch.delenv("NOUGEN_TRIGGERS", raising=False)
        yield temp_path
        machine.host_label.cache_clear()
        machine.machine_id.cache_clear()
        machine.hostname.cache_clear()


def _as_machine(monkeypatch, host, machine_id):
    monkeypatch.setenv("NOUGEN_MACHINE", host)
    monkeypatch.setenv("NOUGEN_MACHINE_ID", machine_id)
    machine.host_label.cache_clear()
    machine.machine_id.cache_clear()


# --- identity ---------------------------------------------------------------

def test_handoff_records_the_machine_that_wrote_it(monkeypatch):
    _as_machine(monkeypatch, "who-mac-mini", "aaaa1111")
    path = handoff.create_handoff(message="from the mac", agent="claude-cli")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["machine"]["host"] == "who-mac-mini"
    assert data["machine"]["machine_id"] == "aaaa1111"
    assert data["machine"]["platform"]
    assert data["machine"]["os"]
    # The host is folded into the id so two boxes on the same branch and second
    # cannot produce the same record.
    assert "who-mac-mini" in data["handoff_id"]


def test_machine_columns_are_indexed_in_sqlite(monkeypatch):
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    path = handoff.create_handoff(message="from the pc", agent="gemini")
    data = json.loads(path.read_text(encoding="utf-8"))

    conn = sqlite3.connect(handoff.get_handoff_db_path())
    try:
        row = conn.execute(
            "SELECT host, machine_id, platform FROM handoff_records WHERE handoff_id = ?",
            (data["handoff_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "who-pc"
    assert row[1] == "bbbb2222"


def test_origin_flips_when_read_from_another_machine(monkeypatch):
    _as_machine(monkeypatch, "who-mac-mini", "aaaa1111")
    path = handoff.create_handoff(message="written on the mac", agent="claude-cli")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert machine.record_origin(data) == "local"

    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    assert machine.record_origin(data) == "remote"
    assert machine.is_local_record(data) is False


def test_pre_machine_records_still_read(monkeypatch):
    """Records written before machine stamping must not break the reader."""
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    legacy = {"handoff_id": "old", "agent": "gemini"}
    assert machine.record_machine(legacy)["host"] == "unknown"
    assert machine.record_origin(legacy) == "local"


def test_bare_string_machine_field_is_read_as_a_host(monkeypatch):
    """Other fleet tooling stamps `"machine": "whoart"` — keep the name."""
    _as_machine(monkeypatch, "phoebus", "aaaa1111")
    record = {"handoff_id": "x", "agent": "claude-cli", "machine": "whoart"}
    assert machine.record_machine(record)["host"] == "whoart"
    assert machine.record_machine(record)["machine_id"] == "unknown"
    # A named host is enough to place it elsewhere — otherwise remote-origin
    # triggers would never fire for records from that tooling.
    assert machine.record_origin(record) == "remote"
    assert machine.record_origin({**record, "machine": "phoebus"}) == "local"
    # A record with no machine field at all predates stamping: still local.
    assert machine.record_origin({"handoff_id": "old"}) == "local"


def test_ack_records_the_acknowledging_machine(monkeypatch):
    _as_machine(monkeypatch, "who-mac-mini", "aaaa1111")
    path = handoff.create_handoff(message="hand over", agent="claude-cli")

    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    monkeypatch.setenv("NOUGEN_AGENT", "codex")
    handoff.acknowledge_handoff()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["acknowledged_by"] == "codex"
    assert data["acknowledged_on"]["host"] == "who-pc"
    # The writing machine is untouched — both ends of the transfer are on record.
    assert data["machine"]["host"] == "who-mac-mini"


def test_checkpoints_carry_the_machine(monkeypatch):
    _as_machine(monkeypatch, "who-mac-mini", "aaaa1111")
    path = handoff.create_handoff(message="start here", agent="claude-cli")

    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    handoff.start_orchestration(message="picking up remotely")
    handoff.complete_orchestration(message="built on the pc")

    data = json.loads(path.read_text(encoding="utf-8"))
    hosts = {c.get("host") for c in data["orchestration"]["checkpoints"]}
    assert hosts == {"who-pc"}
    assert data["completed_on"]["host"] == "who-pc"

    conn = sqlite3.connect(handoff.get_handoff_db_path())
    try:
        rows = conn.execute(
            "SELECT host FROM handoff_checkpoints WHERE handoff_id = ?",
            (data["handoff_id"],),
        ).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == ["who-pc", "who-pc"]


def test_private_mode_drops_local_account_details(monkeypatch):
    _as_machine(monkeypatch, "who-mac-mini", "aaaa1111")
    monkeypatch.setenv("NOUGEN_MACHINE_PRIVATE", "1")
    identity = machine.machine_identity(repo_root="/somewhere/private")
    assert "user" not in identity
    assert "repo_root" not in identity
    assert identity["host"] == "who-mac-mini"


def test_list_machines_builds_the_fleet_roster(monkeypatch):
    _as_machine(monkeypatch, "who-mac-mini", "aaaa1111")
    handoff.create_handoff(message="mac work", agent="claude-cli")
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    handoff.create_handoff(message="pc work", agent="gemini")

    # A bulk import of unstamped records from another box must not be counted
    # as this machine's own work.
    imported = handoff.HANDOFF_DIR / "handoff_imported.json"
    imported.write_text(
        json.dumps({"handoff_id": "imported", "agent": "gemini", "timestamp": "2026-01-01T00:00:00",
                    "git": {"branch": "main"}, "tasks": {}, "status": "open"}),
        encoding="utf-8",
    )
    unattributed = [m for m in handoff.list_machines() if not m["attributed"]]
    assert len(unattributed) == 1
    assert unattributed[0]["is_self"] is False

    roster = {m["host"]: m for m in handoff.list_machines() if m["attributed"]}
    assert set(roster) == {"who-mac-mini", "who-pc"}
    assert roster["who-pc"]["is_self"] is True
    assert roster["who-mac-mini"]["is_self"] is False
    assert roster["who-mac-mini"]["agents"] == ["claude-cli"]


# --- triggers ---------------------------------------------------------------

def test_trigger_fires_on_create_and_sees_handoff_env(monkeypatch, tmp_path):
    _as_machine(monkeypatch, "who-mac-mini", "aaaa1111")
    receipt = tmp_path / "receipt.txt"
    handoff_triggers.add_trigger(
        trigger_id="receipt",
        run=f'echo "$NOUGEN_HANDOFF_EVENT $NOUGEN_HANDOFF_HOST" > "{receipt}"',
        events=["created"],
    )
    handoff.create_handoff(message="fire it", agent="claude-cli")

    assert receipt.exists()
    assert receipt.read_text().split() == ["created", "who-mac-mini"]


def test_remote_only_trigger_ignores_local_handoffs(monkeypatch, tmp_path):
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    receipt = tmp_path / "remote.txt"
    handoff_triggers.add_trigger(
        trigger_id="remote-only",
        run=f'echo fired > "{receipt}"',
        events=["created"],
        origin="remote",
    )

    handoff.create_handoff(message="local work", agent="gemini")
    assert not receipt.exists(), "a local handoff must not fire a remote-only rule"

    # A record written by the other box, read here, is remote — and fires.
    path = handoff.create_handoff(message="pretend remote", agent="gemini")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["machine"] = {"host": "who-mac-mini", "machine_id": "aaaa1111"}
    handoff_triggers.fire("created", data, path)
    assert receipt.exists()


def test_on_machine_scopes_a_shared_registry(monkeypatch, tmp_path):
    """One triggers.json can be synced everywhere; each rule owns one box."""
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    receipt = tmp_path / "mac-only.txt"
    handoff_triggers.add_trigger(
        trigger_id="mac-only",
        run=f'echo fired > "{receipt}"',
        events=["created"],
        on_machine="who-mac-mini",
    )
    handoff.create_handoff(message="on the pc", agent="gemini")
    assert not receipt.exists()

    _as_machine(monkeypatch, "who-mac-mini", "aaaa1111")
    handoff.create_handoff(message="on the mac", agent="gemini")
    assert receipt.exists()


def test_match_filters_narrow_by_agent_and_goal(monkeypatch, tmp_path):
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    receipt = tmp_path / "narrow.txt"
    handoff_triggers.add_trigger(
        trigger_id="narrow",
        run=f'echo fired > "{receipt}"',
        events=["created"],
        agent="codex",
        goal_contains="deploy",
    )
    handoff.create_handoff(goal="run the deploy", agent="gemini")
    assert not receipt.exists(), "agent filter should have blocked this"

    handoff.create_handoff(goal="write docs", agent="codex")
    assert not receipt.exists(), "goal filter should have blocked this"

    handoff.create_handoff(goal="run the deploy", agent="codex")
    assert receipt.exists()


def test_kill_switch_and_dry_run(monkeypatch, tmp_path):
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    receipt = tmp_path / "switch.txt"
    handoff_triggers.add_trigger(
        trigger_id="switch",
        run=f'echo fired > "{receipt}"',
        events=["created"],
    )

    monkeypatch.setenv("NOUGEN_TRIGGERS", "off")
    handoff.create_handoff(message="silenced", agent="gemini")
    assert not receipt.exists()

    monkeypatch.setenv("NOUGEN_TRIGGERS", "dry")
    path = handoff.create_handoff(message="dry", agent="gemini")
    assert not receipt.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = handoff.get_trigger_runs(limit=5)
    assert runs and runs[0]["status"] == "dry-run"
    assert runs[0]["handoff_id"] == data["handoff_id"]


def test_trigger_failure_never_loses_the_handoff(monkeypatch):
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    handoff_triggers.add_trigger(
        trigger_id="broken",
        run="exit 3",
        events=["created"],
    )
    path = handoff.create_handoff(message="still written", agent="gemini")
    assert path is not None and path.exists()

    runs = handoff.get_trigger_runs(limit=1)
    assert runs[0]["status"] == "failed"
    assert runs[0]["exit_code"] == 3


def test_disabled_trigger_does_not_run(monkeypatch, tmp_path):
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    receipt = tmp_path / "off.txt"
    handoff_triggers.add_trigger(
        trigger_id="toggle", run=f'echo x > "{receipt}"', events=["created"]
    )
    assert handoff_triggers.set_trigger_enabled("toggle", False) is True
    handoff.create_handoff(message="quiet", agent="gemini")
    assert not receipt.exists()


def test_add_trigger_rejects_unknown_events(monkeypatch):
    _as_machine(monkeypatch, "who-pc", "bbbb2222")
    with pytest.raises(ValueError):
        handoff_triggers.add_trigger("bad", run="true", events=["exploded"])
