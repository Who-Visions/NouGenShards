"""Endpoint resolution is dynamic: env -> local file -> None. No operator host
may appear as a default in shipped runtime code."""
import json
import re
from pathlib import Path

from nougen_shards import endpoints

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "src" / "nougen_shards"
OPERATOR_HOST = re.compile(r"whoentertains\.workers\.dev|whovisions-nga-hgf-space|nougenai-nougenshards\.hf\.space")


def test_unset_endpoints_resolve_to_none(monkeypatch, tmp_path):
    for var in ("NOUGEN_FLEET_GATEWAY_URL", "HF_SPACE_URL", "NOUGEN_WORKERS_SUBDOMAIN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NOUGEN_ENDPOINTS_FILE", str(tmp_path / "missing.json"))
    assert endpoints.fleet_gateway_url() is None
    assert endpoints.hf_space_url() is None
    assert endpoints.worker_live_url("w") is None


def test_env_beats_file_and_trailing_slash_is_stripped(monkeypatch, tmp_path):
    f = tmp_path / "endpoints.json"
    f.write_text(json.dumps({"fleet_gateway_url": "https://file.example/"}), encoding="utf-8")
    monkeypatch.setenv("NOUGEN_ENDPOINTS_FILE", str(f))
    monkeypatch.delenv("NOUGEN_FLEET_GATEWAY_URL", raising=False)
    assert endpoints.fleet_gateway_url() == "https://file.example"
    monkeypatch.setenv("NOUGEN_FLEET_GATEWAY_URL", "https://env.example/")
    assert endpoints.fleet_gateway_url() == "https://env.example"


def test_worker_live_url_uses_resolved_subdomain(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_ENDPOINTS_FILE", str(tmp_path / "none.json"))
    monkeypatch.setenv("NOUGEN_WORKERS_SUBDOMAIN", "acme")
    assert endpoints.worker_live_url("api") == "https://api.acme.workers.dev"


def test_no_operator_hosts_hardcoded_in_runtime():
    offenders = []
    for path in RUNTIME.rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if OPERATOR_HOST.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{path.relative_to(ROOT)}:{n}")
    assert not offenders, offenders
