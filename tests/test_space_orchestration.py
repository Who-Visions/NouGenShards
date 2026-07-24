import pytest

from nougen_shards import space_orchestration

# Rule 0.2: read the Space id and the primary token key from the same module
# the code reads them from, so a re-pointed Space or a renamed credential does
# not silently mean "the test asserts the old deployment".
SPACE_ID = space_orchestration.normalize_space_id()
PRIMARY_TOKEN_KEY = space_orchestration.DEFAULT_TOKEN_KEYS[0]
FAKE_TOKEN = "hf_test_secret"  # fixture value; never a real credential


@pytest.fixture(name="isolated_credentials")
def fixture_isolated_credentials(monkeypatch):
    """Strip every credential source so token resolution is fully controlled."""
    monkeypatch.delenv("NOUGEN_HF_TOKEN_KEY", raising=False)
    monkeypatch.delenv("NOUGEN_HF_SPACE_ID", raising=False)
    for key in space_orchestration.DEFAULT_TOKEN_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(space_orchestration.keymaker, "get_secret", lambda key: None)
    return monkeypatch


def test_space_log_url_normalizes_space_id():
    """A full Space web URL must normalize to the owner/name API log endpoint."""
    for source in (
        f"https://huggingface.co/spaces/{SPACE_ID}",
        f"https://huggingface.co/api/spaces/{SPACE_ID}",
        f"{SPACE_ID}/",
        SPACE_ID,
    ):
        url = space_orchestration.space_log_url("run", source)
        assert url == f"https://huggingface.co/api/spaces/{SPACE_ID}/logs/run"
        # Structure, not a pinned deployment: API host, no /spaces/ web path.
        assert url.startswith("https://huggingface.co/api/spaces/")
        assert "/spaces/spaces/" not in url
        assert url.endswith("/logs/run")

    assert space_orchestration.space_log_url("build", SPACE_ID).endswith("/logs/build")
    with pytest.raises(ValueError):
        space_orchestration.space_log_url("not-a-kind", SPACE_ID)


def test_build_log_request_redacts_token(monkeypatch):
    monkeypatch.setattr(
        space_orchestration.keymaker,
        "get_secret",
        lambda key: FAKE_TOKEN if key == PRIMARY_TOKEN_KEY else None,
    )

    request = space_orchestration.build_log_request(kind="build")

    assert request["space_id"] == SPACE_ID
    assert request["kind"] == "build"
    assert request["url"] == space_orchestration.space_log_url("build")
    assert request["token_key"] == PRIMARY_TOKEN_KEY
    assert request["token_present"] is True
    assert request["headers"] == {"Authorization": f"Bearer <redacted:{PRIMARY_TOKEN_KEY}>"}
    assert FAKE_TOKEN not in str(request)


def test_build_log_request_reports_token_absent(isolated_credentials):
    """Negative case: with NO credential anywhere, presence must report False.

    Without this, `token_present` hardcoded to True was invisible — the positive
    test monkeypatches a token in and then asserts the value it just fed.
    """
    request = space_orchestration.build_log_request(kind="run")

    assert request["token_present"] is False, "absent token reported as present"
    assert request["token_key"] is None
    assert request["headers"] == {}
    assert not request["headers"], "a redacted auth header was emitted with no token"
    # The rest of the request is still well-formed.
    assert request["space_id"] == SPACE_ID
    assert request["kind"] == "run"
    assert request["url"] == space_orchestration.space_log_url("run")


def test_build_log_request_token_presence_tracks_the_credential(isolated_credentials):
    """Presence must be a function of the credential, not a constant."""
    absent = space_orchestration.build_log_request(kind="run")

    isolated_credentials.setattr(
        space_orchestration.keymaker,
        "get_secret",
        lambda key: FAKE_TOKEN if key == PRIMARY_TOKEN_KEY else None,
    )
    present = space_orchestration.build_log_request(kind="run")

    assert absent["token_present"] is not present["token_present"]
    assert present["token_present"] is True
    assert present["token_key"] == PRIMARY_TOKEN_KEY
    assert present["headers"] != absent["headers"]
    assert FAKE_TOKEN not in str(present)


def test_space_anchor_reports_credential_absence(isolated_credentials):
    """The anchor must not claim a credential is present when none resolved."""
    anchor = space_orchestration.get_space_orchestration_anchor(
        limit=1, max_chars=4000, space_id=SPACE_ID,
    )

    assert "[HF_SPACE_ORCHESTRATION]" in anchor
    assert "present=false" in anchor.lower()
    assert "present=true" not in anchor.lower()


def test_space_anchor_layers_over_local_handoff_anchor(monkeypatch):
    monkeypatch.setattr(
        space_orchestration.keymaker,
        "get_secret",
        lambda key: FAKE_TOKEN if key == PRIMARY_TOKEN_KEY else None,
    )

    anchor = space_orchestration.get_space_orchestration_anchor(
        limit=1,
        max_chars=4000,
        space_id=SPACE_ID,
    )

    assert "[HF_SPACE_ORCHESTRATION]" in anchor
    assert "Mode: additive control-plane" in anchor
    assert "local handoff JSON and handoffs.db remain source of truth" in anchor
    assert f"Credential: key={PRIMARY_TOKEN_KEY}; present=true" in anchor
    assert SPACE_ID in anchor
    assert FAKE_TOKEN not in anchor


def test_redact_token_from_log_text():
    credential = space_orchestration.SpaceCredential(
        key=PRIMARY_TOKEN_KEY,
        token=FAKE_TOKEN,
    )
    redacted = space_orchestration._redact_token(f"token={FAKE_TOKEN}", credential)

    assert redacted == f"token=<redacted:{PRIMARY_TOKEN_KEY}>"
    assert FAKE_TOKEN not in redacted
