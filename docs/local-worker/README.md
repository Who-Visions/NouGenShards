# Antigravity Local Worker Routing Setup

A structured repository and toolkit to integrate local LLMs (**Gemma 4 E2B** via **Ollama**) with the **Google Antigravity IDE** to optimize agentic routing.

---

## 📂 Repository Structure

*   **[`docs/`](docs/)**: Deep dives on routing rules, use cases, setup configurations, and prompt templates:
    *   [Routing Matrix](docs/routing-matrix.md): Categorization into `LOCAL_FAST`, `LOCAL_STRUCTURED`, `LOCAL_SCOPED_CODE`, and `CLOUD_COMPLEX`.
    *   [Gemma 4 E2B Use Cases](docs/gemma-e2b-use-cases.md): Areas where the local worker shines.
    *   [Setup Paths](docs/global-setup.md): Global vs. local configuration paths.
    *   [Prompt Templates](docs/prompt-templates.md): Bounded prompt templates for local workers.
*   **[`config/`](config/)**: Ready-to-use configuration files:
    *   [GEMINI.global.md](config/GEMINI.global.md): Global instructions for routing.
    *   [mcp_config.example.json](config/mcp_config.example.json): Template for Ollama MCP setup.
*   **[`scripts/`](scripts/)**: Routing execution and helper utilities:
    *   [verify_ollama.sh](scripts/verify_ollama.sh): Service checks and dependency validations.
    *   [model_router.py](scripts/model_router.py): Routing engine using local Gemma classification.
    *   [route_task.py](scripts/route_task.py): CLI interface to run/simulate local routing workflows.
*   **[`examples/`](examples/)**: Structured input/output scenarios:
    *   [Local Structured Example](examples/local-structured.json.md)
    *   [Local Scoped Code Example](examples/local-scoped-code.md)
    *   [Cloud Complex Example](examples/cloud-complex.md)

---

## ✨ Quick Setup: The Magic Prompt

The absolute easiest way to set this up is to let your Antigravity Agent do the work for you. Simply copy the prompt block below, paste it directly into your Antigravity chat, and hit run!

```text
Please configure a local Gemma worker for me by performing the following two steps:

1. Write the following JSON configuration to `~/.gemini/antigravity-ide/mcp_config.json` (overwrite if exists):
{
  "mcpServers": {
    "ollama-local": {
      "url": "http://localhost:11434/v1",
      "type": "openai-compatible",
      "model": "gemma:e2b-it",
      "env": {
        "OLLAMA_BASE_URL": "http://localhost:11434"
      }
    }
  }
}

2. Write the following markdown content to `~/.gemini/config/plugins/google-antigravity-sdk/skills/local-inspection-worker/SKILL.md` (create directories if needed):
---
name: local-inspection-worker
description: "A local worker that handles log inspection, file scanning, summaries, cleanup, first-pass debugging, and messy input inspection using a local Ollama model (gemma4:e2b or gemma:e2b-it)."
---

# Local Inspection Worker

## Role
You are a local inspection worker. Read messy input and return only: finding, evidence pointer, confidence, next action. Do not dump raw logs.

## When to Use
Use this skill/worker whenever you need to:
- Inspect logs
- Perform file scanning
- Generate summaries
- Do cleanup
- Run first-pass debugging
- Perform messy input inspection

## Output Format
Your response MUST only contain:
- **Finding**: A brief summary of the finding.
- **Evidence Pointer**: Line numbers, file names, or specific error snippets.
- **Confidence**: High, Medium, or Low (with explanation if weak).
- **Next Action**: The suggested immediate next step.

Do not dump raw logs, do not overexplain, and keep explanations extremely concise. Preserve paths, IDs, line numbers, and error codes.
```

---

## 🛠️ Testing the Helper Scripts

1.  Verify that your local Ollama server is running and the model is pulled:
    ```bash
    ./scripts/verify_ollama.sh
    ```
2.  Test the task classifier router:
    ```bash
    ./scripts/route_task.py "Refactor the function 'calculate_area' to use a lambda expression"
    ```
3.  Simulate a cloud-only task:
    ```bash
    ./scripts/route_task.py "Perform an audit of all authentication controllers to patch potential SQL injection vectors"
    ```
