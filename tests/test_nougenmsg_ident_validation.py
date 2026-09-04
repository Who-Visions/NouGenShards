"""Regression coverage for NouGenMsgBus.emit_node identifier validation.

`emit_node` interpolates `node` and `target` into a command string handed to a
remote login shell. It refuses anything outside `_SAFE_IDENT` rather than
escaping it, because those names are chosen by us -- shell syntax in one is a
bug or an attack, never a legitimate name.

That refusal had no tests. It was first written with `.match()`, and Python's
`$` matches before a trailing newline, so `"claude\\n"` passed validation and
truncated the remote command (the message then dispatched without `--stdin`).
Not a break-out -- the charset blocks every metacharacter, so nothing
attacker-chosen can follow the newline -- but validation code is where "close
enough" is the wrong standard. These tests pin the behaviour so the anchor
cannot regress silently.
"""

from __future__ import annotations

import json

import pytest

from nougen_shards.nougenmsg import AgentPinger, NouGenMsgBus

# A node name that is neither "local" nor the current node, so emit_node reaches
# the validation branch instead of short-circuiting to a local delivery.
REMOTE_NODE = "somewhere-else"


def _assert_refused(result, node, label):
    assert result == {node: result[node]}, result
    assert result[node].startswith(f"Error: refusing unsafe {label}"), result


@pytest.mark.parametrize(
    "target",
    [
        "claude\n",                     # the $-anchor hole: trailing newline
        "claude\n; touch /tmp/PWNED",   # newline plus a second command
        "a$(id)",                       # command substitution
        "a`id`",                        # backtick substitution
        'a"b',                          # quote break-out
        "a b",                          # argument split
        "",                             # empty
        "x" * 65,                       # over the 64-char bound
    ],
)
def test_unsafe_target_is_refused(target):
    result = NouGenMsgBus.emit_node(REMOTE_NODE, target, "hello")
    _assert_refused(result, REMOTE_NODE, "target")


@pytest.mark.parametrize("node", ["bad node", "node\n", "node;id", "n$(id)"])
def test_unsafe_node_is_refused(node):
    result = NouGenMsgBus.emit_node(node, "claude", "hello")
    _assert_refused(result, node, "node")


@pytest.mark.parametrize(
    "value", ["claude", "claude-cli", "blade1tb", "a.b:c_d-1", "x" * 64]
)
def test_legitimate_identifiers_pass_validation(value):
    """These must NOT be refused -- guarding against an over-tight anchor."""
    assert NouGenMsgBus._SAFE_IDENT.fullmatch(value), value


def test_remote_ollama_payload_is_stdin_not_remote_shell(monkeypatch):
    """Prompt and model must never be interpolated into the ssh command."""
    calls = []

    class Result:
        stdout = '{"response": "ok"}'
        stderr = ""

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr("nougen_shards.nougenmsg.subprocess.run", fake_run)
    prompt = 'hello " $(touch /tmp/PWNED) ; `id`'
    model = 'model"; rm -rf /'
    result = AgentPinger.ping_ollama(prompt, node=REMOTE_NODE, model=model)

    assert result["response"] == "ok"
    args, kwargs = calls[0]
    assert args[0] == [
        "ssh", "--", REMOTE_NODE,
        "curl -sS -X POST http://127.0.0.1:11434/api/generate --data-binary @-",
    ]
    assert json.loads(kwargs["input"]) == {
        "model": model, "prompt": prompt, "stream": False,
    }
    assert prompt not in args[0]
    assert model not in args[0]


def test_read_inbox_normalizes_legacy_source_to_sender(tmp_path, monkeypatch):
    """Ping receipts using the legacy field must not render as Unknown."""
    inbox = tmp_path / ".codex" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "ping.json").write_text(
        '{"source": "nougen-phoebus", "text": "hello"}', encoding="utf-8"
    )
    monkeypatch.setattr(
        "nougen_shards.nougenmsg.os.path.expanduser", lambda _path: str(inbox)
    )

    messages = NouGenMsgBus.read_inbox("codex")

    assert messages[0]["source"] == "nougen-phoebus"
    assert messages[0]["sender"] == "nougen-phoebus"
