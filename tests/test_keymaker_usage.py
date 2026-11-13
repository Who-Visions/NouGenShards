from nougen_shards import keymaker


def test_exa_alias_covers_numbered_keys():
    assert "EXA_API_KEY_1" in keymaker.CANONICAL_ALIASES["EXA_API_KEY"]


def test_auth_add_reports_a_refused_blank_key_as_failure(monkeypatch, capsys):
    """Codex review on #1057: a blank key was refused by the vault but the CLI still printed 'saved'."""
    from types import SimpleNamespace
    from nougen_shards import cli
    monkeypatch.setattr(keymaker, "ingest_secret", lambda key, value: False)
    rc = cli.cmd_auth(SimpleNamespace(action="set-key", provider="openrouter", input="   "))
    out = capsys.readouterr().out
    assert rc == 1
    assert "nothing was saved" in out
    assert "saved to vault" not in out
