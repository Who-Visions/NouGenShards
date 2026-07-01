"""
Unit tests for the Brain Scan / Memory Recon engine.
"""
import pytest
from pathlib import Path
from nougen_shards.brain_scan.classifiers import classify_file, detect_tool
from nougen_shards.brain_scan.redaction import redact_content
from nougen_shards.brain_scan.parsers import parse_universal
from nougen_shards.brain_scan.scanner import _is_safe_dir
from nougen_shards.brain_scan.importer import run_import
import nougen_shards.brain_scan.scanner as scanner

@pytest.fixture(autouse=True)
def mock_global_roots(monkeypatch, tmp_path):
    monkeypatch.setattr(scanner, "GLOBAL_ROOTS", [tmp_path / "global_dummy"])

def test_detect_tool():
    assert detect_tool(Path("/home/user/.claude/history.jsonl")) == "claude"
    assert detect_tool(Path("/home/user/.cursor/workspace/state.json")) == "cursor"
    assert detect_tool(Path("/home/user/.gemini/settings.json")) == "gemini"
    assert detect_tool(Path("/home/user/my_project/AGENTS.md")) == "unknown"

def test_classify_file():
    assert classify_file(Path("conversation_123.json")) == "high"
    assert classify_file(Path("settings.json")) == "medium"
    assert classify_file(Path("cache_blob.bin")) == "low"
    assert classify_file(Path("node_modules/bla/package.json")) == "low"
    assert classify_file(Path("unknown_file.md")) == "medium"
    assert classify_file(Path("unknown_file.xyz")) == "low"

def test_redact_content():
    content = 'Here is my key: "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"\nAnd an openai key: sk-abcdefghijklmnopqrstuvwxyz1234567890\nAlso a fake token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'
    redacted = redact_content(content)
    assert "sk-ant-" not in redacted
    assert "<REDACTED_ANTHROPIC_KEY>" in redacted
    assert "<REDACTED_OPENAI_KEY>" in redacted
    assert "<REDACTED_JWT>" in redacted
    assert "Here is my key:" in redacted

def test_redact_db_url_without_path():
    # Regression: a DB URL with no trailing /db must still redact the password.
    content = "conn = postgres://admin:s3cr3tP@ss@db.internal:5432"
    redacted = redact_content(content)
    assert "s3cr3tP" not in redacted
    assert "<REDACTED_DB_URL>" in redacted

def test_redact_sk_proj_key():
    # Regression: newer sk-proj-/sk-svcacct- keys contain - and _.
    content = "OPENAI=sk-proj-abc_DEF-ghi0123456789jklmnopqrstuv"
    redacted = redact_content(content)
    assert "sk-proj-abc" not in redacted
    assert "<REDACTED_OPENAI_KEY>" in redacted

def test_is_safe_dir():
    assert _is_safe_dir(Path("/home/user/.claude")) is True
    assert _is_safe_dir(Path("/home/user/.ssh")) is False
    assert _is_safe_dir(Path("/home/user/project/node_modules/bla")) is False
    assert _is_safe_dir(Path("/home/user/.config/gcloud")) is False
    assert _is_safe_dir(Path("/home/user/.aws")) is False

def test_parse_json(tmp_path):
    f = tmp_path / "chat.json"
    f.write_text('{"title": "Test Chat", "messages": [{"role": "user", "content": "hi"}]}')
    records = parse_universal(f, "claude", False)
    assert len(records) == 1
    assert records[0].title == "Test Chat"
    assert "messages" in records[0].content

def test_parse_jsonl(tmp_path):
    f = tmp_path / "history.jsonl"
    f.write_text('{"role": "user", "content": "hello"}\n{"role": "assistant", "content": "hi"}')
    records = parse_universal(f, "claude", False)
    assert len(records) == 2
    assert records[0].role == "user"
    assert records[1].role == "assistant"

def test_parse_markdown(tmp_path):
    f = tmp_path / "AGENTS.md"
    f.write_text("# Agent Rules\nDo this.")
    records = parse_universal(f, "unknown", True)
    assert len(records) == 1
    assert records[0].source_kind == "markdown_document"
    assert records[0].title == "AGENTS.md"

def test_dry_run_import(tmp_path):
    # Setup a dummy project dir
    proj = tmp_path / "myproj"
    proj.mkdir()
    (proj / "CLAUDE.md").write_text("Rule 1")
    claude_dir = proj / ".claude"
    claude_dir.mkdir()
    (claude_dir / "conversations.jsonl").write_text('{"role": "user", "content": "hi"}')
    
    result = run_import(project_path=str(proj), confirm=False)
    # Both files should be picked up (CLAUDE.md is PROJECT_FILES, .claude is PROJECT_ROOT_NAMES)
    assert result.files_scanned == 2
    # Estimation should be > 0
    assert result.records_parsed > 0
    assert result.shards_created == 0 # Dry run means nothing actually hits DB

@pytest.fixture(autouse=True)
def mock_db_capture(monkeypatch):
    """Prevent tests from actually writing to the real shards DB during the confirm test."""
    monkeypatch.setattr("nougen_shards.core.capture", lambda *args, **kwargs: True)

def test_confirm_import(tmp_path):
    proj = tmp_path / "myproj2"
    proj.mkdir()
    (proj / "GEMINI.md").write_text("Rule 2")
    
    result = run_import(project_path=str(proj), confirm=True)
    assert result.files_scanned == 1
    assert result.records_parsed == 1
    assert result.shards_created == 1
