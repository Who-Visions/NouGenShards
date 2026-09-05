"""A resource failure must not impersonate an auth failure.

Wishlist item 9 (Kaedra, relay leg 20260904T134723Z): "Add explicit auth
failure taxonomy … A 503 from Phoebus resource exhaustion must not masquerade
as 'no token'."

That was written from a measured incident. On 2026-09-04 the phoebus node hit
its 256-descriptor launchd limit, could not open tenants.json, and returned
`503 {"detail":"Tenant registry is invalid."}` on every data endpoint — a
claim about its own CONFIGURATION that was false. Its credentials were fine;
it was out of file descriptors. `/health` returned 200 throughout, because it
never opens the registry, so the node looked healthy while refusing all recall.

The distinction is load-bearing because the two failures have opposite fixes:
a malformed registry is a page for the operator, exhaustion is a retry.
"""
import errno
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("gradio")

from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as node  # noqa: E402
from nougen_shards import tenants  # noqa: E402

TOKEN = "taxonomy-token"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(node, "NODE_TOKEN", TOKEN)
    return TestClient(node.app, raise_server_exceptions=False)


def _registry_raising(exc):
    def _fake(*a, **k):
        raise exc
    return _fake


def test_emfile_is_reported_as_resource_exhaustion_not_bad_config(client, monkeypatch):
    """The exact production failure."""
    monkeypatch.setattr(
        tenants, "credentials_configured",
        _registry_raising(tenants.RegistryUnreadableError(
            "cannot read tenant registry: Too many open files (errno 24)")))
    r = client.post("/search", json={"query": "q"}, headers={"X-NGS-Token": TOKEN})

    assert r.status_code == 503
    assert r.headers.get("X-NouGen-Failure-Class") == "local_resource_exhaustion"
    assert r.headers.get("Retry-After") == "30"
    detail = r.json()["detail"]
    assert "resource exhaustion" in detail.lower()
    # The node must NOT claim its own credentials are broken when they are not.
    assert "registry is invalid" not in detail.lower()


def test_a_malformed_registry_still_says_so(client, monkeypatch):
    """The marker must discriminate. If both cases got the same class, this
    would be the old bug with extra ceremony."""
    monkeypatch.setattr(
        tenants, "credentials_configured",
        _registry_raising(tenants.TenantRegistryError("tenant_id 'owner' is reserved")))
    r = client.post("/search", json={"query": "q"}, headers={"X-NGS-Token": TOKEN})

    assert r.status_code == 503
    assert r.headers.get("X-NouGen-Failure-Class") == "registry_invalid"
    assert "Retry-After" not in r.headers
    assert "invalid" in r.json()["detail"].lower()


def test_load_registry_classifies_emfile(tmp_path, monkeypatch):
    reg = tmp_path / "tenants.json"
    reg.write_text(json.dumps({"tenants": []}))

    def boom(*a, **k):
        raise OSError(errno.EMFILE, "Too many open files")

    monkeypatch.setattr(Path, "read_text", boom)
    with pytest.raises(tenants.RegistryUnreadableError):
        tenants.load_registry(reg)


def test_load_registry_does_not_misclassify_a_permission_error(tmp_path, monkeypatch):
    """EACCES is a real configuration fault — not something a retry fixes."""
    reg = tmp_path / "tenants.json"
    reg.write_text(json.dumps({"tenants": []}))

    def boom(*a, **k):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(Path, "read_text", boom)
    with pytest.raises(tenants.TenantRegistryError) as ei:
        tenants.load_registry(reg)
    assert not isinstance(ei.value, tenants.RegistryUnreadableError)


def test_existing_callers_still_catch_it(tmp_path):
    """RegistryUnreadableError subclasses TenantRegistryError on purpose, so
    no existing `except TenantRegistryError` changes behaviour."""
    assert issubclass(tenants.RegistryUnreadableError, tenants.TenantRegistryError)
