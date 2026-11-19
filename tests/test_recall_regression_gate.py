"""P6 Gate-Then-Score Retrieval Regression Gate (deterministic, zero-network).

Verifies:
1. Older high-signal shards outrank newer generic noise (temporal fairness).
2. Compositional cross-shard retrieval surfaces split entity facts in top-5.
3. Explicit tenant domain isolation yields zero cross-tenant leaks.
4. Full Gate-Then-Score end-to-end execution passes governance and quality gates.
"""
import json
import sys
import time
from pathlib import Path

import pytest

import nougen_shards.core as core

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import recall_eval as ev  # noqa: E402


@pytest.fixture
def isolated_vault(monkeypatch, tmp_path):
    """Build an isolated synthetic 9-DB vault with embeddings and distill lanes off."""
    monkeypatch.setattr(core, "GLOBAL_DIR", tmp_path)
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path))
    monkeypatch.setenv("NOUGEN_ROOT", str(tmp_path))
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")
    monkeypatch.setenv("NOUGEN_DISTILL_LANES", "0")
    monkeypatch.setenv("NOUGEN_RERANK", "0")
    core.close_readonly_pool()

    specs = [
        # Known-item domain corpus
        (
            "hvac_spec",
            "KNOWLEDGE",
            "Commercial HVAC condenser airflow specification",
            "Chiller loop pressure differential calibration uses variable frequency drives "
            "and manifold gauge inspection across rooftop economizer dampers.",
            "global",
            "2026-06-10T10:00:00Z",
        ),
        (
            "sqlite_wal",
            "KNOWLEDGE",
            "SQLite WAL checkpoint compaction behavior",
            "Write-ahead log frames persist across transactions until passive checkpointing "
            "synchronizes pages back into the primary database file safely.",
            "global",
            "2026-07-12T10:00:00Z",
        ),
        (
            "oauth_allowlist",
            "KNOWLEDGE",
            "OAuth allowlist comma-separated email parser",
            "Normalized lowercase membership filtering trims whitespace and fails closed "
            "whenever the configured allowlist string is empty or undefined.",
            "global",
            "2026-08-01T10:00:00Z",
        ),
        (
            "mercator_tiles",
            "KNOWLEDGE",
            "Satellite Mercator projection tile stitcher",
            "Clamping spherical latitude bounds avoids projection singularities while "
            "wrapping longitudinal viewport boundaries smoothly across the antimeridian.",
            "global",
            "2026-08-20T10:00:00Z",
        ),
        (
            "rust_napi",
            "KNOWLEDGE",
            "Rust N-API native addon Linux toolchain",
            "Configuring system shared library linking avoids missing archive downloads "
            "when cross-compiling prebuilt binary modules for container targets.",
            "global",
            "2026-09-05T10:00:00Z",
        ),
        # Temporal fairness: older high-signal shards (2024) vs newer noise decoys (2026)
        (
            "old_turbine",
            "PROJECT",
            "Helios Cryogenic Turbine Bearing Calibration",
            "Helios cryogenic turbine magnetic bearing telemetry specifies liquid nitrogen "
            "preload tolerances and helium seal pressure thresholds for rotor stability.",
            "global",
            "2024-03-15T12:00:00Z",
        ),
        (
            "old_grid",
            "PROJECT",
            "Solstice Microgrid Inverter Sync Protocol",
            "Solstice microgrid inverter phase-locked loop synchronization maintains harmonic "
            "distortion limits during islanded battery bank failover events.",
            "global",
            "2024-03-15T12:00:00Z",
        ),
        (
            "noise_1",
            "NOTE",
            "Daily standup calibration note alpha",
            "Morning team check-in discussed general calibration schedule updates and routine "
            "paperwork tasks with nothing specific.",
            "global",
            "2026-11-18T12:00:00Z",
        ),
        (
            "noise_2",
            "NOTE",
            "Daily standup calibration note beta",
            "Afternoon check-in mentioned calibration status briefly alongside unrelated "
            "logistics and lunch planning.",
            "global",
            "2026-11-18T12:05:00Z",
        ),
        (
            "noise_3",
            "NOTE",
            "Weekly inverter note gamma",
            "Quick status ping about routine inverter inventory count and shelf labels "
            "for upcoming warehouse audit.",
            "global",
            "2026-11-18T12:10:00Z",
        ),
        # Cross-source compositional entity split across two separate shards
        (
            "comp_arch",
            "PROJECT",
            "Apex Thermal Beacon Architecture Spec",
            "Apex Thermal Beacon uses dual infrared bolometer sensors mounted inside a "
            "sealed aluminum enclosure with zero moving shutters.",
            "global",
            "2025-10-01T09:00:00Z",
        ),
        (
            "comp_deploy",
            "PROJECT",
            "Apex Thermal Beacon Deployment & Compliance",
            "Apex Thermal Beacon firmware passes FCC Part 15 emissions compliance and "
            "streams signed telemetry packets over LoRaWAN gateways.",
            "global",
            "2025-11-15T09:00:00Z",
        ),
        # Tenant isolation pair sharing overlapping terms across distinct domain_keys
        (
            "alpha_1",
            "KNOWLEDGE",
            "Alpha Tenant Billing Pipeline Quota",
            "Tenant settlement pipeline executes nightly invoice reconciliation for "
            "billing cluster alpha with strict audit ledger checks.",
            "tenant_alpha",
            "2026-10-01T08:00:00Z",
        ),
        (
            "alpha_2",
            "KNOWLEDGE",
            "Alpha Tenant Webhook Retry Queue",
            "Dead-letter webhook delivery worker retries settlement notifications for "
            "billing cluster alpha with exponential backoff jitter.",
            "tenant_alpha",
            "2026-10-02T08:00:00Z",
        ),
        (
            "beta_1",
            "KNOWLEDGE",
            "Beta Tenant Billing Pipeline Secrets",
            "Tenant settlement pipeline executes private reconciliation for "
            "billing cluster beta and must never leak into alpha scope.",
            "tenant_beta",
            "2026-10-01T08:00:00Z",
        ),
        (
            "beta_2",
            "KNOWLEDGE",
            "Beta Tenant Webhook Routing Table",
            "Dead-letter webhook routing configuration for settlement notifications "
            "in billing cluster beta private namespace.",
            "tenant_beta",
            "2026-10-02T08:00:00Z",
        ),
    ]

    captured_map = {}
    for name, etype, title, content, dom, ts in specs:
        res = core.capture(
            etype,
            title,
            content,
            domain_key=dom,
            original_timestamp=ts,
        )
        assert getattr(res, "captured", False), f"Failed to capture {name}: {res}"
        captured_map[name] = f"{res.shard_id}@{res.db_index}"

    core.close_readonly_pool()
    try:
        yield tmp_path, captured_map
    finally:
        core.close_readonly_pool()


def test_older_high_signal_shards_beat_newer_noise(isolated_vault):
    _, keys = isolated_vault
    res = core.retrieve(
        "Helios cryogenic turbine magnetic bearing calibration",
        limit=5,
        domain_key="*",
    )
    assert res, "Expected results for 2024 high-signal turbine shard"
    ranked = [f"{r['id']}@{r['_db_index']}" for r in res]
    assert ranked[0] == keys["old_turbine"], (
        f"Expected older high-signal shard {keys['old_turbine']} at #1, got {ranked}"
    )


def test_compositional_cross_shard_recall_surfaces_both_facts(isolated_vault):
    _, keys = isolated_vault
    res = core.retrieve("Apex Thermal Beacon", limit=5, domain_key="*")
    ranked = [f"{r['id']}@{r['_db_index']}" for r in res]
    assert keys["comp_arch"] in ranked[:5], f"Missing architecture shard in top-5: {ranked}"
    assert keys["comp_deploy"] in ranked[:5], f"Missing deployment shard in top-5: {ranked}"


def test_older_close_rrf_shard_not_evicted(isolated_vault):
    _, keys = isolated_vault
    res = core.retrieve("Apex Thermal Beacon", limit=5, domain_key="*")
    by_key = {f"{r['id']}@{r['_db_index']}": r for r in res}
    assert {keys["comp_arch"], keys["comp_deploy"]} <= set(by_key), (
        f"Older close-RRF candidate silently evicted: {list(by_key)}"
    )
    for key in (keys["comp_arch"], keys["comp_deploy"]):
        assert by_key[key]["utility_score_tripartite"] >= 0.01


def test_tenant_domain_isolation_zero_cross_leaks(isolated_vault):
    _, keys = isolated_vault
    res = core.retrieve(
        "Tenant settlement pipeline billing reconciliation",
        limit=10,
        domain_key="tenant_alpha",
    )
    assert res, "Expected tenant_alpha results"
    returned_domains = {r.get("domain_key") for r in res}
    assert returned_domains == {"tenant_alpha"}, f"Cross-tenant leak detected: {returned_domains}"
    ranked = {f"{r['id']}@{r['_db_index']}" for r in res}
    assert keys["beta_1"] not in ranked
    assert keys["beta_2"] not in ranked


def test_full_p6_gate_then_score_end_to_end(isolated_vault):
    tmp_path, keys = isolated_vault
    golden = {
        "created_utc": "2026-11-19T00:00:00Z",
        "seed": 42,
        "include_research": False,
        "queries": [
            {
                "tier": "title",
                "query": "Commercial HVAC condenser airflow specification",
                "relevant": [keys["hvac_spec"]],
                "target": keys["hvac_spec"],
            },
            {
                "tier": "body",
                "query": "passive checkpointing synchronizes pages primary database",
                "relevant": [keys["sqlite_wal"]],
                "target": keys["sqlite_wal"],
            },
            {
                "tier": "body",
                "query": "spherical latitude bounds antimeridian viewport",
                "relevant": [keys["mercator_tiles"]],
                "target": keys["mercator_tiles"],
            },
            {
                "tier": "temporal",
                "query": "Helios cryogenic turbine magnetic bearing telemetry",
                "relevant": [keys["old_turbine"]],
                "target": keys["old_turbine"],
            },
            {
                "tier": "temporal",
                "query": "Solstice microgrid inverter phase-locked loop synchronization",
                "relevant": [keys["old_grid"]],
                "target": keys["old_grid"],
            },
            {
                "tier": "compositional",
                "query": "Apex Thermal Beacon bolometer FCC Part 15 LoRaWAN",
                "relevant": [keys["comp_arch"], keys["comp_deploy"]],
                "target": keys["comp_arch"],
            },
            {
                "tier": "tenant",
                "query": "Tenant settlement pipeline nightly invoice reconciliation",
                "relevant": [keys["alpha_1"]],
                "target": keys["alpha_1"],
                "domain_key": "tenant_alpha",
            },
            {
                "tier": "tenant",
                "query": "Dead-letter webhook routing configuration namespace",
                "relevant": [keys["beta_2"]],
                "target": keys["beta_2"],
                "domain_key": "tenant_beta",
            },
        ],
        "negatives": ev.negative_queries(6, seed=42),
    }

    golden_file = tmp_path / "golden_p6.json"
    golden_file.write_text(json.dumps(golden, indent=1), encoding="utf-8")

    report = ev.run(
        golden_file,
        k=10,
        no_embed=True,
        fp_target=0.1,
        domain="*",
        out_dir=tmp_path,
        write_report=True,
    )
    verdict = ev.evaluate_gate(
        report,
        min_recall5=0.90,
        min_mrr=0.80,
        max_fp_rate=0.0,
        max_p95_ms=2000.0,
        max_domain_leaks=0,
    )

    assert report["domain_leaks"] == 0
    assert report["vault_leaks"] == 0
    assert report["tenant_leaks"] == 0
    assert report["isolation_probes_run"] >= 9
    assert report["vault_isolation"]["positive_hits"] == 3
    assert "p95" in report["negative_latency_ms"]
    assert report["negatives_nonempty"] == 0
    assert verdict["governance_passed"] is True
    assert verdict["quality_passed"] is True
    assert verdict["passed"] is True, f"P6 gate failed: {verdict}"
    assert list(tmp_path.glob("report_*.json")), "Expected report artifact in out_dir"


def test_real_tenant_vault_isolation_shared_domain(isolated_vault):
    iso = ev.probe_tenant_vault_isolation(core, k=10, domain_key="shared_domain")
    assert iso["probes_run"] == 9
    assert iso["positive_expected"] == 3
    assert iso["positive_hits"] == 3
    assert iso["cross_leaks"] == 0


def test_negative_query_latency_included_in_gate_p95(isolated_vault, monkeypatch):
    tmp_path, keys = isolated_vault
    neg_q = "qxzkjmvplr vbtgfnhwds"
    golden = {
        "created_utc": "2026-11-19T00:00:00Z",
        "seed": 42,
        "include_research": False,
        "queries": [
            {
                "tier": "title",
                "query": "Commercial HVAC condenser airflow specification",
                "relevant": [keys["hvac_spec"]],
                "target": keys["hvac_spec"],
            },
        ],
        "negatives": [neg_q, neg_q],
    }
    golden_file = tmp_path / "golden_neg_lat.json"
    golden_file.write_text(json.dumps(golden, indent=1), encoding="utf-8")

    orig_retrieve = core.retrieve

    def delayed_negative(q, *args, **kwargs):
        if q == neg_q:
            time.sleep(0.05)
        return orig_retrieve(q, *args, **kwargs)

    monkeypatch.setattr(core, "retrieve", delayed_negative)
    report = ev.run(
        golden_file,
        k=10,
        no_embed=True,
        fp_target=0.1,
        domain="*",
        out_dir=tmp_path,
        write_report=False,
        max_latency_ms=25.0,
        verify_vault_isolation=True,
    )
    verdict = ev.evaluate_gate(report, max_p95_ms=25.0)
    assert report["negative_latency_ms"]["p95"] >= 40.0
    assert report["latency_ms"]["p95"] >= 40.0
    assert report["taxonomy_counts"].get(ev.ERROR_LATENCY_BREACH, 0) >= 2
    assert verdict["governance_passed"] is False
    assert any("latency_p95_ms" in msg for msg in verdict["failures"])
