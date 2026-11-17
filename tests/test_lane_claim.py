import sys
import time

import pytest
from nougen_shards.lane_claim import (
    claim_lane,
    release_lane,
    active_claims,
    conflicts_for,
)


@pytest.fixture(autouse=True)
def fleet_side_effects(monkeypatch):
    """Keep every test in this file off the live fleet.

    claim_lane() captures a "Lane Claim" shard and broadcasts a wake message on
    NouGenMsg and into ~/.nougen/agy_inbox. Unstubbed, each run of this file
    wrote two real shards and sent two "MANDATORY LANE WORK EXECUTION" messages
    for src/foo.py and src/mcp_test.py to every lane. The stubs record the
    calls so tests can still assert the claim path reaches both hooks.
    """
    from nougen_shards import lane_claim

    calls = {"shards": [], "wakes": []}

    def fake_replicate(claim):
        calls["shards"].append(claim)
        return True

    def fake_wake(claim):
        calls["wakes"].append(claim)
        return {"stubbed": True}

    monkeypatch.setattr(lane_claim, "replicate_to_nougen_shards", fake_replicate)
    monkeypatch.setattr(lane_claim, "dispatch_lane_wake", fake_wake)
    return calls


@pytest.fixture
def temp_claims_dir(tmp_path):
    claims = tmp_path / "claims"
    claims.mkdir(parents=True, exist_ok=True)
    return claims


def test_claim_and_active_claims(temp_claims_dir):
    res = claim_lane(
        scope=["src/nougen_shards/lane_claim.py", "tools/lane_claim.py"],
        goal="testing native lane claim",
        agent="antigravity",
        machine="testbox",
        claims_dir=temp_claims_dir,
        replicate_shard=False,
        notify=False,
    )
    assert res["status"] == "claimed"
    claim = res["claim"]
    assert claim["agent"] == "antigravity"
    assert claim["machine"] == "testbox"
    assert "src/nougen_shards/lane_claim.py" in claim["scope"]

    active = active_claims(claims_dir=temp_claims_dir)
    assert len(active) == 1
    assert active[0]["agent"] == "antigravity"
    assert active[0]["goal"] == "testing native lane claim"


def test_conflicts_detection(temp_claims_dir):
    claim_lane(
        scope=["src/nougen_shards/*.py"],
        goal="work on shards core",
        agent="claude",
        machine="blade",
        claims_dir=temp_claims_dir,
        replicate_shard=False,
        notify=False,
    )

    # Agent 'antigravity' on 'phoebus' editing a matching path should detect conflict
    hits = conflicts_for(
        paths=["src/nougen_shards/core.py"],
        me_agent="antigravity",
        me_machine="phoebus",
        claims_dir=temp_claims_dir,
    )
    assert len(hits) == 1
    path, claim = hits[0]
    assert path == "src/nougen_shards/core.py"
    assert claim["agent"] == "claude"

    # The same agent 'claude' on 'blade' should NOT see conflict against itself
    self_hits = conflicts_for(
        paths=["src/nougen_shards/core.py"],
        me_agent="claude",
        me_machine="blade",
        claims_dir=temp_claims_dir,
    )
    assert len(self_hits) == 0


def test_release_claim(temp_claims_dir):
    claim_lane(
        scope=["test_file.py"],
        goal="temporary claim",
        agent="antigravity",
        machine="testbox",
        claims_dir=temp_claims_dir,
        replicate_shard=False,
        notify=False,
    )
    assert len(active_claims(claims_dir=temp_claims_dir)) == 1

    ok = release_lane(agent="antigravity", machine="testbox", claims_dir=temp_claims_dir)
    assert ok is True
    assert len(active_claims(claims_dir=temp_claims_dir)) == 0


def test_immediate_execution_enforcement(temp_claims_dir, tmp_path):
    marker = tmp_path / "work_executed.txt"
    cmd = f'"{sys.executable}" -c "import pathlib; pathlib.Path(r\'{marker}\').write_text(\'done\')"'
    res = claim_lane(
        scope=["work.py"],
        goal="run immediately",
        agent="antigravity",
        machine="testbox",
        execute_cmd=cmd,
        claims_dir=temp_claims_dir,
        replicate_shard=False,
        notify=False,
    )
    assert "execution_pid" in res
    # Wait up to 2 seconds for subprocess execution
    for _ in range(20):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists()
    assert marker.read_text() == "done"


def test_cli_cmd_claim_workflow(temp_claims_dir, monkeypatch):
    import argparse
    import io
    import json
    from contextlib import redirect_stdout
    from nougen_shards import cli, lane_claim

    monkeypatch.setattr(lane_claim, "CLAIMS_DIR", temp_claims_dir)

    # 1. Status empty
    out = io.StringIO()
    with redirect_stdout(out):
        cli.cmd_claim(argparse.Namespace(claim_args=["status"], json=False))
    assert "no active claims" in out.getvalue()

    # 2. Claim scope
    out = io.StringIO()
    with redirect_stdout(out):
        cli.cmd_claim(argparse.Namespace(
            claim_args=["src/foo.py"],
            goal="cli claim test",
            execute_cmd=None,
            ttl_hours=1.0,
            json=True,
        ))
    res = json.loads(out.getvalue())
    assert res["status"] == "claimed"
    assert "src/foo.py" in res["claim"]["scope"]

    # 3. Status with claim
    out = io.StringIO()
    with redirect_stdout(out):
        cli.cmd_claim(argparse.Namespace(claim_args=[], json=False))
    assert "src/foo.py" in out.getvalue()

    # 4. Release claim
    out = io.StringIO()
    with redirect_stdout(out):
        cli.cmd_claim(argparse.Namespace(claim_args=["release"], json=False))
    assert "released" in out.getvalue()


def test_mcp_lane_claim_and_hi_tools(temp_claims_dir, monkeypatch):
    import json
    from nougen_shards import lane_claim, mcp

    monkeypatch.setattr(lane_claim, "CLAIMS_DIR", temp_claims_dir)

    # 1. List claims (empty)
    raw = mcp.list_lane_claims()
    data = json.loads(raw)
    assert data["count"] == 0

    # 2. Claim lane
    raw_claim = mcp.claim_lane(scope=["src/mcp_test.py"], goal="mcp test goal")
    claim_data = json.loads(raw_claim)
    assert claim_data["status"] == "claimed"

    # 3. List claims (1 active)
    raw = mcp.list_lane_claims()
    data = json.loads(raw)
    assert data["count"] == 1

    # 4. Release lane
    raw_rel = mcp.release_lane()
    rel_data = json.loads(raw_rel)
    assert rel_data["released"] is True

    # 5. Session hi tool
    raw_hi = mcp.session_hi(fleet=False)
    hi_data = json.loads(raw_hi)
    assert "identity" in hi_data


def test_claim_reaches_both_fleet_hooks_through_the_stubs(temp_claims_dir, fleet_side_effects):
    result = claim_lane(scope=["src/x.py"], goal="hook wiring", agent="tester", machine="box",
                        claims_dir=temp_claims_dir)
    assert result["shard_replicated"] is True
    assert result["wake_dispatch"] == {"stubbed": True}
    assert [c["goal"] for c in fleet_side_effects["shards"]] == ["hook wiring"]
    assert [c["goal"] for c in fleet_side_effects["wakes"]] == ["hook wiring"]


def test_opting_out_skips_both_fleet_hooks(temp_claims_dir, fleet_side_effects):
    result = claim_lane(scope=["src/x.py"], goal="quiet", agent="tester", machine="box",
                        claims_dir=temp_claims_dir, replicate_shard=False, notify=False)
    assert "shard_replicated" not in result
    assert "wake_dispatch" not in result
    assert fleet_side_effects == {"shards": [], "wakes": []}
