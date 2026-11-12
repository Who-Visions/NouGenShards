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


def test_body_only_without_begin_document_fails_closed(tmp_path, monkeypatch):
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    preamble_only = r"\documentclass{article}" "\n" r"\newcommand{\score}{99 percent}" "\n"
    assert "99 percent" not in paper.body_only(preamble_only)
    assert paper.body_only("plain fragment") == ""


def test_body_only_drops_text_after_end_document(tmp_path, monkeypatch):
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    tex = r"\begin{document}" "\nreal body\n" r"\end{document}" "\ntrailing 99 percent\n"
    body = paper.body_only(tex)
    assert "real body" in body
    assert "99 percent" not in body


def test_body_only_unclosed_abstract_fails_closed(tmp_path, monkeypatch):
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    assert paper.body_only(r"\begin{document}\begin{abstract}99 percent") == ""


def test_empty_body_and_zero_length_matches_are_not_evidence(tmp_path, monkeypatch):
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    assert paper.body_hits("", ".*") == []
    assert paper.body_hits("some body", "x*") == []
    assert paper.body_hits("some body", "body")


def test_gate_does_not_pass_a_preamble_only_paper_on_a_wildcard(tmp_path, monkeypatch):
    import importlib.util
    gate_mod = _load("arxiv_paper", tmp_path, monkeypatch)  # sets env/home
    spec = importlib.util.spec_from_file_location(
        "_vend_morph_gate", arxiv_radar.VENDORED_RADAR_DIR / "morph_gate.py")
    mg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mg)
    src = tmp_path / "fulltext.tex"
    src.write_text(r"\documentclass{article}" "\n" r"\newcommand{\s}{99 percent}" "\n", encoding="utf-8")
    monkeypatch.setattr(mg.ap, "fulltext", lambda ref, refresh=False: src)
    result = mg.gate("2609.34785", [".*"])
    assert result["evidence_type"] != "paper_body"
    assert result["confidence"] == 0
    del gate_mod


def _tar_gz(files):
    import gzip, io, tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return gzip.compress(buf.getvalue())


def test_input_resolves_exact_path_not_a_suffix_match(tmp_path, monkeypatch):
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    blob = _tar_gz({
        "unused/intro.tex": "decoy 99 percent",
        "main.tex": r"\documentclass{article}\begin{document}\input{intro}\end{document}",
        "intro.tex": "real intro",
    })
    tex = paper.extract_tex(blob)
    assert "real intro" in tex and "decoy" not in tex


def test_gzip_bomb_is_refused(tmp_path, monkeypatch):
    import gzip
    import pytest
    paper = _load("arxiv_paper", tmp_path, monkeypatch)
    monkeypatch.setattr(paper, "MAX_EXPANDED_BYTES", 1000)
    with pytest.raises(IOError):
        paper.extract_tex(gzip.compress(b"a" * 5000))


def test_routing_honours_recipe_min_percentiles(tmp_path, monkeypatch):
    rss = _load("arxiv_rss_radar", tmp_path, monkeypatch)
    recipe = {"category_priors": {"promotion_eligible": ["cs.AI"]},
              "lanes": {"beacon": {"min_percentile": 99.5, "burst_cap": 10},
                        "review": {"min_percentile": 97.0, "burst_cap": 60}}}

    def p(pct):
        return {"priority_pct": pct, "primary_category": "cs.AI", "reason_codes": ["x"],
                "matched_pillars": ["y"], "score": 5, "abstract": "word " * 20}
    lanes = rss.route_papers([p(99.1), p(96.0)], recipe)
    assert [x["priority_pct"] for x in lanes["beacon"]] == []
    assert [x["priority_pct"] for x in lanes["review"]] == [99.1]
    assert [x["priority_pct"] for x in lanes["shard"]] == [96.0]


def test_vendored_text_names_no_person():
    for path in arxiv_radar.VENDORED_RADAR_DIR.glob("*.py"):
        assert "Tom Brown" not in path.read_text(encoding="utf-8"), path.name


def test_request_bound_tenant_vault_wins_over_process_env(tmp_path, monkeypatch):
    """One process can serve several tenants: a request-bound vault must win over NOUGEN_VAULT_DIR."""
    from nougen_shards import core

    paper = _load("arxiv_paper", tmp_path, monkeypatch, tmp_path / "process-vault")
    lab = _load("arxiv_lab_watch", tmp_path, monkeypatch, tmp_path / "process-vault")
    rss = _load("arxiv_rss_radar", tmp_path, monkeypatch, tmp_path / "process-vault")
    tenant = tmp_path / "tenant-b"
    tokens = core.bind_active_vault(tenant, "tenant-b")
    try:
        assert paper.cache_dir() == tenant / "lab" / "papers"
        assert lab.lab_root() == tenant / "lab"
        assert rss.radar_dir() == tenant / "radar"
    finally:
        core.reset_active_vault(tokens)
    assert paper.cache_dir() == tmp_path / "process-vault" / "lab" / "papers"
