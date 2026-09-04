"""`NouGenMsgBus.emit_node` node/target name validation.

`emit_node` builds an ssh command line for a remote node. The message body was
moved to stdin precisely so no caller-controlled text reaches argv -- but the
*node* and *target* names still do, so `_SAFE_IDENT` is the only thing standing
between a name and the remote login shell. Its job is to refuse, not to escape:
`shlex.quote` would fix the POSIX lane and silently break the nodes that ssh
into cmd.exe.

The defect these cover: `_SAFE_IDENT` was `re.compile(r"^...$")` used with
`.match()`, and `$` matches immediately before a trailing newline as well as at
end-of-string -- so `"node-a\n"` was accepted as a node name. Closed on node-a and
on node-b on 2026-09-04; the node-c copy was still on `.match()` afterwards,
because each machine carries its own copy and all three lanes assumed the others
were covered. Hence this file: the guarantee is now pinned by a test rather than
by three separate memories of having fixed it.
"""
import pytest

from nougen_shards.nougenmsg import NouGenMsgBus

ACCEPTED = ["node-a", "node-b", "node-c", "n0de", "a", "node.1", "node:1",
            "node-1", "node_1", "A" * 64]

REJECTED = [
    "node-a\n",            # the regression: `$` matches before a trailing LF
    "node-a\n\n",
    "node-a\r\n",
    "node-a\r",
    "node-a\nrm -rf /",
    "node-a; rm -rf /",
    "node-a && whoami",
    "node-a`whoami`",
    "$(whoami)",
    "node-a | tee x",
    'node-a"',
    "node a",   # space
    "",
    None,
    "A" * 65,             # length bound
    "../../etc/passwd",
]


@pytest.mark.parametrize("name", ACCEPTED)
def test_ordinary_node_names_are_accepted(name):
    assert NouGenMsgBus._SAFE_IDENT.fullmatch(name)


@pytest.mark.parametrize("name", REJECTED)
def test_unsafe_node_names_are_rejected(name):
    assert not NouGenMsgBus._SAFE_IDENT.fullmatch(str(name or ""))


def test_trailing_newline_is_the_documented_regression():
    """Named on its own so a revert to `.match()` says why it broke."""
    assert NouGenMsgBus._SAFE_IDENT.fullmatch("node-a")
    assert not NouGenMsgBus._SAFE_IDENT.fullmatch("node-a\n")


def test_pattern_carries_no_anchors():
    """`fullmatch` anchors on its own. A `^...$` left in the pattern is an
    invitation for the next reader to switch back to `.match()`, which is
    exactly the hole that was closed -- so the anchors are gone deliberately."""
    assert "$" not in NouGenMsgBus._SAFE_IDENT.pattern
    assert not NouGenMsgBus._SAFE_IDENT.pattern.startswith("^")


@pytest.mark.parametrize("bad", ["node-a\n", "node-a; rm -rf /", "$(whoami)"])
def test_emit_node_refuses_rather_than_escaping(bad, monkeypatch):
    """No ssh is attempted for a name that fails validation. Asserted by making
    any subprocess call an error -- a refusal that still shelled out would be a
    silent pass here."""
    import nougen_shards.nougenmsg as mod

    def explode(*a, **k):
        raise AssertionError("emit_node shelled out with an unsafe name")

    monkeypatch.setattr(mod.subprocess, "run", explode)
    result = mod.NouGenMsgBus.emit_node(bad, "claude", "body")
    assert "refusing unsafe node" in result[bad]


def test_emit_node_refuses_an_unsafe_target_too(monkeypatch):
    """Both names reach the command line, so both are gated."""
    import nougen_shards.nougenmsg as mod

    def explode(*a, **k):
        raise AssertionError("emit_node shelled out with an unsafe target")

    monkeypatch.setattr(mod.subprocess, "run", explode)
    result = mod.NouGenMsgBus.emit_node("node-a", "claude\n", "body")
    assert "refusing unsafe target" in result["node-a"]


def test_body_never_reaches_argv(monkeypatch):
    """The stdin design is the other half of the guarantee: a body full of shell
    metacharacters must travel as input, never inside the command string."""
    import nougen_shards.nougenmsg as mod

    body = 'ordinary prose (with parens) and $(whoami) and `backticks` and "quotes"'
    seen = {}

    class Result:
        stdout, stderr = "ok", ""

    def capture(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["input"] = kwargs.get("input")
        return Result()

    monkeypatch.setattr(mod.subprocess, "run", capture)
    mod.NouGenMsgBus.emit_node("node-a", "claude", body)

    assert seen["input"] == body
    assert not any(body in str(part) for part in seen["cmd"])
    assert "$(whoami)" not in " ".join(str(p) for p in seen["cmd"])
