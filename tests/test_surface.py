import json
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

import pytest

from nougen_shards import surface


@pytest.fixture(autouse=True)
def surface_home(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_SURFACE_HOME", str(tmp_path / "surface"))
    monkeypatch.setenv("NOUGEN_HANDOFFS_DIR", str(tmp_path / "legs"))


def test_policy_denies_by_default():
    with pytest.raises(surface.SurfaceError, match="not allowed"):
        surface.check_command("python -V")


def test_job_records_receipt():
    exe = sys.executable
    surface.set_policy({"allow": ["python"], "review": "auto"})
    surface.add_job("hello", command=f'"{exe}" -c "print(41+1)"')
    result = surface.run_job("hello")
    assert result["status"] == "ok"
    assert surface.runs()[0]["job"] == "hello"
    assert surface.find("42", shard_search=lambda q, limit: [])[0]["source"] == "run"


def test_denied_job_is_failed_receipt():
    surface.add_job("blocked", command="python -V")
    assert surface.run_job("blocked")["status"] == "failed"


def test_task_uses_headless_conhost():
    surface.add_job("nightly", prompt="hi", at="03:15")
    argv = surface.task_command("nightly")
    assert "conhost.exe --headless" in argv[-1] and "03:15" in argv


@pytest.mark.parametrize("name", ["../x", "A", ""])
def test_rejects_bad_names(name):
    with pytest.raises(surface.SurfaceError):
        surface.add_job(name, prompt="hi")


def test_boost_needs_two_models():
    def ask(prompt, **kw):
        return [{"model": "same", "text": "a"}, {"model": "same", "text": "b"}]

    with pytest.raises(surface.SurfaceError, match="two distinct"):
        surface.boost("q", ask=ask, merge=lambda p: "m")


def test_boost_merges_and_keeps_receipt():
    def ask(prompt, **kw):
        return [{"model": "a", "text": "x"}, {"model": "b", "text": "y"}]

    assert surface.boost("q", ask=ask, merge=lambda p: "final")["merged"] == "final"
    assert list((surface.home() / "boost").glob("*.json"))


def test_plan_gate_invalidates_edited_approval():
    plan = surface.new_plan("deploy site", body="1. deploy")
    assert surface.plan_gate(plan["id"])[0] is False
    surface.approve_plan(plan["id"])
    assert surface.plan_gate(plan["id"])[0] is True
    path = surface._plan_path(plan["id"])
    data = json.loads(path.read_text())
    data["body"] = "1. deploy and delete"
    path.write_text(json.dumps(data))
    assert surface.plan_gate(plan["id"])[0] is False


def test_compact_refuses_empty_summary():
    with pytest.raises(surface.SurfaceError):
        surface.compact("s1", "text", summarize=lambda p: " ", store=lambda *a, **k: None)


def test_compact_stores_under_domain():
    seen = {}
    surface.compact("s1", "x" * 30000, summarize=lambda p: "sum", store=lambda *a, **k: seen.update(k))
    assert seen["domain_key"] == "session-compact:s1"


def _skill(tmp_path):
    source = tmp_path / "demo"
    source.mkdir()
    (source / "SKILL.md").write_text("hello")
    return source


def test_bundle_round_trip(tmp_path):
    bundle = surface.pack(_skill(tmp_path), tmp_path / "demo.zip")
    surface.trust(surface.publisher_key())
    target = surface.install(bundle, tmp_path / "skills")
    assert (target / "SKILL.md").read_text() == "hello"


def test_untrusted_bundle_refused(tmp_path):
    bundle = surface.pack(_skill(tmp_path), tmp_path / "demo.zip")
    with pytest.raises(surface.SurfaceError, match="not trusted"):
        surface.install(bundle, tmp_path / "skills")


def test_tampered_bundle_refused(tmp_path):
    bundle = surface.pack(_skill(tmp_path), tmp_path / "demo.zip")
    surface.trust(surface.publisher_key())
    tampered = tmp_path / "bad.zip"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(tampered, "w") as dst:
        for item in src.namelist():
            dst.writestr(item, b"evil" if item.startswith("payload/") else src.read(item))
    with pytest.raises(surface.SurfaceError, match="digest"):
        surface.install(tampered, tmp_path / "skills")


@pytest.fixture
def console():
    sent = []
    handler = surface.console_handler("tok", {"127.0.0.1"}, lambda t, m: sent.append((t, m)))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", sent
    server.shutdown()


def _call(url, token=None, data=None, host=None):
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_console_requires_token(console):
    url, _ = console
    assert _call(url + "/api/state") == 401
    assert _call(url + "/api/state", "tok") == 200


def test_console_rejects_foreign_host(console):
    url, _ = console
    assert _call(url + "/", host="evil.example") == 403


def test_console_sends_message(console):
    url, sent = console
    assert _call(url + "/api/message", "tok", json.dumps({"target": "n", "text": "hi"}).encode()) == 200
    assert sent == [("n", "hi")]


def test_editing_goal_after_approval_needs_reapproval(tmp_path, monkeypatch):
    import inspect
    from nougen_shards import surface

    src = inspect.getsource(surface.plan_gate) + inspect.getsource(surface.approve_plan)
    assert "_plan_digest(plan)" in src
    a = surface._plan_digest({"goal": "read logs", "body": "step"})
    b = surface._plan_digest({"goal": "delete prod", "body": "step"})
    assert a != b
