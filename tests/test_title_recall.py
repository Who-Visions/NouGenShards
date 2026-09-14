"""A query that names a shard exactly must return that shard first, even when
the shard is old, low-utility and surrounded by newer shards that share its words
(recall_eval 9/14/2026: title Recall@10 0.68 before this fix)."""
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards import core  # noqa: E402


@pytest.fixture()
def vault(monkeypatch):
    d = Path(tempfile.mkdtemp())
    monkeypatch.setattr(core, "GLOBAL_DIR", d)
    monkeypatch.setattr(core, "get_db_path", lambda i: d / f"test_shards_{i}.db")
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")
    monkeypatch.setenv("NOUGEN_DISTILL_LANES", "0")
    core._INITIALIZED_DBS.clear()
    yield d
    core._INITIALIZED_DBS.clear()
    shutil.rmtree(d, ignore_errors=True)


TITLE = "Tracker relay — two implementations, one night"


def _seed():
    core.capture("KNOWLEDGE", TITLE, "the old write-up of how the relay was built twice",
                 original_timestamp="2025-01-01T00:00:00Z", utility=0.5)
    for n in range(12):  # newer, higher-utility shards sharing the query's words
        core.capture("KNOWLEDGE", f"Relay night log {n}",
                     f"tracker relay implementations two one night notes {n} " * 3, utility=2.0)


def test_exact_title_is_pinned_first(vault):
    _seed()
    got = core.retrieve(TITLE, limit=5, domain_key="*")
    assert got and got[0]["title"] == TITLE


def test_exact_title_is_case_insensitive(vault):
    _seed()
    assert core.retrieve(TITLE.upper(), limit=5, domain_key="*")[0]["title"] == TITLE


def test_exact_title_respects_scope_filter(vault):
    _seed()
    got = core.retrieve(TITLE, limit=5, domain_key="*", scope={"machine": "nowhere"})
    assert all(r["title"] != TITLE for r in got)


def test_non_title_query_is_unchanged(vault):
    _seed()
    got = core.retrieve("relay night log", limit=5, domain_key="*")
    assert all(not r.get("_title_exact") for r in got)
