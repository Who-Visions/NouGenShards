import json
import sqlite3

import pytest

from nougen_shards.canonical_facts import CanonicalFactIndex, validate_snapshot
from nougen_shards.cli import cmd_facts, get_parser


def snapshot(*, as_of="2026-09-16", captured_at="2026-09-16T10:00:00-04:00",
             machines=("blade1tb", "phoebus", "whoart"), values=None, version=1,
             supersedes=None, missing=(), state="complete"):
    machines = list(machines)
    values = values or {m: {"value": "100.25", "exact": True} for m in machines}
    return {
        "canonical_key": "token_usage:fleet:YTD:2026",
        "intent": "Resolve this year's all-machine token usage",
        "entities": ["fleet", "token_usage"],
        "aliases": {
            "fleet": ["all machines", "Blade Phoebus WhoArt", "all machine tokens ytd",
                      "fleet tokens this year", "Blade Phoebus WhoArt YTD"],
            "token_usage": ["tokens", "token chart", "today token chart"],
        },
        "metric_namespace": "token_usage",
        "artifact_kind": "FACT_SNAPSHOT",
        "canonical": True,
        "temporal": {
            "timezone": "America/New_York",
            "period": "YTD",
            "year": 2026,
            "as_of": as_of,
            "event_at": as_of,
            "captured_at": captured_at,
        },
        "scope": {"expected_machines": machines, "expected_entities": ["fleet", "token_usage"]},
        "per_machine": values,
        "total": str(sum((float(v["value"]) for v in values.values()), 0)),
        "completeness": {"state": state, "missing_machines": list(missing)},
        "provenance": {"source_ids": ["shard:42@db2", "relay:leg-7"],
                       "source_hashes": {"shard:42@db2": "a" * 64}},
        "version": version,
        "supersedes": supersedes,
    }


def _exact_total(values):
    from decimal import Decimal
    return str(sum((Decimal(str(v["value"])) for v in values.values()), Decimal(0)))


def test_snapshot_requires_every_expected_machine_and_exact_total():
    data = snapshot()
    assert validate_snapshot(data)["scope"]["expected_machines"] == ["blade1tb", "phoebus", "whoart"]

    missing = snapshot(machines=("blade1tb",))
    missing["scope"]["expected_machines"] = ["blade1tb", "phoebus", "whoart"]
    with pytest.raises(ValueError, match="cover exactly"):
        validate_snapshot(missing)

    bad_sum = snapshot()
    bad_sum["total"] = "300"
    with pytest.raises(ValueError, match="sum"):
        validate_snapshot(bad_sum)


@pytest.mark.parametrize("changes, message", [
    ({"canonical": False}, "explicitly canonical"),
    ({"artifact_kind": "SHARD"}, "FACT_SNAPSHOT"),
    ({"completeness": {"state": "partial", "missing_machines": ["whoart"]}}, "incomplete snapshots"),
])
def test_invalid_snapshot_contract_rejected(changes, message):
    data = snapshot()
    data.update(changes)
    with pytest.raises(ValueError, match=message):
        validate_snapshot(data)


def test_naive_timestamp_and_nonfinite_metric_rejected():
    data = snapshot()
    data["temporal"]["captured_at"] = "2026-09-16T10:00:00"
    with pytest.raises(ValueError, match="timezone"):
        validate_snapshot(data)
    data = snapshot()
    data["per_machine"]["phoebus"]["value"] = "NaN"
    data["total"] = "NaN"
    with pytest.raises(ValueError, match="finite"):
        validate_snapshot(data)


def test_index_is_append_only_idempotent_and_resolves_latest_as_of(tmp_path):
    index = CanonicalFactIndex(tmp_path / "facts.sqlite")
    older = snapshot(as_of="2026-09-14", captured_at="2026-09-16T11:00:00-04:00", version=9)
    newer = snapshot(as_of="2026-09-16", captured_at="2026-09-16T09:00:00-04:00", version=1)
    index.put(older)
    new_id = index.put(newer)

    assert index.put(newer) == new_id
    result = index.resolve("token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"])
    assert result["status"] == "complete"
    assert result["snapshot"]["snapshot_id"] == new_id
    assert result["snapshot"]["temporal"]["as_of"] == "2026-09-16"
    assert result["candidates"] == [new_id]
    assert result["rejected"] == []

    with index._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM fact_snapshots").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM canonical_current").fetchone()[0] == 1
        plan = conn.execute("""EXPLAIN QUERY PLAN SELECT snapshot_id FROM fact_snapshots
            WHERE canonical_key=? AND scope_json=? AND as_of_ts<=?
            ORDER BY as_of_ts DESC, version DESC, event_at_ts DESC LIMIT 1""",
            ("token_usage:fleet:YTD:2026", json.dumps({"expected_entities": ["fleet", "token_usage"],
             "expected_machines": ["blade1tb", "phoebus", "whoart"]}, sort_keys=True,
             separators=(",", ":")), 1789603200)).fetchall()
        assert any("idx_fact_history_seek" in row["detail"] for row in plan)
        posting_plan = conn.execute("""EXPLAIN QUERY PLAN SELECT canonical_key FROM fact_query_terms
            WHERE term IN (?, ?)""", ("fleet", "token")).fetchall()
        assert any("idx_fact_terms_lookup" in row["detail"] for row in posting_plan)


def test_blade_only_never_satisfies_fleet_and_receipt_explains_why(tmp_path):
    index = CanonicalFactIndex(tmp_path / "facts.sqlite")
    index.put(snapshot(machines=("blade1tb",)))
    result = index.resolve("token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"])
    assert result["status"] == "cannot_determine"
    assert result["snapshot"] is None
    assert result["coverage"]["complete"] is False
    assert result["rejected"][0]["reason"] == "scope_mismatch:expected_machines"


def test_future_snapshot_is_rejected_without_substituting_it(tmp_path):
    index = CanonicalFactIndex(tmp_path / "facts.sqlite")
    index.put(snapshot(as_of="2026-09-17"))
    result = index.resolve("token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"], as_of="2026-09-16")
    assert result["status"] == "cannot_determine"
    assert result["rejected"][0]["reason"] == "future_as_of"


def test_scope_filter_and_estimated_flags_are_preserved(tmp_path):
    index = CanonicalFactIndex(tmp_path / "facts.sqlite")
    data = snapshot()
    data["per_machine"]["whoart"]["exact"] = False
    data["total"] = _exact_total(data["per_machine"])
    index.put(data)
    found = index.resolve("token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"])
    assert found["snapshot"]["per_machine"]["whoart"]["exact"] is False

    no_match = index.resolve("token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"], scope={"metric_namespace": "cost"})
    assert no_match["status"] == "cannot_determine"
    assert no_match["rejected"][0]["reason"] == "scope_mismatch:query_scope"

    entity_mismatch = index.resolve(
        "token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"],
        expected_entities=["fleet", "cost"],
    )
    assert entity_mismatch["status"] == "cannot_determine"
    assert entity_mismatch["rejected"][0]["reason"] == "scope_mismatch:expected_entities"

    period_mismatch = index.resolve(
        "token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"],
        temporal_scope={"period": "MTD"},
    )
    assert period_mismatch["status"] == "cannot_determine"
    assert period_mismatch["rejected"][0]["reason"] == "scope_mismatch:temporal_scope"


def test_invalid_json_numbers_are_not_silently_normalized():
    data = snapshot()
    data["total"] = float("inf")
    with pytest.raises(ValueError, match="Out of range float values"):
        validate_snapshot(data)


def test_read_only_open_does_not_create_missing_index(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        CanonicalFactIndex(path, create=False)
    assert not path.exists()


def test_v1_migration_backfills_current_pointer_and_query_postings(tmp_path):
    path = tmp_path / "legacy.sqlite"
    data = snapshot(as_of="2025-11-30")
    body = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    import hashlib
    snapshot_id = hashlib.sha256(body.encode("utf-8")).hexdigest()
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE fact_snapshots (
            snapshot_id TEXT PRIMARY KEY, canonical_key TEXT NOT NULL, as_of TEXT NOT NULL,
            event_at TEXT NOT NULL, captured_at TEXT NOT NULL, version INTEGER NOT NULL,
            scope_json TEXT NOT NULL, snapshot_json TEXT NOT NULL)""")
        conn.execute("INSERT INTO fact_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            snapshot_id, data["canonical_key"], data["temporal"]["as_of"],
            data["temporal"]["event_at"], data["temporal"]["captured_at"], data["version"],
            json.dumps(data["scope"], sort_keys=True, separators=(",", ":")), body,
        ))
        conn.execute("PRAGMA user_version = 1")

    index = CanonicalFactIndex(path)
    receipt = index.resolve_query("all machine tokens ytd", expected_machines=["blade1tb", "phoebus", "whoart"])
    assert receipt["status"] == "complete"
    assert receipt["snapshot"]["temporal"]["as_of"] == "2025-11-30"
    with index._connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM fact_query_terms").fetchone()[0] > 0
        assert conn.execute("SELECT as_of_ms FROM fact_snapshots").fetchone()[0] is not None


def test_historical_lookup_uses_index_and_does_not_return_entire_history(tmp_path):
    index = CanonicalFactIndex(tmp_path / "history.sqlite")
    old = snapshot(as_of="2025-11-30", version=1)
    current = snapshot(as_of="2026-09-16", version=2)
    old_id = index.put(old)
    current_id = index.put(current)

    old_result = index.resolve("token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"],
                               as_of="2025-11-30")
    now_result = index.resolve("token_usage:fleet:YTD:2026", expected_machines=["blade1tb", "phoebus", "whoart"])
    assert old_result["snapshot"]["snapshot_id"] == old_id
    assert now_result["snapshot"]["snapshot_id"] == current_id
    assert old_result["candidates"] == [old_id]
    assert now_result["candidates"] == [current_id]

    with index._connect() as conn:
        scope_json = json.dumps({"expected_entities": ["fleet", "token_usage"],
                                 "expected_machines": ["blade1tb", "phoebus", "whoart"]},
                                sort_keys=True, separators=(",", ":"))
        plan = conn.execute("""EXPLAIN QUERY PLAN SELECT snapshot_id FROM fact_snapshots
            WHERE canonical_key=? AND scope_json=? AND as_of_ms<=?
            ORDER BY as_of_ms DESC, version DESC, event_at_ms DESC, captured_at_ms DESC LIMIT 1""",
            ("token_usage:fleet:YTD:2026", scope_json, 1764460800000)).fetchall()
        assert any("idx_fact_history_ms" in row["detail"] for row in plan)


def test_facts_cli_indexes_then_resolves_with_receipt(tmp_path, capsys):
    index_path = tmp_path / "facts.sqlite"
    input_path = tmp_path / "snapshot.json"
    input_path.write_text(json.dumps(snapshot()), encoding="utf-8")
    parser = get_parser()

    index_args = parser.parse_args(["facts", "index", "--index", str(index_path), "--input", str(input_path)])
    cmd_facts(index_args)
    indexed = json.loads(capsys.readouterr().out)
    assert indexed["status"] == "indexed"

    resolve_args = parser.parse_args([
        "facts", "resolve", "all machine tokens ytd", "--index", str(index_path),
        "--machine", "blade1tb", "--machine", "phoebus", "--machine", "whoart",
        "--entity", "fleet", "--entity", "token_usage",
    ])
    cmd_facts(resolve_args)
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "complete"
    assert receipt["lanes_queried"] == ["canonical_fact_index:structured_query", "canonical_fact_index"]
    assert receipt["coverage"]["complete"] is True


def test_natural_language_aliases_resolve_same_snapshot_and_today_is_fresh(tmp_path):
    index = CanonicalFactIndex(tmp_path / "facts.sqlite")
    latest = snapshot(as_of="2026-09-16")
    index.put(latest)
    phrases = [
        "all machine tokens ytd", "fleet tokens this year",
        "today token chart", "Blade Phoebus WhoArt YTD",
    ]
    ids = []
    for phrase in phrases:
        result = index.resolve_query(
            phrase, expected_machines=["blade1tb", "phoebus", "whoart"],
            expected_entities=["fleet", "token_usage"], as_of="2026-09-16",
        )
        assert result["status"] == "complete"
        ids.append(result["snapshot"]["snapshot_id"])
    assert len(set(ids)) == 1

    stale_index = CanonicalFactIndex(tmp_path / "stale.sqlite")
    stale_index.put(snapshot(as_of="2026-09-15"))
    stale = stale_index.resolve_query(
        "today token chart", expected_machines=["blade1tb", "phoebus", "whoart"],
        expected_entities=["fleet", "token_usage"], as_of="2026-09-16",
    )
    assert stale["status"] == "cannot_determine"
    assert stale["rejected"][0]["reason"] == "scope_mismatch:temporal_scope"


def test_query_filters_scope_before_ambiguity_resolution(tmp_path):
    index = CanonicalFactIndex(tmp_path / "facts.sqlite")
    blade_only = snapshot(machines=("blade1tb",))
    blade_only["canonical_key"] = "token_usage:blade:YTD:2026"
    fleet = snapshot()
    index.put(blade_only)
    index.put(fleet)

    result = index.resolve_query(
        "all machine tokens ytd", expected_machines=["blade1tb", "phoebus", "whoart"],
        expected_entities=["fleet", "token_usage"],
    )
    assert result["status"] == "complete"
    assert result["snapshot"]["canonical_key"] == "token_usage:fleet:YTD:2026"
    assert any(item["reason"] == "scope_mismatch:expected_machines" for item in result["rejected"])
