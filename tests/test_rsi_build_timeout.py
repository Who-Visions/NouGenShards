"""A Gradle compile that is cut off by the timeout is "unknown", not "broken".

2026-11-22: the canary on a loaded Windows box flipped BUILD_BROKEN <-> ok about eight times a
day. Every non-ok report was {"ok": false, "code": null, "error": "timeout"}, never a compile
error, and the limit was a hardcoded 300 s.
"""
from pathlib import Path

import pytest

from nougen_shards import rsi


def _gradle_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "app"
    repo.mkdir()
    (repo / "gradlew.bat").write_text("", encoding="utf-8")
    (repo / "gradlew").write_text("", encoding="utf-8")
    return repo


def test_timeout_is_marked_timed_out_and_uses_the_configured_limit(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, cwd, timeout=300):
        seen["timeout"] = timeout
        return {"ok": False, "code": None, "error": "timeout"}

    monkeypatch.setattr(rsi, "_run", fake_run)
    monkeypatch.setenv("NOUGEN_RSI_BUILD_TIMEOUT_S", "1234")
    result = rsi.check_builds(_gradle_repo(tmp_path))
    assert seen["timeout"] == 1234
    assert result["timed_out"] is True
    assert result["timeout_s"] == 1234
    assert result["ok"] is False


def test_real_compile_failure_is_not_marked_timed_out(tmp_path, monkeypatch):
    monkeypatch.setattr(rsi, "_run", lambda cmd, cwd, timeout=300: {"ok": False, "code": 1})
    result = rsi.check_builds(_gradle_repo(tmp_path))
    assert "timed_out" not in result
    assert result["code"] == 1


@pytest.mark.parametrize("raw", ["", "abc", "0", "-5"])
def test_bad_timeout_setting_falls_back_to_the_default(monkeypatch, raw):
    monkeypatch.setenv("NOUGEN_RSI_BUILD_TIMEOUT_S", raw)
    assert rsi._build_timeout_s() == rsi._BUILD_TIMEOUT_S_FALLBACK


def test_default_timeout_is_longer_than_the_old_hardcoded_300(monkeypatch):
    monkeypatch.delenv("NOUGEN_RSI_BUILD_TIMEOUT_S", raising=False)
    assert rsi._build_timeout_s() > 300


TIMEOUT = {"checked": True, "ok": False, "code": None, "error": "timeout",
           "timed_out": True, "timeout_s": 900}
OK = {"checked": True, "ok": True, "code": 0}


def _cycle(monkeypatch, tmp_path, build, prev=None, surfaces=None):
    """Run one cycle with every outside call stubbed so nothing is posted or fetched.

    Returns (summary, calls) where calls lists "degraded:<status>" / "recovered:<prev>"."""
    calls = []
    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    monkeypatch.setenv("NOUGEN_RSI_REPORTS_DIR", str(reports))
    monkeypatch.delenv("NOUGEN_RSI_UNKNOWN_ALERT_AFTER", raising=False)
    monkeypatch.setattr(rsi, "check_builds", lambda repo: build)
    monkeypatch.setattr(rsi, "check_self_update_health", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(rsi, "check_surfaces", lambda *a, **k: surfaces or {"degraded": False})
    monkeypatch.setattr(rsi, "fetch_exa_temporal_latest", lambda *a, **k: {"hits": []})
    monkeypatch.setattr(rsi, "propose_improvement", lambda *a, **k: {"skipped": False})
    monkeypatch.setattr(rsi, "_record_bitemporal_receipt", lambda *a, **k: {})
    monkeypatch.setattr(rsi, "_previous_report", lambda: prev)
    monkeypatch.setattr(rsi.core, "_title_retrieve", lambda **k: [])
    monkeypatch.setattr(rsi, "_alert_degraded",
                        lambda status, *a, **k: calls.append(f"degraded:{status}") or {"posted": True})
    monkeypatch.setattr(rsi, "_alert_recovered",
                        lambda prev_status, *a, **k: calls.append(f"recovered:{prev_status}") or {"posted": True})
    return rsi.run(), calls


def test_cycle_reports_a_timeout_as_unknown_not_broken(tmp_path, monkeypatch):
    summary, _ = _cycle(monkeypatch, tmp_path, TIMEOUT)
    assert summary["status"] == "BUILD_UNKNOWN"
    assert "timed out" in summary["proposal"]["reason"]


def test_cycle_still_reports_a_real_failure_as_broken(tmp_path, monkeypatch):
    summary, calls = _cycle(monkeypatch, tmp_path, {"checked": True, "ok": False, "code": 1})
    assert summary["status"] == "BUILD_BROKEN"
    assert calls == ["degraded:BUILD_BROKEN"]


def test_ok_then_one_timeout_then_ok_posts_nothing(tmp_path, monkeypatch):
    """The 11/22 flap pattern: a lone timeout must not alert, and its recovery must not either."""
    first, calls = _cycle(monkeypatch, tmp_path, TIMEOUT, prev={"status": "ok"})
    assert calls == []
    assert first["consecutive_unknown"] == 1
    assert first["alert"]["posted"] is False

    _, calls = _cycle(monkeypatch, tmp_path, OK, prev=first)
    assert calls == []


def test_two_timeouts_in_a_row_alert_once(tmp_path, monkeypatch):
    first, calls = _cycle(monkeypatch, tmp_path, TIMEOUT, prev={"status": "ok"})
    assert calls == []
    second, calls = _cycle(monkeypatch, tmp_path, TIMEOUT, prev=first)
    assert calls == ["degraded:BUILD_UNKNOWN"]
    assert second["consecutive_unknown"] == 2
    third, calls = _cycle(monkeypatch, tmp_path, TIMEOUT, prev=second)
    assert calls == []  # steady state: no repeat leg


def test_recovery_after_an_alerted_timeout_run_does_post_recovered(tmp_path, monkeypatch):
    first, _ = _cycle(monkeypatch, tmp_path, TIMEOUT, prev={"status": "ok"})
    second, _ = _cycle(monkeypatch, tmp_path, TIMEOUT, prev=first)
    _, calls = _cycle(monkeypatch, tmp_path, OK, prev=second)
    assert calls == ["recovered:BUILD_UNKNOWN"]


def test_alert_threshold_is_configurable(tmp_path, monkeypatch):
    summary, calls = _cycle(monkeypatch, tmp_path, TIMEOUT, prev={"status": "ok"})
    monkeypatch.setenv("NOUGEN_RSI_UNKNOWN_ALERT_AFTER", "1")
    monkeypatch.setattr(rsi, "_previous_report", lambda: {"status": "ok"})
    calls.clear()
    out = rsi.run()
    assert out["status"] == "BUILD_UNKNOWN"
    assert calls == ["degraded:BUILD_UNKNOWN"]


def test_broken_then_one_timeout_then_ok_still_posts_recovered_for_the_broken_incident(tmp_path, monkeypatch):
    """Codex P2 (rsi.py:503): an alerted BUILD_BROKEN carried through one UNKNOWN must still close."""
    broken, calls = _cycle(monkeypatch, tmp_path, {"checked": True, "ok": False, "code": 1},
                           prev={"status": "ok"})
    assert calls == ["degraded:BUILD_BROKEN"]
    assert broken["open_incident"] == "BUILD_BROKEN"
    unknown, calls = _cycle(monkeypatch, tmp_path, TIMEOUT, prev=broken)
    assert calls == []
    assert unknown["open_incident"] == "BUILD_BROKEN"
    _, calls = _cycle(monkeypatch, tmp_path, OK, prev=unknown)
    assert calls == ["recovered:BUILD_BROKEN"]


def test_a_timeout_does_not_hide_a_degraded_surface_in_the_same_run(tmp_path, monkeypatch):
    """Codex P2 (rsi.py:497): the timeout grace applies only when the other checks are healthy."""
    summary, calls = _cycle(monkeypatch, tmp_path, TIMEOUT, prev={"status": "ok"},
                            surfaces={"degraded": True})
    assert summary["status"] == "DEGRADED"
    assert calls == ["degraded:DEGRADED"]
