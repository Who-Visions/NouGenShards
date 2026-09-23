"""The daemon must watch wherever the quota writer resolves the wake dir.

#495 fixed the writer to honour NOUGEN_RELAY_DIR; the daemon's list stayed
hard-coded, so on whoart (env var set to the Outpost relay clone) the split simply
changed direction: 196 tickets sat in a directory the daemon never read.
"""
from pathlib import Path

from nougen_shards import wake_daemon
from nougen_shards.wake import quota


def test_watch_dirs_follow_the_writer(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "registry"))
    assert quota.relay_wake_dir() in wake_daemon.watch_dirs()


def test_watch_dirs_accept_handoffs_form_and_keep_canonical(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "registry" / ".handoffs"))
    dirs = wake_daemon.watch_dirs()
    assert tmp_path / "registry" / ".relay" / "wake" in dirs
    assert quota.CANONICAL_RELAY_DIR / ".relay" / "wake" in dirs


def test_watch_dirs_deduplicate_when_env_is_canonical(monkeypatch):
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(quota.CANONICAL_RELAY_DIR))
    dirs = [str(d) for d in wake_daemon.watch_dirs()]
    assert len(dirs) == len(set(dirs))


def test_snapshot_reads_tickets_from_the_resolved_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_RELAY_DIR", str(tmp_path / "registry"))
    wake = Path(quota.relay_wake_dir())
    wake.mkdir(parents=True)
    (wake / "ticket.json").write_text('{"source": "quota", "text": "reset"}', encoding="utf-8")
    assert str(wake / "ticket.json") in wake_daemon.get_snapshot()


def test_banner_survives_a_cp1252_console(monkeypatch):
    """The emoji banner must not kill the daemon on a Windows console.

    Writing the siren raised UnicodeEncodeError under cp1252, so the daemon
    crashed on the one line that reports a detected ping.
    """
    import sys

    class CP1252Stream:
        encoding = "cp1252"

        def __init__(self):
            self.written = []

        def write(self, text):
            text.encode("cp1252")  # raises on emoji, like the real console
            self.written.append(text)

        def flush(self):
            pass

    stream = CP1252Stream()
    monkeypatch.setattr(sys, "stdout", stream)
    wake_daemon._emit("🚨 ping detected")
    assert "ping detected" in "".join(stream.written)
