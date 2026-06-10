# pylint: disable=duplicate-code, redefined-outer-name, protected-access
"""Tests for auto_research.py."""

import json
from unittest.mock import patch, MagicMock
import pytest

from nougen_shards import auto_research


@pytest.fixture
def mock_ollama_alive():
    """Mock the ollama alive check."""
    with patch("nougen_shards.auto_research.check_ollama_alive") as mock:
        yield mock


@pytest.fixture
def mock_urlopen():
    """Mock urllib.request.urlopen."""
    with patch("urllib.request.urlopen") as mock:
        yield mock


@pytest.fixture
def mock_capture():
    """Mock capture from shards."""
    with patch("nougen_shards.auto_research.capture") as mock:
        yield mock


def test_check_ollama_alive_success():
    """Test ollama alive check success."""
    with patch("socket.socket") as mock_sock:
        mock_instance = MagicMock()
        mock_sock.return_value = mock_instance
        assert auto_research.check_ollama_alive() is True
        mock_instance.connect.assert_called_once_with(("127.0.0.1", 11434))


def test_check_ollama_alive_failure():
    """Test ollama alive check failure."""
    with patch("socket.socket") as mock_sock:
        mock_instance = MagicMock()
        mock_instance.connect.side_effect = Exception("Connection error")
        mock_sock.return_value = mock_instance
        assert auto_research.check_ollama_alive() is False


def test_get_best_model_not_alive(mock_ollama_alive):
    """Test get best model when ollama is not alive."""
    mock_ollama_alive.return_value = False
    assert auto_research.get_best_model() is None


def test_get_best_model_success(mock_ollama_alive, mock_urlopen):
    """Test get best model success."""
    mock_ollama_alive.return_value = True

    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_response.read.return_value = json.dumps({
        "models": [{"name": "model_1"}, {"name": "test_e2b_model"}]
    }).encode("utf-8")

    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_context

    model = auto_research.get_best_model()
    assert model == "test_e2b_model"


def test_get_best_model_fallback(mock_ollama_alive, mock_urlopen):
    """Test get best model fallback to first."""
    mock_ollama_alive.return_value = True

    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_response.read.return_value = json.dumps({
        "models": [{"name": "model_1"}, {"name": "model_2"}]
    }).encode("utf-8")

    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_context

    model = auto_research.get_best_model()
    assert model == "model_1"


def test_get_best_model_exception(mock_ollama_alive, mock_urlopen):
    """Test get best model exception."""
    mock_ollama_alive.return_value = True
    mock_urlopen.side_effect = Exception("API error")
    assert auto_research.get_best_model() is None


def test_query_local_llm_success(mock_urlopen):
    """Test query local LLM success."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_response.read.return_value = json.dumps({"response": " test response "}).encode("utf-8")

    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_context

    res = auto_research.query_local_llm("test_model", "test prompt")
    assert res == "test response"


def test_query_local_llm_exception(mock_urlopen):
    """Test query local LLM exception."""
    mock_urlopen.side_effect = Exception("timeout")
    res = auto_research.query_local_llm("test_model", "test prompt")
    assert "[Model timed out or failed: timeout]" in res


def test_search_arxiv_success(mock_urlopen):
    """Test search arXiv success."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200

    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <entry>
            <id>http://arxiv.org/abs/1234.5678</id>
            <title>Test Title</title>
            <summary>Test Summary</summary>
            <published>2023-01-01T00:00:00Z</published>
        </entry>
    </feed>
    """
    mock_response.read.return_value = xml_content.encode("utf-8")

    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_context

    papers = auto_research.search_arxiv("test query")
    assert len(papers) == 1
    assert papers[0]["id"] == "1234.5678"
    assert papers[0]["title"] == "Test Title"
    assert papers[0]["summary"] == "Test Summary"
    assert papers[0]["published"] == "2023-01-01T00:00:00Z"


def test_search_arxiv_missing_fields(mock_urlopen):
    """Test search arXiv with missing fields."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200

    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <entry>
        </entry>
    </feed>
    """
    mock_response.read.return_value = xml_content.encode("utf-8")

    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_context

    papers = auto_research.search_arxiv("test query")
    assert len(papers) == 1
    assert papers[0]["id"] == "0000.0000"
    assert papers[0]["title"] == "Untitled"
    assert papers[0]["summary"] == "No abstract."
    assert papers[0]["published"] == ""


def test_search_arxiv_exception(mock_urlopen):
    """Test search arXiv exception."""
    mock_urlopen.side_effect = Exception("network error")
    papers = auto_research.search_arxiv("test query")
    assert not papers


def test_get_backup_papers():
    """Test get backup papers."""
    papers = auto_research.get_backup_papers()
    assert len(papers) == 2


@patch("nougen_shards.auto_research.query_local_llm")
def test_evaluate_paper_with_model(mock_query_llm):
    """Test evaluate paper with model."""
    mock_query_llm.return_value = "Test Analysis"
    paper = {"title": "Title", "summary": "Summary", "id": "1234"}

    res = auto_research.evaluate_paper(paper, "test_model")
    assert res == "Test Analysis"
    # Should be called twice due to recursive improvement
    assert mock_query_llm.call_count == 2


@patch("nougen_shards.auto_research.query_local_llm")
def test_evaluate_paper_timeout(mock_query_llm):
    """Test evaluate paper timeout."""
    mock_query_llm.return_value = "[Model timed out"
    paper = {"title": "Title", "summary": "Summary", "id": "1234"}

    res = auto_research.evaluate_paper(paper, "test_model")
    assert "[Model timed out" in res


def test_evaluate_paper_no_model():
    """Test evaluate paper without model."""
    paper = {"title": "Title", "summary": "Summary", "id": "1234"}
    res = auto_research.evaluate_paper(paper, None)
    assert "Evaluated arXiv:1234" in res


@patch("nougen_shards.auto_research.get_best_model")
@patch("nougen_shards.auto_research.search_arxiv")
@patch("nougen_shards.auto_research.evaluate_paper")
def test_main_success(mock_eval, mock_search, mock_get_model, mock_capture):
    """Test main execution success."""
    mock_get_model.return_value = "test_model"

    mock_search.side_effect = [
        [{"id": "1", "title": "T1", "summary": "S1", "published": "P1"}],
        [{"id": "2", "title": "T2", "summary": "S2", "published": "P2"}],
        [{"id": "3", "title": "T3", "summary": "S3", "published": "P3"}],
    ]

    mock_eval.return_value = "Eval result"
    mock_capture.side_effect = [True, False, True]

    auto_research.main()

    assert mock_search.call_count == 3
    assert mock_eval.call_count == 3
    assert mock_capture.call_count == 3


@patch("nougen_shards.auto_research.get_best_model")
@patch("nougen_shards.auto_research.search_arxiv")
def test_main_backup_papers(mock_search, mock_get_model, mock_capture):
    """Test main execution with backup papers."""
    mock_get_model.return_value = None
    mock_search.return_value = []
    mock_capture.return_value = True

    auto_research.main()

    # Backup papers has 2 items
    assert mock_capture.call_count == 2


@patch("nougen_shards.auto_research.get_best_model")
@patch("nougen_shards.auto_research.search_arxiv")
def test_main_search_break(mock_search, mock_get_model, mock_capture):
    """Test main execution breaking early if enough papers found."""
    mock_get_model.return_value = None
    # Provide 3 papers in first query
    mock_search.return_value = [
        {"id": "1", "title": "T1", "summary": "S1", "published": "P1"},
        {"id": "2", "title": "T2", "summary": "S2", "published": "P2"},
        {"id": "3", "title": "T3", "summary": "S3", "published": "P3"},
    ]
    mock_capture.return_value = True

    auto_research.main()

    # Search should only be called once because it returned >= 3 papers
    assert mock_search.call_count == 1
    assert mock_capture.call_count == 3
