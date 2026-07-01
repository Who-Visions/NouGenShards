from nougen_shards import space_orchestration


def test_space_log_url_normalizes_space_id():
    url = space_orchestration.space_log_url(
        "run",
        "https://huggingface.co/spaces/WhoVisions/nga_hgf_Space",
    )
    assert url == "https://huggingface.co/api/spaces/WhoVisions/nga_hgf_Space/logs/run"


def test_build_log_request_redacts_token(monkeypatch):
    monkeypatch.setattr(
        space_orchestration.keymaker,
        "get_secret",
        lambda key: "hf_test_secret" if key == "Yuki_HGF_key" else None,
    )

    request = space_orchestration.build_log_request(kind="build")

    assert request["space_id"] == "WhoVisions/nga_hgf_Space"
    assert request["kind"] == "build"
    assert request["token_key"] == "Yuki_HGF_key"
    assert request["token_present"] is True
    assert request["headers"] == {"Authorization": "Bearer <redacted:Yuki_HGF_key>"}
    assert "hf_test_secret" not in str(request)


def test_space_anchor_layers_over_local_handoff_anchor(monkeypatch):
    monkeypatch.setattr(
        space_orchestration.keymaker,
        "get_secret",
        lambda key: "hf_test_secret" if key == "Yuki_HGF_key" else None,
    )

    anchor = space_orchestration.get_space_orchestration_anchor(
        limit=1,
        max_chars=4000,
        space_id="WhoVisions/nga_hgf_Space",
    )

    assert "[HF_SPACE_ORCHESTRATION]" in anchor
    assert "Mode: additive control-plane" in anchor
    assert "local handoff JSON and handoffs.db remain source of truth" in anchor
    assert "Credential: key=Yuki_HGF_key; present=true" in anchor
    assert "hf_test_secret" not in anchor


def test_redact_token_from_log_text():
    credential = space_orchestration.SpaceCredential(
        key="Yuki_HGF_key",
        token="hf_test_secret",
    )
    redacted = space_orchestration._redact_token("token=hf_test_secret", credential)

    assert redacted == "token=<redacted:Yuki_HGF_key>"
