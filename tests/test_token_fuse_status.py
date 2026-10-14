from nougen_shards import token_fuse


def test_hypervisor_status_is_a_plain_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(token_fuse, "STATE_DIR", tmp_path)
    monkeypatch.setattr(token_fuse, "FUSE_STORE", tmp_path / "ledger.json")
    monkeypatch.setattr(token_fuse.TokenFuse, "_instance", None)
    fuse = token_fuse.TokenFuse.get_instance()
    fuse.request_task_lease("t1", model="m")
    fuse.record_usage("t1", input_tokens=10, output_tokens=5)
    out = token_fuse.get_hypervisor_status()
    assert out["cumulative_tokens"] == 15
    assert out["tripped"] is False
    assert out["active_tasks"] == 1
    assert out["tasks"]["t1"]["total_tokens"] == 15
    monkeypatch.setattr(token_fuse.TokenFuse, "_instance", None)
