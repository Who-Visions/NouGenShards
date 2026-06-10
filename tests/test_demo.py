"""
Tests for the demo module.
"""

# pylint: disable=duplicate-code
# pylint: disable=redefined-outer-name

import io
import json
import urllib.error
from unittest.mock import patch, MagicMock
import pytest

from examples.demo import (
    check_ollama_alive,
    get_available_models,
    query_local_llm,
    get_selected_model,
    simulate_amnesia_response,
    simulate_recall_response,
    phase_one_amnesia,
    phase_two_capture,
    phase_three_retrieve,
    phase_four_recall,
    print_scoreboard,
    main
)


@pytest.fixture
def mock_socket():
    """Mock the socket module."""
    with patch("examples.demo.socket.socket") as mock_sock:
        yield mock_sock


@pytest.fixture
def mock_urlopen():
    """Mock urllib.request.urlopen."""
    with patch("examples.demo.urllib.request.urlopen") as mock_url:
        yield mock_url


def test_check_ollama_alive_success(mock_socket):
    """Test check_ollama_alive when the server is running."""
    mock_instance = MagicMock()
    mock_socket.return_value = mock_instance
    assert check_ollama_alive() is True
    mock_instance.connect.assert_called_with(("127.0.0.1", 11434))


def test_check_ollama_alive_failure(mock_socket):
    """Test check_ollama_alive when the server is down."""
    mock_instance = MagicMock()
    mock_instance.connect.side_effect = OSError("Connection refused")
    mock_socket.return_value = mock_instance
    assert check_ollama_alive() is False


@patch("examples.demo.check_ollama_alive", return_value=True)
def test_get_available_models_success(mock_check, mock_urlopen):
    """Test getting available models successfully."""
    # pylint: disable=unused-argument
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    models_data = {"models": [{"name": "model1"}, {"name": "model2:e2b"}]}
    mock_response.read.return_value = json.dumps(models_data).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    models = get_available_models()
    assert models == ["model1", "model2:e2b"]


@patch("examples.demo.check_ollama_alive", return_value=False)
def test_get_available_models_offline(mock_check):
    """Test getting available models when server is offline."""
    # pylint: disable=unused-argument
    assert get_available_models() == []


@patch("examples.demo.check_ollama_alive", return_value=True)
def test_get_available_models_error(mock_check, mock_urlopen):
    """Test getting models handles HTTP error."""
    # pylint: disable=unused-argument
    mock_urlopen.side_effect = urllib.error.URLError("Error")
    assert get_available_models() == []


@patch("examples.demo.check_ollama_alive", return_value=True)
def test_query_local_llm_success(mock_check, mock_urlopen):
    """Test querying local LLM successfully."""
    # pylint: disable=unused-argument
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200
    mock_response.read.return_value = json.dumps({"response": "Hello world"}).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = query_local_llm("test_model", "test prompt", "system prompt")
    assert response == "Hello world"


@patch("examples.demo.check_ollama_alive", return_value=False)
def test_query_local_llm_offline(mock_check):
    """Test querying local LLM when server is offline."""
    # pylint: disable=unused-argument
    response = query_local_llm("test_model", "test prompt")
    assert "Offline" in response


@patch("examples.demo.check_ollama_alive", return_value=True)
def test_query_local_llm_error(mock_check, mock_urlopen):
    """Test querying local LLM handles error."""
    # pylint: disable=unused-argument
    mock_urlopen.side_effect = urllib.error.URLError("Connection error")
    response = query_local_llm("test_model", "test prompt")
    assert "Model execution failed" in response


@patch("examples.demo.get_available_models")
def test_get_selected_model_no_models(mock_get_models):
    """Test selecting a model when none are available."""
    mock_get_models.return_value = []
    assert get_selected_model() == ""


@patch("examples.demo.get_available_models")
def test_get_selected_model_preferred(mock_get_models):
    """Test selecting a model when preferred model is present."""
    mock_get_models.return_value = ["model1", "preferred:e4b"]
    assert get_selected_model() == "preferred:e4b"


@patch("examples.demo.get_available_models")
def test_get_selected_model_fallback(mock_get_models):
    """Test selecting a model when no preferred model is present."""
    mock_get_models.return_value = ["model1", "model2"]
    assert get_selected_model() == "model1"


def test_simulate_amnesia_response():
    """Test simulated amnesia response."""
    assert "Check your PATH" in simulate_amnesia_response()


def test_simulate_recall_response():
    """Test simulated recall response."""
    assert "Based on the recalled memory" in simulate_recall_response()


@patch("examples.demo.query_local_llm")
def test_phase_one_amnesia_success(mock_query, capsys):
    """Test phase one amnesia with success response."""
    mock_query.return_value = "Real model response"
    phase_one_amnesia("model", "query", "system")
    captured = capsys.readouterr()
    assert "Real model response" in captured.out


@patch("examples.demo.query_local_llm")
def test_phase_one_amnesia_failure(mock_query, capsys):
    """Test phase one amnesia with failure response."""
    mock_query.return_value = "Model execution failed"
    phase_one_amnesia("model", "query", "system")
    captured = capsys.readouterr()
    assert "Falling back to simulated" in captured.out


@patch("examples.demo.query_local_llm")
def test_phase_one_amnesia_no_model(mock_query, capsys):
    """Test phase one amnesia when no model is selected."""
    # pylint: disable=unused-argument
    phase_one_amnesia("", "query", "system")
    captured = capsys.readouterr()
    assert "Check your PATH" in captured.out


@patch("examples.demo.capture")
def test_phase_two_capture_new(mock_capture, capsys):
    """Test phase two capture when shard is new."""
    mock_capture.return_value = True
    phase_two_capture()
    captured = capsys.readouterr()
    assert "Successfully captured shard" in captured.out


@patch("examples.demo.capture")
def test_phase_two_capture_exists(mock_capture, capsys):
    """Test phase two capture when shard exists."""
    mock_capture.return_value = False
    phase_two_capture()
    captured = capsys.readouterr()
    assert "Shard already exists" in captured.out


@patch("examples.demo.retrieve")
@patch("examples.demo.compile_recall_packet")
def test_phase_three_retrieve(mock_compile, mock_retrieve, capsys):
    """Test phase three retrieve."""
    mock_retrieve.return_value = [{"content": "test"}]
    mock_compile.return_value = "Compiled packet"
    res = phase_three_retrieve()
    captured = capsys.readouterr()
    assert "Retrieved 1 matching shards" in captured.out
    assert res == "Compiled packet"


@patch("examples.demo.query_local_llm")
def test_phase_four_recall_success(mock_query, capsys):
    """Test phase four recall with success response."""
    mock_query.return_value = "Memory response"
    phase_four_recall("model", "query", "system", "packet")
    captured = capsys.readouterr()
    assert "Memory response" in captured.out


@patch("examples.demo.query_local_llm")
def test_phase_four_recall_failure(mock_query, capsys):
    """Test phase four recall with failure response."""
    mock_query.return_value = "Model execution failed"
    phase_four_recall("model", "query", "system", "packet")
    captured = capsys.readouterr()
    assert "Falling back to simulated" in captured.out


@patch("examples.demo.query_local_llm")
def test_phase_four_recall_no_model(mock_query, capsys):
    """Test phase four recall when no model is selected."""
    # pylint: disable=unused-argument
    phase_four_recall("", "query", "system", "packet")
    captured = capsys.readouterr()
    assert "Based on the recalled memory" in captured.out


def test_print_scoreboard(capsys):
    """Test print scoreboard."""
    print_scoreboard()
    captured = capsys.readouterr()
    assert "NOUGENSHARDS SCOREBOARD" in captured.out


@patch("sys.stdout", new_callable=io.StringIO)
@patch("examples.demo.get_selected_model")
@patch("examples.demo.phase_one_amnesia")
@patch("examples.demo.phase_two_capture")
@patch("examples.demo.phase_three_retrieve")
@patch("examples.demo.phase_four_recall")
@patch("examples.demo.print_scoreboard")
def test_main(
    mock_scoreboard,
    mock_four,
    mock_three,
    mock_two,
    mock_one,
    mock_get,
    mock_stdout
):
    """Test main workflow."""
    # pylint: disable=unused-argument
    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-positional-arguments
    mock_get.return_value = "test_model"
    mock_three.return_value = "packet"
    main()
    mock_one.assert_called_once()
    mock_two.assert_called_once()
    mock_three.assert_called_once()
    mock_four.assert_called_once()
    mock_scoreboard.assert_called_once()
