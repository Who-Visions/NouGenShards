"""POST /msg concurrency is bounded: excess connections get 503, not a new thread (WG-1011)."""
import importlib.util
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def _load_node():
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("nougenmsg_node_inflight_t", TOOLS / "nougenmsg_node.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Block(BaseHTTPRequestHandler):
    gate = None

    def do_GET(self):
        _Block.gate.wait(5)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


def _request(port):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
    data = b""
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    finally:
        s.close()
    return data


def test_excess_connections_get_503_past_cap():
    node = _load_node()
    _Block.gate = threading.Event()
    server = node.BoundedThreadingHTTPServer(("127.0.0.1", 0), _Block, max_inflight=1)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        holder = {}
        first = threading.Thread(target=lambda: holder.setdefault("r", _request(port)), daemon=True)
        first.start()
        # Wait until the first handler holds the only slot.
        for _ in range(200):
            if server._slots._value == 0:
                break
            threading.Event().wait(0.01)
        second = _request(port)
        assert second.startswith(b"HTTP/1.1 503"), second[:60]
        _Block.gate.set()
        first.join(5)
        assert b" 200 " in holder["r"].split(b"\r\n")[0]
        # Slot released: a new request succeeds.
        assert b" 200 " in _request(port).split(b"\r\n")[0]
    finally:
        _Block.gate.set()
        server.shutdown()
        server.server_close()
