"""Tests for the host power surface.

These must pass on every platform — the module is Windows-only in *capability* but
must import and degrade cleanly everywhere, since most users of the public repo are
not on Windows. Anything touching `powercfg` / `Get-WinEvent` is stubbed.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from nougen_shards import host_power


def _stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class TestParsing:
    def test_parses_millisecond_and_second_forms(self):
        assert host_power._parse_utc("2026-07-24T18:51:55.239Z") is not None
        assert host_power._parse_utc("2026-07-24T18:51:55Z") is not None

    def test_rejects_garbage_without_raising(self):
        assert host_power._parse_utc("not a timestamp") is None
        assert host_power._parse_utc(None) is None

    def test_sql_stamp_matches_stored_shard_shape(self):
        # Shard timestamps are compared as TEXT, so a bound truncated to whole
        # seconds would drop shards written in the final fractional second.
        stamped = host_power._sql_stamp(datetime(2026, 7, 24, 18, 51, 55, 239000, tzinfo=timezone.utc))
        assert stamped == "2026-07-24T18:51:55.239000Z"


class TestUnsupportedHost:
    """A non-Windows user must be able to import and call everything safely."""

    @pytest.fixture(autouse=True)
    def _force_unsupported(self, monkeypatch):
        monkeypatch.setattr(host_power.sys, "platform", "linux")

    def test_is_supported_false_with_reason(self):
        supported, reason = host_power.is_supported()
        assert supported is False
        assert reason

    def test_status_reports_unsupported_not_raises(self):
        assert host_power.status()["supported"] is False

    def test_guard_is_transparent_noop(self):
        ran = []
        with host_power.dispatch_guard() as info:
            ran.append(True)
        assert ran == [True]           # the wrapped work still runs
        assert info["applied"] is False

    def test_setter_raises_explicitly(self):
        with pytest.raises(host_power.PowerUnsupported):
            host_power.set_cpu_range(70)

    def test_shutdown_query_marked_not_queried(self):
        # Distinguishable from "queried fine, found nothing" — an empty result is
        # never self-evidently healthy.
        found = host_power.shutdown_events()
        assert found["queried"] is False
        assert found["events"] == []


class TestCollapsePaired:
    """One host death writes several log records; counting records doubles it."""

    def test_pairs_within_window_collapse_to_one_death(self):
        base = datetime(2026, 7, 24, 18, 51, 55, tzinfo=timezone.utc)
        events = [
            {"utc": _stamp(base), "event_id": 41, "bugcheck": False,
             "button": False, "thermal": False, "unexplained_rail_loss": True},
            {"utc": _stamp(base + timedelta(seconds=11)), "event_id": 6008,
             "bugcheck": False, "button": False, "thermal": False,
             "unexplained_rail_loss": False},
        ]
        collapsed = host_power._collapse_paired(events)
        assert len(collapsed) == 1
        assert sorted(collapsed[0]["record_ids"]) == [41, 6008]
        assert collapsed[0]["unexplained_rail_loss"] is True

    def test_distant_events_stay_separate(self):
        base = datetime(2026, 7, 24, 18, 0, 0, tzinfo=timezone.utc)
        events = [
            {"utc": _stamp(base), "event_id": 41, "bugcheck": False,
             "button": False, "thermal": False, "unexplained_rail_loss": True},
            {"utc": _stamp(base + timedelta(days=3)), "event_id": 41, "bugcheck": False,
             "button": False, "thermal": False, "unexplained_rail_loss": True},
        ]
        assert len(host_power._collapse_paired(events)) == 2

    def test_flagless_record_cannot_erase_an_explanation(self):
        base = datetime(2026, 7, 24, 18, 51, 55, tzinfo=timezone.utc)
        events = [
            {"utc": _stamp(base), "event_id": 41, "bugcheck": True,
             "button": False, "thermal": False, "unexplained_rail_loss": False},
            {"utc": _stamp(base + timedelta(seconds=5)), "event_id": 6008,
             "bugcheck": False, "button": False, "thermal": False,
             "unexplained_rail_loss": False},
        ]
        merged = host_power._collapse_paired(events)[0]
        assert merged["bugcheck"] is True
        assert merged["unexplained_rail_loss"] is False


class TestBootAttribution:
    """Regression: the death record for a boot is logged AFTER that boot."""

    def test_selects_record_logged_just_after_boot(self, monkeypatch):
        boot = datetime(2026, 7, 24, 18, 51, 50, tzinfo=timezone.utc)
        this_boot_death = {
            "utc": _stamp(boot + timedelta(seconds=5)), "event_id": 41,
            "bugcheck": False, "button": False, "thermal": False,
            "unexplained_rail_loss": True, "record_ids": [41],
        }
        older_death = {
            "utc": _stamp(boot - timedelta(days=3)), "event_id": 41,
            "bugcheck": False, "button": False, "thermal": False,
            "unexplained_rail_loss": True, "record_ids": [41],
        }

        monkeypatch.setattr(host_power, "is_supported", lambda: (True, "ok"))
        monkeypatch.setattr(host_power, "shutdown_events",
                            lambda *a, **k: {"queried": True, "count": 2,
                                             "events": [this_boot_death, older_death]})
        monkeypatch.setattr(host_power, "_run_ps", lambda script: (
            0, '{"boot_utc":"%s","now_utc":"%s"}' % (
                _stamp(boot), _stamp(boot + timedelta(hours=1))), ""))

        report = host_power.boot_report()
        assert report["previous_shutdown_clean"] is False
        # Must be the record 5s after boot, NOT the one from three days earlier.
        assert report["previous_death"]["utc"] == this_boot_death["utc"]
        assert report["uptime_s"] == 3600

    def test_clean_boot_when_no_record_near_boot(self, monkeypatch):
        boot = datetime(2026, 7, 24, 18, 51, 50, tzinfo=timezone.utc)
        stale = {"utc": _stamp(boot - timedelta(days=9)), "event_id": 41,
                 "bugcheck": False, "button": False, "thermal": False,
                 "unexplained_rail_loss": True, "record_ids": [41]}
        monkeypatch.setattr(host_power, "is_supported", lambda: (True, "ok"))
        monkeypatch.setattr(host_power, "shutdown_events",
                            lambda *a, **k: {"queried": True, "count": 1, "events": [stale]})
        monkeypatch.setattr(host_power, "_run_ps", lambda script: (
            0, '{"boot_utc":"%s","now_utc":"%s"}' % (
                _stamp(boot), _stamp(boot + timedelta(minutes=5))), ""))

        assert host_power.boot_report()["previous_shutdown_clean"] is True


class TestBaseRate:
    """Silence before a death means nothing without knowing how quiet the vault is."""

    def test_base_rate_counts_only_occupied_windows(self, tmp_path, monkeypatch):
        db = tmp_path / "nougen_shards_1.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT)")
        now = datetime.now(timezone.utc)
        # Three shards, two of them inside the same 30-minute window.
        for delta in (timedelta(minutes=5), timedelta(minutes=10), timedelta(hours=5)):
            conn.execute("INSERT INTO shards (timestamp) VALUES (?)",
                         (host_power._sql_stamp(now - delta),))
        conn.commit()
        conn.close()

        monkeypatch.setattr(host_power.core, "GLOBAL_DIR", tmp_path)
        rate = host_power.shard_window_base_rate(days=1, window_min=30)
        assert rate["computed"] is True
        assert rate["windows_total"] == 48
        assert rate["windows_with_activity"] == 2   # not 3 — two shards shared a window
        assert 0 < rate["active_fraction"] < 1

    def test_missing_vault_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(host_power.core, "GLOBAL_DIR", tmp_path / "nope")
        assert host_power.shard_window_base_rate(days=1, window_min=30)["computed"] is False
