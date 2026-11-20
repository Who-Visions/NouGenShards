"""npx resolution (relay_golive) and the join deploy's Google-client fallback."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_npx_path_env_override(monkeypatch):
    g = _load("relay_golive_t", "tools/relay_golive.py")
    monkeypatch.setenv("NOUGEN_GOLIVE_NPX", "custom-npx")
    assert g.npx_path() == "custom-npx"


def test_npx_path_uses_which(monkeypatch):
    g = _load("relay_golive_t2", "tools/relay_golive.py")
    monkeypatch.delenv("NOUGEN_GOLIVE_NPX", raising=False)
    monkeypatch.setattr(g.shutil, "which", lambda n: "/opt/node/npx.cmd" if n == "npx" else None)
    assert g.npx_path() == "/opt/node/npx.cmd"


def test_google_pair(monkeypatch):
    import pytest
    d = _load("join_deploy_t", "workers/join/deploy.py")
    both = {"NOUGEN_JOIN_GOOGLE_CLIENT_ID": "id", "NOUGEN_JOIN_GOOGLE_CLIENT_SECRET": "sec"}
    monkeypatch.setattr(d.keymaker, "get_secret", lambda n: both.get(n))
    assert {b["type"] for b in d._google_pair()} == {"plain_text", "secret_text"}
    monkeypatch.setattr(d.keymaker, "get_secret", lambda n: None)
    assert [b["type"] for b in d._google_pair()] == ["inherit", "inherit"]
    monkeypatch.setattr(d.keymaker, "get_secret", lambda n: "id" if n.endswith("_ID") else None)
    with pytest.raises(SystemExit):
        d._google_pair()
