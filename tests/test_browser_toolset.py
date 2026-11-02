import http.server
import json
import threading

import pytest

from nougen_shards.browser_toolset import (
    ALLOW,
    APPROVAL_REQUIRED,
    BLOCK,
    BROWSER,
    COMPUTER,
    HALT_TEXT,
    AuditLog,
    ScopePolicy,
    ToolError,
    ToolsetConfigError,
    ToolsetRunner,
    UrlPolicy,
    make_confirmed_runner,
    validate_input,
)


class FakeDriver:
    def __init__(self, url="https://example.com/"):
        self.url = url
        self.calls = []
        self.fail_on = None

    def implemented(self):
        return {"navigate", "screenshot", "read_page", "left_click", "type", "list_tabs"}

    def page_url(self):
        return self.url

    def viewport(self):
        return (1280, 720)

    def browser_state(self):
        return {"type": "browser_state", "tabs": [
            {"tab_id": "t1", "title": "T", "url": self.url, "active": True}]}

    def call(self, member, tool_input):
        self.calls.append(member)
        if member == self.fail_on:
            raise RuntimeError("C:/secret/path exploded")
        if member == "screenshot":
            return b"png"
        return "done"


def block(name, tool_input=None, id_="t", toolset=BROWSER):
    return {"type": "tool_use", "id": id_, "name": name, "toolset_name": toolset,
            "input": tool_input or {}}


def runner(driver=None, policy=None, tmp=None):
    policy = policy or ScopePolicy(UrlPolicy(["example.com"]))
    return ToolsetRunner(driver or FakeDriver(), policy, AuditLog(tmp))


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "file:///etc/passwd", "data:text/html,x", "view-source:https://example.com",
    "http://127.0.0.1/", "http://localhost/", "http://169.254.169.254/latest", "http://[::1]/",
    "http://10.0.0.5/", "https://evil.test/", "https://example.com.evil.test/",
    "https://user:pw@example.com/", "https://evil.test\\@example.com/", "https://exa\nmple.com/", "",
])
def test_url_policy_refuses(url):
    assert UrlPolicy(["example.com"]).refusal(url)


@pytest.mark.parametrize("url", [
    "https://example.com/a", "http://docs.example.com/", "example.com/path", "about:blank",
    "HTTPS://EXAMPLE.COM/",
])
def test_url_policy_allows(url):
    assert UrlPolicy(["example.com"]).refusal(url) is None


def test_missing_policy_fails_closed(monkeypatch):
    assert UrlPolicy(None).refusal("https://example.com/") == "no URL policy configured"
    monkeypatch.delenv("NOUGEN_TOOLSET_ALLOWED_HOSTS", raising=False)
    assert UrlPolicy.from_env().refusal("https://example.com/") == "no URL policy configured"


def test_loopback_needs_listing_and_flag():
    assert UrlPolicy(["127.0.0.1"]).refusal("http://127.0.0.1:8000/")
    assert UrlPolicy(["127.0.0.1"], allow_private=True).refusal("http://127.0.0.1:8000/") is None
    assert UrlPolicy(["example.com"], allow_private=True).refusal("http://127.0.0.1/")


def test_verdicts_default_deny():
    policy = ScopePolicy(UrlPolicy(["example.com"]))
    assert policy.decide("read_page", {}).verdict == ALLOW
    assert policy.decide("navigate", {"url": "https://example.com"}).verdict == ALLOW
    assert policy.decide("navigate", {"url": "back"}).verdict == ALLOW
    assert policy.decide("navigate", {"url": "https://evil.test"}).verdict == BLOCK
    assert policy.decide("left_click", {}).verdict == APPROVAL_REQUIRED
    assert policy.decide("type", {"text": "x"}).verdict == APPROVAL_REQUIRED
    assert policy.decide("javascript_exec", {"text": "1"}).verdict == BLOCK
    assert policy.decide("made_up_member", {}).verdict == BLOCK


def test_dangerous_member_stays_gated_even_when_enabled():
    policy = ScopePolicy(UrlPolicy(["example.com"]), enabled_optional={"javascript_exec"})
    assert policy.decide("javascript_exec", {"text": "1"}).verdict == APPROVAL_REQUIRED
    with pytest.raises(ToolsetConfigError):
        ScopePolicy(UrlPolicy([]), auto_allow={"javascript_exec"})


def test_approval_binds_to_exact_call():
    policy = ScopePolicy(UrlPolicy(["example.com"]))
    click = {"target": {"type": "ref", "ref": "ref_1"}}
    key = policy.decide("left_click", click, "https://example.com/a").approval_key
    policy.approve(key)
    assert policy.decide("left_click", click, "https://example.com/a").verdict == ALLOW
    assert policy.decide("left_click", click, "https://example.com/b").verdict == APPROVAL_REQUIRED
    other = {"target": {"type": "ref", "ref": "ref_2"}}
    assert policy.decide("left_click", other, "https://example.com/a").verdict == APPROVAL_REQUIRED


@pytest.mark.parametrize("toolset", [BROWSER, COMPUTER])
def test_batch_halts_and_answers_every_block(toolset):
    driver = FakeDriver()
    driver.fail_on = "screenshot"
    r = runner(driver, ScopePolicy(UrlPolicy(["example.com"]), toolset=toolset))
    results = r.run_batch([
        block("screenshot", id_="a", toolset=toolset),
        block("zoom", {"region": [0, 0, 1, 1]}, id_="b", toolset=toolset),
        block("wait", {"duration": 1}, id_="c", toolset=toolset),
    ])
    assert [x["tool_use_id"] for x in results] == ["a", "b", "c"]
    assert all(x["toolset_name"] == toolset and x["is_error"] for x in results)
    assert results[1]["content"] == HALT_TEXT[toolset] == results[2]["content"]
    assert driver.calls == ["screenshot"]
    assert "secret" not in results[0]["content"]


def test_blocked_navigation_halts_and_never_reaches_driver():
    driver = FakeDriver()
    results = runner(driver).run_batch([
        block("navigate", {"url": "file:///etc/passwd"}, id_="a"), block("read_page", id_="b")])
    assert "refused" in results[0]["content"]
    assert results[1]["content"] == HALT_TEXT[BROWSER]
    assert driver.calls == []


def test_approval_required_then_approved():
    driver = FakeDriver()
    r = runner(driver)
    call = block("type", {"text": "hello"}, id_="a")
    first = r.run_batch([call])[0]
    assert first["is_error"] and "approval_required" in first["content"]
    assert driver.calls == []
    r.approve_pending(next(iter(r.pending)))
    assert "is_error" not in r.run_batch([call])[0]
    assert driver.calls == ["type"]
    with pytest.raises(ToolError):
        r.approve_pending("nope")


def test_confirmed_runner_asks_and_respects_no():
    driver = FakeDriver()
    asked = []
    run = make_confirmed_runner(driver, ScopePolicy(UrlPolicy(["example.com"])),
                                lambda c: asked.append(c) or False, AuditLog())
    assert run([block("left_click", {"target": {"type": "ref", "ref": "r"}})])[0]["is_error"]
    assert driver.calls == [] and asked[0]["member"] == "left_click"


def test_browser_results_carry_state_and_images():
    results = runner().run_batch([block("screenshot", id_="a"), block("list_tabs", id_="b")])
    assert results[0]["content"][0]["type"] == "image"
    assert results[0]["content"][-1]["type"] == "browser_state"
    assert [c["type"] for c in results[1]["content"]] == ["browser_state"]


def test_tools_entry_disables_unimplemented_members():
    entry = runner().tools_entry()
    assert entry["type"] == "browser_toolset_20260801"
    assert entry["configs"]["hover"] == {"enabled": False}
    assert "navigate" not in entry["configs"]


def test_validation_refuses_rather_than_clamps():
    validate_input("left_click", {"coordinate": [10, 10]}, (100, 100))
    for bad in ({"coordinate": [100, 10]}, {"coordinate": [-1, 0]}, {"coordinate": ["a", 1]},
                {"target": {"type": "coordinate", "x": 500, "y": 1}}, {"repeat": 1000},
                {"duration": 999}, {"scroll_amount": True}):
        with pytest.raises(ToolError):
            validate_input("x", bad, (100, 100))


def test_audit_records_blocks_and_never_logs_typed_text(tmp_path):
    log = tmp_path / "audit.jsonl"
    r = runner(tmp=log)
    r.run_batch([block("navigate", {"url": "https://evil.test"})])
    r.run_batch([block("type", {"text": "hunter2-password"})])
    raw = log.read_text()
    assert "hunter2" not in raw
    rows = [json.loads(line) for line in raw.splitlines()]
    assert [row["outcome"] for row in rows] == ["blocked", "awaiting_approval"]


def test_real_browser_end_to_end(tmp_path):
    pytest.importorskip("playwright")
    from nougen_shards.browser_toolset import PlaywrightDriver

    page = (b"<title>Local</title><h1>Hello</h1><div hidden>secret-hidden</div>"
            b"<button onclick=\"document.title='clicked'\">Press</button>"
            b"<img src='http://203.0.113.9/x.png'>")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    urls = UrlPolicy(["127.0.0.1"], allow_private=True)
    try:
        driver = PlaywrightDriver(urls)
    except Exception as exc:
        server.shutdown()
        pytest.skip(f"no Chrome here: {type(exc).__name__}")
    try:
        r = ToolsetRunner(driver, ScopePolicy(urls), AuditLog(tmp_path / "a.jsonl"))
        out = r.run_batch([block("navigate", {"url": base}, id_="a"), block("get_page_text", id_="b"),
                           block("read_page", id_="c")])
        assert not any(x.get("is_error") for x in out)
        assert "Hello" in out[1]["content"][0]["text"]
        assert "secret-hidden" not in out[1]["content"][0]["text"]
        assert "[ref_1]" in out[2]["content"][0]["text"]
        click = block("left_click", {"target": {"type": "ref", "ref": "ref_1"}})
        assert r.run_batch([click])[0]["is_error"]
        r.approve_pending(next(iter(r.pending)))
        result = r.run_batch([click])[0]
        assert result["content"][-1]["tabs"][0]["title"] == "clicked"
        stale = block("left_click", {"target": {"type": "ref", "ref": "ref_9"}})
        r.policy.approve(r.policy.decide("left_click", stale["input"], base).approval_key)
        assert "stale" in r.run_batch([stale])[0]["content"]
    finally:
        driver.close()
        server.shutdown()
