"""
Tests for OpenRouter MCP Client Module.
"""
# pylint: disable=duplicate-code
import sys
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# Mock the module before importing the client
mock_openrouter_guard = MagicMock()
mock_openrouter_guard.call_openrouter.return_value = {"content": "mocked response"}
sys.modules["openrouter_guard"] = mock_openrouter_guard

# pylint: disable=wrong-import-position
from nougen_shards.openrouter_mcp_client import MultiMCPBridge, run_query


@pytest.fixture
def mock_openrouter():
    """Fixture to reset the mock for openrouter."""
    mock_openrouter_guard.call_openrouter.reset_mock()
    return mock_openrouter_guard


@pytest.mark.asyncio
async def test_initialize_servers_no_file(capfd):
    """Test initialize_servers when config file doesn't exist."""
    bridge = MultiMCPBridge()
    with patch("nougen_shards.openrouter_mcp_client.os.path.exists", return_value=False):
        await bridge.initialize_servers()
    out, _ = capfd.readouterr()
    assert "[!] Config not found" in out


@pytest.mark.asyncio
async def test_initialize_servers_with_file():
    """Test initialize_servers with a mocked config file."""
    bridge = MultiMCPBridge()
    mock_config = {
        "mcpServers": {
            "exa": {"command": "node", "args": ["index.js"]},
            "ignored_server": {"command": "echo"}
        }
    }

    mock_stdio_transport = (MagicMock(), MagicMock())

    with patch("nougen_shards.openrouter_mcp_client.os.path.exists", return_value=True), \
         patch("nougen_shards.openrouter_mcp_client.open", MagicMock()), \
         patch("nougen_shards.openrouter_mcp_client.json.load", return_value=mock_config), \
         patch("nougen_shards.openrouter_mcp_client.stdio_client") as mock_stdio_client, \
         patch("nougen_shards.openrouter_mcp_client.ClientSession") as mock_session_cls, \
         patch("nougen_shards.openrouter_mcp_client.AsyncExitStack.enter_async_context") as mock_enter:

        mock_stdio_client.return_value = "mocked_stdio_cm"
        mock_session_cls.return_value = "mocked_session_cm"

        mock_session_instance = AsyncMock()
        mock_tools_resp = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "test description"
        # Using a dictionary directly for mock properties might fail if the code uses getattr,
        # but in openrouter_mcp_client:
        # input_schema = getattr(tool, "inputSchema", {})
        # so mock_tool.inputSchema works if it's an attribute.
        mock_tool.inputSchema = {"properties": {}, "required": []}
        mock_tools_resp.tools = [mock_tool]
        mock_session_instance.list_tools.return_value = mock_tools_resp

        async def side_effect_enter(cm):
            if cm == "mocked_stdio_cm":
                return mock_stdio_transport
            if cm == "mocked_session_cm":
                return mock_session_instance
            return cm

        mock_enter.side_effect = side_effect_enter

        await bridge.initialize_servers()

    assert "exa" in bridge.sessions
    assert "ignored_server" not in bridge.sessions
    assert "test_tool" in bridge.tools_map


@pytest.mark.asyncio
async def test_get_openai_tool_definitions():
    """Test get_openai_tool_definitions."""
    bridge = MultiMCPBridge()
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.description = "test description"
    mock_tool.inputSchema = {"properties": {"a": {}}, "required": ["a"]}
    bridge.tools_map["test_tool"] = ("exa", mock_tool)

    tools = bridge.get_openai_tool_definitions()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "test_tool"


@pytest.mark.asyncio
async def test_execute_tool_success():
    """Test execute_tool success."""
    bridge = MultiMCPBridge()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "tool output"
    mock_result.content = [mock_block]
    mock_session.call_tool.return_value = mock_result

    bridge.sessions["exa"] = mock_session
    bridge.tools_map["test_tool"] = ("exa", MagicMock())

    result = await bridge.execute_tool("test_tool", {"a": "b"})
    assert result == "tool output"


@pytest.mark.asyncio
async def test_execute_tool_not_found():
    """Test execute_tool when tool is not found."""
    bridge = MultiMCPBridge()
    result = await bridge.execute_tool("missing_tool", {})
    assert "not found" in result


@pytest.mark.asyncio
async def test_shutdown():
    """Test shutdown method."""
    bridge = MultiMCPBridge()
    mock_stack = AsyncMock()
    bridge.exit_stacks.append(mock_stack)
    await bridge.shutdown()
    mock_stack.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_query(mock_openrouter): # pylint: disable=redefined-outer-name
    """Test run_query."""
    mock_openrouter.call_openrouter.side_effect = [
        {
            "tool_calls": [
                {
                    "id": "1",
                    "function": {"name": "test_tool", "arguments": "{}"}
                }
            ]
        },
        {"content": "Final answer"}
    ]

    with patch("nougen_shards.openrouter_mcp_client.MultiMCPBridge") as mock_bridge_cls:
        mock_bridge = AsyncMock()
        mock_bridge.get_openai_tool_definitions = MagicMock(
            return_value=[{"type": "function", "function": {"name": "test_tool"}}]
        )
        mock_bridge.execute_tool.return_value = "tool result"
        mock_bridge_cls.return_value = mock_bridge

        await run_query("test query")

        assert mock_openrouter.call_openrouter.call_count == 2
        mock_bridge.execute_tool.assert_awaited_once_with("test_tool", {})
        mock_bridge.shutdown.assert_awaited_once()
