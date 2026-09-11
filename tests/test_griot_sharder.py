"""Every test here is a defect this fleet actually paid for."""

from nougen_shards import griot_sharder as g


def tools(**over):
    base = dict(whoami=lambda: {"node": "phoebus"},
                recall=lambda q: [], search=lambda q: [],
                coverage=lambda: {"complete": True, "dropped_lanes": []})
    base.update(over)
    return g.Tools(**base)


def test_no_hits_with_complete_coverage_is_NONE():
    assert g.gather(tools(), "q").state == g.NONE


def test_no_hits_with_incomplete_coverage_is_UNKNOWN_not_NONE():
    """The 2026-09-08 error: a miss reported as absence.

    I grepped a log for 'elevation', found none, and told another node to stop
    investigating. The events were real and lived in a different store.
    """
    out = g.gather(tools(coverage=lambda: {"complete": False,
                                           "dropped_lanes": ["phoebus:local"]}), "q")
    assert out.state == g.UNKNOWN
    assert any("Do not report absence" in n for n in out.notes)
    assert any("dropped" in n for n in out.notes)


def test_coverage_failure_also_yields_UNKNOWN():
    def boom(): raise RuntimeError("db errored")
    out = g.gather(tools(coverage=boom), "q")
    assert out.state == g.UNKNOWN
    assert any("coverage failed" in n for n in out.notes)


def test_a_failed_retrieval_downgrades_NONE_to_UNKNOWN():
    """Half a search returning nothing is not a search returning nothing."""
    def boom(q): raise RuntimeError("timeout")
    out = g.gather(tools(search=boom), "q")
    assert out.state == g.UNKNOWN
    assert any("search failed" in n for n in out.notes)


def test_both_retrievals_run_and_results_dedupe():
    """Rule 2: recall and search fail differently, so both run."""
    out = g.gather(tools(recall=lambda q: [{"id": 1, "file_hash": "aa"}],
                         search=lambda q: [{"id": 1, "file_hash": "aa"},
                                           {"id": 2, "file_hash": "bb"}]), "q")
    assert out.state == g.FOUND
    assert [h["file_hash"] for h in out.hits] == ["aa", "bb"]


def test_hits_order_by_event_time_not_capture_time():
    """Rule 4: a shard written at 3 AM about Sunday belongs on Sunday."""
    late_capture_early_event = {"id": 1, "timestamp": "2026-09-08T03:00:00Z",
                                "event_time": "2026-09-06T10:00:00Z"}
    early_capture_late_event = {"id": 2, "timestamp": "2026-09-07T01:00:00Z",
                                "event_time": "2026-09-07T20:00:00Z"}
    out = g.gather(tools(recall=lambda q: [early_capture_late_event,
                                           late_capture_early_event]), "q")
    assert [h["id"] for h in out.hits] == [1, 2]


def test_undated_hits_sort_last_not_first():
    """An undated record must not claim to be the earliest thing that happened."""
    out = g.gather(tools(recall=lambda q: [{"id": "undated"},
                                           {"id": "dated", "event_time": "2026-01-01"}]), "q")
    assert [h["id"] for h in out.hits] == ["dated", "undated"]


def test_gather_never_raises_when_a_tool_dies():
    """A gather that dies takes the answer with it."""
    def boom(*a): raise RuntimeError("down")
    out = g.gather(g.Tools(whoami=boom, recall=boom, search=boom, coverage=boom,
                           griot=boom, window=boom), "q", since="a", until="b")
    assert out.state == g.UNKNOWN
    assert len(out.notes) >= 4


def test_only_FOUND_or_NONE_is_distillable():
    """UNKNOWN must never reach a model.

    Asking a model to summarise 'the grid could not see' invites it to fill the
    gap with plausible text -- the failure this pipeline exists to prevent.
    """
    assert g.gather(tools(recall=lambda q: [{"id": 1}]), "q").distillable() is True
    assert g.gather(tools(), "q").distillable() is True
    assert g.gather(tools(coverage=lambda: {"complete": False}), "q").distillable() is False


def test_optional_tools_are_genuinely_optional():
    out = g.gather(tools(), "q")
    assert out.archive == {}


def test_window_results_merge_without_duplicating():
    out = g.gather(tools(recall=lambda q: [{"id": 1, "file_hash": "aa", "event_time": "1"}],
                         window=lambda s, u: [{"id": 1, "file_hash": "aa", "event_time": "1"},
                                              {"id": 3, "file_hash": "cc", "event_time": "2"}]),
                   "q", since="x", until="y")
    assert [h["id"] for h in out.hits] == [1, 3]


def test_module_defines_no_tools_of_its_own():
    """Policy only. If this file starts importing grid tools, a signature it
    guessed at can break callers silently -- which is why they are injected."""
    src = open(g.__file__, encoding="utf-8").read()
    assert "from .core import" not in src
    assert "import requests" not in src
