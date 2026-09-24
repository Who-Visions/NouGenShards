"""A fresh clone ships no fleet roster: rosters come from local config only."""
import json
from pathlib import Path

from nougen_shards import rich_hud


def test_hud_rows_are_empty_without_local_nodes(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert rich_hud._local_fleet_rows() == []


def test_hud_rows_come_from_local_nodes_json(monkeypatch, tmp_path):
    (tmp_path / ".nougen").mkdir()
    (tmp_path / ".nougen" / "nodes.json").write_text(json.dumps({"a": {"name": "Alpha", "role": "hub", "ip": "192.0.2.1"}}))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert rich_hud._local_fleet_rows() == [("Alpha", "hub", "-", "-", "192.0.2.1", "[green]CONFIGURED[/]")]
