"""Health must publish which journal mode the vault actually uses.

#253 made the mode configurable because forcing WAL on object-storage mounts
causes corruption and spurious quarantines. Configurable is not configured --
the default is still WAL -- and during the #255 investigation the one fact
nobody could measure was which mode the affected node was on. Publishing it
turns that from an inference into a reading.
"""

import app
from nougen_shards.core import get_vault_journal_mode


def test_health_reports_the_mode_core_would_use():
    assert app._vault_journal_mode() == get_vault_journal_mode()


def test_default_is_wal_and_is_reported_as_such(monkeypatch):
    """The unsafe-on-bucket-mounts default must be visible, not hidden."""
    monkeypatch.delenv("NOUGEN_VAULT_JOURNAL_MODE", raising=False)
    assert app._vault_journal_mode() == "WAL"


def test_override_is_reflected(monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_JOURNAL_MODE", "delete")
    assert app._vault_journal_mode() == "DELETE"


def test_pre_253_nodes_report_their_own_absence(monkeypatch):
    """A node with no such function cannot configure the mode at all.

    Reporting 'unavailable (pre-#253)' says that plainly. Falling back to
    'WAL' would be indistinguishable from a node that had chosen WAL, and the
    distinction is the whole point.
    """
    import nougen_shards.core as core
    monkeypatch.delattr(core, "get_vault_journal_mode")
    assert "pre-#253" in app._vault_journal_mode()
