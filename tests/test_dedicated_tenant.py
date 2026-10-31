"""NOUGEN_DEDICATED_TENANT promotes one tenant to owner on its own machine."""
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


def test_non_ascii_env_value_is_ignored_not_fatal(tmp_path, monkeypatch):
    # hmac.compare_digest raises TypeError on non-ASCII str; one bad env value must not break every caller.
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("NOUGEN_DEDICATED_TENANT", "añn")
    assert tenants.resolve_token("tok-a", "owner", tmp_path / "o").tenant_id == "ann"
    assert tenants.resolve_token("tok-b", "owner", tmp_path / "o").tenant_id == "bob"


def test_unicode_case_fold_to_ascii_is_still_rejected(tmp_path, monkeypatch):
    """U+212A KELVIN SIGN lowercases to plain ASCII 'k' under str.lower(). Validation
    must reject non-ASCII input BEFORE lowercasing, or this slips through as tenant 'k'."""
    path = tmp_path / "tenants.json"
    monkeypatch.setattr(tenants, "tenants_file", lambda: path)
    monkeypatch.setenv("NOUGEN_TENANT_VAULT_ROOT", str(tmp_path / "t"))
    tenants.register_tenant("k", "K-tenant", "tok-k", path=path)
    monkeypatch.setenv("NOUGEN_DEDICATED_TENANT", "K")  # KELVIN SIGN, .lower() == "k"
    assert tenants.dedicated_tenant() == ""
    got = tenants.resolve_token("tok-k", "owner", tmp_path / "o")
    assert got.tenant_id == "k"
    assert got.vault_dir != tmp_path / "o"


def test_env_value_is_case_and_space_insensitive(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("NOUGEN_DEDICATED_TENANT", "  ANN ")
    assert tenants.resolve_token("tok-a", "owner", tmp_path / "o").tenant_id == tenant_policy.OWNER_TENANT_ID


def test_invalid_env_value_promotes_nobody(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    for bad in ("../ann", "an n", "a" * 40):
        monkeypatch.setenv("NOUGEN_DEDICATED_TENANT", bad)
        assert tenants.dedicated_tenant() == ""
        assert tenants.resolve_token("tok-a", "owner", tmp_path / "o").tenant_id == "ann"


def test_colliding_digest_never_early_returns_as_owner(tmp_path, monkeypatch):
    from types import SimpleNamespace
    digest = tenants.token_sha256("tok-shared")

    def rec(tid):
        return SimpleNamespace(tenant_id=tid, label=tid, token_sha256=digest, lane="tenant",
                               allow_federation=False)

    monkeypatch.setattr(tenants, "load_registry", lambda *a, **k: [rec("ann"), rec("bob")])
    monkeypatch.setenv("NOUGEN_DEDICATED_TENANT", "ann")
    assert tenants.resolve_token("tok-shared", "owner", tmp_path / "o") is None


def test_join_kit_only_sets_dedicated_when_asked(tmp_path):
    from nougen_shards import tenant_onboard as to
    plain = to.write_kit("ann", "tok", "tun", 4444, root=tmp_path / "a")
    for name in ("join.ps1", "join.sh"):
        assert "NOUGEN_DEDICATED_TENANT" not in (plain / name).read_text()
    ded = to.write_kit("ann", "tok", "tun", 4444, root=tmp_path / "b", dedicated=True)
    assert "$env:NOUGEN_DEDICATED_TENANT = 'ann'" in (ded / "join.ps1").read_text()
    assert "export NOUGEN_DEDICATED_TENANT='ann'" in (ded / "join.sh").read_text()


def test_dedicated_kit_warns_when_a_node_is_already_running(tmp_path):
    from nougen_shards import tenant_onboard as to
    ded = (to.write_kit("ann", "tok", "tun", 4444, root=tmp_path / "d", dedicated=True) / "join.ps1").read_text()
    assert "Dedicated mode only applies to a node this kit starts" in ded
    plain = (to.write_kit("ann", "tok", "tun", 4444, root=tmp_path / "p") / "join.ps1").read_text()
    assert "Dedicated mode" not in plain
