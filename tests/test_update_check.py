"""Update awareness: stale builds say so, current builds stay quiet, offline
boxes never break. All offline - the network layer is monkeypatched."""

from nougen_shards import update_check


def _fresh(monkeypatch, local, remote):
    monkeypatch.setattr(update_check, "_cache", {"at": 0.0, "result": None})
    monkeypatch.setattr(update_check, "local_build_sha", lambda: local)
    monkeypatch.setattr(update_check, "latest_remote_sha", lambda: remote)


def test_stale_build_reports_update_available(monkeypatch):
    _fresh(monkeypatch, "aaaa1111aaaa1111", "bbbb2222bbbb2222")
    v = update_check.check_for_update(force=True)
    assert v["update_available"] is True
    assert v["local_sha"] == "aaaa1111aaaa"
    assert v["latest_sha"] == "bbbb2222bbbb"


def test_current_build_is_quiet(monkeypatch):
    _fresh(monkeypatch, "cccc3333cccc3333", "cccc3333cccc3333")
    v = update_check.check_for_update(force=True)
    assert v["update_available"] is False
    assert update_check.llm_notice() == ""


def test_short_baked_sha_matches_full_remote(monkeypatch):
    # .deploy_sha bakes a prefix; a prefix match is the same build, not stale.
    _fresh(monkeypatch, "dddd4444", "dddd4444eeee5555ffff6666")
    assert update_check.check_for_update(force=True)["update_available"] is False


def test_offline_is_unknown_not_error(monkeypatch):
    _fresh(monkeypatch, "aaaa1111", None)
    v = update_check.check_for_update(force=True)
    assert v["update_available"] is None
    assert update_check.llm_notice() == ""


def test_llm_notice_names_action_and_repo(monkeypatch):
    _fresh(monkeypatch, "aaaa1111aaaa1111", "bbbb2222bbbb2222")
    update_check.check_for_update(force=True)
    notice = update_check.llm_notice()
    assert "update" in notice.lower()
    assert update_check.REPO in notice
    assert "aaaa1111aaaa" in notice and "bbbb2222bbbb" in notice


def test_cache_avoids_repeat_network_calls(monkeypatch):
    calls = {"n": 0}

    def counting_remote():
        calls["n"] += 1
        return "bbbb2222"

    monkeypatch.setattr(update_check, "_cache", {"at": 0.0, "result": None})
    monkeypatch.setattr(update_check, "local_build_sha", lambda: "aaaa1111")
    monkeypatch.setattr(update_check, "latest_remote_sha", counting_remote)
    update_check.check_for_update(force=True)
    update_check.check_for_update()
    update_check.check_for_update()
    assert calls["n"] == 1
