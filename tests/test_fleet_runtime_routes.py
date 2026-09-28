"""Fleet routes are tenant-configured and empty on a clean install."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_fleet():
    path = Path(__file__).parents[1] / "tools" / "fleet.py"
    spec = importlib.util.spec_from_file_location("fleet_runtime_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_clean_install_has_no_private_local_routes(monkeypatch, tmp_path):
    monkeypatch.delenv("NOUGEN_LOCAL_ROUTES_JSON", raising=False)
    monkeypatch.setenv("NOUGEN_LOCAL_ROUTES_FILE", str(tmp_path / "missing.json"))
    fleet = _load_fleet()
    assert fleet.LOCAL_ROUTES == []


def test_runtime_routes_load_from_explicit_json(monkeypatch):
    routes = [{
        "name": "local-ollama-node-a",
        "url": "http://node-a.test:11434/v1",
        "model": "installed:test",
        "headers": {},
        "kind": "local",
    }]
    monkeypatch.setenv("NOUGEN_LOCAL_ROUTES_JSON", json.dumps(routes))
    fleet = _load_fleet()
    assert fleet.LOCAL_ROUTES == routes


def test_runtime_routes_load_from_user_file(monkeypatch, tmp_path):
    path = tmp_path / "local_routes.json"
    path.write_text(json.dumps({"routes": [{
        "name": "lmstudio-workstation",
        "url": "http://workstation.test:1234/v1",
        "model": "local-model",
        "kind": "lmstudio",
    }]}), encoding="utf-8")
    monkeypatch.delenv("NOUGEN_LOCAL_ROUTES_JSON", raising=False)
    monkeypatch.setenv("NOUGEN_LOCAL_ROUTES_FILE", str(path))
    fleet = _load_fleet()
    assert fleet.LOCAL_ROUTES == [{
        "name": "lmstudio-workstation",
        "url": "http://workstation.test:1234/v1",
        "model": "local-model",
        "headers": {},
        "kind": "lmstudio",
    }]
