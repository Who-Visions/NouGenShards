"""Unit tests for NouGen Human Translation Layer."""
from nougen_shards.human_translation import translate_to_human, detect_uncertainty


def test_jargon_translation():
    raw = "NouGen uses federated multi vault ingress with context aware routing across nodes."
    res = translate_to_human(raw, mode="human_first")
    assert "three machines sharing one memory highway" in res.human_response.lower()
    assert res.technical_layer is not None


def test_uncertainty_and_error_preservation():
    raw = "Blade returned HTTP 502 Bad Gateway while Phoebus timed out after 20.0s (unknown status)."
    res = translate_to_human(raw, mode="dual_layer")
    assert "unreachable or restarting" in res.human_response
    assert "uncertainty_state:unknown" in res.uncertainty_markers
    assert "502" in res.preserved_facts or "HTTP 502" in res.preserved_facts
    assert "phoebus" in [f.lower() for f in res.preserved_facts]


def test_concise_mode():
    raw = "HTTP 401 Unauthorized\nFull stacktrace follows with 20 lines of debug output."
    res = translate_to_human(raw, mode="concise")
    assert "credential check failed" in res.human_response.lower()
