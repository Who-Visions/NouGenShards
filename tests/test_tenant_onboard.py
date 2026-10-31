"""tenant onboard / status against an in-memory Cloudflare."""
import json
import re

import pytest

from nougen_shards import tenant_onboard as to
from nougen_shards import tenants


class FakeCF:
    account_id = "acct"
    tunnel_config = {}

    def __init__(self, kv=None):
        self.kv = dict(kv or {})
        self.tunnels = {}
        self.dns = {}
        self.calls = []

    def call(self, method, path, body=None, query=None, raw=False):
        self.calls.append((method, path))
        if path == "/accounts/acct/storage/kv/namespaces":
            return [{"id": "ns1", "title": "TENANTS"}]
        m = re.match(r"/accounts/acct/storage/kv/namespaces/ns1/(keys|values/(.+))", path)
        if m:
            if m.group(1) == "keys":
                pre = (query or {}).get("prefix", "")
                return [{"name": k} for k in self.kv if k.startswith(pre)]
            key = m.group(2).replace("%3A", ":").replace("%40", "@")
            if method == "GET":
                return self.kv.get(key)
            self.kv[key] = body
            return None
        if path == "/zones":
            return [{"id": "zone1"}] if query["name"] == "example.com" else []
        if path == "/zones/zone1/dns_records":
            if method == "GET":
                return self.dns.get(query["name"], [])
            self.dns[body["name"]] = [{"id": "d1", **body}]
            return {}
        if path.startswith("/zones/zone1/dns_records/"):
            self.dns[body["name"]] = [{"id": "d1", **body}]
            return {}
        if path == "/accounts/acct/cfd_tunnel":
            if method == "GET":
                return [t for t in self.tunnels.values() if t["name"] == query["name"]]
            self.tunnels["t1"] = {"id": "t1", "name": body["name"]}
            return self.tunnels["t1"]
        if path.endswith("/configurations"):
            if method == "GET":
                return self.tunnel_config
            return {}
        if path.endswith("/token"):
            return "TUNNELTOKEN"
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_TENANT_DOMAIN", "example.com")
    return dict(registry_path=tmp_path / "tenants.json", kit_root=tmp_path,
                prober=lambda url: (530, "offline: test"))


def test_identity_from_email_and_name():
    assert to.derive_identity("alex.q@example.com", "Alex", None, None)[0] == "alex-shards"
    assert to.derive_identity("Jo.Doe+x@a.io", None, None, None)[0] == "jo-doe-shards"
    with pytest.raises(to.OnboardError):
        to.derive_identity("nope", None, None, None)


def test_onboard_creates_everything_and_token_matches(env):
    cf = FakeCF()
    res = to.onboard("a@b.co", name="Ann", cf=cf, **env)
    rec = json.loads(cf.kv["tenant:a@b.co"])
    reg = tenants.load_registry(env["registry_path"])
    assert [r.tenant_id for r in reg] == ["ann-shards"]
    assert tenants.token_sha256(rec["token"]) == reg[0].token_sha256
    assert rec["node_url"] == res.node_url and rec["tenant_id"] == "ann-shards"
    assert cf.kv["allow:a@b.co"] == "1"
    assert json.loads(cf.kv["tunnel:a@b.co"])["tunnel_token"] == "TUNNELTOKEN"
    assert cf.dns[res.hostname][0]["content"] == "t1.cfargotunnel.com"
    ps1 = (res.kit_dir / "join.ps1").read_text()
    assert rec["token"] in ps1 and "TUNNELTOKEN" in ps1
    assert res.probe_status == 530


def test_onboard_is_idempotent_and_keeps_token(env):
    cf = FakeCF()
    first = to.onboard("a@b.co", name="Ann", cf=cf, **env)
    tok = json.loads(cf.kv["tenant:a@b.co"])["token"]
    second = to.onboard("a@b.co", name="Ann", cf=cf, **env)
    assert json.loads(cf.kv["tenant:a@b.co"])["token"] == tok
    assert second.hostname == first.hostname
    assert len(tenants.load_registry(env["registry_path"])) == 1
    assert any("already consistent" in s for s in second.steps)


def test_mismatch_is_repaired_by_rotate(env):
    cf = FakeCF()
    to.onboard("a@b.co", name="Ann", cf=cf, **env)
    rec = json.loads(cf.kv["tenant:a@b.co"])
    rec["token"] = "drifted"
    cf.kv["tenant:a@b.co"] = json.dumps(rec)
    bad = to.status("a@b.co", cf=cf, registry_path=env["registry_path"], prober=env["prober"])
    assert any(not ok and "mismatch" in line for ok, line in bad)
    to.onboard("a@b.co", name="Ann", rotate=True, cf=cf, **env)
    good = to.status("a@b.co", cf=cf, registry_path=env["registry_path"],
                     prober=lambda u: (401, "online"))
    assert all(ok for ok, _ in good), good


def test_dry_run_changes_nothing(env):
    cf = FakeCF()
    res = to.onboard("a@b.co", name="Ann", dry_run=True, cf=cf, **env)
    assert not cf.kv and not cf.tunnels and res.kit_dir is None
    assert not env["registry_path"].exists()


def test_status_unknown_tenant_says_what_to_run(env):
    out = to.status("nobody@x.io", cf=FakeCF(), registry_path=env["registry_path"])
    assert out[0][0] is False and "onboard" in out[0][1]


def test_existing_tunnel_port_is_kept(env):
    cf = FakeCF()
    first = to.onboard("a@b.co", name="Ann", cf=cf, **env)
    cf.tunnel_config = {"config": {"ingress": [{"hostname": first.hostname,
                                                "service": "http://127.0.0.1:4460"}]}}
    second = to.onboard("a@b.co", name="Ann", cf=cf, **env)
    assert "4460" in (second.kit_dir / "join.ps1").read_text()
