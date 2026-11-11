"""NvidiaNimClient: fallback rules, embeddings and the no-key path, all offline."""
import pytest

from nougen_shards import nvidia_nim as nim


def _client(responses, monkeypatch):
    """A client whose transport answers from ``responses``: {(path, model): (status, json)}."""
    c = nim.NvidiaNimClient(api_key="test-key", base_url="https://nim.example/v1")
    calls = []

    def fake(path, body=None, timeout=None):
        model = (body or {}).get("model")
        calls.append((path, model, body))
        return responses.get((path, model), (404, None))

    monkeypatch.setattr(c, "_request", fake)
    return c, calls


def _answer(text, model="m"):
    return 200, {"choices": [{"message": {"content": text}}], "model": model}


def test_auto_uses_the_first_verified_model_that_answers(monkeypatch):
    first, second = nim.VERIFIED_CHAT_MODELS[:2]
    c, calls = _client({("/chat/completions", first): (410, None),
                        ("/chat/completions", second): _answer("OK")}, monkeypatch)
    assert c.chat("auto", [{"role": "user", "content": "hi"}]) == "OK"
    assert c.last_model == second
    assert [m for _, m, _ in calls] == [first, second]
    assert c.last_errors == {first: "410"}


def test_named_model_is_tried_first_then_the_verified_list(monkeypatch):
    target = nim.VERIFIED_CHAT_MODELS[0]
    c, calls = _client({("/chat/completions", "google/gemma-4-31b-it"): ("TimeoutError", None),
                        ("/chat/completions", target): _answer("OK")}, monkeypatch)
    assert c.chat("google/gemma-4-31b-it", [{"role": "user", "content": "hi"}]) == "OK"
    assert [m for _, m, _ in calls] == ["google/gemma-4-31b-it", target]


def test_empty_fallbacks_means_only_the_named_model(monkeypatch):
    c, calls = _client({}, monkeypatch)
    out = c.chat("x/y", [{"role": "user", "content": "hi"}], fallbacks=())
    assert out.startswith("Error: no NVIDIA model answered")
    assert [m for _, m, _ in calls] == ["x/y"]


def test_bad_key_stops_instead_of_burning_every_model(monkeypatch):
    first = nim.VERIFIED_CHAT_MODELS[0]
    c, calls = _client({("/chat/completions", first): (401, None)}, monkeypatch)
    out = c.chat("auto", [{"role": "user", "content": "hi"}])
    assert "=401" in out
    assert len(calls) == 1


def test_empty_content_moves_on_to_the_next_model(monkeypatch):
    first, second = nim.VERIFIED_CHAT_MODELS[:2]
    c, _ = _client({("/chat/completions", first): _answer(""),
                    ("/chat/completions", second): _answer("OK")}, monkeypatch)
    assert c.chat("auto", [{"role": "user", "content": "hi"}]) == "OK"
    assert c.last_errors == {first: "empty content"}


def test_reasoning_models_always_get_enough_tokens(monkeypatch):
    first = nim.VERIFIED_CHAT_MODELS[0]
    c, calls = _client({("/chat/completions", first): _answer("OK")}, monkeypatch)
    c.chat("auto", [{"role": "user", "content": "hi"}], max_tokens=4)
    assert calls[0][2]["max_tokens"] >= 256


def test_lane_header_is_sent_once(monkeypatch):
    first = nim.VERIFIED_CHAT_MODELS[0]
    c, calls = _client({("/chat/completions", first): _answer("OK")}, monkeypatch)
    c.chat("auto", [{"role": "user", "content": "hi"}])
    sent = calls[0][2]["messages"]
    assert sent[0] == {"role": "system", "content": nim.NvidiaNimClient.lane_tools.header()}
    assert sent[1] == {"role": "user", "content": "hi"}


def test_no_key_never_calls_out(monkeypatch):
    monkeypatch.setattr(nim.keymaker, "get_secret", lambda name: None)
    c = nim.NvidiaNimClient(base_url="https://nim.example/v1")
    called = []
    monkeypatch.setattr(c, "_request", lambda *a, **k: called.append(a) or (200, {}))
    assert c.chat("auto", [{"role": "user", "content": "hi"}]).startswith("Error: NVIDIA_API_KEY missing")
    assert c.batch_embed(None, ["a"]) == [[]]
    assert called == []


def test_batch_embed_returns_vectors_in_input_order(monkeypatch):
    first = nim.VERIFIED_EMBED_MODELS[0]
    data = {"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]}
    c, calls = _client({("/embeddings", first): (200, data)}, monkeypatch)
    assert c.batch_embed(None, ["a", "b"]) == [[1.0], [2.0]]
    assert calls[0][2]["input_type"] == "passage"


def test_embed_falls_back_across_embed_models(monkeypatch):
    first, second = nim.VERIFIED_EMBED_MODELS[:2]
    c, _ = _client({("/embeddings", second): (200, {"data": [{"index": 0, "embedding": [0.5]}]})}, monkeypatch)
    assert c.embed(None, "a") == [0.5]
    assert c.last_model == second
    assert c.pinned_embed_model == second


def test_named_embed_model_is_pinned_and_never_falls_back(monkeypatch):
    first, second = nim.VERIFIED_EMBED_MODELS[:2]
    c, calls = _client({
        ("/embeddings", first): (503, None),
        ("/embeddings", second): (200, {"data": [{"index": 0, "embedding": [0.9]}]}),
    }, monkeypatch)
    assert c.embed(first, "doc") == []
    assert c.last_model is None
    assert c.last_errors == {first: "503"}
    assert [m for _, m, _ in calls] == [first]


def test_auto_embed_pins_selected_model_across_subsequent_calls(monkeypatch):
    first, second, third = nim.VERIFIED_EMBED_MODELS[:3]
    responses = {
        ("/embeddings", first): (404, None),
        ("/embeddings", second): (200, {"data": [{"index": 0, "embedding": [0.5]}]}),
        ("/embeddings", third): (200, {"data": [{"index": 0, "embedding": [0.7]}]}),
    }
    c, calls = _client(responses, monkeypatch)
    assert c.batch_embed(None, ["doc"]) == [[0.5]]
    assert c.pinned_embed_model == second

    # Transient failure on pinned model must fail rather than mixing embedding spaces.
    responses[("/embeddings", second)] = (503, None)
    calls.clear()
    assert c.embed(None, "query", input_type="query") == []
    assert c.last_model is None
    assert [m for _, m, _ in calls] == [second]

    # Explicit reset lets a caller re-select before re-indexing.
    c.reset_embed_model()
    assert c.embed(None, "reindexed") == [0.7]
    assert c.pinned_embed_model == third


def test_list_models_and_probe(monkeypatch):
    c, _ = _client({("/models", None): (200, {"data": [{"id": "b"}, {"id": "a"}]}),
                    ("/chat/completions", "a"): _answer("OK")}, monkeypatch)
    assert c.list_models() == ["a", "b"]
    assert c.probe(["a", "b"]) == {"a": 200, "b": 404}


def test_base_url_comes_from_the_keymaker_usage_record(monkeypatch):
    monkeypatch.setattr(nim.key_usage, "usage_for", lambda name: {"base_url": "https://from-record/v1/"})
    c = nim.NvidiaNimClient(api_key="k")
    assert c.base_url == "https://from-record/v1"


@pytest.mark.parametrize("status", [404, 410, 429, 500, 502, 503, 504, "TimeoutError"])
def test_model_side_failures_fall_through(monkeypatch, status):
    first, second = nim.VERIFIED_CHAT_MODELS[:2]
    c, _ = _client({("/chat/completions", first): (status, None),
                    ("/chat/completions", second): _answer("OK")}, monkeypatch)
    assert c.chat("auto", [{"role": "user", "content": "hi"}]) == "OK"


def test_incomplete_read_is_caught_in_request_and_falls_back(monkeypatch):
    import http.client
    import json

    class _FakeResp:
        def __init__(self, status, payload=None, fail=None):
            self.status = status
            self._payload = payload
            self._fail = fail

        def read(self):
            if self._fail is not None:
                raise self._fail
            return json.dumps(self._payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    first, second = nim.VERIFIED_CHAT_MODELS[:2]
    attempts = []

    def fake_urlopen(req, timeout=None):
        model = json.loads(req.data.decode())["model"]
        attempts.append(model)
        if model == first:
            return _FakeResp(200, fail=http.client.IncompleteRead(b'{"choices":'))
        return _FakeResp(200, payload={"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(nim.urllib.request, "urlopen", fake_urlopen)
    c = nim.NvidiaNimClient(api_key="test-key", base_url="https://nim.example/v1")
    assert c.chat("auto", [{"role": "user", "content": "hi"}]) == "OK"
    assert attempts == [first, second]
    assert c.last_errors[first] == "IncompleteRead"

    monkeypatch.setattr(
        nim.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResp(200, fail=http.client.IncompleteRead(b"partial")),
    )
    assert c.embed(nim.VERIFIED_EMBED_MODELS[0], "hello") == []
    assert c.last_errors[nim.VERIFIED_EMBED_MODELS[0]] == "IncompleteRead"
