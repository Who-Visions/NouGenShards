import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "relay_golive", Path(__file__).resolve().parents[1] / "tools" / "relay_golive.py")
rg = importlib.util.module_from_spec(SPEC)
sys.modules["relay_golive"] = rg
SPEC.loader.exec_module(rg)

ACCT = "a" * 32


def cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class FakeRun:
    def __init__(self, pr_state="MERGED", ancestor_rc=0, deploy_rc=0, acct_rc=0, releases=None, local_rc=0):
        self.local_rc = local_rc
        self.calls = []
        self.pr_state, self.ancestor_rc = pr_state, ancestor_rc
        self.deploy_rc, self.acct_rc = deploy_rc, acct_rc
        self.releases = releases or [{"tagName": "supervisor-v1.3.2", "isDraft": False}]

    def __call__(self, argv, env=None):
        self.calls.append(argv)
        if argv[:3] == ["gh", "pr", "view"]:
            return cp(out=json.dumps({"state": self.pr_state, "mergedAt": "t", "baseRefName": "main",
                                      "mergeCommit": {"oid": "f" * 40}}))
        if "_cf-account" in argv:
            return cp(self.acct_rc, ACCT + "\n" if self.acct_rc == 0 else "", "denied")
        if "wrangler" in argv:
            return cp(self.deploy_rc, "", "boom")
        if argv[:3] == ["gh", "release", "list"]:
            return cp(out=json.dumps(self.releases))
        if argv[:2] == ["git", "merge-base"]:
            return cp(self.local_rc if argv[-1] == "HEAD" else self.ancestor_rc)
        raise AssertionError(argv)


def run(fake, apply=False, health=(200, "ok")):
    lines = []
    rc = rg.run_steps(rg.Ctx(apply=apply, run=fake, fetch=lambda u, t: health), out=lines.append)
    return rc, lines


def test_dry_run_never_deploys():
    fake = FakeRun()
    rc, lines = run(fake)
    assert rc == 0
    assert not any("wrangler" in c for c in fake.calls)
    assert "dry run" in lines[-1]
    assert "NOUGEN_JOIN_RELAY_AUTH_KV_ID" in lines[3]
    assert "wss://relay.nougenai.com/_relay/connect'" in lines[3]


def test_unmerged_pr_stops_first():
    fake = FakeRun(pr_state="OPEN")
    rc, lines = run(fake, apply=True)
    assert rc == 1 and lines[-1].startswith("[STOP] merged")
    assert len(fake.calls) == 1


def test_apply_deploys_with_resolved_account_and_keyfor():
    fake = FakeRun()
    rc, _ = run(fake, apply=True)
    assert rc == 0
    deploy = [c for c in fake.calls if "wrangler" in c][0]
    assert "--exec" in deploy and "CLOUDFLARE_API_TOKEN_NOUGEN_FULL" in deploy


def test_deploy_failure_stops_before_supervisor():
    fake = FakeRun(deploy_rc=1)
    rc, lines = run(fake, apply=True)
    assert rc == 1 and lines[-1].startswith("[STOP] relay")
    assert not any(c[:3] == ["gh", "release", "list"] for c in fake.calls)


def test_unhealthy_after_apply_stops():
    rc, lines = run(FakeRun(), apply=True, health=(522, ""))
    assert rc == 1 and "health" in lines[-1]


def test_dry_run_tolerates_relay_not_live():
    rc, lines = run(FakeRun(), health=(0, "dns"))
    assert rc == 0 and "not live yet" in lines[1]


def test_account_resolve_failure_stops():
    rc, lines = run(FakeRun(acct_rc=1))
    assert rc == 1 and "account resolve failed" in lines[-1]


def test_release_predating_merge_is_reported():
    rc, lines = run(FakeRun(ancestor_rc=1))
    assert rc == 0 and "RELEASE NEEDED" in lines[2]


def test_newer_release_means_bump():
    rel = [{"tagName": "supervisor-v1.3.2", "isDraft": False}, {"tagName": "supervisor-v1.4.0", "isDraft": False}]
    rc, lines = run(FakeRun(releases=rel))
    assert "BUMP NEEDED" in lines[2]


def test_cf_account_picks_owner_of_namespace(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "x")
    pages = {"/accounts?per_page=50": {"result": [{"id": "wrong"}, {"id": ACCT}]},
             f"/accounts/{ACCT}/storage/kv/namespaces/kv1": {"success": True}}
    assert rg.cf_account("kv1", get=lambda p: pages.get(p, {"success": False})) == ACCT


def test_cf_account_without_token(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    with pytest.raises(rg.GateError):
        rg.cf_account("kv1", get=lambda p: {})


def test_strip_jsonc_keeps_urls_in_strings():
    assert json.loads(rg.strip_jsonc('{"a": "https://x//y", // c\n "b": [1,],}')) == {"a": "https://x//y", "b": [1]}


def test_relay_paths_come_from_worker_source():
    connect, health = rg.relay_paths()
    assert connect.endswith("/connect") and health.endswith("/health")


def test_probe_and_url_use_worker_paths():
    seen = []
    lines = []
    ctx = rg.Ctx(apply=False, run=FakeRun(), fetch=lambda u, t: (seen.append(u), (200, "ok"))[1])
    assert rg.run_steps(ctx, out=lines.append) == 0
    connect, health = rg.relay_paths()
    assert seen and seen[0].endswith(health)
    assert ctx.relay_url.endswith(connect)


def test_relay_paths_missing_routes(tmp_path):
    f = tmp_path / "worker.js"
    f.write_text("export default {}", encoding="utf-8")
    with pytest.raises(rg.GateError):
        rg.relay_paths(f)


def test_checkout_missing_merge_stops_before_deploy():
    fake = FakeRun(local_rc=1)
    rc, lines = run(fake, apply=True)
    assert rc == 1 and lines[-1].startswith("[STOP] merged") and "pull main" in lines[-1]
    assert not any("wrangler" in c for c in fake.calls)


def test_merge_unknown_locally_stops():
    rc, lines = run(FakeRun(local_rc=128), apply=True)
    assert rc == 1 and "fetch" in lines[-1]


def test_deploy_and_health_failures_are_labelled_apart():
    _, dep = run(FakeRun(deploy_rc=1), apply=True)
    _, hea = run(FakeRun(), apply=True, health=(522, ""))
    assert "DEPLOY FAILED" in dep[-1] and "HEALTH FAILED" in hea[-1]
