"""Tests for context_client.py."""
# pylint: disable=protected-access
import contextlib
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from nougen_shards.context_client import ContextClient


@contextlib.contextmanager
def mcp_transport(reply="mcp reply"):
    """Patch the MCP transport boundary and yield the mocked session.

    The public helpers (execute/search/...) are exercised through this rather
    than by stubbing the subject's own ``_call_tool``: a test that patches the
    method it is testing can only observe its own mock, so calling the WRONG
    tool with EMPTY arguments still passes (the exact mutation the audit found
    uncaught). Patching the transport lets us assert the real outbound call.
    """
    session = AsyncMock()
    block = MagicMock()
    block.type = "text"
    block.text = reply
    result = MagicMock()
    result.content = [block]
    session.call_tool.return_value = result

    with patch("nougen_shards.context_client.stdio_client") as mock_stdio_client, \
         patch("nougen_shards.context_client.ClientSession") as mock_session_cls, \
         patch("nougen_shards.context_client.AsyncExitStack.enter_async_context") as mock_enter:

        mock_stdio_client.return_value = "mocked_stdio_cm"
        mock_session_cls.return_value = "mocked_session_cm"

        async def side_effect_enter(cm):
            if cm == "mocked_stdio_cm":
                return (MagicMock(), MagicMock())
            if cm == "mocked_session_cm":
                return session
            return cm

        mock_enter.side_effect = side_effect_enter
        yield session


def assert_tool_call(session, tool_name, arguments):
    """Assert the exact MCP tool name and argument payload that went out."""
    session.call_tool.assert_awaited_once()
    called_args, called_kwargs = session.call_tool.await_args
    sent_name = called_kwargs.get("name", called_args[0] if called_args else None)
    sent_arguments = called_kwargs.get(
        "arguments", called_args[1] if len(called_args) > 1 else None
    )
    assert sent_name == tool_name, f"called {sent_name!r}, expected {tool_name!r}"
    assert sent_arguments == arguments, f"sent {sent_arguments!r}, expected {arguments!r}"

@pytest.mark.asyncio
async def test_call_tool_success():
    """Test _call_tool success path."""
    client = ContextClient()

    mock_stdio_transport = (MagicMock(), MagicMock())
    mock_session_instance = AsyncMock()

    mock_result = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "success output"
    mock_result.content = [mock_block]
    mock_session_instance.call_tool.return_value = mock_result

    with patch("nougen_shards.context_client.stdio_client") as mock_stdio_client, \
         patch("nougen_shards.context_client.ClientSession") as mock_session_cls, \
         patch("nougen_shards.context_client.AsyncExitStack.enter_async_context") as mock_enter:

        mock_stdio_client.return_value = "mocked_stdio_cm"
        mock_session_cls.return_value = "mocked_session_cm"

        async def side_effect_enter(cm):
            if cm == "mocked_stdio_cm":
                return mock_stdio_transport
            if cm == "mocked_session_cm":
                return mock_session_instance
            return cm

        mock_enter.side_effect = side_effect_enter

        result = await client._call_tool("test_tool", {"arg": "val"})
        assert result == "success output"
        mock_session_instance.initialize.assert_awaited_once()
        mock_session_instance.call_tool.assert_awaited_once_with("test_tool", {"arg": "val"})

@pytest.mark.asyncio
async def test_call_tool_runtime_error():
    """Test _call_tool handling RuntimeError."""
    client = ContextClient()

    with patch("nougen_shards.context_client.stdio_client", side_effect=RuntimeError("connection failed")):
        result = await client._call_tool("test_tool", {})
        assert "Error: Context Mode failed: connection failed" in result

@pytest.mark.asyncio
async def test_call_tool_general_exception():
    """Test _call_tool handling general Exception."""
    client = ContextClient()

    with patch("nougen_shards.context_client.stdio_client", side_effect=ValueError("unexpected")):
        result = await client._call_tool("test_tool", {})
        assert "Unexpected error in Context Mode: unexpected" in result

def test_execute_calls_ctx_execute_with_code_and_language():
    """execute() must route to ctx_execute carrying the code and language."""
    with mcp_transport("executed") as session:
        res = ContextClient().execute("print(1)")
        assert res == "executed"
        assert_tool_call(
            session, "ctx_execute", {"code": "print(1)", "language": "javascript"}
        )


def test_execute_honours_an_explicit_language():
    """A caller-supplied language must reach the server, not the default."""
    with mcp_transport("executed") as session:
        ContextClient().execute("print(1)", language="python")
        assert_tool_call(
            session, "ctx_execute", {"code": "print(1)", "language": "python"}
        )


def test_execute_file_calls_ctx_execute_file_with_path():
    """execute_file() must route to ctx_execute_file carrying the path."""
    with mcp_transport("file executed") as session:
        res = ContextClient().execute_file("test.js")
        assert res == "file executed"
        assert_tool_call(session, "ctx_execute_file", {"path": "test.js"})


def test_search_calls_ctx_search_with_query():
    """search() must route to ctx_search carrying the query."""
    with mcp_transport("found results") as session:
        res = ContextClient().search("needle")
        assert res == "found results"
        assert_tool_call(session, "ctx_search", {"query": "needle"})


def test_stats_calls_ctx_stats_with_no_arguments():
    """stats() must route to ctx_stats and send an empty argument object."""
    with mcp_transport("stats data") as session:
        res = ContextClient().stats()
        assert res == "stats data"
        assert_tool_call(session, "ctx_stats", {})


def test_insight_calls_ctx_insight_with_query():
    """insight() must route to ctx_insight carrying the query."""
    with mcp_transport("architectural insight") as session:
        res = ContextClient().insight("how it works")
        assert res == "architectural insight"
        assert_tool_call(session, "ctx_insight", {"query": "how it works"})


def test_public_helpers_use_distinct_tools_and_never_send_empty_args():
    """No two helpers may collapse onto the same tool, and only stats is argless."""
    seen = {}
    for name, invoke, expects_args in (
        ("execute", lambda c: c.execute("x"), True),
        ("execute_file", lambda c: c.execute_file("f.js"), True),
        ("search", lambda c: c.search("q"), True),
        ("stats", lambda c: c.stats(), False),
        ("insight", lambda c: c.insight("q"), True),
    ):
        with mcp_transport() as session:
            invoke(ContextClient())
            called_args, called_kwargs = session.call_tool.await_args
            tool = called_kwargs.get("name", called_args[0] if called_args else None)
            arguments = called_kwargs.get(
                "arguments", called_args[1] if len(called_args) > 1 else None
            )
        assert tool and tool.startswith("ctx_"), f"{name} called {tool!r}"
        assert tool not in seen, f"{name} reuses the tool already used by {seen.get(tool)}"
        seen[tool] = name
        assert isinstance(arguments, dict)
        assert bool(arguments) is expects_args, f"{name} sent {arguments!r}"
    assert len(seen) == 5
