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
