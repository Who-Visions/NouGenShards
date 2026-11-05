import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.lane_header import (  # noqa: E402
    NEEDS_ARITHMETIC, NEEDS_CODE_RUN, NEEDS_FRESH_FACTS, LaneTools, route, unmet_needs,
)

BARE = LaneTools("ollama-local")
SEARCH = LaneTools("search-lane", frozenset({"search"}))
CODE = LaneTools("code-lane", frozenset({"code_interpreter", "search"}))


def test_toolless_header_forbids_exact_answers():
    header = BARE.header()
    assert "tools: none" in header
    assert "exact arithmetic" in header


def test_header_lists_tools_sorted():
    assert CODE.header() == "[lane code-lane] tools: code_interpreter, search"


def test_bare_lane_cannot_do_arithmetic_or_fresh_facts():
    assert unmet_needs([NEEDS_ARITHMETIC, NEEDS_FRESH_FACTS], BARE) == {NEEDS_ARITHMETIC, NEEDS_FRESH_FACTS}


def test_search_only_lane_can_fetch_facts_but_not_compute():
    assert unmet_needs([NEEDS_FRESH_FACTS], SEARCH) == frozenset()
    assert unmet_needs([NEEDS_ARITHMETIC], SEARCH) == {NEEDS_ARITHMETIC}


def test_code_lane_meets_every_need():
    assert unmet_needs([NEEDS_ARITHMETIC, NEEDS_FRESH_FACTS, NEEDS_CODE_RUN], CODE) == frozenset()


def test_unknown_need_is_an_error_not_a_pass():
    with pytest.raises(ValueError):
        unmet_needs(["vibes"], CODE)


def test_route_picks_first_lane_that_fits():
    assert route([NEEDS_ARITHMETIC], [BARE, SEARCH, CODE]) is CODE


def test_route_returns_none_when_no_lane_fits():
    assert route([NEEDS_ARITHMETIC], [BARE, SEARCH]) is None
