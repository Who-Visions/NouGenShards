"""The running process must be able to identify its own build.

Disk-based drift checks answer the wrong question. On 2026-09-03 a node
pulled canonical, every file matched byte-for-byte, and the still-running
process kept serving pre-pull code for the whole window between the pull and
the reload — reported as 5/5 MATCH throughout. These tests pin the property
that closes that class: the identifier comes from the file the process
actually loaded, so a reload that never happened cannot be mistaken for one
that did.
"""
from __future__ import annotations

import hashlib
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


@pytest.fixture
def node(monkeypatch):
    monkeypatch.setenv("NOUGEN_AGY_MSG_TOKEN", "t")
    sys.path.insert(0, str(TOOLS))
    sys.modules.pop("nougenmsg_node", None)
    mod = importlib.import_module("nougenmsg_node")
    yield mod
    sys.modules.pop("nougenmsg_node", None)
    sys.path.remove(str(TOOLS))


def test_build_id_is_the_hash_of_the_loaded_file(node):
    expected = hashlib.sha256((TOOLS / "nougenmsg_node.py").read_bytes()).hexdigest()[:12]
    assert node.build_id() == expected


def test_build_id_is_stable_across_calls(node):
    assert node.build_id() == node.build_id()


def test_build_id_appears_in_status_payload(node):
    # /status must carry it so a checker never has to scrape a log line.
    src = (TOOLS / "nougenmsg_node.py").read_text()
    assert '"build": build_id()' in src


def test_changing_the_file_changes_the_id(tmp_path):
    """The property that makes this useful: edit the file, the id moves.

    A disk-vs-canonical check cannot distinguish 'reloaded' from 'not
    reloaded'; an id derived from the loaded bytes can.
    """
    staged = tmp_path / "nougenmsg_node.py"
    shutil.copy(TOOLS / "nougenmsg_node.py", staged)
    shutil.copy(TOOLS / "_agy_live_delivery.py", tmp_path / "_agy_live_delivery.py")
    read = "import sys;sys.path.insert(0,{!r});import nougenmsg_node as m;print(m.build_id())".format(str(tmp_path))
    before = subprocess.run([sys.executable, "-c", read], capture_output=True, text=True,
                            env={"NOUGEN_AGY_MSG_TOKEN": "t", "PATH": "/usr/bin:/bin"}).stdout.strip()
    staged.write_text(staged.read_text() + "\n# a change on disk\n")
    after = subprocess.run([sys.executable, "-c", read], capture_output=True, text=True,
                           env={"NOUGEN_AGY_MSG_TOKEN": "t", "PATH": "/usr/bin:/bin"}).stdout.strip()
    assert before and after and before != after, (before, after)


def test_unreadable_file_yields_unknown_not_a_crash(node, monkeypatch):
    """Identifying yourself must never break startup, and 'unknown' must be
    distinguishable from a real id so a checker treats it as cannot-determine."""
    monkeypatch.setattr(node.Path, "resolve", lambda self: (_ for _ in ()).throw(OSError("gone")))
    assert node.build_id() == "unknown"
