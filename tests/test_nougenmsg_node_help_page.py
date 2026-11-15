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
