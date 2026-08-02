

# --- capture must not block on an optional enrichment ---------------------

def test_density_scoring_is_off_by_default(monkeypatch):
    """A memory write must not wait on a model.

    Measured before this: 48s per capture, of which the SQLite write was 0.03s
    and the gzip fallback 0.0000s. The whole cost was one local Ollama
    inference producing a single float. It never failed — it waited, which is
    why it survived so long.
    """
    from nougen_shards import core
    monkeypatch.delenv("NOUGEN_DENSITY_LLM", raising=False)
    monkeypatch.setattr(core, "_llm_scoring_enabled", lambda: False)

    called = []
    monkeypatch.setattr(core, "_llm_density", lambda c: called.append(c) or 0.9)
    score = core.calculate_contrastive_perplexity("some text")

    assert called == [], "no model may be consulted unless opted in"
    assert score == core.compression_density("some text")


def test_the_gate_refuses_under_pytest_regardless_of_the_env():
    """Belt and braces: even opted in, a test run never calls out."""
    import os
    from nougen_shards.core import _llm_scoring_enabled
    os.environ["NOUGEN_DENSITY_LLM"] = "1"
    try:
        assert _llm_scoring_enabled() is False
    finally:
        os.environ.pop("NOUGEN_DENSITY_LLM", None)


def test_the_scorer_does_not_reference_its_callers_locals():
    """It was extracted from the caller and kept returning `fallback_score`,
    a name that no longer existed in its scope — a NameError on the
    no-provider path."""
    import inspect
    from nougen_shards.core import _llm_density
    assert "fallback_score" not in inspect.getsource(_llm_density)


def test_the_budget_bounds_a_call_already_in_flight(monkeypatch):
    """The first version checked a deadline only BETWEEN provider attempts, so
    it gated whether a call started and did nothing about one already running —
    measured at 48s with the budget set to 3."""
    import time as _t
    from nougen_shards import core
    monkeypatch.setattr(core, "_llm_scoring_enabled", lambda: True)
    monkeypatch.setenv("NOUGEN_DENSITY_TIMEOUT", "0.3")
    monkeypatch.setattr(core, "_llm_density", lambda c: (_t.sleep(30), 0.9)[1])

    started = _t.perf_counter()
    score = core.calculate_contrastive_perplexity("text")
    elapsed = _t.perf_counter() - started

    assert elapsed < 5, f"budget not enforced: took {elapsed:.1f}s"
    assert score == core.compression_density("text")


def test_an_opted_in_score_is_used_when_it_arrives_in_time(monkeypatch):
    from nougen_shards import core
    monkeypatch.setattr(core, "_llm_scoring_enabled", lambda: True)
    monkeypatch.setattr(core, "_llm_density", lambda c: 0.77)
    assert core.calculate_contrastive_perplexity("text") == 0.77
