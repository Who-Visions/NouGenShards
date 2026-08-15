"""Read-through upstreams: seeded from env, because disk does not survive."""
import ast
import contextlib
import logging
import os

import pytest

import nougen_shards.keymaker as keymaker

APP = "app.py"


def _load(*names):
    src = open(APP, encoding="utf-8").read()
    tree = ast.parse(src)
    ns = {"os": os, "logging": logging, "contextlib": contextlib}
    for name in names:
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        mod = ast.Module(body=[fn], type_ignores=[])
        exec(compile(ast.fix_missing_locations(mod), APP, "exec"), ns)
    return ns


@pytest.fixture
def app_ns(tmp_path, monkeypatch):
    monkeypatch.setattr(keymaker, "DB_PATH", tmp_path / "agent_secrets.db")
    monkeypatch.delenv("NGS_UPSTREAM_URL", raising=False)
    monkeypatch.delenv("NGS_UPSTREAM_NAME", raising=False)
    return _load("_seed_upstreams", "_registered_upstreams")


def test_no_env_registers_nothing(app_ns):
    assert app_ns["_seed_upstreams"]() == []
    assert app_ns["_registered_upstreams"]() == []


def test_single_upstream_derives_name_from_host(app_ns, monkeypatch):
    monkeypatch.setenv("NGS_UPSTREAM_URL", "https://blade.nougenai.com")
    seeded = app_ns["_seed_upstreams"]()
    assert seeded == [{"name": "blade.nougenai.com", "url": "https://blade.nougenai.com"}]
    assert app_ns["_registered_upstreams"]() == seeded


def test_several_upstreams_with_explicit_names(app_ns, monkeypatch):
    monkeypatch.setenv("NGS_UPSTREAM_URL", "https://a.example, https://b.example")
    monkeypatch.setenv("NGS_UPSTREAM_NAME", "blade,outpost")
    seeded = app_ns["_seed_upstreams"]()
    assert [s["name"] for s in seeded] == ["blade", "outpost"]
    assert [s["url"] for s in seeded] == ["https://a.example", "https://b.example"]


def test_reseeding_is_idempotent(app_ns, monkeypatch):
    """Every boot re-seeds; a restart must not multiply the peer list."""
    monkeypatch.setenv("NGS_UPSTREAM_URL", "https://blade.nougenai.com")
    for _ in range(3):
        app_ns["_seed_upstreams"]()
    assert len(app_ns["_registered_upstreams"]()) == 1


def test_a_bad_upstream_does_not_block_the_others(app_ns, monkeypatch):
    """Startup must never die on a peer."""
    monkeypatch.setenv("NGS_UPSTREAM_URL", "https://good.example")
    real = keymaker.register_cloud_node
    calls = {"n": 0}

    def flaky(url, name):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("vault locked")
        return real(url, name)

    monkeypatch.setattr(keymaker, "register_cloud_node", flaky)
    assert app_ns["_seed_upstreams"]() == []       # swallowed, not raised
    assert app_ns["_seed_upstreams"]()             # second boot succeeds


def test_returns_a_list_not_a_context_manager(app_ns, monkeypatch):
    """Regression: the lifespan decorator once slid onto this function."""
    monkeypatch.setenv("NGS_UPSTREAM_URL", "https://blade.nougenai.com")
    assert isinstance(app_ns["_seed_upstreams"](), list)


def test_lifespan_keeps_its_decorator_and_seed_has_none():
    """The two are adjacent; a decorator on the wrong one breaks startup."""
    tree = ast.parse(open(APP, encoding="utf-8").read())
    lifespan = next(n for n in tree.body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "_lifespan")
    seed = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "_seed_upstreams")
    assert [ast.unparse(d) for d in lifespan.decorator_list] == ["contextlib.asynccontextmanager"]
    assert seed.decorator_list == []


def test_lifespan_seeds_on_startup():
    """Wiring check: seeding has to actually be called from the lifespan."""
    tree = ast.parse(open(APP, encoding="utf-8").read())
    lifespan = next(n for n in tree.body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "_lifespan")
    called = {n.func.id for n in ast.walk(lifespan)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_seed_upstreams" in called
