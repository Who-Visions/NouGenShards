"""Tests for nougen_shards.tree_probe (process provenance / import resolution)."""
from __future__ import annotations

import json
import os

from nougen_shards import tree_probe as tp


def test_run_returns_empty_when_binary_missing(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("ps")

    monkeypatch.setattr(tp.subprocess, "run", boom)
    assert tp._run(["ps"]) == ""


def test_find_pids_filters_and_skips_self(monkeypatch):
    out = (
        "  101 python app.py --serve\n"
        "202 python tree_probe.py app.py\n"
        "\n"
        "303 bash other.sh\n"
        "abc python app.py\n"
        "404 /usr/bin/python3 /srv/app.py\n"
    )
    monkeypatch.setattr(tp, "_run", lambda cmd: out)
    assert tp.find_pids("app.py") == [
        (101, "python app.py --serve"),
        (404, "/usr/bin/python3 /srv/app.py"),
    ]


def test_cwd_of_parses_lsof_field_output(monkeypatch):
    monkeypatch.setattr(tp, "_run", lambda cmd: "p123\nfcwd\nn/srv/app\n")
    assert tp.cwd_of(123) == "/srv/app"


def test_cwd_of_none_when_unavailable(monkeypatch):
    monkeypatch.setattr(tp, "_run", lambda cmd: "")
    assert tp.cwd_of(123) is None


def test_pythonpath_of_reads_process_env(monkeypatch):
    monkeypatch.setattr(tp, "_run", lambda cmd: "123 ?? S python app.py HOME=/h PYTHONPATH=/a:/b LANG=C")
    assert tp.pythonpath_of(123) == "/a:/b"


def test_pythonpath_of_none_when_absent(monkeypatch):
    monkeypatch.setattr(tp, "_run", lambda cmd: "123 python HOME=/h")
    assert tp.pythonpath_of(123) is None


def test_resolve_module_roots_order_and_dedupe(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    (a / "pkg").mkdir(parents=True)
    (b / "src" / "pkg").mkdir(parents=True)
    (a / "pkg" / "mod.py").write_text("x")
    (b / "src" / "pkg" / "mod.py").write_text("y")
    hits = tp.resolve_module_roots("pkg.mod", [str(a), "", str(b), str(a)])
    assert hits == [
        str(a / "pkg" / "mod.py"),
        str(b / "src" / "pkg" / "mod.py"),
    ]


def test_resolve_module_roots_no_match(tmp_path):
    assert tp.resolve_module_roots("pkg.mod", [str(tmp_path)]) == []


def test_count_marker(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("re.compile(a)\nre.compile(b)\nother\n")
    assert tp.count_marker(str(f), r"re\.compile") == 2
    assert tp.count_marker(str(tmp_path / "missing.py"), "x") == -1


def test_inspect_node_health_appends_health_and_parses(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode()

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(tp.urllib.request, "urlopen", fake_urlopen)
    assert tp.inspect_node_health("http://node:1/", timeout=3) == {"ok": True}
    assert seen == {"url": "http://node:1/health", "timeout": 3}
    tp.inspect_node_health("http://node:1/health")
    assert seen["url"] == "http://node:1/health"


def test_probe_local_tree_no_process(monkeypatch):
    monkeypatch.setattr(tp, "find_pids", lambda p: [])
    res = tp.probe_local_tree(proc_pattern="zzz")
    assert res["status"] == "error" and res["processes"] == []


def _fixture_tree(tmp_path, n):
    mod = tmp_path / "pkg" / "mod.py"
    mod.parent.mkdir(parents=True)
    mod.write_text("re.compile(1)\n" * n)
    return mod


def test_probe_local_tree_ok_and_mismatch(monkeypatch, tmp_path):
    mod = _fixture_tree(tmp_path, 3)
    monkeypatch.setattr(tp, "find_pids", lambda p: [(7, "python app.py")])
    monkeypatch.setattr(tp, "cwd_of", lambda pid: str(tmp_path))
    monkeypatch.setattr(tp, "pythonpath_of", lambda pid: None)

    ok = tp.probe_local_tree(module="pkg.mod", expect=3)
    assert ok["status"] == "ok"
    assert ok["processes"][0]["resolved_file"] == str(mod)
    assert ok["processes"][0]["marker_count"] == 3

    bad = tp.probe_local_tree(module="pkg.mod", expect=5)
    assert bad["status"] == "mismatch"
    assert bad["processes"][0]["is_expected"] is False

    assert tp.probe_local_tree(module="pkg.mod", expect=None)["status"] == "ok"


def test_probe_local_tree_unresolved_module_is_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(tp, "find_pids", lambda p: [(7, "python app.py")])
    monkeypatch.setattr(tp, "cwd_of", lambda pid: str(tmp_path))
    monkeypatch.setattr(tp, "pythonpath_of", lambda pid: os.pathsep.join(["", str(tmp_path)]))
    res = tp.probe_local_tree(module="nope.mod", expect=None)
    assert res["status"] == "mismatch"
    assert res["processes"][0]["resolved_file"] is None
