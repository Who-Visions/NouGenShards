from nougen_shards import keymaker


def test_exa_alias_covers_numbered_keys():
    assert "EXA_API_KEY_1" in keymaker.CANONICAL_ALIASES["EXA_API_KEY"]
