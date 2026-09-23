"""Public code ships no fleet names: without a fleet_hosts.json a clone is standalone."""
from nougen_shards import nougenmsg as m


def test_fresh_clone_without_config_is_standalone(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_FLEET_HOSTS_FILE", str(tmp_path / "absent.json"))
    monkeypatch.setattr(m, "resolve_origin_host", lambda: "phoebus")
    monkeypatch.delenv("NOUGEN_FLEET_NODE", raising=False)
    assert m.get_current_node() == "standalone"
    assert m.normalize_fleet_node("hyperion") == "hyperion"


def test_config_file_drives_node_and_coach_routes(monkeypatch, tmp_path):
    cfg = tmp_path / "fleet_hosts.json"
    cfg.write_text('{"nodes": {"alpha": {"host_patterns": ["box-a"]}}, "coach_routes": {"captain": "alpha"}}')
    monkeypatch.setenv("NOUGEN_FLEET_HOSTS_FILE", str(cfg))
    monkeypatch.setattr(m, "resolve_origin_host", lambda: "box-a-01")
    monkeypatch.delenv("NOUGEN_FLEET_NODE", raising=False)
    assert m.get_current_node() == "alpha"
    assert m.normalize_fleet_node("captain") == "alpha"
    assert m.coach_for_machine("alpha") == "captain"
