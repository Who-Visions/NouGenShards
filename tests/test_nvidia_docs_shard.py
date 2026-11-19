"""Unit tests for tools/nvidia_docs_shard.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import nvidia_docs_shard as nds


def test_norm_and_split_and_title():
    assert nds.norm("/nim/overview.md#intro") == "/nim/overview"
    assert nds.norm("https://docs.api.nvidia.com/ngc/index") == "/ngc/index"
    assert nds.norm("https://example.com/other") is None
    assert nds.norm("/assets/logo.png") is None

    assert nds.title_of("# NIM Overview\n\nBody", "/nim/overview") == "NIM Overview"
    assert nds.title_of("No heading here", "/nim/overview") == "overview"

    long_md = "# Title\n" + "\n## Sec A\n" + ("a" * 8000) + "\n## Sec B\n" + ("b" * 8000)
    parts = nds.split(long_md)
    assert len(parts) == 2
    assert all(len(p) <= nds.PART for p in parts)


def test_main_state_and_manifest_preservation_and_failure_handling(tmp_path, monkeypatch):
    out_dir = tmp_path / "canon"
    monkeypatch.setattr(nds, "OUT", out_dir)
    monkeypatch.setattr(nds, "sitemap_paths", lambda: ["/nim/a", "/nim/b"])
    monkeypatch.setattr(nds, "fetch", lambda url, tries=3: f"# Page {url.split('/')[-1]}\n\nContent for {url}")

    # First run: /nim/a succeeds, /nim/b fails capture
    def fake_capture_1(event_type, title, content, **kwargs):
        if "a.md" in title:
            return {"reason": "written", "shard_id": 101, "db_index": 1}
        return {"reason": "error"}

    monkeypatch.setattr(nds, "capture", fake_capture_1)
    rc1 = nds.main(["--max", "10", "--workers", "1"])
    assert rc1 == 2  # failed page returns non-zero

    state1 = json.loads((out_dir / "_state.json").read_text(encoding="utf-8"))
    manifest1 = json.loads((out_dir / "_manifest.json").read_text(encoding="utf-8"))
    assert "/nim/a" in state1
    assert "/nim/b" not in state1
    assert manifest1 == [{"path": "/nim/a", "part": 1, "shard": 101, "db": 1}]

    # Second run: /nim/a is skipped as unchanged (manifest preserved!), /nim/b now succeeds
    def fake_capture_2(event_type, title, content, **kwargs):
        return {"reason": "written", "shard_id": 202, "db_index": 2}

    monkeypatch.setattr(nds, "capture", fake_capture_2)
    rc2 = nds.main(["--max", "10", "--workers", "1"])
    assert rc2 == 0

    state2 = json.loads((out_dir / "_state.json").read_text(encoding="utf-8"))
    manifest2 = json.loads((out_dir / "_manifest.json").read_text(encoding="utf-8"))
    assert "/nim/a" in state2 and "/nim/b" in state2
    assert manifest2 == [
        {"path": "/nim/a", "part": 1, "shard": 101, "db": 1},
        {"path": "/nim/b", "part": 1, "shard": 202, "db": 2},
    ]
