"""Tests for expanded fleet tools integrated into nougen CLI."""
import subprocess
import sys


def test_cli_tree_help():
    res = subprocess.run([sys.executable, "-m", "nougen_shards.cli", "tree", "--help"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "usage: nougen tree" in res.stdout
    assert "--health URL" in res.stdout


def test_cli_evidence_classes():
    res = subprocess.run([sys.executable, "-m", "nougen_shards.cli", "evidence"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0
    assert "evidence:measured" in res.stdout
    assert "evidence:verified" in res.stdout


def test_cli_viz_tokens():
    res = subprocess.run([sys.executable, "-m", "nougen_shards.cli", "viz", "--json"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert '"tokens"' in res.stdout or '"status"' in res.stdout


def test_cli_arxiv_help():
    res = subprocess.run([sys.executable, "-m", "nougen_shards.cli", "arxiv", "--help"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "usage: nougen arxiv" in res.stdout
    assert "{search,ingest}" in res.stdout


def test_cli_tube_help():
    res = subprocess.run([sys.executable, "-m", "nougen_shards.cli", "tube", "--help"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "usage: nougen tube" in res.stdout
    assert "--dry-run" in res.stdout


def test_cli_msg_help():
    res = subprocess.run([sys.executable, "-m", "nougen_shards.cli", "msg", "--help"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "usage: nougen msg" in res.stdout
    assert "--to TARGET" in res.stdout
