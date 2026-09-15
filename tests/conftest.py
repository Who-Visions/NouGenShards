"""Suite-wide safety rails.

The secrets vault used to resolve to a CWD-relative `.nougen_vault`, so tests
happened to get an empty throwaway directory and nobody noticed they were never
isolated on purpose. Once resolution became deterministic (`~/.nougen/secrets`),
five tests started reading the operator's REAL vault -- `doctor` found live API
keys and "empty vault" assertions failed against 41 real secrets.

The accident was doing the isolating. This makes it explicit: every test gets its
own empty secrets vault, so no test can read, mutate, or leak real credentials.
A test that wants a specific location can still set the env var itself.
"""
import os

import pytest

from nougen_shards import keymaker


@pytest.fixture(autouse=True)
def isolated_secrets_vault(tmp_path_factory, monkeypatch):
    vault = tmp_path_factory.mktemp("secrets_vault")
    monkeypatch.setenv(keymaker.ENV_SECRETS_VAULT, str(vault))
    # keymaker binds VAULT_DIR/DB_PATH at import time, so patch the live module
    # too -- tests that never reimport it would otherwise keep the real paths.
    monkeypatch.setattr(keymaker, "VAULT_DIR", vault, raising=False)
    monkeypatch.setattr(keymaker, "DB_PATH", vault / keymaker.DB_FILENAME, raising=False)
    monkeypatch.setattr(keymaker, "CSV_PATH", vault / "shards_secrets.csv", raising=False)
    monkeypatch.setattr(keymaker, "SECRETS_JSON_DIR", vault / "service_accounts",
                        raising=False)
    # Probe-chain discovery (resolve_secrets_store) deliberately looks BEYOND
    # the configured store -- that is its job in production, and it is exactly
    # what would carry a test past this isolation boundary into the operator's
    # real vault. Force it off; tests that are ABOUT the probe chain re-enable
    # it against a fabricated home (see test_vault_discovery.py).
    monkeypatch.setenv(keymaker.ENV_VAULT_PROBE, "0")
    # Isolate tenant registry so tests do not pick up host ~/.nougen/tenants.json
    monkeypatch.setenv("NOUGEN_TENANTS_FILE", str(vault / "nonexistent_tenants.json"))
    yield vault


@pytest.fixture(autouse=True)
def no_network_embed_at_capture(monkeypatch):
    """Keep `capture()` hermetic.

    `core.capture()` now embeds at write time (see HARDENING.md section 2), which
    is correct in production and wrong in a unit test: it turns every capture into
    a live ollama round-trip, so the suite becomes slow, network-dependent, and
    non-deterministic depending on whether a daemon happens to be up.

    Default it off for tests. A test that is specifically about embed-at-capture
    opts back in with `monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "1")` and
    stubs the embedder, which is what the tests in test_audit_fixes.py do.
    """
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")


@pytest.fixture(autouse=True)
def isolate_vram_gate(monkeypatch):
    """Isolate `NOUGEN_VRAM_GATE` so host environment settings do not bypass or leak into tests.

    `vram_gate.check_vram()` checks `PYTEST_CURRENT_TEST` to bypass the VRAM check
    unless `NOUGEN_VRAM_GATE=1` is explicitly set in the host environment. If the host
    has `NOUGEN_VRAM_GATE=1` set, unit tests checking unmeasured models fail.
    Default it to 0 for all tests unless a test explicitly monkeypatches it.
    """
    monkeypatch.setenv("NOUGEN_VRAM_GATE", "0")



class _HomePath:
    """`os.path` for one module, with `~` pointing at a throwaway home."""

    def __init__(self, real, home):
        self._real = real
        self._home = str(home)

    def expanduser(self, path):
        path = os.fspath(path)
        if path == "~" or path.startswith("~/") or path.startswith("~" + os.sep):
            return self._home + path[1:]
        return self._real.expanduser(path)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _HomeOs:
    """`os` for one module: everything real except `path.expanduser`."""

    def __init__(self, real, home):
        self._real = real
        self.path = _HomePath(real.path, home)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture(autouse=True)
def isolated_msg_home(tmp_path_factory, monkeypatch):
    """Keep NouGenMsg's `~/...` writes out of the operator's real inboxes.

    `nougen_shards.nougenmsg` resolves its inboxes inline with
    `os.path.expanduser("~/...")`: ~/.nougen/agy_inbox, ~/.gemini/config/inbox,
    ~/.codex/inbox, the claude inbox and the session registry. A test that
    mocks only the transport still reaches `_drop_model_reply` ->
    `ping_antigravity`, which wrote real inbox files. On 2026-09-14 the
    shell-injection fixtures (sender `ollama:model"; rm -rf /`) landed in the
    live agy and Antigravity inboxes, where hooks surfaced them to live sessions.

    Scoped to that module on purpose. Redirecting HOME suite-wide would break
    the tests that shell out to git, and patching the global `os.path` would
    reach every module. Tests that patch `nougenmsg.os.path.expanduser`
    themselves still win.
    """
    import os as real_os
    from nougen_shards import nougenmsg
    home = tmp_path_factory.mktemp("msg_home")
    monkeypatch.setattr(nougenmsg, "os", _HomeOs(real_os, home))
    yield home
