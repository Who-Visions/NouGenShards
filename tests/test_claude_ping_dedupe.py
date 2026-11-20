"""One message, one delivery: the direct route and the ssh hop route must not
both land in every live Claude session."""
from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import AgentPinger, _ping_seen_before


def _isolate(monkeypatch, tmp_path, ttl="600"):
    inbox = tmp_path / "claude_inbox"
    monkeypatch.setattr(AgentPinger, "_claude_inbox_dir", staticmethod(lambda: str(inbox)))
    monkeypatch.setenv("NOUGEN_PING_DEDUPE_S", ttl)


def test_second_identical_ping_is_a_duplicate(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert _ping_seen_before("hello fleet", None) is False
    assert _ping_seen_before("hello fleet", None) is True
    assert _ping_seen_before("different text", None) is False


def test_targeted_and_broadcast_are_separate_audiences(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert _ping_seen_before("same", None) is False
    assert _ping_seen_before("same", "session-a") is False
    assert _ping_seen_before("same", "session-a") is True


def test_ttl_zero_disables(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, ttl="0")
    assert _ping_seen_before("x", None) is False
    assert _ping_seen_before("x", None) is False


def test_expired_entries_deliver_again(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, ttl="60")
    clock = [1000.0]
    monkeypatch.setattr(nougenmsg.time, "time", lambda: clock[0])
    assert _ping_seen_before("x", None) is False
    clock[0] += 61
    assert _ping_seen_before("x", None) is False


def test_ping_claude_skips_duplicate_before_touching_pipes(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: False)
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(tmp_path / "none.json")))
    first = AgentPinger.ping_claude("roll call")
    assert not first.get("duplicate")
    second = AgentPinger.ping_claude("roll call")
    assert second["duplicate"] is True and second["delivered"] == []
    assert second["inbox_file"] is None


def test_hop_receiver_does_not_restyle():
    src = (__import__("pathlib").Path(__file__).resolve().parents[1] / "tools" / "nougenmsg.py").read_text(encoding="utf-8")
    assert "if not raw_text and not from_hop:" in src
