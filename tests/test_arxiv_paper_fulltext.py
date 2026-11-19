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


def test_empty_ref_validation(monkeypatch):
    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": _FakePaper(None)})
    res = arxiv_radar.run_arxiv_paper("lookup", "")
    assert res["status"] == "error"
    assert "ref is required" in res["error"]

    res_spaces = arxiv_radar.run_arxiv_paper("fulltext", "   ")
    assert res_spaces["status"] == "error"
    assert "ref is required" in res_spaces["error"]


def test_fulltext_preserves_internal_type_error(monkeypatch):
    class _BuggyPaper(_FakePaper):
        def fulltext(self, aid, refresh=False):
            return 1 + "str"

    monkeypatch.setattr(arxiv_radar, "get_radar_tools", lambda: {"paper": _BuggyPaper(None)})
    res = arxiv_radar.run_arxiv_paper("fulltext", "2609.39915")
    assert res["status"] == "error"
    assert "unsupported operand type" in res["error"]

