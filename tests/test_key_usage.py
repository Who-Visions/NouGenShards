import json

import pytest

from nougen_shards import key_usage, keymaker


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setattr(keymaker, "VAULT_DIR", tmp_path)
    monkeypatch.setattr(keymaker, "DB_PATH", tmp_path / "shards_secrets.db")
    monkeypatch.setattr(keymaker, "CSV_PATH", tmp_path / "shards_secrets.csv")
    monkeypatch.setattr(keymaker, "SECRETS_JSON_DIR", tmp_path / "service_accounts")
    # never reach the real macOS Keychain from a test
    monkeypatch.setattr(keymaker, "_protect", lambda value, *args, **kwargs: value)
    keymaker.init_vault()
    return tmp_path


def test_exa_usage_says_http_transport_and_header_not_url(vault):
    record = key_usage.usage_for("EXA_API_KEY_2")
    assert record["provider"] == "Exa"
    assert record["mcp"]["type"] == "http"
    assert record["auth"] == {"header": "x-api-key", "scheme": "{key}"}
    assert any("never \"sse\"" in note for note in record["notes"])


def test_longest_prefix_wins(vault):
    assert key_usage.usage_for("OLLAMACLOUD_KEY_3")["provider"] == "Ollama Cloud"
    assert key_usage.usage_for("NGS_NODE_OWNER_TOKEN")["auth"]["header"] == "X-NGS-Token"


def test_unknown_key_returns_none_not_a_guess(vault):
    assert key_usage.usage_for("TOTALLY_UNKNOWN_THING") is None
    assert "do not guess" in key_usage.format_usage("TOTALLY_UNKNOWN_THING")


def test_curl_example_references_the_name_never_a_value(vault):
    keymaker.ingest_secret("EXA_API_KEY", "sk-real-looking-value-123456")
    record = key_usage.usage_for("EXA_API_KEY")
    assert "$EXA_API_KEY" in record["curl"]
    assert "-X POST" in record["curl"] and '"https://api.exa.ai/search"' in record["curl"]
    assert not record["curl"].startswith("#")
    assert "sk-real-looking-value-123456" not in json.dumps(key_usage.describe("EXA_API_KEY"))
    assert "sk-real-looking-value-123456" not in key_usage.format_usage("EXA_API_KEY")


def test_query_style_auth_has_no_header(vault):
    record = key_usage.usage_for("SERPAPI_KEY")
    assert record["auth"] == {"query": "api_key"}
    assert record["curl"].endswith('?api_key=$SERPAPI_KEY"')


def test_vault_override_wins_and_is_the_only_place_for_a_new_provider(vault):
    assert key_usage.usage_for("ACME_API_KEY") is None
    key_usage.set_usage("ACME_API_KEY", {
        "provider": "Acme", "base_url": "https://api.acme.test",
        "auth": {"header": "X-Acme-Key", "scheme": "{key}"},
    })
    record = key_usage.usage_for("ACME_API_KEY")
    assert record["provider"] == "Acme"
    assert '-H "X-Acme-Key: $ACME_API_KEY"' in record["curl"]
    key_usage.set_usage("EXA_API_KEY", {"provider": "Exa (override)"})
    assert key_usage.usage_for("EXA_API_KEY")["provider"] == "Exa (override)"


def test_describe_reports_presence_without_the_value(vault):
    assert key_usage.describe("EXA_API_KEY")["present"] is False
    keymaker.ingest_secret("EXA_API_KEY", "abc-secret-value-9999")
    described = key_usage.describe("EXA_API_KEY")
    assert described["present"] is True
    assert "abc-secret-value-9999" not in json.dumps(described)


def test_example_without_a_resource_path_is_flagged_as_auth_only(vault):
    record = key_usage.usage_for("SERPAPI_KEY")
    assert record["curl"].startswith("# auth-only template")
    assert key_usage.usage_for("TMDB_KEY")["curl"].endswith('/3/configuration"')


def test_cloud_credentials_do_not_get_the_node_token_record(vault):
    assert key_usage.usage_for("NGS_CLOUD_CREDENTIALS") is None
    assert key_usage.usage_for("NGS_NODE_TOKEN")["auth"]["header"] == "X-NGS-Token"


def test_overrides_use_the_tenant_aware_db_path(vault, tmp_path, monkeypatch):
    tenant_db = tmp_path / "tenant" / "shards_secrets.db"
    tenant_db.parent.mkdir()
    monkeypatch.setattr(keymaker, "db_path", lambda: tenant_db)
    key_usage.set_usage("ACME_API_KEY", {"provider": "Acme (tenant)"})
    assert tenant_db.is_file()
    assert key_usage.usage_for("ACME_API_KEY")["provider"] == "Acme (tenant)"
    monkeypatch.setattr(keymaker, "db_path", lambda: tmp_path / "shards_secrets.db")
    assert key_usage.usage_for("ACME_API_KEY") is None
