"""Exhaustive era enumeration: recall_window_page / recall_window_count.

Proves the audit contract: a caller can sweep a date window page-by-page and
reconcile the walk against an exact count — no relevance sampling, no silent
truncation, cross-DB timestamp ties enumerated exactly once. Legacy
recall_window must stay byte-compatible.
"""
import uuid

import pytest

pytest.importorskip("gradio")


@pytest.fixture(scope="module")
def seeded_env(tmp_path_factory):
    """Bind a fresh vault via core.bind_active_vault and seed two cluster DBs
    with known rows (including a timestamp TIE across DBs).

    NOT via NOUGEN_HOME: core freezes GLOBAL_DIR from env at import time, and
    conftest imports the package before any fixture runs — mutating env here
    would silently seed whatever store the process resolved at import
    (observed 2026-08-23: nine test rows landed in the live per-user vault).
    The contextvar binding wins regardless of import order."""
    home = tmp_path_factory.mktemp("windowpage-vault")
    from nougen_shards import core
    tokens = core.bind_active_vault(home, "owner")

    def insert(db_index, timestamp, title):
        core.init_db(db_index)
        conn = core.get_connection(db_index)
        try:
            cur = conn.execute(
                "INSERT INTO shards (timestamp, event_type, title, content, "
                "tags, file_hash) VALUES (?, ?, ?, ?, ?, ?)",
                (timestamp, "TEST_WINDOW", title, "body of " + title,
                 "test", uuid.uuid4().hex))
            conn.commit()
            return (timestamp, db_index, cur.lastrowid)
        finally:
            conn.close()

    inside = []
    # DB1: five rows spread across the window.
    for hour in (9, 10, 11, 12, 13):
        inside.append(insert(1, "2026-08-18T%02d:00:00.000000Z" % hour,
                             "db1-h%d" % hour))
    # DB2: two rows, one of them TYING db1-h11's timestamp exactly —
    # the cross-DB tiebreak is the part naive pagination gets wrong.
    inside.append(insert(2, "2026-08-18T11:00:00.000000Z", "db2-tie"))
    inside.append(insert(2, "2026-08-20T08:30:00.000000Z", "db2-late"))
    # Outside the window on both sides: must never appear.
    insert(1, "2026-08-16T23:59:59.000000Z", "before-window")
    insert(2, "2026-08-24T00:00:00.000000Z", "after-window")

    yield {"inside": inside}

    core.reset_active_vault(tokens)


WINDOW = {"since": "2026-08-17", "until": "2026-08-23"}


def _walk(app, page_limit):
    """Walk pages to exhaustion; return every (timestamp, db, id) key seen."""
    seen, cursor, hops = [], None, 0
    while True:
        page = app._window_page(limit=page_limit, cursor=cursor, **WINDOW)
        assert "error" not in page, page
        for r in page["rows"]:
            seen.append((r["timestamp"], r["_db_index"], r["id"]))
        cursor = page["next_cursor"]
        hops += 1
        assert hops <= 50, "pagination did not terminate"
        if not cursor:
            return seen


@pytest.mark.parametrize("page_limit", [1, 2, 3, 100])
def test_walk_is_exhaustive_and_duplicate_free(seeded_env, page_limit):
    import app
    seen = _walk(app, page_limit)
    assert len(seen) == len(set(seen)), "duplicate rows across pages"
    assert set(seen) == set(seeded_env["inside"]), (
        "walk must return exactly the seeded in-window rows")
    # Newest-first, with ties broken deterministically (db ASC, id ASC):
    # sorting by (timestamp DESC, db ASC, id ASC) must be a fixed point.
    assert seen == sorted(seen, key=lambda s: (s[0], -s[1], -s[2]),
                          reverse=True)


def test_count_matches_walk(seeded_env):
    import app
    walked = _walk(app, 2)
    counted = app.recall_window_count(**WINDOW)
    assert counted["total"] == len(walked) == len(seeded_env["inside"])
    assert counted["per_db"]["1"] == 5
    assert counted["per_db"]["2"] == 2


def test_tie_rows_both_enumerated(seeded_env):
    import app
    seen = _walk(app, 1)  # worst case: page boundary lands ON the tie
    tied = [s for s in seen if s[0] == "2026-08-18T11:00:00.000000Z"]
    assert len(tied) == 2, "cross-DB timestamp tie lost a row"
    assert {db for _, db, _ in tied} == {1, 2}


def test_legacy_recall_window_shape_unchanged(seeded_env):
    import app
    rows = app.recall_window(since=WINDOW["since"], until=WINDOW["until"],
                             limit=3)
    assert isinstance(rows, list) and len(rows) == 3
    assert rows[0]["timestamp"] >= rows[-1]["timestamp"]
    assert {"id", "timestamp", "event_type", "title", "content", "tags",
            "utility_score", "_db_index"} <= set(rows[0].keys())


def test_bad_cursor_fails_closed(seeded_env):
    import app
    page = app._window_page(cursor="not-a-cursor", **WINDOW)
    assert page["rows"] == [] and page["next_cursor"] is None
    assert "error" in page
