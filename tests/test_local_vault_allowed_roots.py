"""The federated-search path boundary — `_allowed_roots` / `_path_is_allowed`.

`_path_is_allowed` is what stops a registered vault row from turning a federated
search into arbitrary file access, and `_allowed_roots` is the list it checks
against. Between them they are the whole boundary, and **nothing in this repo
tested them** until 2026-09-04.

That absence is why the boundary could be widened without anything noticing. An
uncommitted working-tree change had replaced the single tenant root with

    [vdir, vdir.parent, ~/.nougen, ~/.nougen/vault, ~/Watchtower/vault, ~/Watchtower]

directly reversing the comment above it, which says the owner root must not be
used here because it "would let a tenant's federated sweep read the owner's
vault root". `active_vault_dir()` resolves to `~/.nougen/shards`, so `.parent`
alone re-grants `~/.nougen` — the owner root, which holds the Keymaker secrets
store. For a tenant vault it grants that tenant's siblings.

These tests state the guarantee so the next widening has to argue with a red
suite instead of a comment.
"""
from pathlib import Path

import pytest

from nougen_shards.connectors import local_vault


@pytest.fixture
def tenant(tmp_path, monkeypatch):
    """A tenant vault with a sibling tenant, a parent, and a secrets store —
    the real shape of `~/.nougen`, which is what makes `.parent` dangerous."""
    owner = tmp_path / "dot_nougen"
    vault = owner / "shards"
    sibling = owner / "other_tenant"
    secrets = owner / "secrets"
    for d in (vault, sibling, secrets):
        d.mkdir(parents=True)
    (secrets / "shards_secrets.db").write_bytes(b"x")
    (sibling / "someone_else.db").write_bytes(b"x")
    (vault / "mine.db").write_bytes(b"x")

    monkeypatch.delenv("NOUGEN_LOCAL_VAULT_ROOTS", raising=False)
    monkeypatch.setattr(local_vault, "_allowed_roots",
                        local_vault._allowed_roots)  # keep the real one
    import nougen_shards.core as core
    monkeypatch.setattr(core, "active_vault_dir", lambda: str(vault))
    return {"owner": owner, "vault": vault, "sibling": sibling,
            "secrets": secrets, "home": tmp_path}


def test_the_tenant_vault_itself_is_allowed(tenant):
    assert local_vault._path_is_allowed(tenant["vault"] / "mine.db")


def test_only_one_root_by_default(tenant):
    """The list is exactly the tenant vault. Length is asserted on purpose: a
    future addition has to change this number and explain itself."""
    roots = local_vault._allowed_roots()
    assert roots == [tenant["vault"].resolve()]


def test_the_parent_of_the_vault_is_not_allowed(tenant):
    """The specific regression. `.parent` of ~/.nougen/shards is ~/.nougen."""
    assert not local_vault._path_is_allowed(tenant["owner"] / "loose.db")


def test_a_sibling_tenant_is_not_readable(tenant):
    """What `.parent` actually costs in a multi-tenant deployment."""
    assert not local_vault._path_is_allowed(tenant["sibling"] / "someone_else.db")


def test_the_secrets_store_is_not_readable(tenant):
    """~/.nougen holds the Keymaker store. Granting the parent grants this."""
    assert not local_vault._path_is_allowed(tenant["secrets"] / "shards_secrets.db")


@pytest.mark.parametrize("relative", [
    "../secrets/shards_secrets.db",
    "../other_tenant/someone_else.db",
    "../../etc/passwd",
])
def test_traversal_out_of_the_vault_is_blocked(tenant, relative):
    """`_path_is_allowed` resolves before comparing, so `..` must not escape."""
    assert not local_vault._path_is_allowed(tenant["vault"] / relative)


def test_an_unrelated_absolute_path_is_blocked(tenant, tmp_path):
    assert not local_vault._path_is_allowed(tmp_path / "elsewhere" / "any.db")


def test_home_directories_are_not_implicitly_allowed(tenant, monkeypatch):
    """The widening added ~/.nougen and ~/Watchtower unconditionally. Nothing
    under $HOME is allowed unless it IS the resolved vault dir."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tenant["home"]))
    for candidate in [".nougen", ".nougen/vault", "Watchtower", "Watchtower/vault"]:
        p = tenant["home"] / candidate / "x.db"
        assert not local_vault._path_is_allowed(p), candidate


def test_env_override_is_the_supported_way_to_widen(tenant, tmp_path, monkeypatch):
    """Widening is not forbidden — it is required to be explicit and per
    deployment, rather than every process inheriting a bigger default."""
    extra = tmp_path / "extra_root"
    (extra / "sub").mkdir(parents=True)
    (extra / "sub" / "ok.db").write_bytes(b"x")
    monkeypatch.setenv("NOUGEN_LOCAL_VAULT_ROOTS", str(extra))
    assert local_vault._path_is_allowed(extra / "sub" / "ok.db")
    # and the override REPLACES the default rather than adding to it
    assert not local_vault._path_is_allowed(tenant["vault"] / "mine.db")


def test_the_allow_list_follows_the_tenant(tenant, tmp_path, monkeypatch):
    """The reason the comment says active_vault_dir() and not GLOBAL_DIR: the
    boundary has to move with the request, not stay pinned to the owner."""
    other = tmp_path / "tenant_b" / "shards"
    other.mkdir(parents=True)
    import nougen_shards.core as core
    monkeypatch.setattr(core, "active_vault_dir", lambda: str(other))
    assert local_vault._allowed_roots() == [other.resolve()]
    assert not local_vault._path_is_allowed(tenant["vault"] / "mine.db")


def test_a_nonexistent_path_is_not_allowed_by_accident(tenant):
    """resolve() on a missing path must not throw the check open."""
    assert not local_vault._path_is_allowed(tenant["owner"] / "nope" / "x.db")
