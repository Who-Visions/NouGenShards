import json
import time

import pytest

from nougen_shards import telemetry_model as tm
from nougen_shards import amv_contract as amv


@pytest.fixture()
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "STATE_DIR", tmp_path)
    monkeypatch.setattr(tm, "INTENT_STORE", tmp_path / "fleet_intent.json")
    monkeypatch.setattr(tm, "TELEMETRY_STORE", tmp_path / "fleet_telemetry.json")
    return tmp_path


def test_all_services_healthy(state):
    p = tm.evaluate_node_health("N1", True, services_status={"a": True, "b": True})
    assert p["host_state"] == "ONLINE_HEALTHY"


def test_partial_services_degraded(state):
    p = tm.evaluate_node_health("N1", True, services_status={"a": True, "b": False})
    assert p["host_state"] == "ONLINE_DEGRADED"


def test_ping_but_nothing_listening_is_service_down(state):
    p = tm.evaluate_node_health("N1", True, ports_open={22: False})
    assert p["host_state"] == "ONLINE_SERVICE_DOWN"


def test_open_port_without_services_is_healthy(state):
    p = tm.evaluate_node_health("N1", True, ports_open={22: True})
    assert p["reason"] == "host_and_ports_listening"


def test_recent_heartbeat_unreachable_is_sleeping(state):
    p = tm.evaluate_node_health("N1", False, last_heartbeat=time.time() - 10)
    assert p["host_state"] == "SLEEPING"


def test_expired_heartbeat_is_unexpected_offline(state):
    p = tm.evaluate_node_health("N1", False, last_heartbeat=time.time() - 1000)
    assert p["host_state"] == "OFFLINE_UNEXPECTED"
    assert tm.evaluate_node_health("N1", False)["host_state"] == "OFFLINE_UNEXPECTED"


def test_declared_downtime_is_expected_offline_and_case_insensitive(state):
    tm.declare_planned_downtime("Blade", reason="maintenance", duration_minutes=5)
    assert tm.get_planned_intent("BLADE")["reason"] == "maintenance"
    p = tm.evaluate_node_health("blade", False)
    assert p["host_state"] == "OFFLINE_EXPECTED"
    assert p["reason"] == "maintenance"


def test_ping_clears_declared_downtime(state):
    tm.declare_planned_downtime("blade")
    tm.evaluate_node_health("blade", True, services_status={"a": True})
    assert tm.get_planned_intent("blade") is None
    data = json.loads(tm.INTENT_STORE.read_text(encoding="utf-8"))
    assert data["blade"]["active"] is False and "cleared_at" in data["blade"]


def test_telemetry_persisted_and_corrupt_intent_tolerated(state):
    tm.INTENT_STORE.write_text("{not json", encoding="utf-8")
    assert tm.get_planned_intent("x") is None
    tm.evaluate_node_health("X", True, services_status={"a": True})
    saved = json.loads(tm.TELEMETRY_STORE.read_text(encoding="utf-8"))
    assert saved["x"]["host_state"] == "ONLINE_HEALTHY"


# ---- amv_contract ----
SHA = "a" * 64


def _asset(**kw):
    base = dict(asset_id="a1", sha256=SHA, project_uri="media/a.mp4", fps_num=24,
                fps_den=1, duration_frames=240, rights_status="authorized",
                rights_evidence_ref="license.txt")
    base.update(kw)
    return amv.SourceAsset(**base)


def _edit(**kw):
    base = dict(asset_id="a1", source_sha256=SHA, shot_id="s1", source_in_frame=0,
                source_out_frame=24, output_start_frame=0, output_end_frame=30,
                rationale_evidence_refs=("beat-1",))
    base.update(kw)
    return amv.EditDecision(**base)


def _manifest(edits, assets=None, **kw):
    base = dict(project_id="p", audio_sha256=SHA, audio_project_uri="a.wav",
                audio_sample_rate_hz=48000, output_fps_num=30, output_fps_den=1,
                output_width=1920, output_height=1080, duration_frames=300,
                config_sha256=SHA, assets=tuple(assets or (_asset(),)),
                edits=tuple(edits))
    base.update(kw)
    return amv.AMVManifest(**base)


def test_round_ties_even():
    assert amv.round_ratio_ties_even(1, 2) == 0
    assert amv.round_ratio_ties_even(3, 2) == 2
    assert amv.round_ratio_ties_even(-3, 2) == -2
    with pytest.raises(ValueError):
        amv.round_ratio_ties_even(1, 0)


def test_unsafe_paths_rejected():
    for bad in ("/abs", "../x", "a\\b", "http://x/y", ""):
        with pytest.raises(ValueError):
            _asset(project_uri=bad)


def test_authorized_asset_needs_evidence_and_blocked_not_renderable():
    with pytest.raises(ValueError):
        _asset(rights_evidence_ref=" ")
    with pytest.raises(ValueError, match="not authorized"):
        _manifest([_edit()], assets=[_asset(rights_status="review", rights_evidence_ref=None)])


def test_valid_manifest_hash_is_stable():
    m1 = _manifest([_edit()])
    m2 = _manifest([_edit()])
    assert m1.manifest_sha256() == m2.manifest_sha256()
    assert json.loads(m1.to_canonical_json())["project_id"] == "p"


def test_duration_mismatch_and_ordering_rejected():
    with pytest.raises(ValueError, match="1x"):
        _manifest([_edit(output_end_frame=31)])
    e2 = _edit(shot_id="s2", output_start_frame=0, output_end_frame=30)
    e3 = _edit(shot_id="s3", output_start_frame=40, output_end_frame=70)
    with pytest.raises(ValueError, match="ordered"):
        _manifest([e3, e2])


def test_impact_alignment():
    start = amv.impact_aligned_output_start_frame(
        anchor_sample_index=48000, audio_sample_rate_hz=48000, output_fps_num=30,
        output_fps_den=1, source_fps_num=24, source_fps_den=1, source_in_frame=0,
        impact_source_frame=12)
    assert start == 30 - 15
    e = _edit(output_start_frame=start, output_end_frame=start + 30,
              anchor_sample_index=48000, impact_source_frame=12)
    _manifest([e])
    bad = _edit(output_start_frame=start + 1, output_end_frame=start + 31,
                anchor_sample_index=48000, impact_source_frame=12)
    with pytest.raises(ValueError, match="align"):
        _manifest([bad])
