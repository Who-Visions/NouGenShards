"""LOCAL_VAULT rows are raw file bodies and must be redacted on the way out.

2026-08-29: a grid search returned a LOCAL_VAULT row carrying a LIVE Notion
integration token in plaintext, into two agents' contexts at once. LOCAL_VAULT
rows are not curated shards -- they are whole source files read in place from
registered vaults, reachable by any lane holding a connector token. The
redactor already existed in brain_scan/redaction.py; it simply was not on this
path.

Redaction happens at RETURN, not at ingest, because these vaults are read in
place and were never rewritten.
"""
# pylint: disable=protected-access
import pytest

from nougen_shards.brain_scan.redaction import redact_content
from nougen_shards.connectors import local_vault

NOTION = "ntn_5433204355aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.mark.parametrize("secret,marker", [
    (NOTION, "<REDACTED_NOTION_TOKEN>"),
    ("sk-ant-" + "a" * 40, "<REDACTED_ANTHROPIC_KEY>"),
    ("ghp_" + "b" * 36, "<REDACTED_GITHUB_TOKEN>"),
])
def test_known_provider_secrets_are_redacted(secret, marker):
    out = redact_content(f"const client = new Client({{ auth: '{secret}' }})")
    assert secret not in out
    assert marker in out


def test_local_vault_redactor_strips_a_live_looking_token():
    body = f"const notion = new Client({{ auth: '{NOTION}' }});"
    assert NOTION not in local_vault._redact(body)


def test_local_vault_redactor_withholds_the_body_when_it_cannot_run(monkeypatch):
    """A redactor that raises must NOT degrade to passing the secret through."""
    import nougen_shards.brain_scan.redaction as redaction

    def boom(_content):
        raise RuntimeError("redactor exploded")

    monkeypatch.setattr(redaction, "redact_content", boom)
    out = local_vault._redact(f"auth: '{NOTION}'")
    assert NOTION not in out
    assert "WITHHELD" in out
