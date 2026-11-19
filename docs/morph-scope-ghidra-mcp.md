# NouGenMorph: bethington/ghidra-mcp (Production-Grade Ghidra MCP Server)

**Repo**: https://github.com/bethington/ghidra-mcp  
**Local Path**: `~\Outpost\ghidra-mcp`  
**Installed Skill**: `~\.gemini\config\skills\ghidra-mcp`  
**MCP Server**: `ghidra-mcp`  

---

## 1. System Architecture & Intelligence

`bethington/ghidra-mcp` is the definitive Ghidra MCP implementation, providing **209 MCP tools** (3x larger API surface than competing bridges):
- **Full Write Access**: Renaming, typing, plate comments, struct creation, script execution.
- **P-Code Emulation**: Native `EmulatorHelper` execution of isolated functions (e.g., API hash brute-forcing).
- **Live Debugger**: Ghidra TraceRmi integration (17 Java endpoints + 22 Python tools via Windows dbgeng or gdb/lldb).
- **Opinionated Convention Arbitration**: Enforces Hungarian notation (`dwCount`, `lpBuffer`) and PascalCase (`ProcessData`), eliminating naming hallucinations.
- **Completeness Scoring**: 0–100% function audit calculating documentation density and type resolution.

---

## 2. Integration & Wiring
- **Python Environment**: Isolated `.venv` created at `~\Outpost\ghidra-mcp\.venv` with `mcp<2` compatibility.
- **MCP Server Registration**: Configured in `~\.gemini\antigravity-ide\mcp_config.json` under `ghidra-mcp`.
- **Fleet Skill**: Deployed to `~\.gemini\config\skills\ghidra-mcp\SKILL.md`.
- **Synergy with REA**: Works alongside `morluto/rea` (which handles high-level multi-layer investigation and Hopper/CDP), while `ghidra-mcp` provides deep headless/GUI Java bridge access into Ghidra's decompiler and emulator.
