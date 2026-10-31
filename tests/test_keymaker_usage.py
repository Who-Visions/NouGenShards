from nougen_shards import keymaker


def test_exa_alias_covers_numbered_keys():
    assert "EXA_API_KEY_1" in keymaker.CANONICAL_ALIASES["EXA_API_KEY"]


def test_usage_returns_header_without_value():
    usage = keymaker.provider_usage("EXA_API_KEY_2")
    assert usage["header"] == "x-api-key: {key}"
    assert keymaker.provider_usage("UNKNOWN_KEY") is None
