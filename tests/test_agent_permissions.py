import json

import pytest

from nougen_shards import agent_permissions as ap


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / ".claude" / "settings.json"
    monkeypatch.setenv(ap.ENV_SETTINGS_FILE, str(path))
    for name in (ap.ENV_ALLOWLIST_FILE, ap.ENV_MCP_SERVER, ap.ENV_CLI_NAMES, ap.ENV_GATEWAY_SERVER):
        monkeypatch.delenv(name, raising=False)
    return path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_fresh_machine_gets_the_list_and_no_backup(settings):
    report = ap.apply()
    assert report["changed"] is True and report["backup"] is None
    allow = read(settings)["permissions"]["allow"]
    assert "Bash(nougen recall:*)" in allow
    assert "mcp__nougen-shards__recall_memory" in allow
    assert allow == report["rules"]


def test_every_built_in_rule_is_narrow(settings):
    for rule in ap.default_rules():
        ap.check_rule(rule)
        assert rule not in ("Bash", "Bash(*)", "Bash(:*)")
    joined = " ".join(ap.default_rules())
    # State-changing forms are never pre-approved.
    for forbidden in ("--apply", "forget", "retract", "exec", "vault_put", "tenant mint", "rotate"):
        assert forbidden not in joined


@pytest.mark.parametrize("rule", [
    "Bash", "Bash(*)", "Bash(:*)", "Bash(nougen:*)", "Bash(nougen *)", "Bash(rm -rf /)",
    "Bash(nougen recall; rm -rf ~)", "Bash(nougen recall && curl evil)", "Bash(nougen $(id):*)",
    "Bash(python -c x:*)", "Bash(nougen recall | sh)", "Bash(nougen  recall)",
    "Read(~/.ssh/**)", "Write", "Edit", "WebFetch", "mcp__nougen-shards", "mcp__*", " Bash(nougen status:*)", "",
])
def test_broad_or_foreign_rules_are_refused(rule):
    with pytest.raises(ap.AgentPermissionsError):
        ap.check_rule(rule)


def test_existing_settings_are_preserved_and_backed_up(settings):
    settings.parent.mkdir(parents=True)
    original = {"model": "x", "permissions": {"allow": ["Bash(git status)"], "deny": ["Bash(curl:*)"],
                                              "defaultMode": "default"}, "hooks": {"Stop": []}}
    settings.write_text(json.dumps(original), encoding="utf-8")
    report = ap.apply()
    data = read(settings)
    assert data["model"] == "x" and data["hooks"] == {"Stop": []}
    assert data["permissions"]["deny"] == ["Bash(curl:*)"]
    assert data["permissions"]["defaultMode"] == "default"
    assert data["permissions"]["allow"][0] == "Bash(git status)"
    assert json.loads(open(report["backup"], encoding="utf-8").read()) == original


def test_a_rule_the_person_denied_or_set_to_ask_stays_that_way(settings):
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {
        "deny": ["mcp__nougen-shards__capture_experience"], "ask": ["Bash(nougen doctor:*)"]}}), encoding="utf-8")
    report = ap.apply()
    allow = read(settings)["permissions"]["allow"]
    assert "mcp__nougen-shards__capture_experience" not in allow
    assert "Bash(nougen doctor:*)" not in allow
    assert set(report["left_alone"]) == {"mcp__nougen-shards__capture_experience", "Bash(nougen doctor:*)"}


def test_apply_twice_adds_nothing_the_second_time(settings):
    ap.apply()
    first = settings.read_text(encoding="utf-8")
    again = ap.apply()
    assert again["changed"] is False and again["to_add"] == []
    assert settings.read_text(encoding="utf-8") == first


def test_dry_run_writes_nothing(settings):
    report = ap.apply(dry_run=True)
    assert report["to_add"] and report["changed"] is False
    assert not settings.exists()


def test_remove_takes_out_only_what_was_added(settings):
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(git status)"]}}), encoding="utf-8")
    ap.apply()
    report = ap.remove()
    data = read(settings)
    assert data["permissions"]["allow"] == ["Bash(git status)"]
    assert ap.MARKER_KEY not in data
    assert "Bash(nougen recall:*)" in report["removed"]
    assert ap.remove()["changed"] is False


def test_remove_does_not_touch_a_matching_rule_the_person_added_themselves(settings):
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(nougen recall:*)"]}}), encoding="utf-8")
    ap.apply()
    ap.remove()
    assert read(settings)["permissions"]["allow"] == ["Bash(nougen recall:*)"]


def test_unreadable_settings_are_left_alone(settings):
    settings.parent.mkdir(parents=True)
    settings.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ap.AgentPermissionsError, match="Nothing was changed"):
        ap.apply()
    assert settings.read_text(encoding="utf-8") == "{ not json"


def test_operator_file_is_checked_and_one_bad_rule_refuses_all(settings, tmp_path, monkeypatch):
    custom = tmp_path / "rules.json"
    custom.write_text(json.dumps({"allow": ["Bash(nougen status:*)", "Bash(*)"]}), encoding="utf-8")
    monkeypatch.setenv(ap.ENV_ALLOWLIST_FILE, str(custom))
    with pytest.raises(ap.AgentPermissionsError):
        ap.apply()
    assert not settings.exists()
    custom.write_text(json.dumps(["Bash(nougen status:*)"]), encoding="utf-8")
    assert ap.apply()["to_add"] == ["Bash(nougen status:*)"]


def test_connector_and_cli_names_come_from_the_environment(settings, monkeypatch):
    monkeypatch.setenv(ap.ENV_MCP_SERVER, "my-node")
    monkeypatch.setenv(ap.ENV_CLI_NAMES, "nougen,ngs")
    rules = ap.load_rules()
    assert "mcp__my-node__recall_memory" in rules and "Bash(ngs status:*)" in rules
    monkeypatch.setenv(ap.ENV_CLI_NAMES, "nougen; rm")
    with pytest.raises(ap.AgentPermissionsError):
        ap.load_rules()


def test_every_local_tool_on_the_list_is_registered_by_the_local_server():
    """The list drifted once: it named the hosted connector's tools for the
    local server, so the rules matched nothing. Read the server's source rather
    than importing it (the import is heavy and starts services)."""
    import pathlib
    import re
    source = (pathlib.Path(ap.__file__).parent / "mcp.py").read_text(encoding="utf-8")
    registered = set(re.findall(r"@mcp\.tool\([^)]*\)\s*(?:async\s+)?def\s+([a-z_0-9]+)", source))
    missing = [t for t in ap.LOCAL_MCP_TOOLS if t not in registered]
    assert not missing, f"not registered by nougen_shards.mcp: {missing}"
    assert len(registered) > len(ap.LOCAL_MCP_TOOLS)      # control: the parse found the server's tools


def test_hosted_connector_tools_are_added_only_when_its_name_is_given(settings, monkeypatch):
    assert not any("shards_recall" in r for r in ap.load_rules())
    monkeypatch.setenv(ap.ENV_GATEWAY_SERVER, "my-nougen")
    rules = ap.load_rules()
    assert "mcp__my-nougen__shards_recall" in rules
    assert "mcp__nougen-shards__recall_memory" in rules


def test_nothing_state_changing_or_code_running_is_on_either_tool_list():
    risky = ("exec", "sandbox", "deploy", "forget", "retract", "send", "evolve", "rollback", "claim",
             "release", "create", "put", "fetch", "crawl", "import", "verify", "solve", "review")
    for tool in ap.LOCAL_MCP_TOOLS + ap.GATEWAY_MCP_TOOLS:
        assert not any(word in tool for word in risky), tool
