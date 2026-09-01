"""Snapshot mode: serve the grid from read-only snapshot artifacts.

Architecture decision B (GM, 2026-08-31): row-wise sqlite replication to
Space-local storage corrupted the grid on every backend tried - network-
backed mounts (persistent volume, then FUSE bucket mount) do not honor the
POSIX locking sqlite's write path requires. So the Space stops WRITING
sqlite entirely: blade publishes whole-file snapshots to the bucket
(tools/publish_vault_snapshot.py), this module points the grid at the
newest complete snapshot and opens it immutable, and captures are FORWARDED
to blade over the tunnel instead of written locally. No writes = no
corruption; restarts are trivially safe.

Activation is env-first: set NOUGEN_SNAPSHOT_DIR to the directory holding
snapshots/ (on the Space: /data, so LATEST.json lives at
/data/snapshots/LATEST.json). Unset = everything behaves exactly as before.

  NOUGEN_SNAPSHOT_DIR         root containing snapshots/LATEST.json
  NOUGEN_SNAPSHOT_REFRESH_S   how often to re-read LATEST.json (default 300)
  NOUGEN_CAPTURE_FORWARD_URL  where captures go (e.g. https://blade.nougenai.com)
  NGS_FORWARD_TOKEN           X-NGS-Token for the forward target (falls back
                              to NGS_NODE_TOKEN)
"""
import json
import logging
import os
import time
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_cache: dict = {"at": 0.0, "dir": None, "stamp": None}


def _refresh_s() -> float:
    raw = os.environ.get("NOUGEN_SNAPSHOT_REFRESH_S", "")
    try:
        return float(raw) if raw.strip() else 300.0
    except ValueError:
        logger.warning("NOUGEN_SNAPSHOT_REFRESH_S=%r invalid; using 300", raw)
        return 300.0


def root() -> Optional[Path]:
    raw = os.environ.get("NOUGEN_SNAPSHOT_DIR", "").strip()
    return Path(raw) if raw else None


def enabled() -> bool:
    return root() is not None


def snapshot_dir() -> Optional[Path]:
    """Directory of the newest COMPLETE snapshot, or None.

    LATEST.json is written last by the publisher, so a readable LATEST that
    names an existing directory is a complete set by construction. Cached for
    NOUGEN_SNAPSHOT_REFRESH_S so the hot read path costs one stat every few
    minutes, not one JSON parse per query.
    """
    base = root()
    if base is None:
        return None
    now = time.time()
    if _cache["dir"] is not None and now - _cache["at"] < _refresh_s():
        return _cache["dir"]
    latest = base / "snapshots" / "LATEST.json"
    resolved = None
    stamp = None
    try:
        meta = json.loads(latest.read_text(encoding="utf-8"))
        stamp = meta.get("stamp")
        cand = base / "snapshots" / str(stamp)
        if stamp and cand.is_dir():
            resolved = cand
        else:
            logger.warning("snapshot LATEST names %r but the directory is "
                           "missing; keeping previous snapshot", stamp)
            resolved = _cache["dir"]
            stamp = _cache["stamp"]
    except (OSError, ValueError) as exc:
        logger.warning("snapshot LATEST unreadable (%s); keeping previous "
                       "snapshot", exc)
        resolved = _cache["dir"]
        stamp = _cache["stamp"]
    _cache.update(at=now, dir=resolved, stamp=stamp)
    return resolved


def stamp() -> Optional[str]:
    snapshot_dir()
    return _cache["stamp"]


def forward_capture(payload: dict) -> dict:
    """Forward one capture to the writer node. Returns CaptureResult-shaped
    keys; never raises (a broken forward is a reported failure, not a 500)."""
    url = os.environ.get("NOUGEN_CAPTURE_FORWARD_URL", "").strip().rstrip("/")
    if not url:
        return {"captured": False, "reason": "error",
                "error": "snapshot mode without NOUGEN_CAPTURE_FORWARD_URL: "
                         "this node cannot write and has nowhere to forward"}
    token = (os.environ.get("NGS_FORWARD_TOKEN")
             or os.environ.get("NGS_NODE_TOKEN") or "")
    body = json.dumps({"shards": [payload]}).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/sync/push", data=body,
        headers={"Content-Type": "application/json", "X-NGS-Token": token})
    try:
        timeout = float(os.environ.get("NOUGEN_FORWARD_TIMEOUT_S", "20"))
    except ValueError:
        timeout = 20.0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            answer = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("capture forward to %s failed: %s: %s",
                     url, type(exc).__name__, exc)
        return {"captured": False, "reason": "error",
                "error": f"forward failed: {type(exc).__name__}"}
    if answer.get("count"):
        return {"captured": True, "reason": "forwarded"}
    if answer.get("skipped"):
        return {"captured": False, "reason": "duplicate"}
    return {"captured": False, "reason": "error",
            "error": f"forward target answered {answer}"}
