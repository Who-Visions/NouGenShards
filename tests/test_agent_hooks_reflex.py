"""Shard + relay as a reflex, and context mode as a gate, enforced by the host's
lifecycle rather than by a rule the agent has to remember."""
import json
import subprocess
import sys

import pytest

from nougen_shards import agent_hooks as ah

SID = "sess-reflex-1"


@pytest.fixture
def env(tmp_path, monkeypatch):
    from nougen_shards import handoff
    monkeypatch.setattr(handoff, "HANDOFF_DIR", tmp_path / "handoffs")
    monkeypatch.setattr(handoff, "_log_context_event", lambda *a, **k: None)
    monkeypatch.setattr(handoff, "_fire_triggers", lambda *a, **k: [])
    for name in ("NOUGEN_REFLEX", "NOUGEN_CTX_GATE", "NOUGEN_CTX_READ_MAX_KB"):
        monkeypatch.delenv(name, raising=False)
    work = tmp_path / "proj"
    work.mkdir()
    monkeypatch.chdir(work)  # not a git repo: git helpers return ""
    return tmp_path


def _tool(name, **tool_input):
    return ah.run("post-tool", json.dumps({"session_id": SID, "tool_name": name, "tool_input": tool_input}))


def _stop(**extra):
    return json.loads(ah.run("stop", json.dumps({"session_id": SID, **extra})))


def _pre(name, **tool_input):
    return json.loads(ah.run("pre-tool", json.dumps({"session_id": SID, "tool_name": name, "tool_input": tool_input})))


def _denied(out):
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


# ------------------------------------------------------------------ reflex

def test_a_session_that_changed_nothing_stops_freely(env):
    _tool("Bash", command="git status --short")
    _tool("mcp__nougen__shards_recall", query="x")
    assert _stop() == {}


def test_work_without_shard_or_leg_sends_the_agent_back_once(env):
    _tool("Edit", file_path="a.py")
    out = _stop()
    assert out["decision"] == "block"
    assert "shards_capture" in out["reason"] and "relay_create" in out["reason"]
    assert "without asking the operator" in out["reason"]
    # Asked once for this stretch of work: a second stop is not blocked again.
    assert _stop() == {}


def test_stop_hook_active_never_blocks(env):
    """The host is already continuing because of a Stop hook; blocking again loops."""
    _tool("Write", file_path="a.py")
    assert _stop(stop_hook_active=True) == {}


def test_only_the_missing_half_is_asked_for(env):
    _tool("Edit", file_path="a.py")
    _tool("mcp__564cae0a__shards_capture", title="t")
    out = _stop()
    assert out["decision"] == "block"
    assert "relay_create" in out["reason"] and "shards_capture" not in out["reason"]


def test_shard_and_leg_close_the_stretch_and_new_work_reopens_it(env):
    _tool("Edit", file_path="a.py")
    _tool("mcp__nougen-shards__capture_experience", title="t")
    _tool("mcp__564cae0a__relay_create", goal="g")
    assert ah.reflex_state(SID) == {"work": 0, "done": 1}
    assert _stop() == {}
    _tool("Edit", file_path="b.py")
    assert _stop()["decision"] == "block"


def test_more_work_after_a_declined_ask_is_asked_again(env):
    _tool("Edit", file_path="a.py")
    assert _stop()["decision"] == "block"
    assert _stop() == {}
    _tool("Edit", file_path="b.py")
    assert _stop()["decision"] == "block"


@pytest.mark.parametrize("command,key", [
    ('nougen add "title" "body"', "shard"),
    ('.venv/Scripts/python.exe -m nougen_shards.cli capture -t x', "shard"),
    ('python -m nougen_relay.cli create -g "goal" -M body.md', "relay"),
    ('python tools/git_handoff.py ack 20261109T000000Z__x__y', "relay"),
])
def test_cli_forms_count_as_the_reflex(env, command, key):
    _tool("Edit", file_path="a.py")
    _tool("PowerShell", command=command)
    assert ah.reflex_state(SID).get(key) is True


def test_a_commit_counts_as_work_and_a_grep_for_the_word_does_not_fake_a_shard(env):
    _tool("Bash", command='git commit -m "fix: thing"')
    assert ah.reflex_state(SID)["work"] == 1
    _tool("Bash", command="grep -c shards_capture README.md")
    assert "shard" not in ah.reflex_state(SID)


def test_nudge_mode_does_not_block_and_off_mode_is_silent(env, monkeypatch):
    _tool("Edit", file_path="a.py")
    monkeypatch.setenv("NOUGEN_REFLEX", "off")
    assert _stop() == {}
    monkeypatch.setenv("NOUGEN_REFLEX", "nudge")
    out = _stop()
    assert "decision" not in out
    assert "NouGen reflex" in out["hookSpecificOutput"]["additionalContext"]


def test_simultaneous_shard_and_leg_are_both_recorded(env):
    """Codex P2 on PR 994: two PostToolUse processes finishing together must not
    overwrite each other, or Stop asks for a record that already exists."""
    import threading
    _tool("Edit", file_path="a.py")
    real_read = ah.reflex_state
    gate = threading.Barrier(2, timeout=5)

    def slow_read(sid):
        state = real_read(sid)
        try:
            gate.wait(timeout=0.3)  # without the lock both readers meet here holding the old state
        except threading.BrokenBarrierError:
            pass
        return state

    ah.reflex_state = slow_read
    try:
        threads = [threading.Thread(target=_tool, args=(name,), kwargs={"x": 1})
                   for name in ("mcp__n__shards_capture", "mcp__n__relay_create")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        ah.reflex_state = real_read
    assert ah.reflex_state(SID) == {"work": 0, "done": 1}
    assert _stop() == {}
    assert not ah._reflex_path(SID).with_suffix(".lock").exists()


def test_a_stale_lock_from_a_dead_hook_is_taken_over(env):
    import os
    import time
    lock = ah._reflex_path(SID).with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("", encoding="utf-8")
    old = time.time() - 60
    os.utime(lock, (old, old))
    _tool("Edit", file_path="a.py")
    assert ah.reflex_state(SID)["work"] == 1 and not lock.exists()


def test_session_end_clears_the_reflex_state(env):
    _tool("Edit", file_path="a.py")
    assert ah._reflex_path(SID).exists()
    ah.run("session-end", json.dumps({"session_id": SID}))
    assert not ah._reflex_path(SID).exists()


# ------------------------------------------------------------ context mode

@pytest.mark.parametrize("command", [
    "curl https://example.com/api/list",
    "git log",
    "git log --oneline",
    "git diff",
    "git show HEAD",
    "grep -rn TODO src",
    "rg FAST_LOCAL",
    "Get-ChildItem C:\\repo -Recurse",
    "find . -name '*.py'",
    "python -m pytest tests -q",
    "cd repo && git diff",
    "python -m pytest tests | tee /tmp/test.log",  # tee copies to stdout too
    "git diff | Tee-Object diff.log",
])
def test_unbounded_commands_are_refused_with_the_sandbox_route(env, command):
    out = _pre("Bash", command=command)
    assert _denied(out), command
    assert "ctx_execute" in out["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("command", [
    "git status --short",
    "git log -5 --oneline",
    "git log --oneline -n 20",
    "git log | head -20",
    "git diff --stat",
    "git diff --name-only origin/main",
    "git show --stat HEAD",
    "grep -rn TODO src | head -30",
    "grep -rlc TODO src",
    "rg -l FAST_LOCAL",
    "Get-ChildItem C:\\repo -Recurse | Select-Object -First 20",
    "python -m pytest tests -q 2>&1 | Select-Object -Last 25",
    "python -m pytest tests -q > out.txt",
    "curl -s http://127.0.0.1:4444/health",
    "curl -L -o model.bin https://example.com/model.bin",
    'git commit -m "fix: stop curl and git log from flooding context"',
    "ls",
    "git push -u origin feat/x",
])
def test_bounded_or_small_commands_pass(env, command):
    assert _pre("PowerShell", command=command) == {}, command


def test_big_file_dump_is_refused_and_a_small_one_passes(env, monkeypatch):
    monkeypatch.setenv("NOUGEN_CTX_READ_MAX_KB", "1")
    big = env / "big.log"
    big.write_text("x" * 5000, encoding="utf-8")
    small = env / "small.txt"
    small.write_text("hello", encoding="utf-8")
    assert _denied(_pre("Bash", command=f'cat "{big}"'))
    assert _pre("Bash", command=f'cat "{small}"') == {}
    assert _pre("Bash", command=f'Get-Content "{big}" -Tail 20') == {}
    assert _pre("Bash", command="cat does-not-exist.txt") == {}


def test_read_of_a_big_file_needs_a_window(env, monkeypatch):
    monkeypatch.setenv("NOUGEN_CTX_READ_MAX_KB", "1")
    big = env / "big.py"
    big.write_text("x = 1\n" * 2000, encoding="utf-8")
    out = _pre("Read", file_path=str(big))
    assert _denied(out) and "ctx_execute_file" in out["hookSpecificOutput"]["permissionDecisionReason"]
    assert _pre("Read", file_path=str(big), limit=80) == {}
    assert _pre("Read", file_path=str(big), offset=100) == {}
    img = env / "shot.png"
    img.write_bytes(b"\x89PNG" + b"0" * 5000)
    assert _pre("Read", file_path=str(img)) == {}


def test_ctx_gate_warn_and_off(env, monkeypatch):
    monkeypatch.setenv("NOUGEN_CTX_GATE", "warn")
    out = _pre("Bash", command="git log")
    assert not _denied(out) and "context mode" in out["hookSpecificOutput"]["additionalContext"]
    monkeypatch.setenv("NOUGEN_CTX_GATE", "off")
    assert _pre("Bash", command="git log") == {}


def test_other_tools_and_garbage_input_are_ignored(env):
    assert _pre("Grep", pattern="x") == {}
    assert json.loads(ah.run("pre-tool", "not json")) == {}
    assert json.loads(ah.run("post-tool", json.dumps({"tool_name": "Bash", "tool_input": "oops"}))) == {}
    assert json.loads(ah.run("pre-tool", json.dumps({"tool_name": "Read", "tool_input": None}))) == {}


# --------------------------------------------------------------- installer

def test_install_wires_the_tool_events_with_matchers_and_the_fast_entry(env):
    settings = env / "settings.json"
    foreign = {"matcher": "Bash", "hooks": [{"type": "command", "command": "python guard.py"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [foreign]}}), encoding="utf-8")
    ah.install(settings, python="py")
    hooks = json.loads(settings.read_text(encoding="utf-8"))["hooks"]
    assert hooks["PreToolUse"][0] == foreign
    pre, post = hooks["PreToolUse"][1], hooks["PostToolUse"][0]
    assert pre["matcher"] == ah.TOOL_MATCHERS["pre-tool"]
    assert pre["hooks"][0]["command"] == '"py" -m nougen_shards.agent_hooks run pre-tool'
    assert post["hooks"][0]["command"] == '"py" -m nougen_shards.agent_hooks run post-tool'
    assert "nougen_shards.cli hook run stop" in hooks["Stop"][0]["hooks"][0]["command"]
    assert ah.status(settings)["missing"] == []
    assert ah.install(settings, python="py")["changed"] is False  # idempotent
    ah.install(settings, python="py", uninstall=True)
    assert json.loads(settings.read_text(encoding="utf-8")) == {"hooks": {"PreToolUse": [foreign]}}


def test_module_entry_point_speaks_the_hook_contract(env):
    import os
    from pathlib import Path
    src = str(Path(ah.__file__).resolve().parents[1])
    sub_env = {**os.environ, "PYTHONPATH": src, "NOUGEN_HANDOFF_DIR": str(env / "handoffs")}
    evt = json.dumps({"session_id": SID, "tool_name": "Bash", "tool_input": {"command": "git log"}})
    proc = subprocess.run([sys.executable, "-m", "nougen_shards.agent_hooks", "run", "pre-tool"],
                          input=evt.encode("utf-8"), capture_output=True, timeout=60, check=False, env=sub_env)
    assert proc.returncode == 0, proc.stderr
    assert _denied(json.loads(proc.stdout.decode("utf-8")))
    bad = subprocess.run([sys.executable, "-m", "nougen_shards.agent_hooks", "run", "nope"],
                         input=b"{}", capture_output=True, timeout=60, check=False, env=sub_env)
    assert bad.returncode == 2
