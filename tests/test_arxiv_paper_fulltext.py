"""run_arxiv_paper(action='fulltext') must return bounded text, not just a cache path."""
import hashlib

from nougen_shards import arxiv_radar


class _FakePaper:
    def __init__(self, path):
        self._path = path

    def normalize_id(self, ref):
        return ref.replace("arXiv:", "")

    def fulltext(self, aid):
        return self._path


def _use(monkeypatch, tmp_path, body):
    f = tmp_path / "fulltext.tex"
    f.write_text(body, encoding="utf-8")
    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": _FakePaper(f)})
    return f


def test_fulltext_returns_text_with_hash_and_flags(monkeypatch, tmp_path):
    body = "x" * 500
    _use(monkeypatch, tmp_path, body)
    res = arxiv_radar.run_arxiv_paper("fulltext", "2609.39915")
    assert res["status"] == "success"
    assert res["text"] == body
    assert res["chars_total"] == 500 and res["chars_returned"] == 500
    assert res["truncated"] is False
    assert res["sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert res["bytes"] == 500 and res["cached_path"].endswith("fulltext.tex")


def test_fulltext_is_bounded_and_flags_truncation(monkeypatch, tmp_path):
    _use(monkeypatch, tmp_path, "y" * 5000)
    res = arxiv_radar.run_arxiv_paper("fulltext", "2609.39915", max_chars=1200)
    assert res["chars_returned"] == 1200 and len(res["text"]) == 1200
    assert res["chars_total"] == 5000 and res["truncated"] is True


def test_fulltext_cap_has_floor_and_ceiling(monkeypatch, tmp_path):
    _use(monkeypatch, tmp_path, "z" * (arxiv_radar.MAX_FULLTEXT_CHARS + 5000))
    low = arxiv_radar.run_arxiv_paper("fulltext", "2609.39915", max_chars=10)
    assert low["chars_returned"] == 1000
    high = arxiv_radar.run_arxiv_paper("fulltext", "2609.39915", max_chars=10**9)
    assert high["chars_returned"] == arxiv_radar.MAX_FULLTEXT_CHARS and high["truncated"] is True


def test_empty_ref_fails_explicitly():
    for empty in ("", "   ", None):
        res = arxiv_radar.run_arxiv_paper("lookup", ref=empty)
        assert res["status"] == "error"
        assert "ref is required" in res["error"]

        res_ft = arxiv_radar.run_arxiv_paper("fulltext", ref=empty)
        assert res_ft["status"] == "error"
        assert "ref is required" in res_ft["error"]

        res_cl = arxiv_radar.run_arxiv_paper("claim", ref=empty, pattern="test")
        assert res_cl["status"] == "error"
        assert "ref is required" in res_cl["error"]

        res_mg = arxiv_radar.run_morph_gate(ref=empty, claims=["claim1"])
        assert res_mg["status"] == "error"
        assert "ref is required" in res_mg["error"]


def test_morph_gate_empty_claims_fails():
    for bad_claims in ([], None, "not-a-list"):
        res = arxiv_radar.run_morph_gate(ref="2609.39915", claims=bad_claims)
        assert res["status"] == "error"
        assert "claims must be a non-empty list" in res["error"]


def test_narrow_type_error_compatibility_fallback(monkeypatch, tmp_path):
    # Case 1: Legacy fulltext() that does not accept refresh keyword argument
    f = tmp_path / "fulltext.tex"
    f.write_text("legacy body", encoding="utf-8")

    class _LegacyPaper:
        def normalize_id(self, ref): return ref
        def fulltext(self, aid): return f

    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": _LegacyPaper()})
    res = arxiv_radar.run_arxiv_paper("fulltext", "2609.39915", refresh=True)
    assert res["status"] == "success"
    assert res["text"] == "legacy body"

    # Case 2: Genuine internal TypeError inside fulltext implementation must NOT be swallowed
    class _BuggyPaper:
        def normalize_id(self, ref): return ref
        def fulltext(self, aid, refresh=False):
            raise TypeError("internal implementation bug: unsupported operand type(s) for +: 'int' and 'str'")

    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": _BuggyPaper()})
    res_bug = arxiv_radar.run_arxiv_paper("fulltext", "2609.39915", refresh=True)
    assert res_bug["status"] == "error"
    assert "internal implementation bug" in res_bug["error"]

