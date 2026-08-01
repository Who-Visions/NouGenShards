"""The ack-targeting regressions, both found by claiming the wrong handoff.

A bare `nougen handoff ack` once claimed a record the operator had never seen:
`handoff read` showed the newest record, another agent acknowledged it a few
seconds later, and `ack` walked silently past it to an older one. These pin
both halves of that — how records are ordered, and what happens when the
newest one is already spoken for.
"""
import json
import os

import pytest

from nougen_shards import handoff as H


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "HANDOFF_DIR", tmp_path)
    return tmp_path


def _write(root, handoff_id, timestamp, mtime=None, **fields):
    record = {
        "handoff_id": handoff_id,
        "timestamp": timestamp,
        "goal": f"goal for {handoff_id}",
        "git": {"branch": "main", "changes": [], "commits": []},
        "tasks": {"summary": "", "raw_count": 0},
        "agent": "claude-cli",
        "status": "open",
    }
    record.update(fields)
    path = root / f"handoff_{handoff_id}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# --- ordering -------------------------------------------------------------

def test_records_order_by_timestamp_not_file_mtime(registry):
    """A fresh clone or a sync rewrites mtimes; it must not reorder history."""
    _write(registry, "older", "2026-07-31T09:00:00", mtime=9_000_000_000)  # newest mtime
    _write(registry, "newer", "2026-07-31T13:52:41", mtime=1_000_000_000)  # oldest mtime

    order = [H._read_handoff(p)["handoff_id"] for p in H.get_handoff_files()]
    assert order[0] == "newer", "newest RECORD must sort first regardless of mtime"


def test_a_write_to_an_old_record_does_not_make_it_newest(registry):
    """Acking or checkpointing an old record touches its file — and used to
    promote it to 'latest' for every later read."""
    _write(registry, "old", "2026-01-01T00:00:00", mtime=1_000_000)
    _write(registry, "current", "2026-07-31T13:52:41", mtime=2_000_000)
    os.utime(registry / "handoff_old.json", (9_000_000_000, 9_000_000_000))

    newest = H._read_handoff(H.get_handoff_files()[0])
    assert newest["handoff_id"] == "current"


def test_missing_timestamp_degrades_instead_of_raising(registry):
    _write(registry, "stamped", "2026-07-31T13:00:00", mtime=1_000)
    path = registry / "handoff_unstamped.json"
    path.write_text(json.dumps({"handoff_id": "unstamped", "status": "open"}), encoding="utf-8")
    os.utime(path, (2_000, 2_000))

    ids = [H._read_handoff(p).get("handoff_id") for p in H.get_handoff_files()]
    assert set(ids) == {"stamped", "unstamped"}


# --- ack targeting --------------------------------------------------------

def test_bare_ack_claims_the_newest_open_handoff(registry):
    _write(registry, "target", "2026-07-31T13:52:41")
    assert H.acknowledge_handoff() is not None
    assert json.loads((registry / "handoff_target.json").read_text())["status"] == "acknowledged"


def test_bare_ack_refuses_when_the_newest_is_already_claimed(registry):
    """The exact race: read showed one record, another agent took it, ack ran."""
    _write(registry, "claimed", "2026-07-31T13:52:41",
           status="acknowledged", acknowledged_by="gemini",
           acknowledged_at="2026-07-31T22:05:05")
    _write(registry, "bystander", "2026-07-31T09:56:26")

    assert H.acknowledge_handoff() is None, "must not silently claim a different record"
    bystander = json.loads((registry / "handoff_bystander.json").read_text())
    assert bystander["status"] == "open", "the older handoff must be left untouched"


def test_explicit_id_still_claims_past_a_taken_record(registry):
    """--id is the operator saying they know; it must keep working."""
    _write(registry, "claimed", "2026-07-31T13:52:41",
           status="acknowledged", acknowledged_by="gemini")
    _write(registry, "wanted", "2026-07-31T09:56:26")

    assert H.acknowledge_handoff(handoff_id="wanted") is not None
    assert json.loads((registry / "handoff_wanted.json").read_text())["status"] == "acknowledged"


def test_all_acknowledged_is_not_reported_as_a_conflict(registry):
    _write(registry, "done", "2026-07-31T13:52:41", status="acknowledged",
           acknowledged_by="gemini")
    assert H.acknowledge_handoff() is None


# --- version reporting ----------------------------------------------------

def test_reported_version_matches_the_packaged_one():
    """The v1.2.0 release bumped pyproject and left two hardcoded copies at
    1.1.0, so `nougen --version` under-reported by two releases.

    pyproject is read with a regex rather than tomllib: this repo supports
    3.10, where tomllib does not exist, and a version-agreement test that only
    runs on some interpreters is not a guarantee. The `version = "..."` line
    under [project] is a fixed shape — a full TOML parser buys nothing here.
    """
    import pathlib
    import re

    import nougen_shards
    from nougen_shards import cli

    root = pathlib.Path(nougen_shards.__file__).resolve().parents[2]
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    project = text.split("[project]", 1)[1]
    match = re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE)
    assert match, "no version found under [project] in pyproject.toml"
    declared = match.group(1)

    assert nougen_shards.__version__ == declared
    assert cli.VERSION == declared, "the CLI must not carry its own copy"


# --- machine identity: one box, two names ---------------------------------

def test_a_record_from_this_box_under_another_name_is_not_remote(monkeypatch):
    """The bug: a record written on this Mac sixty seconds earlier was
    announced as 'REMOTE — written elsewhere' because NOUGEN_MACHINE was set in
    the writing shell and not the reading one."""
    from nougen_shards import machine as M

    record = {"machine": {"machine_id": M.machine_id(), "host": "phoebus"}}
    monkeypatch.setattr(M, "host_label", lambda: "KushBoyGroups-Mac-mini")

    assert M.is_local_record(record) is True
    assert M.record_origin(record) == "local"


def test_the_alias_is_still_surfaced_as_a_warning(monkeypatch):
    """Not remote, but not silent either — one box counted twice is how a
    fleet total quietly doubles."""
    from nougen_shards import machine as M

    record = {"machine": {"machine_id": M.machine_id(), "host": "phoebus"}}
    monkeypatch.setattr(M, "host_label", lambda: "KushBoyGroups-Mac-mini")

    warning = M.record_alias_warning(record)
    assert warning and "phoebus" in warning and "NOUGEN_MACHINE" in warning


def test_a_genuinely_foreign_record_is_still_remote():
    from nougen_shards import machine as M

    record = {"machine": {"machine_id": "ffffffffffff", "host": "blade1tb"}}
    assert M.is_local_record(record) is False
    assert M.record_origin(record) == "remote"
    assert M.record_alias_warning(record) is None


def test_matching_name_and_id_produces_no_warning():
    from nougen_shards import machine as M

    record = {"machine": {"machine_id": M.machine_id(), "host": M.host_label()}}
    assert M.record_alias_warning(record) is None


# --- ack: not your own ----------------------------------------------------

def test_bare_ack_refuses_to_claim_your_own_handoff(registry, monkeypatch):
    """An ack is a read-back — it tells the fleet someone ELSE picked the work
    up. Self-acking leaves a state indistinguishable from a real claim."""
    from nougen_shards import machine as M

    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    _write(registry, "mine", "2026-08-01T00:10:00", agent="claude-cli",
           machine={"machine_id": M.machine_id(), "host": M.host_label()})

    assert H.acknowledge_handoff() is None
    assert json.loads((registry / "handoff_mine.json").read_text())["status"] == "open"


def test_explicit_id_can_still_ack_your_own(registry, monkeypatch):
    from nougen_shards import machine as M

    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    _write(registry, "mine", "2026-08-01T00:10:00", agent="claude-cli",
           machine={"machine_id": M.machine_id(), "host": M.host_label()})

    assert H.acknowledge_handoff(handoff_id="mine") is not None


def test_another_agents_handoff_is_still_claimed_by_a_bare_ack(registry, monkeypatch):
    """The common case must not regress: picking up someone else's leg."""
    from nougen_shards import machine as M

    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    _write(registry, "theirs", "2026-08-01T00:10:00", agent="gemini",
           machine={"machine_id": M.machine_id(), "host": M.host_label()})

    assert H.acknowledge_handoff() is not None
    assert json.loads((registry / "handoff_theirs.json").read_text())["status"] == "acknowledged"


def test_same_agent_on_a_different_machine_is_still_claimable(registry, monkeypatch):
    """Two boxes both running claude-cli are different participants."""
    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    _write(registry, "remote", "2026-08-01T00:10:00", agent="claude-cli",
           machine={"machine_id": "ffffffffffff", "host": "blade1tb"})

    assert H.acknowledge_handoff() is not None


def test_an_unstamped_handoff_is_claimable_even_from_the_same_agent(registry, monkeypatch):
    """Records predating machine stamping carry nothing to compare. Refusing on
    a guess would make every one of them unclaimable by an agent of the same
    name — refuse when we know, not when we cannot tell."""
    monkeypatch.setenv("NOUGEN_AGENT", "claude-cli")
    _write(registry, "ancient", "2026-01-01T00:00:00", agent="claude-cli")

    assert H.acknowledge_handoff() is not None
