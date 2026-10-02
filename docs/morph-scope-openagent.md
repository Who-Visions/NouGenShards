# OpenAgent / Morph Scope: Bounded Session Tool Activity

## Overview
As agentic sessions increase in reasoning rounds and tool invocation density, raw un-redacted tool outputs and unbounded histories introduce context bloat, token exhaustion, and accidental token credential leakages.

`SessionToolActivityTracker` (`src/nougen_shards/tool_activity.py`) provides:
1. **Bounded Ring Buffer**: Caps session activity history to `max_records` (default 50), dropping oldest invocations deterministically while preserving invocation counts.
2. **Strict Secret Redaction**: Intercepts arguments, outputs, and error strings against Google API keys (`AIza...`), GitHub tokens (`ghp_...`), OpenAI keys (`sk-...`), and HTTP Bearer tokens before persistence or HUD projection.
3. **Low-Token HUD Context Projection**: Renders a compact, human-clear summary string suitable for primary context reinjection or telemetry pulse logging.
4. **Native Kaedra Integration**: Directly wired into `run_tool_loop` in `src/nougen_shards/kaedra_tools.py`.
