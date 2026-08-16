# Global Routing Instructions for Antigravity

This file sets the standard instruction behavior for your Antigravity agent.

## Task Classification & Routing Rules

When processing tasks, you MUST evaluate the scope and classify the task into one of the following:

1.  **`LOCAL_FAST`**: Text styling, docstrings, raw logs/markdown tables, basic git or shell operations.
    *   **Action**: Execute using local MCP model (`gemma:e2b-it`).
2.  **`LOCAL_STRUCTURED`**: Formatting data schemas, JSON list sanitizations, translations.
    *   **Action**: Execute using local MCP model (`gemma:e2b-it`).
3.  **`LOCAL_SCOPED_CODE`**: Editing a single file, micro-refactoring, writing single unit test cases, basic regex.
    *   **Action**: Execute using local MCP model (`gemma:e2b-it`).
4.  **`CLOUD_COMPLEX`**: Multi-file edits, architectural system changes, deep complex bug fixes, internet searches.
    *   **Action**: Escalate to cloud model (`gemini-3.5-pro` or `gemini-3.5-flash`).

## General Directives
*   Prefer the local model whenever a task is deterministic or restricted in scope.
*   Do not send large dumps of raw files/logs to cloud models. Filter or summarize using the local model first.
