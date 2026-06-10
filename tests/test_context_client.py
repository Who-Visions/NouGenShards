"""Tests for context_client.py."""
# pylint: disable=protected-access
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from nougen_shards.context_client import ContextClient

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

def test_execute():
    """Test execute method."""
    client = ContextClient()
    with patch.object(client, "_call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "executed"
        res = client.execute("print(1)")
        assert res == "executed"
        mock_call.assert_called_once()

def test_execute_file():
    """Test execute_file method."""
    client = ContextClient()
    with patch.object(client, "_call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "file executed"
        res = client.execute_file("test.js")
        assert res == "file executed"
        mock_call.assert_called_once()

def test_search():
    """Test search method."""
    client = ContextClient()
    with patch.object(client, "_call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "found results"
        res = client.search("query")
        assert res == "found results"
        mock_call.assert_called_once()

def test_stats():
    """Test stats method."""
    client = ContextClient()
    with patch.object(client, "_call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "stats data"
        res = client.stats()
        assert res == "stats data"
        mock_call.assert_called_once()

def test_insight():
    """Test insight method."""
    client = ContextClient()
    with patch.object(client, "_call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = "architectural insight"
        res = client.insight("how it works")
        assert res == "architectural insight"
        mock_call.assert_called_once()
