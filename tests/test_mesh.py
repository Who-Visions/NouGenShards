"""NouGen mesh: identity, endpoints, repo discovery and cross-repo tool calls."""
import json
import re
import sys
from pathlib import Path

import pytest

from nougen_shards import mesh

_ENV = ("NOUGEN_ROOT", "NOUGEN_MESH_FILE", "NOUGEN_FLEET_NODE", "NOUGEN_NODE_NAME", "NOUGEN_MACHINE",
        "NOUGEN_AGENT", "NOUGEN_TENANT", "NOUGEN_FLEET_HOSTS_FILE", "NOUGEN_ENDPOINTS_FILE", "NOUGEN_INGRESS_URL",
        "NOUGEN_REPOS_DIR", "NOUGEN_OPEN_URL", "NOUGEN_OPEN_PORT", "NOUGEN_OPEN_DIR")


@pytest.fixture(autouse=True)
def clean_home(tmp_path, monkeypatch):
    for var in _ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NOUGEN_ROOT", str(tmp_path / "home"))
    monkeypatch.setattr(mesh, "_git_config", lambda key: "")
    monkeypatch.setattr(mesh, "_hostname", lambda: "tester-laptop")
    return tmp_path


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_fresh_box_is_standalone_and_names_itself():
    ident = mesh.identity()
    assert ident["node"] == "standalone"
    assert ident["machine"] == "tester-laptop"
    assert ident["agent"] == "unknown-agent"
    assert mesh.nodes() == {}
    assert mesh.ingress() is None
    assert mesh.self_address("claude") == "claude"


def test_env_beats_mesh_file_beats_box(monkeypatch, tmp_path):
    _write(tmp_path / "home" / "mesh.json", {"identity": {"machine": "from-file", "agent": "file-agent", "node": "lab"}})
    assert mesh.machine() == "from-file" and mesh.node() == "lab" and mesh.agent() == "file-agent"
    monkeypatch.setenv("NOUGEN_MACHINE", "From Env")
    monkeypatch.setenv("NOUGEN_FLEET_NODE", "edge1")
    assert mesh.machine() == "from-env"
    assert mesh.node() == "edge1"
    assert mesh.self_address("Claude Code") == "claude-code@edge1"


def test_existing_fleet_box_keeps_identity_from_fleet_hosts(monkeypatch, tmp_path):
    _write(tmp_path / "home" / "fleet_hosts.json", {"nodes": {"north": {"host_patterns": ["tester-lap"]}}})
    assert mesh.node() == "north"
    assert "north" in mesh.nodes()


def test_endpoints_local_remote_and_ingress(monkeypatch, tmp_path):
    assert mesh.endpoint("open") == "http://127.0.0.1:8765"
    assert mesh.endpoint("open-mcp") == "http://127.0.0.1:8767"
    monkeypatch.setenv("NOUGEN_OPEN_PORT", "9000")
    assert mesh.endpoint("open") == "http://127.0.0.1:9000"
    assert mesh.endpoint("shards", at="south") is None          # no ingress: never someone else's host
    _write(tmp_path / "home" / "endpoints.json", {"fleet_gateway_url": "https://door.example/"})
    assert mesh.endpoint("shards", at="south") == "https://door.example/south/shards"
    _write(tmp_path / "home" / "mesh.json", {"nodes": {"south": {"endpoints": {"shards": "https://s.example/"}}}})
    assert mesh.endpoint("shards", at="south") == "https://s.example"


def _fake_repo(root: Path, dirname: str, short: str, tools, module_src: str = "") -> Path:
    d = root / dirname
    (d / "src").mkdir(parents=True)
    (d / ".git").mkdir()
    if module_src:
        (d / "src" / f"fake_{short}.py").write_text(module_src, encoding="utf-8")
    _write(d / mesh.MANIFEST_FILE, {"schema": mesh.MANIFEST_SCHEMA, "repo": short, "tools": tools})
    return d


_SERVER_SRC = '''
class _T:
    def __init__(self, fn): self.fn = fn
class _M:
    def __init__(self): self.t = {}
    def get_tool(self, n): return self.t.get(n)
class Server:
    def __init__(self): self._tool_manager = _M()
    def tool(self, fn): self._tool_manager.t[fn.__name__] = _T(fn); return fn
server = Server()
@server.tool
def echo(text: str, times: int = 1):
    return {"echo": text * times}
@server.tool
async def later(x: int):
    return x + 1
def plain(a, b):
    return a + b
'''


def test_cross_repo_calls_python_mcp_and_cli(tmp_path):
    root = tmp_path / "repos"
    tools = [
        {"name": "echo", "transport": "mcp", "server": "fake_open:server"},
        {"name": "later", "transport": "mcp", "server": "fake_open:server"},
        {"name": "add", "transport": "python", "entry": "fake_open:plain"},
        {"name": "say", "transport": "cli", "argv": [sys.executable, "-c", "import json,sys;print(json.dumps(sys.argv[1:]))", "{word}", "{opt?}"]},
    ]
    _fake_repo(root, "NouGenOpen", "open", tools, _SERVER_SRC)
    me = _fake_repo(root, "nougenshards", "shards", [])
    near = str(me / "src")
    assert mesh.repo_dir("open", near) == root / "NouGenOpen"
    assert set(mesh.tools(near)) == {"open.echo", "open.later", "open.add", "open.say"}
    assert mesh.call("open.echo", {"text": "ab", "times": 2}, near=near) == {"echo": "abab"}
    assert mesh.call("open.later", {"x": 41}, near=near) == 42
    assert mesh.call("open.add", {"a": 2, "b": 3}, near=near) == 5
    assert mesh.call("open.say", {"word": "hi"}, near=near) == ["hi"]
    with pytest.raises(mesh.MeshError, match="missing argument"):
        mesh.call("open.say", {}, near=near)
    with pytest.raises(mesh.MeshError, match="not installed"):
        mesh.call("tracker.anything", {}, near=near)
    with pytest.raises(mesh.MeshError, match="only http"):
        mesh.call("open.echo", {"text": "x"}, near=near, at="south")


def test_setup_writes_this_boxs_identity_and_repos(tmp_path):
    root = tmp_path / "repos"
    me = _fake_repo(root, "NouGenShards", "shards", [])
    _fake_repo(root, "NouGenRelay", "relay", [])
    cfg = mesh.setup(near=str(me), agent_name="tester-claude")
    assert cfg["identity"] == {"machine": "tester-laptop", "agent": "tester-claude", "node": "standalone"}
    assert set(cfg["repos"]) == {"shards", "relay"}
    on_disk = json.loads((tmp_path / "home" / "mesh.json").read_text())
    assert on_disk["schema"] == mesh.CONFIG_SCHEMA
    # a second run keeps what the tester chose
    assert mesh.setup(near=str(me))["identity"]["agent"] == "tester-claude"
    doc = mesh.doctor(str(me))
    assert doc["repos"]["relay"] and doc["repos"]["open"] is None


def test_shards_manifest_is_current_and_carries_no_fleet_names():
    repo = Path(__file__).resolve().parents[1]
    data = json.loads((repo / mesh.MANIFEST_FILE).read_text(encoding="utf-8"))
    assert data["schema"] == mesh.MANIFEST_SCHEMA and data["repo"] == "shards"
    assert len(data["tools"]) >= 50
    assert all(t["transport"] in ("mcp", "python", "cli", "http") for t in data["tools"])


_FLEET_WORDS = re.compile(r"(?i)\b(blade|phoebus|whoart|kaedra|apollo|hyperion|nougenai\.com|whovisions|aiwithdav3|super)\b")


@pytest.mark.parametrize("rel", ["src/nougen_shards/mesh.py", "nougen.tools.json"])
def test_no_fleet_names(rel):
    text = (Path(__file__).resolve().parents[1] / rel).read_text(encoding="utf-8")
    assert not _FLEET_WORDS.search(text), _FLEET_WORDS.search(text)


def test_services_start_status_stop_and_need_config(tmp_path, monkeypatch):
    root = tmp_path / "repos"
    d = _fake_repo(root, "NouGenOpen", "open", [])
    (d / "srv.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    m = json.loads((d / mesh.MANIFEST_FILE).read_text())
    m["services"] = [{"name": "open", "argv": ["python", "srv.py", "{port}"], "env": {"X_PORT": "{port}"}},
                     {"name": "gated", "argv": ["python", "srv.py"], "env_required": ["NEEDS_TOKEN_X"]}]
    (d / mesh.MANIFEST_FILE).write_text(json.dumps(m))
    monkeypatch.setenv("NOUGEN_OPEN_PORT", "59871")
    near = str(d)
    up = mesh.start(near=near)
    assert up["open"]["state"] == "started" and up["gated"] == {"repo": "open", "state": "needs_config", "set": ["NEEDS_TOKEN_X"]}
    st = mesh.status(near)
    assert st["open"]["pid"] == up["open"]["pid"] and st["open"]["url"] == "http://127.0.0.1:59871"
    assert mesh.start(["open"], near=near)["open"]["state"] == "already_up"
    assert mesh.stop(["open"], near=near) == {"open": "stopped", "gated": "not_running"}   # a repo name covers its services
    assert mesh.stop(["open"], near=near)["open"] == "not_running"


def test_install_clones_only_missing_repos_from_the_package_file(tmp_path):
    src = tmp_path / "src-relay"
    src.mkdir()
    import subprocess
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    subprocess.run(["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    pkg = _write(tmp_path / "pkg.json", {"repos": {"relay": {"clone": str(src)}}})
    root = tmp_path / "repos"
    me = _fake_repo(root, "NouGenShards", "shards", [])
    out = mesh.install(str(root), source=str(pkg), only=["shards", "relay", "msg"], near=str(me))
    assert out["shards"]["state"] == "present"
    assert out["relay"]["state"] == "cloned" and (root / "NouGenRelay" / ".git").exists()
    assert out["msg"]["state"] == "no_source"


def test_cli_args_accept_key_value_or_json():
    assert mesh.parse_args(['{"a": 1}']) == {"a": 1}
    assert mesh.parse_args(["prompt=hi there", "n=3", "flag=true"]) == {"prompt": "hi there", "n": 3, "flag": True}
    with pytest.raises(ValueError):
        mesh.parse_args(["bare"])


def test_nougen_cli_forwards_mesh_verbs(monkeypatch, capsys):
    from nougen_shards import cli
    seen = {}
    monkeypatch.setattr(mesh, "main", lambda argv: seen.setdefault("argv", argv) and 0)
    for argv, want in ((["nougen", "mesh", "doctor"], ["doctor"]), (["nougen", "call", "open.x", "a=1"], ["call", "open.x", "a=1"])):
        seen.clear()
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit):
            cli.main()
        assert seen["argv"] == want


def test_http_rpc_tools_call_a_remote_mcp_server(tmp_path, monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["auth"] = self.headers.get("Authorization")
            name = seen["body"]["params"]["name"]
            if name == "boom":
                reply = {"jsonrpc": "2.0", "id": 1, "result": {"isError": True, "content": [{"type": "text", "text": "nope"}]}}
            else:
                reply = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": '{"ok": true}'}]}}
            out = ("event: message\ndata: " + json.dumps(reply) + "\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    root = tmp_path / "repos"
    tools = [{"name": "latest", "transport": "http", "path": "/mcp", "rpc": "tools/call"},
             {"name": "boom", "transport": "http", "path": "/mcp", "rpc": "tools/call"}]
    _fake_repo(root, "nougen-fleet-mcp", "fleet-mcp", tools)
    me = _fake_repo(root, "NouGenShards", "shards", [])
    monkeypatch.setenv("NOUGEN_FLEET_MCP_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("NOUGEN_FLEET_MCP_TOKEN", "t0k")
    try:
        assert mesh.call("fleet-mcp.latest", {"limit": 2}, near=str(me)) == {"ok": True}
        assert seen["body"]["method"] == "tools/call"
        assert seen["body"]["params"] == {"name": "latest", "arguments": {"limit": 2}}
        assert seen["auth"] == "Bearer t0k"
        with pytest.raises(mesh.MeshError, match="nope"):
            mesh.call("fleet-mcp.boom", {}, near=str(me))
    finally:
        srv.shutdown()
