"""A node can store canonical and still RUN something else.

Every per-file row in drift_check compares bytes on disk. Python reads a module
once at import, so from that moment the file and the running process are
independent. On 2026-09-03 phoebus reported a clean 5/5 MATCH while an orphaned
receiver started before the pull kept serving a route the pull had just closed.
These cover the two rows that catch it, and -- as important -- the cases that
must stay silent, because a check that invents rows from a failed probe is the
defect this tool exists to find.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import drift_check  # noqa: E402


@pytest.fixture()
def watched(tmp_path):
    f = tmp_path / "nougenmsg_node.py"
    f.write_text("# canonical\n")
    return f


def _procs(monkeypatch, entries):
    monkeypatch.setattr(drift_check, "_live_processes", lambda: entries)


def _managed(monkeypatch, pids):
    monkeypatch.setattr(drift_check, "_service_managed_pids", lambda: pids)


def _states(paths):
    return [r[0] for r in drift_check.process_health(paths)]


def test_process_older_than_the_file_is_stale(monkeypatch, watched):
    """The orphan case: started before the file it runs was rewritten."""
    started = watched.stat().st_mtime - 600
    _procs(monkeypatch, [(26969, 1, started, "python {}".format(watched))])
    _managed(monkeypatch, {26969})
    assert "STALE-PROCESS" in _states([watched])


def test_process_started_after_the_write_is_clean(monkeypatch, watched):
    """A normal reload must not alarm."""
    started = watched.stat().st_mtime + 30
    _procs(monkeypatch, [(31328, 1, started, "python {}".format(watched))])
    _managed(monkeypatch, {31328})
    assert _states([watched]) == []


def test_clock_slack_is_not_treated_as_stale(monkeypatch, watched):
    """Filesystem and process clocks disagree slightly; a restart is not atomic."""
    started = watched.stat().st_mtime - (drift_check.PROCESS_CLOCK_SLACK_S / 2)
    _procs(monkeypatch, [(999, 1, started, "python {}".format(watched))])
    _managed(monkeypatch, {999})
    assert "STALE-PROCESS" not in _states([watched])


def test_orphan_not_owned_by_the_service_manager_is_flagged(monkeypatch, watched):
    started = watched.stat().st_mtime + 30
    _procs(monkeypatch, [(26969, 1, started, "python {}".format(watched))])
    _managed(monkeypatch, {31328})          # launchd owns a different pid
    assert "UNMANAGED-PROCESS" in _states([watched])


def test_unknown_service_manager_suppresses_the_orphan_row(monkeypatch, watched):
    """None means 'cannot tell'. Absent and broken must not share a branch."""
    started = watched.stat().st_mtime + 30
    _procs(monkeypatch, [(26969, 1, started, "python {}".format(watched))])
    _managed(monkeypatch, None)
    assert "UNMANAGED-PROCESS" not in _states([watched])


def test_no_process_enumeration_is_silent_not_alarming(monkeypatch, watched):
    """Fail-soft: a node that cannot enumerate reports nothing at all."""
    _procs(monkeypatch, [])
    _managed(monkeypatch, None)
    assert drift_check.process_health([watched]) == []


def test_unrelated_process_is_ignored(monkeypatch, watched):
    started = watched.stat().st_mtime - 600
    _procs(monkeypatch, [(4242, 1, started, "python /usr/local/bin/something_else.py")])
    _managed(monkeypatch, {4242})
    assert _states([watched]) == []


def test_missing_file_is_skipped_without_error(monkeypatch, tmp_path):
    _procs(monkeypatch, [(1, 1, time.time(), "python ghost.py")])
    _managed(monkeypatch, set())
    assert drift_check.process_health([tmp_path / "ghost.py"]) == []
