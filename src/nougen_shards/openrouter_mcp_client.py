"""
OpenRouter MCP Client Module.
"""
# pylint: disable=duplicate-code

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Add Watchtower directory to python path for importing openrouter_guard
_watchtower_root = os.environ.get("WATCHTOWER_ROOT")
if not _watchtower_root:
    _watchtower_root = str(Path.home() / "Watchtower")
if _watchtower_root not in sys.path:
    sys.path.append(_watchtower_root)
# pylint: disable=import-error,wrong-import-position
from openrouter_guard import call_openrouter

# Resolve mcp.config.json from repository root if it exists, otherwise fall back to global path
_repo_mcp_path = Path(__file__).resolve().parents[2] / "mcp.config.json"
if not _repo_mcp_path.exists():
    _repo_mcp_path = Path(__file__).resolve().parents[2] / "mcp_config.json"

MCP_CONFIG_PATH = os.environ.get(
    "NOUGEN_MCP_CONFIG_PATH",
    str(_repo_mcp_path) if _repo_mcp_path.exists() else str(Path.home() / ".gemini" / "antigravity" / "mcp_config.json")
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FLEET_REGISTRY_NAME = "nougenai-fleet-registry"
MCP_SERVER_ALLOWLIST = {
    "exa",
    "google-developer-knowledge",
    "youtube",
    "web-search",
    FLEET_REGISTRY_NAME,
}


def _build_server_params(name: str, srv_config: dict) -> StdioServerParameters:
    """Build stdio parameters with local Windows/Python startup fixes."""
    cmd = srv_config["command"]
    args = list(srv_config.get("args", []))
    env = srv_config.get("env")

    if env is not None:
        merged_env = os.environ.copy()
        merged_env.update(env)
        env = merged_env

    if cmd.lower() in {"python", "python.exe", "python3", "python3.exe"}:
        cmd = sys.executable

    if name.lower() == FLEET_REGISTRY_NAME:
        wrapper = REPO_ROOT / "tools" / "nougenai_fleet_registry_mcp.py"
        if wrapper.exists():
            cmd = sys.executable
            args = [str(wrapper)]

        env = os.environ.copy() if env is None else env
        env.setdefault(
            "NOUGENAI_MCP_LOCK_DIR",
            str(REPO_ROOT / ".mcp-locks" / f"{FLEET_REGISTRY_NAME}-{os.getpid()}")
        )

    return StdioServerParameters(command=cmd, args=args, env=env)

class MultiMCPBridge:
    """Bridge for managing multiple MCP connections."""

    def __init__(self):
        """Initialize the bridge."""
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stacks = []
        self.tools_map: Dict[str, tuple] = {} # maps tool_name -> (server_name, tool_spec)

    # pylint: disable=too-many-locals
    async def initialize_servers(self):
        """Initialize all MCP servers configured in the local config."""
        print(f"[*] Loading MCP configurations from: {MCP_CONFIG_PATH}")
        if not os.path.exists(MCP_CONFIG_PATH):
            print(f"[!] Config not found at {MCP_CONFIG_PATH}")
            return

        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

        mcp_servers = config.get("mcpServers", {})

        for name, srv_config in mcp_servers.items():
            # Only connect to specific search servers to avoid crashes and timeouts
            if name.lower() not in MCP_SERVER_ALLOWLIST:
                continue

            if "command" in srv_config:
                print(f"[*] Connecting to local server '{name}' via Stdio...")
                try:
                    server_params = _build_server_params(name, srv_config)

                    # Manage async exit stack manually to keep processes running
                    exit_stack = AsyncExitStack()
                    self.exit_stacks.append(exit_stack)

                    stdio_transport = await exit_stack.enter_async_context(
                        stdio_client(server_params)
                    )
                    read_stream, write_stream = stdio_transport

                    session = await exit_stack.enter_async_context(
                        ClientSession(read_stream, write_stream)
                    )
                    await session.initialize()

                    self.sessions[name] = session
                    print(f"    [OK] Active session established for '{name}'")

                    # Fetch available tools
                    tools_resp = await session.list_tools()
                    print(f"    Available Tools: {[t.name for t in tools_resp.tools]}")

                    for t in tools_resp.tools:
                        self.tools_map[t.name] = (name, t)

                except Exception as e: # pylint: disable=broad-exception-caught
                    print(f"    [ERR] Connection failed for server '{name}': {e}")

    def get_openai_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get OpenAI tool definitions from registered tools."""
        openai_tools = []
        for _name, (_server_name, tool) in self.tools_map.items():
            # Get input schema properties and required fields safely
            input_schema = getattr(tool, "inputSchema", {})
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })
        return openai_tools

    async def execute_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool on the registered server."""
        if name not in self.tools_map:
            return f"Error: Tool '{name}' not found in registered fleet."

        server_name, _ = self.tools_map[name]
        session = self.sessions[server_name]

        print(f"[*] Dispatching execution to '{server_name}': {name}({arguments})")
        try:
            result = await session.call_tool(name, arguments)
            # Extracted return format handling
            content = getattr(result, "content", [])
            if isinstance(content, list) and content:
                text_blocks = [
                    block.text for block in content if getattr(block, "type", "") == "text"
                ]
                return "\n".join(text_blocks)
            return str(content)
        except Exception as e: # pylint: disable=broad-exception-caught
            return f"Execution Error: {e}"

    async def shutdown(self):
        """Shutdown all active MCP connections."""
        print("[*] Terminating active local MCP transports...")
        for stack in self.exit_stacks:
            try:
                await stack.aclose()
            except Exception: # pylint: disable=broad-exception-caught
                pass
        print("[*] Transports terminated.")

async def run_query(query: str):
    """Run an OpenRouter query using registered MCP tools."""
    bridge = MultiMCPBridge()
    await bridge.initialize_servers()

    openai_tools = bridge.get_openai_tool_definitions()
    print(f"\n[*] Compiled {len(openai_tools)} tools.")

    messages = [
        {"role": "user", "content": query}
    ]

    # Resolve a free model dynamically from the live roster — never hardcoded.
    from nougen_shards.models_client import OpenRouterClient
    free_model = OpenRouterClient().preferred_free_model()

    print(f"\n[*] Sending request to OpenRouter ({free_model})...")
    try:
        # 1. First model call with tools passed
        response = call_openrouter(
            messages=messages,
            model=free_model,
            tools=openai_tools if openai_tools else None,
            return_raw_message=True
        )

        # Check if the model returned tool calls
        tool_calls = response.get("tool_calls", None)
        if tool_calls:
            messages.append(response)

            for call in tool_calls:
                call_id = call.get("id")
                func_name = call.get("function", {}).get("name")
                func_args = call.get("function", {}).get("arguments", "{}")

                # Parse arguments
                if isinstance(func_args, str):
                    try:
                        args_dict = json.loads(func_args)
                    except Exception: # pylint: disable=broad-exception-caught
                        args_dict = {}
                else:
                    args_dict = func_args

                # Execute local tool
                result_text = await bridge.execute_tool(func_name, args_dict)

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": func_name,
                    "content": result_text
                })

            print("\n[*] Resolving final answer with tool execution output...")
            # 2. Complete loop and get final textual response
            final_response = call_openrouter(
                messages=messages,
                model=free_model
            )
            print(f"\n[Final Response]:\n{final_response}")
        else:
            print(f"\n[Response]:\n{response.get('content')}")

    except Exception as e: # pylint: disable=broad-exception-caught
        print(f"[ERR] Query processing failed: {e}")

    await bridge.shutdown()

if __name__ == "__main__":
    query_input = (
        "Verify the fleet registry statistics and "
        "check if we have any active memory shards."
    )
    if len(sys.argv) > 1:
        query_input = " ".join(sys.argv[1:])

    asyncio.run(run_query(query_input))
