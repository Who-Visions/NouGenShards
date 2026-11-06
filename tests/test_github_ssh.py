import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "github_ssh", Path(__file__).resolve().parents[1] / "tools" / "github_ssh.py")
gs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gs)


def test_transport_classifies_by_prefix():
    assert gs.transport("git@github.com:o/r.git", False) == "ssh"
    assert gs.transport("ssh://git@github.com/o/r.git", False) == "ssh"
    assert gs.transport("https://github.com/o/r.git", True) == "ssh via rewrite"
    assert gs.transport("https://github.com/o/r.git", False) == "https"
    # substring tricks must not pass as github
    assert gs.transport("https://evil.test/https://github.com/x", True) == "other"


def test_auth_reads_text_not_exit_code(monkeypatch):
    monkeypatch.setattr(gs, "run", lambda *a, **k: (1, "Hi X! You've successfully authenticated, but no shell."))
    assert gs.auth()[0] is True
    monkeypatch.setattr(gs, "run", lambda *a, **k: (255, "Permission denied (publickey)."))
    assert gs.auth()[0] is False


def test_probe_rejects_https_fallback(monkeypatch):
    ok_https = "trace: run_command: git-remote-https origin\nabc123def4567890\tHEAD"
    monkeypatch.setattr(gs, "run", lambda *a, **k: (0, ok_https))
    ok, msg = gs.probe()
    assert not ok and "https" in msg
    ok_ssh = "trace: run_command: unset GIT_DIR; ssh -o SendEnv=GIT_PROTOCOL git@github.com 'git-upload-pack'\nabc123def4567890\tHEAD"
    monkeypatch.setattr(gs, "run", lambda *a, **k: (0, ok_ssh))
    assert gs.probe() == (True, "abc123def456 via ssh")


def test_setup_fails_when_config_write_fails(monkeypatch):
    monkeypatch.setattr(gs, "keys", lambda: ["id_ed25519.pub"])
    monkeypatch.setattr(gs, "rewrite_on", lambda: False)
    monkeypatch.setattr(gs, "run", lambda *a, **k: (255, "could not lock config file"))
    assert gs.setup() == 1


def test_undo_targets_only_our_value(monkeypatch):
    seen = {}
    monkeypatch.setattr(gs, "run", lambda *a, **k: (seen.setdefault("cmd", a), (0, ""))[1])
    gs.undo()
    assert seen["cmd"][-1] == "^https://github\.com/$"
