# Routing Matrix

This matrix outlines how tasks are categorized and routed in our agentic setup.

| Route Category | Target Executor | Description & Scope | Examples | Anti-Examples |
|---|---|---|---|---|
| **`LOCAL_FAST`** | Local Gemma 4 E2B | Simple text edits, shell commands, docstrings, raw output formats. | - "Add a docstring explaining arguments to this function"<br>- "Check current git status" | - "Refactor this entire multi-file module"<br>- "Write a security audit report" |
| **`LOCAL_STRUCTURED`** | Local Gemma 4 E2B | Bounded JSON parsing, classification, translation, structured schemas. | - "Extract all error codes from this logs string into a JSON list"<br>- "Translate this UI button label into German" | - "Write a new service layer integration"<br>- "Debug a connection pool issue" |
| **`LOCAL_SCOPED_CODE`** | Local Gemma 4 E2B | Edits confined to a single file, micro-refactorings, minor unit tests. | - "Write a unit test for my simple math library"<br>- "Optimize this regex pattern" | - "Perform a Python 2 to Python 3 framework migration"<br>- "Optimize the database schema" |
| **`CLOUD_COMPLEX`** | Cloud Gemini (Flash/Pro) | Multi-file tasks, architectural plans, deep debugging across modules. | - "Add logging to the entire backend server"<br>- "Analyze performance bottleneck between API and Postgres" | - "Format this git log to markdown table"<br>- "Write docstrings for utility functions" |
