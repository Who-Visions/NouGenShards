"""Red test for the recall domain-mask defect (wargames/recall-domain-mask.md, Move 1).

A shard captured by an external writer carries the *writer's* CWD-resolved
domain. When the reading node resolves a different domain from its own CWD and
that scoped pass returns anything at all, the whole-brain fallback never fires
and the near-exact match stays permanently masked. Reproduced live 2026-08-16:
query "connector fix <gateway-host>" returned two loose same-day shards
and never the near-exact ones written that morning under another domain.
"""
# pylint: disable=duplicate-code, protected-access
import tempfile
from pathlib import Path

import pytest

import nougen_shards.core as shards


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Temporary vault so the real grid is never touched."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(shards, "GLOBAL_DIR", temp_path)

        def mock_get_db_path(index):
            return temp_path / f"test_shards_{index}.db"
        monkeypatch.setattr(shards, "get_db_path", mock_get_db_path)

        shards.init_db(1)
        yield temp_path


def test_implicit_domain_does_not_mask_other_domains(setup_test_env, monkeypatch):
    """A near-exact match in another domain must surface when the caller did
    not ask for domain scoping (domain resolved implicitly from process CWD)."""
    # Shard A: loose match, captured under the node's own domain (X).
    shards.capture(
        "TEST", "Connector notes",
        "Notes about the connector, the gateway, and the endpoint configuration.",
        domain_key="Watchtower/NodeHome")
    # Shard B: near-exact match, captured by an external writer under domain Y.
    shards.capture(
        "TEST", "Connector gateway endpoint patch",
        "connector gateway endpoint patch applied to the tunnel host",
        domain_key="Tools/Migration")

    # The node process resolves domain X from its CWD.
    monkeypatch.setattr(
        shards, "resolve_domain_from_path", lambda target_path=None: "Watchtower/NodeHome")

    results = shards.retrieve("connector gateway endpoint", limit=5)
    titles = [r["title"] for r in results]
    assert "Connector gateway endpoint patch" in titles, (
        "near-exact cross-domain shard masked by non-empty scoped pass: "
        f"got {titles}")


def test_explicit_domain_stays_exclusive(setup_test_env):
    """Callers that ask for a domain still get exclusive scoping (isolation
    semantics preserved -- see test_shards.py::test_domain_isolation_*)."""
    shards.capture("TEST", "Alpha doc", "connector gateway endpoint alpha",
                   domain_key="DomA")
    shards.capture("TEST", "Beta doc", "connector gateway endpoint beta",
                   domain_key="DomB")

    results = shards.retrieve("connector gateway endpoint", limit=5, domain_key="DomA")
    titles = [r["title"] for r in results]
    assert titles == ["Alpha doc"]
