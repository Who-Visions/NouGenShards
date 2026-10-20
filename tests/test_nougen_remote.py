"""Tests for NouGenRemote Pro iPhone 14 Cockpit & Direct Antigravity Injection."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_nougen_remote():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "tools" / "nougen_remote.py"
    spec = importlib.util.spec_from_file_location("nougen_remote", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_design_choices_100_catalog():
    mod = _load_nougen_remote()
    assert len(mod.DESIGN_CHOICES_100) == 100
    pillars = {item["pillar"] for item in mod.DESIGN_CHOICES_100}
    assert len(pillars) == 5
    assert mod.DESIGN_CHOICES_100[0]["id"] == 1
    assert mod.DESIGN_CHOICES_100[-1]["id"] == 100


def test_pwa_html_contains_smartkeys_and_wakelock():
    mod = _load_nougen_remote()
    html = mod.HTML_PWA
    assert "smartkeys-bar" in html
    assert "requestWakeLock" in html
    assert "visualViewport" in html
    assert "pollInboxStatus" in html


def test_get_inbox_status_structure():
    mod = _load_nougen_remote()
    status = mod.get_inbox_status(limit=3)
    assert status["ok"] is True
    assert "watermark" in status
    assert "seen_count" in status
    assert isinstance(status["recent"], list)


def test_inject_to_antigravity_fallback(monkeypatch, tmp_path):
    mod = _load_nougen_remote()
    monkeypatch.setenv("NOUGEN_REMOTE_DISABLE_CONSOLE_PULSE", "1")
    monkeypatch.setattr(mod.Path, "home", lambda: tmp_path)

    def _fail_urlopen(*args, **kwargs):
        raise ConnectionRefusedError("8766 offline in unit test")

    monkeypatch.setattr(mod.urllib.request, "urlopen", _fail_urlopen)
    res = mod.inject_to_antigravity("unit test ping from iPhone 14", sender="iPhone 14 Test")
    assert res["ok"] is True
    assert res["injected"] is True
    inbox_files = list((tmp_path / ".nougen" / "agy_inbox").glob("msg_*.json"))
    assert len(inbox_files) == 1
    doc = json.loads(inbox_files[0].read_text(encoding="utf-8"))
    assert doc["text"] == "unit test ping from iPhone 14"
    assert doc["body"] == "unit test ping from iPhone 14"
    assert doc["target"] == "antigravity"


def test_crd_host_status_and_gestures():
    mod = _load_nougen_remote()
    crd = mod.get_crd_host_status()
    assert crd["ok"] is True
    assert crd["service_name"] == "chromoting"
    assert "touch_mode" in crd["gestures"]
    assert "trackpad_mode" in crd["gestures"]


def test_dispatch_screen_input_simulated(monkeypatch):
    mod = _load_nougen_remote()
    monkeypatch.setenv("NOUGEN_REMOTE_DISABLE_CONSOLE_PULSE", "1")
    res_touch = mod.dispatch_screen_input({"mode": "touch", "action": "left_click", "norm_x": 0.5, "norm_y": 0.5})
    assert res_touch["ok"] is True
    res_pad = mod.dispatch_screen_input({"mode": "trackpad", "action": "right_click", "dx": 15, "dy": -10})
    assert res_pad["ok"] is True
