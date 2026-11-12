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


def _load(name, tmp_path, monkeypatch, vault=None):
    """Load a vendored tool by path (as arxiv_radar does) with a chosen vault env."""
    import importlib.util

    if vault is None:
        monkeypatch.delenv("NOUGEN_VAULT_DIR", raising=False)
    else:
        monkeypatch.setenv("NOUGEN_VAULT_DIR", str(vault))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "owner")
    path = arxiv_radar.VENDORED_RADAR_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_vend_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tenant_vault_env_controls_every_write_root(tmp_path, monkeypatch):
    tenant = tmp_path / "tenant-vault"
    paper = _load("arxiv_paper", tmp_path, monkeypatch, tenant)
    lab = _load("arxiv_lab_watch", tmp_path, monkeypatch, tenant)
    rss = _load("arxiv_rss_radar", tmp_path, monkeypatch, tenant)
    assert paper.CACHE == tenant / "lab" / "papers"
    assert lab.LAB_ROOT == tenant / "lab"
    assert rss.RADAR_DIR == tenant / "radar"


def test_without_vault_env_the_owner_default_is_kept(tmp_path, monkeypatch):
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    assert paper.CACHE == tmp_path / "owner" / ".nougen" / "shards" / "lab" / "papers"


def test_body_only_ignores_preamble_macros_and_abstract(tmp_path, monkeypatch):
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    tex = (r"\documentclass{article}" "\n"
           r"\newcommand{\headline}{self-improved model reaches 75.0 accuracy}" "\n"
           r"\title{macro-only title}" "\n"
           r"\begin{document}" "\n"
           r"\begin{abstract}abstract-only claim\end{abstract}" "\n"
           "The body states a body-only claim.\n"
           r"\end{document}")
    body = paper.body_only(tex)
    assert "body-only claim" in body
    assert "self-improved model reaches 75.0" not in body
    assert "macro-only title" not in body
    assert "abstract-only claim" not in body


def test_body_only_without_begin_document_keeps_text(tmp_path, monkeypatch):
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    assert "plain fragment" in paper.body_only("plain fragment")


def test_vendored_text_names_no_person():
    for path in arxiv_radar.VENDORED_RADAR_DIR.glob("*.py"):
        assert "Tom Brown" not in path.read_text(encoding="utf-8"), path.name
