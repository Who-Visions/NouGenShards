"""OpenRouterClient.get_free_models must keep the live roster when the
catalogue holds a malformed entry: one bad row used to raise inside the
broad try and discard every good model, falling back to FREE_MODEL_SEED."""
import io
import json

import pytest

from nougen_shards import models_client
from nougen_shards.models_client import FREE_MODEL_SEED, OpenRouterClient

GOOD = [
    {"id": "acme/alpha:free", "pricing": {"prompt": "1", "completion": "1"}},
    {"id": "acme/beta", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/paid", "pricing": {"prompt": "0.5", "completion": "1"}},
]


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _client(monkeypatch, payload):
    monkeypatch.setattr(models_client.keymaker, "get_secret", lambda *_a, **_k: "test-key")
    monkeypatch.setattr(models_client, "_FREE_MODELS_CACHE", {})
    body = json.dumps(payload).encode()
    monkeypatch.setattr(models_client.urllib.request, "urlopen",
                        lambda *_a, **_k: _Resp(body))
    return OpenRouterClient(api_key="test-key")


def test_clean_catalogue(monkeypatch):
    assert _client(monkeypatch, {"data": GOOD}).get_free_models(refresh=True) == [
        "acme/alpha:free", "acme/beta"]


@pytest.mark.parametrize("bad", [
    None,
    "acme/str",
    ["acme/list"],
    7,
    {"id": 42, "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/odd-pricing", "pricing": "free"},
], ids=lambda b: type(b).__name__ + ":" + str(b)[:20])
def test_malformed_entry_keeps_live_roster(monkeypatch, bad):
    got = _client(monkeypatch, {"data": [GOOD[0], bad, GOOD[1]]}).get_free_models(refresh=True)
    assert "acme/alpha:free" in got and "acme/beta" in got
    assert got != list(FREE_MODEL_SEED)


@pytest.mark.parametrize("payload", [[GOOD], "x", {"data": "nope"}, {"data": None}])
def test_wrong_shape_body_falls_back_to_seed(monkeypatch, payload):
    assert _client(monkeypatch, payload).get_free_models(refresh=True) == list(FREE_MODEL_SEED)
