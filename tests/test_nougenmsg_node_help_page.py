"""A browser opening the node's address gets a usage page; API clients still get JSON status.

msgs.nougenai.com fronts this node. Before this page, a person or agent that opened the
address saw only a 404 or a JSON blob, with nothing about how to send.
"""
import importlib.util
import json
import sys
import threading
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
TOKEN = "s3cret-node-token-value"


def _load_node(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", TOKEN)
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("nougenmsg_node_help_t", TOOLS / "nougenmsg_node.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get(port, path, accept):
    req = urllib.request.Request("http://127.0.0.1:{}{}".format(port, path), headers={"Accept": accept})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.headers.get("Content-Type", ""), r.read().decode()


def test_browser_gets_help_page_and_api_gets_status(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    server = node.BoundedThreadingHTTPServer(("127.0.0.1", 0), node.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        ctype, body = _get(port, "/", "text/html,application/xhtml+xml")
        assert ctype.startswith("text/html")
        assert "NouGenMsg" in body and "/msg" in body and "NOUGEN_AGY_MSG_TOKEN" in body
        assert TOKEN not in body  # names the key, never its value

        ctype, body = _get(port, "/", "application/json")
        assert ctype.startswith("application/json")
        assert json.loads(body)["service"] == "agy-msg"

        ctype, body = _get(port, "/health", "text/html")
        assert json.loads(body)["ok"] is True  # probes stay JSON regardless of Accept
    finally:
        server.shutdown()


def test_help_page_uses_the_opened_host_and_shows_live_status(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    page = node.help_page("phoebus.nougenai.com", 3)
    assert "https://phoebus.nougenai.com/msg" in page
    assert "3 waiting" in page
    assert node.html.escape(str(node.NODE)) in page
    assert "{{" not in page


def test_help_page_never_echoes_a_hostile_host(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    for bad in ['evil.com"><script>alert(1)</script>', "a b", "", None]:
        page = node.help_page(bad, 0)
        assert "<script>alert" not in page
        assert "https://msgs.nougenai.com/msg" in page
    assert "http://127.0.0.1:8766/msg" in node.help_page("127.0.0.1:8766", 0)


def test_designed_template_is_served_and_falls_back_cleanly(monkeypatch, tmp_path):
    node = _load_node(monkeypatch, tmp_path)
    page = node.help_page("msgs.nougenai.com", 2)
    assert node._HELP_FILE.exists()
    assert "Fleet message bus" in page and "2 waiting" in page
    assert "https://msgs.nougenai.com/msg" in page and "{{" not in page
    for banned in ("cdn.", "googleapis", "tailwind", "<link"):
        assert banned not in page.lower()
    monkeypatch.setattr(node, "_HELP_FILE", tmp_path / "missing.html")
    fallback = node.help_page("msgs.nougenai.com", 0)
    assert "NouGenMsg" in fallback and "https://msgs.nougenai.com/msg" in fallback and "{{" not in fallback
