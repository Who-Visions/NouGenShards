"""The quota wake mirror must land where the daemon actually looks.

`RELAY_WAKE_DIR` was hard-coded to ``~/Outpost/NouGenRelay/.relay/wake``, which
does not exist on phoebus, and the write was guarded by ``is_dir()`` inside a
bare ``except Exception: pass``. So every quota wake ticket was dropped twice
over in silence, while ``wake_daemon`` watched ``~/.nougen/relay/.relay/wake``.

The writer wrote to a dead path and the reader watched a live one. Nothing
failed loudly enough to notice.
"""

import json

import pytest

from nougen_shards.wake import quota
from nougen_shards.wake.quota import NouGenWakeEngine, relay_wake_dir


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in quota.RELAY_DIR_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ------------------------------------------------------------ path resolution
def test_default_is_the_canonical_registry_not_outpost():
    d = relay_wake_dir()
    assert d == quota.CANONICAL_RELAY_DIR / ".relay" / "wake"
    assert "Outpost" not in str(d), "the dead Outpost path is back"


def test_the_daemon_watches_exactly_this_directory():
    """Pin the two together. If wake_daemon's watch list moves, this fails."""
    from nougen_shards import wake_daemon
    watched = {str(p) for p in wake_daemon.WATCH_DIRS}
    assert str(relay_wake_dir()) in watched, (
        f"{relay_wake_dir()} is not in the daemon's watch list {watched}"
    )


def test_env_override_is_honoured(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "reg"))
    assert relay_wake_dir() == tmp_path / "reg" / ".relay" / "wake"


def test_handoffs_form_of_the_env_var_resolves_to_the_registry_root(monkeypatch, tmp_path):
    """relay_guardrail sets NOUGEN_RELAY_DIR to the .handoffs dir, not the root."""
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "reg" / ".handoffs"))
    assert relay_wake_dir() == tmp_path / "reg" / ".relay" / "wake"


def test_first_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "a"))
    monkeypatch.setenv("FLEET_RELAY_DIR", str(tmp_path / "b"))
    assert relay_wake_dir() == tmp_path / "a" / ".relay" / "wake"


# ------------------------------------------------------------- mirror writing
def _engine(tmp_path):
    return NouGenWakeEngine(ticket_dir=tmp_path / "tickets")


def test_mirror_is_written_even_when_the_directory_does_not_exist(monkeypatch, tmp_path):
    """The old code skipped on a missing directory. That is the whole bug."""
    reg = tmp_path / "reg"
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(reg))
    assert not reg.exists()

    t = _engine(tmp_path).create_ticket(raw_error="Resets in 1h30m", target_agent="codex")

    mirrored = reg / ".relay" / "wake" / f"{t['ticket_id']}.wake.json"
    assert mirrored.is_file(), "the wake daemon will never see this ticket"
    assert t["relay_mirror"]["written"] is True
    assert t["relay_mirror"]["error"] is None


def test_the_mirrored_ticket_matches_the_local_one(monkeypatch, tmp_path):
    reg = tmp_path / "reg"
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(reg))
    t = _engine(tmp_path).create_ticket(raw_error="Resets in 15m", target_agent="codex")

    mirrored = json.loads(
        (reg / ".relay" / "wake" / f"{t['ticket_id']}.wake.json").read_text())
    assert mirrored["ticket_id"] == t["ticket_id"]
    assert mirrored["wake_at_epoch"] == t["wake_at_epoch"]


def test_a_failed_mirror_is_reported_not_swallowed(monkeypatch, tmp_path, capsys):
    """The old bare `except Exception: pass` hid real write failures too."""
    reg = tmp_path / "reg"
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(reg))

    def boom(*_a, **_k):
        raise OSError("read-only file system")

    eng = _engine(tmp_path)          # construct first: its own mkdir must succeed
    monkeypatch.setattr(quota.Path, "mkdir", boom)
    t = eng.create_ticket(raw_error="Resets in 5m", target_agent="codex")

    assert t["relay_mirror"]["written"] is False
    assert "read-only file system" in t["relay_mirror"]["error"]
    assert "relay mirror failed" in capsys.readouterr().err


def test_a_failed_mirror_still_leaves_a_durable_local_ticket(monkeypatch, tmp_path):
    """Mirror failure must not cost the ticket -- it is only a doorbell."""
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "reg"))
    eng = _engine(tmp_path)          # construct first
    monkeypatch.setattr(quota.Path, "mkdir",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("nope")))

    t = eng.create_ticket(raw_error="Resets in 5m", target_agent="codex")
    local = tmp_path / "tickets" / f"{t['ticket_id']}.json"
    assert local.is_file()
    assert json.loads(local.read_text())["relay_mirror"]["written"] is False


def test_the_outcome_is_persisted_to_disk_not_just_returned(monkeypatch, tmp_path):
    """An outcome only in the return value is invisible to anything that reads
    the ticket file later."""
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "reg"))
    t = _engine(tmp_path).create_ticket(raw_error="Resets in 2h", target_agent="codex")
    on_disk = json.loads((tmp_path / "tickets" / f"{t['ticket_id']}.json").read_text())
    assert on_disk["relay_mirror"]["written"] is True
