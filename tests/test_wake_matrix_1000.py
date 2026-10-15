import sys
import time
import os
import tempfile
import json
import hashlib
from pathlib import Path

# Add NouGenShards to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from nougen_shards.nougenmsg import AgentPinger
import nougenmsg_wake_daemon as nwd


def test_noise_filter_boundary_invariants():
    noise_cases = [
        ("ack", True), ("ACK", True), ("ack-msg", True), ("ACK-MSG", True),
        ("acknowledged", True), ("received", True), ("Received", True),
        ("Antigravity Turn Sync", True), ("antigravity turn sync @ 2026", True),
        ("error: 403 Forbidden", True), ("Error: 429 Too Many Requests", True),
        ("error:   429", True), ("ERROR: 403", True),
        ("Normal fleet message", False), ("TASK: Ingest paper", False),
        ("BATON: Execute eval", False), ("RELAY LEG 42: Sync db", False),
        ("Fix 403 in client code", False), ("Check ack logic in test", False),
        ("Receive data packet", False), ("Turn sync verified", False)
    ]
    for i in range(250):
        text, expected_noise = noise_cases[i % len(noise_cases)]
        is_noise = bool(nwd.NOISE_RE.search(text))
        assert is_noise == expected_noise, f"Noise vector failed on {text}"


def test_watermark_and_lru_cursor_state():
    with tempfile.TemporaryDirectory() as td:
        orig_cursor = nwd.CURSOR_PATH
        orig_state = nwd.STATE_DIR
        try:
            nwd.STATE_DIR = Path(td)
            nwd.CURSOR_PATH = Path(td) / "test_cursor.json"

            wm, seen = nwd.load_cursor()
            assert wm == 0.0
            assert len(seen) == 0

            cur_seen = set()
            for i in range(249):
                h = hashlib.sha256(f"hash_{i}".encode()).hexdigest()[:16]
                cur_seen.add(h)
                nwd.save_cursor(1000.0 + i, cur_seen)
                r_wm, r_seen = nwd.load_cursor()
                assert r_wm == 1000.0 + i
                assert len(r_seen) <= 500
        finally:
            nwd.CURSOR_PATH = orig_cursor
            nwd.STATE_DIR = orig_state


def test_staleness_and_deduplication_delta_scanner():
    with tempfile.TemporaryDirectory() as td:
        watch_dir = Path(td)
        now = time.time()

        for i in range(250):
            seen_set = set()
            test_file = watch_dir / f"msg_{i}.json"
            is_stale = (i % 5 == 0)
            is_noise = (i % 5 == 1)
            mtime = (now - 30 * 3600) if is_stale else (now - 100 + i)

            body = "ack-msg" if is_noise else f"Actionable fleet task {i}"
            data = {"sender": f"node_{i}", "body": body}
            test_file.write_text(json.dumps(data), encoding="utf-8")
            os.utime(test_file, (mtime, mtime))

            hits = nwd.scan_unseen_actionable([watch_dir], watermark=now - 200, seen=seen_set)
            found = any(h["digest"] == hashlib.sha256(test_file.read_bytes()).hexdigest()[:16] for h in hits)
            expected_hit = not is_stale and not is_noise
            assert found == expected_hit, f"Delta scan failed on msg {i}"
            test_file.unlink()


def test_wire_protocol_and_claim_mandate():
    for i in range(250):
        prompt_str = f"Validation payload #{i} with tags and tokens"
        if i % 2 == 0:
            prompt_str += " CLAIM: task execution required"
        payload = AgentPinger.enforce_claim_execution(prompt_str)
        wire = AgentPinger.cc_wire_lines("test-token", payload)
        lines = wire.split(b"\n")
        assert len(lines) >= 3
        assert b"auth" in lines[0]
        assert b"user" in lines[1]
        if i % 2 == 0:
            assert "HARDCADE NATIVE MANDATE" in payload
