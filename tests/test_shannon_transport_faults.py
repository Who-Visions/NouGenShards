"""Unit tests for Shannon 1948 Transport Fault Tolerance & Semantic Decoupling."""
import json
import time
import pytest
from nougen_shards.shannon_transport import ShannonPacket, ShannonReceiver


def test_packet_creation_and_integrity_verification():
    packet = ShannonPacket.create("pkt-1", 1, "blade1tb", "whoart", {"metric": 42})
    assert packet.verify_integrity() is True
    assert packet.schema_version == "1.0.0"


def test_fault_corruption_detected_and_rejected():
    receiver = ShannonReceiver()
    packet = ShannonPacket.create("pkt-corrupt", 1, "blade1tb", "whoart", {"msg": "clean"})
    d = json.loads(packet.to_envelope())
    # Corrupt data payload
    d["data"]["msg"] = "tampered"
    res = receiver.ingest(json.dumps(d))
    assert res["status"] == "rejected"
    assert res["fault"] == "checksum_mismatch"
    assert res["level"] == "Level_A"


def test_fault_truncation_detected_and_rejected():
    receiver = ShannonReceiver()
    raw_packet = '{"payload_id": "pkt-trunc", "sequence_num": 1, "source_node": "blade1tb", "data": {"key": "val'
    res = receiver.ingest(raw_packet)
    assert res["status"] == "rejected"
    assert res["fault"] == "truncated_json"


def test_fault_duplication_detected_and_deduplicated():
    receiver = ShannonReceiver()
    packet = ShannonPacket.create("pkt-dup", 1, "blade1tb", "whoart", {"msg": "first"})
    res1 = receiver.ingest(packet.to_envelope())
    res2 = receiver.ingest(packet.to_envelope())
    
    assert res1["status"] == "accepted"
    assert res2["status"] == "deduplicated"
    assert res2["fault"] == "duplicate_payload"


def test_fault_reordering_detected():
    receiver = ShannonReceiver()
    pkt2 = ShannonPacket.create("pkt-2", 2, "blade1tb", "whoart", {"seq": 2})
    pkt1 = ShannonPacket.create("pkt-1", 1, "blade1tb", "whoart", {"seq": 1})
    
    res_first = receiver.ingest(pkt2.to_envelope())
    res_second = receiver.ingest(pkt1.to_envelope())
    
    assert res_first["status"] == "accepted"
    assert res_first["reordered"] is False
    assert res_second["status"] == "accepted"
    assert res_second["reordered"] is True


def test_fault_stale_state_rejected():
    receiver = ShannonReceiver(max_stale_seconds=60.0)
    packet = ShannonPacket.create("pkt-stale", 1, "blade1tb", "whoart", {"msg": "old"})
    d = json.loads(packet.to_envelope())
    # Backdate 10 minutes
    d["timestamp_utc"] = time.time() - 600.0
    # Recompute valid checksum for Level A pass so failure happens on stale check
    d["checksum"] = ShannonPacket.create(d["payload_id"], d["sequence_num"], d["source_node"], d["target_node"], d["data"]).checksum
    res = receiver.ingest(json.dumps(d))
    assert res["status"] == "rejected"
    assert res["fault"] == "stale_timestamp"
    assert res["level"] == "Level_B"


def test_fault_schema_drift_and_unknown_fields_preserved():
    receiver = ShannonReceiver()
    packet = ShannonPacket.create("pkt-drift", 1, "blade1tb", "whoart", {"msg": "drift"}, version="2.0.0")
    d = json.loads(packet.to_envelope())
    d["future_quantum_nonce"] = "0xdeadbeef"
    res = receiver.ingest(json.dumps(d))
    assert res["status"] == "accepted"
    assert res["schema_version"] == "2.0.0"
    assert res["unknown_fields_preserved"] == {"future_quantum_nonce": "0xdeadbeef"}
