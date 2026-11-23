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


def _stub_cycle(monkeypatch, tmp_path, build):
    """Run one cycle with every outside call stubbed so nothing is posted or fetched."""
    alerts = []
    monkeypatch.setenv("NOUGEN_RSI_REPORTS_DIR", str(tmp_path / "reports"))
    (tmp_path / "reports").mkdir()
    monkeypatch.setattr(rsi, "check_builds", lambda repo: build)
    monkeypatch.setattr(rsi, "check_self_update_health", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(rsi, "check_surfaces", lambda *a, **k: {"degraded": False})
    monkeypatch.setattr(rsi, "fetch_exa_temporal_latest", lambda *a, **k: {"hits": []})
    monkeypatch.setattr(rsi, "propose_improvement", lambda *a, **k: {"skipped": False})
    monkeypatch.setattr(rsi, "_record_bitemporal_receipt", lambda *a, **k: {})
    monkeypatch.setattr(rsi, "_previous_report", lambda: None)
    monkeypatch.setattr(rsi.core, "_title_retrieve", lambda **k: [])
    monkeypatch.setattr(rsi, "_alert_degraded",
                        lambda status, *a, **k: alerts.append(status) or {"posted": False})
    return alerts


def test_cycle_reports_a_timeout_as_unknown_not_broken(tmp_path, monkeypatch):
    alerts = _stub_cycle(monkeypatch, tmp_path,
                         {"checked": True, "ok": False, "code": None, "error": "timeout",
                          "timed_out": True, "timeout_s": 900})
    summary = rsi.run()
    assert summary["status"] == "BUILD_UNKNOWN"
    assert "timed out" in summary["proposal"]["reason"]
    assert alerts == ["BUILD_UNKNOWN"]


def test_cycle_still_reports_a_real_failure_as_broken(tmp_path, monkeypatch):
    _stub_cycle(monkeypatch, tmp_path, {"checked": True, "ok": False, "code": 1})
    assert rsi.run()["status"] == "BUILD_BROKEN"
