# Setup Paths (Global vs. Local)

You can configure your local Gemma worker in two ways: globally (applies to all IDE projects) or locally (applies only to the current repository/workspace).

## 1. Global Setup (Recommended)
This approach configures the local worker once, allowing it to be used automatically across all directories you open in your IDE.

*   **MCP Config Path**: `~/.gemini/antigravity-ide/mcp_config.json`
*   **Agent Skill Path**: `~/.gemini/config/plugins/google-antigravity-sdk/skills/local-inspection-worker/SKILL.md`

## 2. Repo-Local Setup
This configuration applies only to a specific project workspace. Use this if you want different projects to target different local models or remote URLs.

*   **MCP Config Path**: `<project-root>/.gemini/mcp_config.json`
*   **Agent Skill Path**: `<project-root>/.gemini/skills/local-inspection-worker/SKILL.md`
