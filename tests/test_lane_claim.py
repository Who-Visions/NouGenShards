"""Tests for native NouGen lane claim and execution enforcement."""
import time

import pytest
from nougen_shards.lane_claim import (
    claim_lane,
    release_lane,
    active_claims,
    conflicts_for,
)


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
    cmd = f'python3 -c "import pathlib; pathlib.Path(\'{marker}\').write_text(\'done\')"'
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
