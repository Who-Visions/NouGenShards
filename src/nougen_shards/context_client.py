"""Client for interacting with the local context-mode MCP server."""
import asyncio
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import os
from pathlib import Path

# Dynamic resolution of Watchtower root
_watchtower_root = os.environ.get("WATCHTOWER_ROOT")
if not _watchtower_root:
    _watchtower_root = str(Path.home() / "Watchtower")

# Dynamic resolution of context-mode start script path
_nvm_symlink = os.environ.get("NVM_SYMLINK")
_appdata = os.environ.get("APPDATA")

_start_mjs = None
_candidates = []
if _nvm_symlink:
    _candidates.append(Path(_nvm_symlink) / "node_modules/context-mode/start.mjs")
if _appdata:
    _candidates.append(Path(_appdata) / "npm/node_modules/context-mode/start.mjs")

_candidates.extend([
    Path.home() / "AppData/Roaming/npm/node_modules/context-mode/start.mjs",
    Path("/usr/local/lib/node_modules/context-mode/start.mjs"),
    Path("/usr/lib/node_modules/context-mode/start.mjs")
])

for _path in _candidates:
    try:
        if _path.exists():
            _start_mjs = str(_path)
            break
    except Exception:
        pass

if not _start_mjs:
    # Default fallback path
    _symlink_base = _nvm_symlink or "C:/nvm4w/nodejs"
    _start_mjs = str(Path(_symlink_base) / "node_modules/context-mode/start.mjs")

# Dynamic parameters from system folders observation
CONTEXT_MODE_PARAMS = StdioServerParameters(
    command="node",
    args=[
        _start_mjs,
        _watchtower_root
    ]
)

class ContextClient:
    """Client for the context-mode MCP server."""

    def __init__(self, params: StdioServerParameters = CONTEXT_MODE_PARAMS):
        self.params = params

    async def _call_tool(self, tool_name: str, arguments: dict):
        """Internal helper to connect, call a tool, and close."""
        async with AsyncExitStack() as stack:
            try:
                stdio_transport = await stack.enter_async_context(
                    stdio_client(self.params)
                )
                read_stream, write_stream = stdio_transport
                session = await stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()

                result = await session.call_tool(tool_name, arguments)
                content = getattr(result, "content", [])
                if isinstance(content, list) and content:
                    return "\n".join([
                        block.text for block in content
                        if getattr(block, "type", "") == "text"
                    ])
                return str(content)
            except RuntimeError as e:
                return f"Error: Context Mode failed: {e}"
            except Exception as e: # pylint: disable=broad-exception-caught
                return f"Unexpected error in Context Mode: {e}"

    def execute(self, code: str, language: str = "javascript"):
        """Runs sandboxed code via ctx_execute."""
        return asyncio.run(self._call_tool("ctx_execute", {"code": code, "language": language}))

    def execute_file(self, file_path: str):
        """Runs a script file via ctx_execute_file."""
        return asyncio.run(self._call_tool("ctx_execute_file", {"path": file_path}))

    def search(self, query: str):
        """Performs high-performance search via ctx_search."""
        return asyncio.run(self._call_tool("ctx_search", {"query": query}))

    def stats(self):
        """Gets context mode statistics."""
        return asyncio.run(self._call_tool("ctx_stats", {}))

    def insight(self, query: str):
        """Gets architectural insight via ctx_insight."""
        return asyncio.run(self._call_tool("ctx_insight", {"query": query}))
