"""AgentPinger._ollama_installed caches /api/tags per node (TTL).

Discovery otherwise pays a full ssh round trip (up to the 10 s timeout) on
every ping. These tests pin the cache: a second ask inside the TTL must not
touch the network, and a failed ask caches as [] so an unreachable node is
not re-probed per ping either.

Kept out of test_ollama_default_model.py on purpose: that file's autouse
fixture stubs _ollama_installed itself.
"""
from __future__ import annotations

import nougen_shards.nougenmsg as nougenmsg
from nougen_shards.nougenmsg import AgentPinger


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b'{"models": [{"name": "gemma4:e2b-qat", "size": 1}]}'


def test_local_tags_are_cached(monkeypatch):
    calls = []

    def _fake_urlopen(req, timeout=0):
        calls.append(req)
        return _Resp()

    monkeypatch.setattr(nougenmsg.urllib.request, "urlopen", _fake_urlopen)
    AgentPinger._tags_cache.clear()
    first = AgentPinger._ollama_installed("local", True)
    after_first = len(calls)
    assert after_first >= 1  # the first ask really went to the network
    second = AgentPinger._ollama_installed("local", True)
    assert first == second == [{"name": "gemma4:e2b-qat", "size": 1}]
    assert len(calls) == after_first  # second call served from the TTL cache


def test_failed_lookup_caches_empty(monkeypatch):
    calls = []

    def _boom(req, timeout=0):
        calls.append(req)
        raise OSError("unreachable")

    monkeypatch.setattr(nougenmsg.urllib.request, "urlopen", _boom)
    AgentPinger._tags_cache.clear()
    assert AgentPinger._ollama_installed("local", True) == []
    after_first = len(calls)
    assert after_first >= 1
    assert AgentPinger._ollama_installed("local", True) == []
    assert len(calls) == after_first  # failure cached too: no per-ping re-probe
