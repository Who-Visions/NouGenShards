"""NOUGEN_DEDICATED_TENANT promotes one tenant to owner on its own machine."""
import pytest

from nougen_shards import tenant_policy, tenants


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "tenants.json"
    monkeypatch.setattr(tenants, "tenants_file", lambda: path)
    monkeypatch.setenv("NOUGEN_TENANT_VAULT_ROOT", str(tmp_path / "t"))
    tenants.register_tenant("ann", "Ann", "tok-a", path=path)
    tenants.register_tenant("bob", "Bob", "tok-b", path=path)


def test_shared_node_is_unchanged(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("NOUGEN_DEDICATED_TENANT", raising=False)
    got = tenants.resolve_token("tok-a", "owner", tmp_path / "o")
    assert got.tenant_id == "ann"


def test_dedicated_tenant_becomes_owner_only_for_itself(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("NOUGEN_DEDICATED_TENANT", "ann")
    me = tenants.resolve_token("tok-a", "owner", tmp_path / "o")
    assert me.tenant_id == tenant_policy.OWNER_TENANT_ID and me.vault_dir == tmp_path / "o"
    assert tenants.resolve_token("tok-b", "owner", tmp_path / "o").tenant_id == "bob"
    assert tenants.resolve_token("nope", "owner", tmp_path / "o") is None


def test_duplicate_digest_is_refused_even_when_dedicated(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("NOUGEN_DEDICATED_TENANT", "ann")
    with pytest.raises(tenants.TenantRegistryError):
        tenants.register_tenant("cat", "Cat", "tok-a", path=tmp_path / "tenants.json")
        tenants.resolve_token("tok-a", "owner", tmp_path / "o")


def test_kit_is_not_dedicated_unless_asked(tmp_path):
    from nougen_shards import tenant_onboard as to
    plain = to.write_kit("ann", "t", "tt", 4460, tmp_path / "a")
    assert "DEDICATED" not in (plain / "join.ps1").read_text()
    assert "DEDICATED" not in (plain / "join.sh").read_text()
    own = to.write_kit("ann", "t", "tt", 4460, tmp_path / "b", dedicated=True)
    assert "NOUGEN_DEDICATED_TENANT = 'ann'" in (own / "join.ps1").read_text()
