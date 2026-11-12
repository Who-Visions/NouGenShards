"""A node with no nougen-radar checkout (a tenant) must still load the radar tools."""
from pathlib import Path

from nougen_shards import arxiv_radar


def test_vendored_dir_has_every_required_tool():
    for name in ("arxiv_rss_radar.py", "arxiv_lab_watch.py", "arxiv_paper.py", "morph_gate.py"):
        assert (arxiv_radar.VENDORED_RADAR_DIR / name).is_file(), name


def test_tenant_without_checkout_falls_back_to_vendored(tmp_path, monkeypatch):
    monkeypatch.delenv(arxiv_radar.RADAR_REPO_ENV, raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # empty home: no clones anywhere
    assert arxiv_radar.find_radar_root() == arxiv_radar.VENDORED_RADAR_DIR
    tools = arxiv_radar.get_radar_tools()
    assert tools and tools.get("radar") is not None


def test_real_checkout_still_wins(tmp_path, monkeypatch):
    monkeypatch.delenv(arxiv_radar.RADAR_REPO_ENV, raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    clone = tmp_path / "Outpost" / "nougen-radar" / "tools"
    clone.mkdir(parents=True)
    for name in ("arxiv_rss_radar.py", "arxiv_lab_watch.py"):
        (clone / name).write_text("", encoding="utf-8")
    assert arxiv_radar.find_radar_root() == clone.parent
