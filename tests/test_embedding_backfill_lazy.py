import importlib
import sys
import urllib.request

import pytest


def test_import_does_not_probe_the_network(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    sys.modules.pop("nougen_shards.embedding_backfill", None)

    def _boom(*a, **k):
        raise AssertionError("network touched at import time")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    importlib.import_module("nougen_shards.embedding_backfill")


def test_host_resolves_lazily_and_is_cached(monkeypatch):
    mod = importlib.import_module("nougen_shards.embedding_backfill")
    mod.ollama_host.cache_clear()
    calls = []
    monkeypatch.setattr(mod, "_normalize_host", lambda h: calls.append(h) or "http://127.0.0.1:11436")
    assert mod.ollama_host() == "http://127.0.0.1:11436"
    assert mod.ollama_host() == "http://127.0.0.1:11436"
    assert len(calls) == 1
    mod.ollama_host.cache_clear()


@pytest.mark.parametrize("name", ["count_pending", "backfill_db"])
def test_public_surface_present(name):
    mod = importlib.import_module("nougen_shards.embedding_backfill")
    assert callable(getattr(mod, name))
