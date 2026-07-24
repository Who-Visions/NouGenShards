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


# ---------------------------------------------------------------------------
# Phase tests.
#
# These previously asserted only that a substring appeared on stdout while every
# dependency was mocked, so each phase function could be replaced by a bare
# print() and still pass. They now assert the *contract*: that capture(),
# retrieve(), compile_recall_packet() and query_local_llm() are actually invoked
# with the right arguments, and that their return values drive what is printed.
# ---------------------------------------------------------------------------


@patch("examples.demo.query_local_llm")
def test_phase_one_amnesia_success(mock_query, capsys):
    """Phase 1 must query the model with NO recall packet, and echo its answer."""
    mock_query.return_value = "Real model response"
    phase_one_amnesia("test-model", "the issue query", "base system prompt")

    mock_query.assert_called_once_with("test-model", "the issue query", "base system prompt")
    # The whole point of phase 1 is an un-augmented prompt: the system prompt
    # handed to the model must be the base one, with no packet appended.
    assert mock_query.call_args.args[2] == "base system prompt"

    captured = capsys.readouterr()
    assert "Real model response" in captured.out
    # The printed answer must come from the model, not from the simulation.
    assert simulate_amnesia_response() not in captured.out


@patch("examples.demo.query_local_llm")
def test_phase_one_amnesia_failure(mock_query, capsys):
    """A failed model call must fall back to the simulated amnesia answer."""
    mock_query.return_value = "[Model execution failed: boom]"
    phase_one_amnesia("test-model", "query", "system")

    mock_query.assert_called_once_with("test-model", "query", "system")
    captured = capsys.readouterr()
    assert "Falling back to simulated" in captured.out
    # The substituted text must be the real fallback, not an arbitrary string.
    assert simulate_amnesia_response() in captured.out
    assert "[Model execution failed: boom]" not in captured.out.split("Amnesia]:")[-1]


@patch("examples.demo.query_local_llm")
def test_phase_one_amnesia_no_model(mock_query, capsys):
    """With no model selected the network must not be touched at all."""
    phase_one_amnesia("", "query", "system")

    mock_query.assert_not_called()
    captured = capsys.readouterr()
    assert simulate_amnesia_response() in captured.out


@patch("examples.demo.capture")
def test_phase_two_capture_new(mock_capture, capsys):
    """Phase 2 must call the library capture() with a well-formed shard."""
    mock_capture.return_value = True
    phase_two_capture()

    mock_capture.assert_called_once()
    kwargs = mock_capture.call_args.kwargs
    assert kwargs["event_type"] == "BUG_FIX"
    assert "Spawn" in kwargs["title"]
    # The shard body must carry the actual fix the demo later claims to recall.
    assert "forward slashes" in kwargs["content"]
    assert "subprocess.Popen" in kwargs["content"]
    # Tags are what phase 3's lexical retrieval keys off.
    assert isinstance(kwargs["tags"], list)
    for tag in ("nextjs", "windows", "python", "spawn-helper"):
        assert tag in kwargs["tags"]

    captured = capsys.readouterr()
    assert "Successfully captured shard" in captured.out
    # The reported title must be the one actually captured.
    assert kwargs["title"] in captured.out


@patch("examples.demo.capture")
def test_phase_two_capture_exists(mock_capture, capsys):
    """A duplicate shard must be reported as existing, not as newly captured."""
    mock_capture.return_value = False
    phase_two_capture()

    mock_capture.assert_called_once()
    captured = capsys.readouterr()
    assert "Shard already exists" in captured.out
    assert "Successfully captured" not in captured.out


@patch("examples.demo.retrieve")
@patch("examples.demo.compile_recall_packet")
def test_phase_three_retrieve(mock_compile, mock_retrieve, capsys):
    """Phase 3 must retrieve, feed the hits to the compiler, and return the packet."""
    hits = [{"content": "first"}, {"content": "second"}]
    mock_retrieve.return_value = hits
    mock_compile.return_value = "Compiled packet"

    res = phase_three_retrieve()

    mock_retrieve.assert_called_once()
    query = mock_retrieve.call_args.args[0]
    assert "spawn helper" in query.lower()
    assert "next.js" in query.lower()

    # The compiler must receive exactly what retrieve() returned — the wiring
    # between the two calls is the behaviour under test.
    mock_compile.assert_called_once_with(hits)

    assert res == "Compiled packet"
    captured = capsys.readouterr()
    # The count is derived from the retrieved list, not hardcoded.
    assert f"Retrieved {len(hits)} matching shards" in captured.out
    assert "Compiled packet" in captured.out


@patch("examples.demo.retrieve")
@patch("examples.demo.compile_recall_packet")
def test_phase_three_retrieve_count_tracks_result_size(mock_compile, mock_retrieve, capsys):
    """The reported count must follow the result set (guards a hardcoded '1')."""
    mock_retrieve.return_value = []
    mock_compile.return_value = ""
    phase_three_retrieve()
    assert "Retrieved 0 matching shards" in capsys.readouterr().out


@patch("examples.demo.query_local_llm")
def test_phase_four_recall_success(mock_query, capsys):
    """Phase 4 must inject the recall packet into the system prompt.

    This is the single most important assertion in the demo: the difference
    between phase 1 and phase 4 IS the injected packet.
    """
    mock_query.return_value = "Memory response"
    phase_four_recall("test-model", "the issue query", "base prompt", "RECALL PACKET")

    mock_query.assert_called_once()
    model, prompt, system_prompt = mock_query.call_args.args
    assert model == "test-model"
    assert prompt == "the issue query"
    assert system_prompt == "base prompt\n\nRECALL PACKET"

    captured = capsys.readouterr()
    assert "Memory response" in captured.out
    assert simulate_recall_response() not in captured.out


@patch("examples.demo.query_local_llm")
def test_phase_four_recall_failure(mock_query, capsys):
    """A failed model call must fall back to the simulated recall answer."""
    mock_query.return_value = "[Model execution failed: boom]"
    phase_four_recall("test-model", "query", "base prompt", "RECALL PACKET")

    mock_query.assert_called_once()
    assert mock_query.call_args.args[2] == "base prompt\n\nRECALL PACKET"
    captured = capsys.readouterr()
    assert "Falling back to simulated" in captured.out
    assert simulate_recall_response() in captured.out


@patch("examples.demo.query_local_llm")
def test_phase_four_recall_no_model(mock_query, capsys):
    """With no model selected phase 4 must not call out, and must simulate."""
    phase_four_recall("", "query", "system", "packet")

    mock_query.assert_not_called()
    captured = capsys.readouterr()
    assert simulate_recall_response() in captured.out


def test_print_scoreboard(capsys):
    """The scoreboard must contrast both modes, not just print a banner."""
    print_scoreboard()
    captured = capsys.readouterr()
    assert "NOUGENSHARDS SCOREBOARD" in captured.out
    assert "Amnesia (No Shard)" in captured.out
    assert "Recall (With NouGenShards)" in captured.out
    assert "Lacks repo context" in captured.out
    assert "slash normalization" in captured.out


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
    """main() must wire the phases together, not merely call them.

    Call-count assertions alone pass even if main() hands the phases the wrong
    model or drops the recall packet on the floor — which would silently turn
    phase 4 into a second amnesia run. Assert the data flow.
    """
    # pylint: disable=unused-argument
    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-positional-arguments
    mock_get.return_value = "test_model"
    mock_three.return_value = "COMPILED PACKET"
    main()

    mock_one.assert_called_once()
    mock_two.assert_called_once()
    mock_three.assert_called_once()
    mock_four.assert_called_once()
    mock_scoreboard.assert_called_once()

    one_model, one_query, one_system = mock_one.call_args.args
    four_model, four_query, four_system, four_packet = mock_four.call_args.args

    # The selected model must reach both query phases.
    assert one_model == "test_model"
    assert four_model == "test_model"

    # Both phases must ask the SAME question with the SAME base system prompt —
    # otherwise the amnesia/recall comparison the demo exists to show is invalid.
    assert one_query == four_query
    assert one_system == four_system
    assert "spawn helper" in one_query.lower()

    # Phase 3's return value must be what phase 4 receives as its recall packet.
    assert four_packet == "COMPILED PACKET"
