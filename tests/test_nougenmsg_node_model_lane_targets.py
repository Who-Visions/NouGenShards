"""Model-lane targets are local to the node, so the local-only receiver must accept them.

The bus writes a model as '<lane>:<model>' ('@ollama:gemma4:e2b-qat') and
NouGenMsgBus.parse_destination resolves that to this node. The receiver's own check read
the part before the colon as a node name and refused it as cross-node.
"""
import importlib
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

TOKEN = "model-lane-test-token"
AUTH = {"Content-Type": "application/json", "X-NGS-Token": TOKEN}


@pytest.fixture()
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUGEN_NODE_NAME", "phoebus")
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", TOKEN)
    monkeypatch.setenv("NOUGEN_AGY_MSG_AUTH", "required")
    monkeypatch.setenv("NOUGEN_AGY_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("NOUGEN_MSG_STATE", str(tmp_path / "state.json"))
    for name in [m for m in sys.modules if m.startswith(("nougenmsg_node", "_agy_live"))]:
        del sys.modules[name]
    node = importlib.import_module("nougenmsg_node")
    monkeypatch.setattr(node, "gate_and_deliver", lambda *a, **k: {"attempted": False})
    srv = node.ThreadingHTTPServer(("127.0.0.1", 0), node.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield node, port
    srv.shutdown()
    srv.server_close()


def _post(port, target):
    data = json.dumps({"text": "ping {}".format(target), "sender": "probe", "target": target}).encode()
    req = urllib.request.Request("http://127.0.0.1:{}/msg".format(port), data=data, headers=AUTH, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


@pytest.mark.parametrize(
    "target",
    ["@ollama:gemma4:e2b-qat", "ollama:gemma4:31b-cloud", "@openrouter:nvidia/some-model",
     "@ollama", "openrouter", "@agents", "@phoebus:ollama:gemma4:e2b-qat"],
)
def test_model_lane_target_is_local(server, target):
    _node, port = server
    code, body = _post(port, target)
    assert code == 200, body
    assert body["delivered"] is True and body["node"] == "phoebus"


@pytest.mark.parametrize("target", ["@blade:ollama:gemma4:e2b-qat", "@whoart:openrouter:nvidia/x"])
def test_model_lane_on_another_node_is_still_refused(server, target):
    node, port = server
    code, body = _post(port, target)
    assert code == 422 and body["status"] == "not_routed" and body["delivered"] is False
    assert not list(node.INBOX.glob("*.json"))
