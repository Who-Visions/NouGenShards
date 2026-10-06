"""Fleet MCP worker must never present model text or canned strings as execution/deployment results.

2026-10-04 audit: execute_sandboxed_code fell back to dav1d_exec with prompt=<code>; on the node a
prompt routes to the dav1d chat persona (ollama), so a model's guess (including a fabricated
SHA-256) came back as if the code had run. Other handlers returned hardcoded success strings.
"""
import re
from pathlib import Path

WORKER = Path(__file__).resolve().parents[1] / "tools" / "nougen-fleet-mcp-patched.js"
SRC = WORKER.read_text(encoding="utf-8")


def _handler(name: str) -> str:
    start = SRC.index(f"  async {name}(args, env) {{")
    nxt = re.compile(r"\n  async \w+\(args, env\) \{").search(SRC, start + 10)
    return SRC[start:nxt.start() if nxt else len(SRC)]


def test_execution_handlers_have_no_model_fallback():
    for name in ("execute_sandboxed_code", "batch_execute_sandboxed"):
        body = _handler(name)
        assert "dav1d_exec" not in body, name
        assert "ask_dav1d" not in body and "ask_iris" not in body, name
        assert "toolError(" in body, name


def test_no_canned_success_strings():
    banned = [
        "Batch sandboxed commands processed.",
        "File analysis completed for:",
        "Ollama local GPU inference simulated response.",
        "No specialized skill override needed",
        "[Cloudflare Edge AI]: ${args.prompt}",
    ]
    for phrase in banned:
        assert phrase not in SRC, phrase


def test_deploy_tool_does_not_claim_deployed():
    body = _handler("cf_deploy_worker")
    assert '"deployed"' not in body
    assert "toolError(" in body


def test_static_worker_list_is_labeled():
    assert "static_config_not_live" in _handler("cf_list_workers")
