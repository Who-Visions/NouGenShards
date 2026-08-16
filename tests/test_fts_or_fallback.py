"""Red test for FTS implicit-AND starvation (wargames/fts-or-fallback.md, Move 1).

Multi-term conversational queries die on FTS5 implicit-AND semantics, then fall
to a LIKE scan on the *whole* query string, which is stricter still. Observed
kill: "huggingface nougenai token" -> 0 rows while "huggingface" alone ->
thousands. Retrieval must retry the same safe-quoted tokens joined with OR
(bm25-ranked) before conceding.
"""
# pylint: disable=duplicate-code, protected-access
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Temporary vault so the real grid is never touched."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(shards, "get_db_path", mock_get_db_path)

        shards.init_db(1)
        yield temp_path


def test_multi_term_query_survives_single_token_match(setup_test_env):
    """A shard matching only ONE token of a multi-term query must still be
    returned (AND pass empty -> OR retry, not straight to LIKE-on-full-string)."""
    shards.capture(
        "TEST", "HF integration",
        "The huggingface integration stores its access credentials in the vault.",
        domain_key="global")

    results = shards.retrieve("huggingface nougenai token", limit=5, domain_key="global")
    titles = [r["title"] for r in results]
    assert "HF integration" in titles, (
        f"single-token match starved by implicit AND: got {titles}")


def test_or_retry_ranks_better_coverage_first(setup_test_env):
    """When the OR retry fires, rows covering more query tokens must rank
    above rows covering fewer (bm25 ordering preserved)."""
    shards.capture(
        "TEST", "Coverage one",
        "Only the huggingface lane is mentioned in this shard body.",
        domain_key="global")
    shards.capture(
        "TEST", "Coverage both",
        "Both the huggingface lane and the nougenai lane are mentioned.",
        domain_key="global")

    results = shards.retrieve("huggingface nougenai token", limit=5, domain_key="global")
    titles = [r["title"] for r in results]
    assert "Coverage both" in titles and "Coverage one" in titles, f"got {titles}"
    assert titles.index("Coverage both") < titles.index("Coverage one")
