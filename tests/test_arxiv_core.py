"""arxiv_core.search_arxiv: Atom parsing and env-resolved URL/timeout, no network."""
import logging

import pytest

from nougen_shards import arxiv_core
from nougen_shards.arxiv_core import ARXIV_API_URL, DEFAULT_ARXIV_TIMEOUT_S, search_arxiv

CANNED_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Deep Learning
with Python</title>
    <summary>A summary of deep learning.</summary>
    <published>2024-01-01T00:00:00Z</published>
    <author><name>Author One</name></author>
    <author><name>Author Two</name></author>
  </entry>
</feed>
"""


class _Resp:
    def read(self):
        return CANNED_XML

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def calls(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(arxiv_core.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.delenv("NOUGEN_ARXIV_API_URL", raising=False)
    monkeypatch.delenv("NOUGEN_ARXIV_TIMEOUT_S", raising=False)
    return seen


def test_parses_atom_entry(calls):
    papers = search_arxiv("test")
    assert len(papers) == 1
    paper = papers[0]
    assert paper["arxiv_id"] == "2401.00001v1"
    assert paper["title"] == "Deep Learning with Python"
    assert paper["authors"] == ["Author One", "Author Two"]
    assert paper["pdf_url"].endswith("2401.00001v1.pdf")


def test_defaults_when_env_unset(calls):
    search_arxiv("test")
    assert calls["url"].startswith(ARXIV_API_URL + "?")
    assert calls["timeout"] == DEFAULT_ARXIV_TIMEOUT_S


def test_timeout_env_override(calls, monkeypatch):
    monkeypatch.setenv("NOUGEN_ARXIV_TIMEOUT_S", "42")
    search_arxiv("test")
    assert calls["timeout"] == 42.0


@pytest.mark.parametrize("bad", ["abc", "0", "-3"])
def test_bad_timeout_falls_back_with_warning(calls, monkeypatch, caplog, bad):
    caplog.set_level(logging.WARNING, logger=arxiv_core.__name__)
    monkeypatch.setenv("NOUGEN_ARXIV_TIMEOUT_S", bad)
    search_arxiv("test")
    assert calls["timeout"] == DEFAULT_ARXIV_TIMEOUT_S
    assert "NOUGEN_ARXIV_TIMEOUT_S" in caplog.text
    assert repr(bad) in caplog.text


def test_api_url_override_and_quoting(calls, monkeypatch):
    monkeypatch.setenv("NOUGEN_ARXIV_API_URL", "  https://mirror.example/api/query  ")
    search_arxiv("a b")
    assert calls["url"].startswith("https://mirror.example/api/query?")
    assert "search_query=all:a%20b" in calls["url"]
