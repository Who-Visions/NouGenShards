"""Unit tests for nougen_shards.griot_v2 (HURRICANE KICK Griot v2 Golden Tests)."""
from datetime import datetime, timezone
import json
import sqlite3

from nougen_shards.griot_v2 import (
    CompoundShardRef,
    EpistemicClass,
    NodeCoverageStatus,
    gather_griot_archive,
    infer_epistemic_class,
)


FLEET_OK = tuple(
    NodeCoverageStatus(node_name=node, attempted=True, succeeded=True, status_code=200)
    for node in ("whoart", "blade1tb", "phoebus")
)


def make_shard_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, "
        "title TEXT NOT NULL, content TEXT NOT NULL, tags TEXT)"
    )
    conn.execute("CREATE VIRTUAL TABLE shards_fts USING fts5(title, content)")
    for row in rows:
        shard_id, title, content = row[:3]
        timestamp = row[3] if len(row) > 3 else "2026-09-16T00:00:00Z"
        conn.execute(
            "INSERT INTO shards (id, timestamp, title, content, tags) VALUES (?, ?, ?, ?, ?)",
            (shard_id, timestamp, title, content, json.dumps(["retrieval"])),
        )
        conn.execute(
            "INSERT INTO shards_fts (rowid, title, content) VALUES (?, ?, ?)",
            (shard_id, title, content),
        )
    conn.commit()
    conn.close()


def make_complete_local_grid(directory, rows_per_db=2):
    directory.mkdir(parents=True, exist_ok=True)
    for db_index in range(1, 10):
        rows = [
            (shard_id, f"retrieval note {db_index}-{shard_id}", f"retrieval evidence record {db_index}-{shard_id}")
            for shard_id in range(1, rows_per_db + 1)
        ]
        make_shard_db(directory / f"nougen_shards_{db_index}.db", rows)


def test_coverage_honesty_on_blade_timeout_and_whoart_502(tmp_path):
    """Golden Test 1: Blade timeout + WhoArt 502 MUST NOT return clean failures=[] or complete coverage."""
    simulated_errors = {
        "blade1tb": "TIMEOUT (connection deadline exceeded after 5000ms)",
        "whoart": "HTTP 502 Bad Gateway",
    }
    
    packet = gather_griot_archive(
        query="YTD token cost across fleet",
        simulated_node_failures=simulated_errors,
        vault_dbs_dir=tmp_path,
    )

    # Invariant 1: failures list must explicitly contain both failed nodes
    assert len(packet.coverage.failures) >= 2
    assert any("blade1tb" in f for f in packet.coverage.failures)
    assert any("whoart" in f for f in packet.coverage.failures)

    # Invariant 2: Coverage is NOT marked fully covered
    assert packet.coverage.is_fully_covered is False

    # Invariant 3: Multi-axis state is degraded / partial
    assert packet.state.completeness == "PARTIAL"
    assert packet.state.availability == "DEGRADED"

    # Invariant 4: Recovery dispatcher prescribes continuing federation
    assert packet.recommended_recovery == "CONTINUE_FEDERATION"


def test_compound_shard_id_formatting_and_parsing():
    """Golden Test 2: Shard IDs must use compound notation shard_id@db_index."""
    ref = CompoundShardRef(shard_id=29230, db_index=6)
    assert ref.compound_id == "29230@db6"

    parsed = CompoundShardRef.from_str("29475@db8")
    assert parsed is not None
    assert parsed.shard_id == 29475
    assert parsed.db_index == 8

    invalid = CompoundShardRef.from_str("naked_shard_123")
    assert invalid is None


def test_epistemic_typing_classification():
    """Golden Test 3: Knowledge shards are typed into distinct epistemic truth classes."""
    # 1. Telemetry / Receipt
    ep_telemetry = infer_epistemic_class("Token pull 2026-09-16", ["telemetry", "receipt"])
    assert ep_telemetry == EpistemicClass.VERIFIED_TELEMETRY

    # 2. User Canon
    ep_canon = infer_epistemic_class("Rhea Noir Lore Bible", ["lore", "canon", "character_vault"])
    assert ep_canon == EpistemicClass.USER_CANON

    # 3. External ArXiv Paper
    ep_arxiv = infer_epistemic_class("arxiv_cs_AI_20260521_RAG", ["arxiv", "research-doc"])
    assert ep_arxiv == EpistemicClass.EXTERNAL_PAPER

    # 4. Stale Fact
    ep_stale = infer_epistemic_class("Old Pricing Sheet", ["stale", "expired"])
    assert ep_stale == EpistemicClass.STALE_FACT


def test_truncation_transparency(tmp_path):
    """Golden Test 5: Top-k truncation is transparently reported in packet."""
    make_complete_local_grid(tmp_path)
    packet = gather_griot_archive(
        query="retrieval",
        max_top_k=2,
        node_statuses=FLEET_OK,
        vault_dbs_dir=tmp_path,
    )
    assert packet.candidate_total == 18
    assert packet.is_truncated is True
    assert packet.returned_count == 2
    assert packet.coverage.is_fully_covered is True
    assert packet.artifacts[0].compound_id.endswith("@db1")
    assert len(packet.artifacts[0].content_sha256) == 64


def test_missing_probe_receipts_cannot_claim_complete_coverage(tmp_path):
    make_complete_local_grid(tmp_path, rows_per_db=1)
    packet = gather_griot_archive("retrieval", vault_dbs_dir=tmp_path)

    assert packet.coverage.is_fully_covered is False
    assert packet.state.completeness == "PARTIAL"
    assert packet.state.availability == "DEGRADED"
    assert all(not node.attempted for node in packet.coverage.nodes)
    assert any("not probed" in failure for failure in packet.coverage.failures)


def test_missing_expected_vault_is_a_coverage_failure(tmp_path):
    for db_index in range(1, 9):
        make_shard_db(
            tmp_path / f"nougen_shards_{db_index}.db",
            [(1, "retrieval note", "retrieval evidence")],
        )
    packet = gather_griot_archive(
        "retrieval", node_statuses=FLEET_OK, vault_dbs_dir=tmp_path
    )

    assert packet.coverage.vault_dbs_expected == tuple(range(1, 10))
    assert packet.coverage.vault_dbs_scanned == tuple(range(1, 9))
    assert "vault_db_9: expected database missing" in packet.coverage.failures
    assert packet.state.completeness == "PARTIAL"


def test_failed_http_status_cannot_be_marked_success_by_boolean(tmp_path):
    make_complete_local_grid(tmp_path, rows_per_db=1)
    statuses = list(FLEET_OK)
    statuses[0] = NodeCoverageStatus(
        node_name="whoart", attempted=True, succeeded=True, status_code=502
    )
    packet = gather_griot_archive("retrieval", node_statuses=statuses, vault_dbs_dir=tmp_path)

    assert packet.coverage.is_fully_covered is False
    assert any("whoart" in failure for failure in packet.coverage.failures)


def test_ytd_retrieval_prefilters_historical_rows(tmp_path):
    make_shard_db(
        tmp_path / "nougen_shards_1.db",
        [
            (1, "retrieval note from prior year", "retrieval historical marker", "2025-12-31T23:59:59Z"),
            (2, "retrieval note for current year", "retrieval current marker", "2026-01-01T00:00:00Z"),
        ],
    )
    for db_index in range(2, 10):
        make_shard_db(tmp_path / f"nougen_shards_{db_index}.db", [])

    packet = gather_griot_archive(
        "YTD retrieval",
        now=datetime(2026, 9, 16, tzinfo=timezone.utc),
        node_statuses=FLEET_OK,
        vault_dbs_dir=tmp_path,
    )

    assert packet.candidate_total == 1
    assert [artifact.compound_id for artifact in packet.artifacts] == ["2@db1"]
