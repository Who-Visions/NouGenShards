"""One message, one delivery: the direct route and the ssh hop route must not
both land in every live Claude session, and two deliberate messages must not
collapse into one."""
import threading

from nougen_shards import nougenmsg
from nougen_shards.nougenmsg import (AgentPinger, _ping_key, _ping_mark_delivered,
                                     _ping_seen_before)


def _isolate(monkeypatch, tmp_path, ttl="600"):
    inbox = tmp_path / "claude_inbox"
    monkeypatch.setattr(AgentPinger, "_claude_inbox_dir", staticmethod(lambda: str(inbox)))
    monkeypatch.setenv("NOUGEN_PING_DEDUPE_S", ttl)


def _deliver(prompt, session=None, origin=None):
    seen = _ping_seen_before(prompt, session, origin)
    if not seen:
        _ping_mark_delivered(prompt, session, origin)
    return seen


def test_same_message_twice_is_a_duplicate(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert _deliver("hello fleet") is False
    assert _deliver("hello fleet") is True
    assert _deliver("different text") is False


def test_check_alone_never_records(monkeypatch, tmp_path):
    """A failed delivery must not suppress the retry."""
    _isolate(monkeypatch, tmp_path)
    assert _ping_seen_before("x", None) is False
    assert _ping_seen_before("x", None) is False


def test_msg_id_keys_identical_text_as_different_messages(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert _deliver("ping\n\n[msg m-aaaaaaaaaaaa1111]") is False
    assert _deliver("ping\n\n[msg m-bbbbbbbbbbbb2222]") is False
    # the same msg_id over a second route, even restyled, is the same message
    assert _deliver("🛰️ banner\nping\n\n[msg m-aaaaaaaaaaaa1111]") is True


def test_origin_message_id_wins_over_text(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert _ping_key("a", None, {"message_id": "m-1"}) == _ping_key("b", None, {"message_id": "m-1"})
    assert _ping_key("a", None) != _ping_key("b", None)


def test_targeted_and_broadcast_are_separate_audiences(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert _deliver("same") is False
    assert _deliver("same", "session-a") is False
    assert _deliver("same", "session-a") is True


def test_ttl_zero_disables(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, ttl="0")
    assert _deliver("x") is False
    assert _deliver("x") is False


def test_expired_entries_deliver_again(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, ttl="60")
    clock = [1000.0]
    monkeypatch.setattr(nougenmsg.time, "time", lambda: clock[0])
    assert _deliver("x") is False
    clock[0] += 61
    assert _deliver("x") is False


def test_concurrent_marks_keep_every_key(monkeypatch, tmp_path):
    """Serialized writes: 20 parallel marks must all survive."""
    _isolate(monkeypatch, tmp_path)
    keys = [f"msg {i}" for i in range(20)]
    threads = [threading.Thread(target=_ping_mark_delivered, args=(k, None)) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(_ping_seen_before(k, None) for k in keys)


def test_stale_lock_is_broken(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ledger = nougenmsg._PingLedger()
    open(ledger.lock, "w").close()
    import os
    os.utime(ledger.lock, (0, 0))
    _ping_mark_delivered("after stale lock", None)
    assert _ping_seen_before("after stale lock", None) is True


def test_ping_claude_records_only_after_delivery(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: False)
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(tmp_path / "none.json")))
    first = AgentPinger.ping_claude("roll call")
    assert not first.get("duplicate") and first["inbox_file"]
    second = AgentPinger.ping_claude("roll call")
    assert second["duplicate"] is True and second["delivered"] == []


def test_ping_claude_failed_write_does_not_record(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(nougenmsg, "_tenant_scope", lambda: False)
    monkeypatch.setattr(AgentPinger, "_cc_registry_path", staticmethod(lambda: str(tmp_path / "none.json")))
    real_open = open

    def failing_open(path, *a, **k):
        if "ping_" in str(path) and "claude_inbox" in str(path):
            raise OSError("disk full")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", failing_open)
    res = AgentPinger.ping_claude("lost message")
    monkeypatch.setattr("builtins.open", real_open)
    assert res["inbox_file"] is None and res["delivered"] == []
    assert _ping_seen_before("lost message", None) is False


def test_hop_receiver_does_not_restyle():
    src = (__import__("pathlib").Path(__file__).resolve().parents[1] / "tools" / "nougenmsg.py").read_text(encoding="utf-8")
    assert "if not raw_text and not from_hop:" in src
