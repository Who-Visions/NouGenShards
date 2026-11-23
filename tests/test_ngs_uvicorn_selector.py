"""The node runs on the selector loop on Windows (WinError 64 closes Proactor's listener)."""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import ngs_node_serve  # noqa: E402


def test_windows_command_adds_selector_loop(monkeypatch):
    monkeypatch.delenv("NOUGEN_NODE_LOOP", raising=False)
    cmd = ngs_node_serve.node_command("0.0.0.0", 4444, platform="win32")
    assert cmd[1:3] == ["-m", "uvicorn"]
    assert cmd[-2:] == ["--loop", "asyncio:SelectorEventLoop"]


def test_proactor_opt_out_and_non_windows_keep_default_loop(monkeypatch):
    monkeypatch.setenv("NOUGEN_NODE_LOOP", "proactor")
    assert "--loop" not in ngs_node_serve.node_command("h", 1, platform="win32")
    monkeypatch.delenv("NOUGEN_NODE_LOOP", raising=False)
    assert "--loop" not in ngs_node_serve.node_command("h", 1, platform="linux")


@pytest.mark.skipif(sys.platform != "win32", reason="the selector loop flag is Windows-only")
def test_uvicorn_serves_on_selector_loop_with_the_node_flag(tmp_path):
    """End to end with the exact flag the node uses: uvicorn serves, on a selector loop."""
    (tmp_path / "tinyapp.py").write_text(
        "async def app(scope, receive, send):\n"
        "    if scope['type'] != 'http':\n        return\n"
        "    import asyncio\n"
        "    body = type(asyncio.get_running_loop()).__name__.encode()\n"
        "    await send({'type': 'http.response.start', 'status': 200, 'headers': []})\n"
        "    await send({'type': 'http.response.body', 'body': body})\n")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tinyapp:app", "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "warning", "--loop", ngs_node_serve.WINDOWS_LOOP],
        cwd=str(tmp_path), env={**os.environ, "PYTHONPATH": str(tmp_path)})
    try:
        body = None
        for _ in range(60):
            try:
                body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1).read().decode()
                break
            except OSError:
                time.sleep(0.25)
        assert body is not None, "uvicorn never served"
        assert "Selector" in body, body
    finally:
        proc.terminate()
        proc.wait(10)
