"""Cross-vault scoring for `query_local_vaults`: oversized-row penalty and
content cap.

Root-caused 2026-08-18 (VeilVerse locations stress test, source leg
`20260818T024952Z__claude-app__g-whoentertains`, queued as
`20260818T025149Z__ccr__claude-cli`): a `shards_search` for "locations" was
swamped by one huge, tangentially-matching LOCAL_VAULT row (a Three.js source
dump that happened to say "location" many times) — its final_score used raw
occurrence count with no length normalization, so it tied or beat a short,
directly-on-topic canon entry, and its full content then filled the recall
packet, crowding the real results out before the caller saw them.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.connectors import local_vault  # noqa: E402


def _conf(db, vid=1):
    return {"id": vid, "path": str(db), "table_name": "shards",
            "title_col": "title", "content_col": "content"}


@pytest.fixture(autouse=True)
def _allow_tmp_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_LOCAL_VAULT_ROOTS", str(tmp_path))
    monkeypatch.delenv("NOUGEN_FEDERATE_TIER2", raising=False)
    monkeypatch.delenv("NOUGEN_FEDERATE_HOT", raising=False)
    monkeypatch.delenv("NOUGEN_FEDERATE_HOT_MAX_MB", raising=False)
    monkeypatch.delenv("NOUGEN_LOCAL_VAULT_OVERSIZE_CHARS", raising=False)
    monkeypatch.delenv("NOUGEN_LOCAL_VAULT_OVERSIZE_CONTENT_CAP", raising=False)
    local_vault._FTS_PROBE_CACHE.clear()


def _mixed_store(tmp_path):
    """One compact, on-topic row and one huge, tangential row -- both match
    "locations" via the LIKE path. Neither title mentions "locations", so
    this isolates content-term scoring from the title_hits bonus. The huge
    row has more RAW occurrences of the term than the compact row (that was
    enough to win under the old un-normalized score), but the term is sparse
    relative to its bulk -- lower density than the compact row, which is
    what should win once the score reflects density instead of raw count."""
    db = tmp_path / "mixed.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE shards (title TEXT, content TEXT)")
    canon = ("VeilVerse Canon Entry 402: Shadow Dweller Core locations are "
             "Olympus Mons, the Undercroft, and the Ashen Gate.")
    # A huge, mostly-unrelated document where "locations" appears only every
    # 20th line -- the failure mode's shape (a whole-file dump that happens
    # to mention the term some number of times), not its literal content.
    lines = []
    for i in range(4000):
        if i % 20 == 0:
            lines.append(f"camera.locations[{i}] = computeLocations(mesh, frame{i});")
        else:
            lines.append(f"const mesh{i} = geometry.clone().translate(dx{i}, dy{i}, dz{i});")
    noise = " ".join(lines)
    conn.executemany(
        "INSERT INTO shards VALUES (?, ?)",
        [("VeilVerse Canon Entry 402", canon), ("Three.js render loop", noise)])
    conn.commit()
    conn.close()
    return db


class TestOversizePenalty:
    def test_penalty_zero_under_threshold(self):
        assert local_vault._oversize_penalty(local_vault.OVERSIZE_CHARS) == 0.0

    def test_penalty_grows_past_threshold(self):
        small = local_vault._oversize_penalty(local_vault.OVERSIZE_CHARS * 2)
        large = local_vault._oversize_penalty(local_vault.OVERSIZE_CHARS * 100)
        assert 0.0 < small < large <= 0.35

    def test_content_capped_past_threshold(self):
        body = "x" * (local_vault.OVERSIZE_CHARS + 5000)
        capped = local_vault._cap_content(body, len(body))
        assert len(capped) < len(body)
        assert capped.startswith("x" * local_vault.OVERSIZE_CONTENT_CAP)
        assert "truncated" in capped

    def test_content_untouched_under_threshold(self):
        body = "x" * 100
        assert local_vault._cap_content(body, len(body)) == body


class TestCompactRowOutranksOversizedRow:
    def test_compact_on_topic_row_scores_above_huge_tangential_row(self, tmp_path):
        db = _mixed_store(tmp_path)
        rows = local_vault.query_local_vaults("locations", [_conf(db)], limit=10)
        by_title = {r["title"]: r for r in rows}
        assert by_title["VeilVerse Canon Entry 402"]["final_score"] > \
            by_title["Three.js render loop"]["final_score"]

    def test_huge_row_content_is_capped_in_results(self, tmp_path):
        db = _mixed_store(tmp_path)
        rows = local_vault.query_local_vaults("locations", [_conf(db)], limit=10)
        huge = next(r for r in rows if r["title"] == "Three.js render loop")
        assert len(huge["content"]) <= local_vault.OVERSIZE_CONTENT_CAP + 100

    def test_compact_row_content_is_not_truncated(self, tmp_path):
        db = _mixed_store(tmp_path)
        rows = local_vault.query_local_vaults("locations", [_conf(db)], limit=10)
        compact = next(r for r in rows if r["title"] == "VeilVerse Canon Entry 402")
        assert "truncated" not in compact["content"]
