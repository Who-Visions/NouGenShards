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
  NOUGEN_SNAPSHOT_LOCALIZE    "1" (default): copy the snapshot to container-
                              local disk before serving - sqlite FTS queries
                              do random page reads, which are unusable over a
                              FUSE mount (measured: a 2-term search exceeded
                              280s cold). "0" serves straight off the mount.
  NOUGEN_SNAPSHOT_REFRESH_S   how often to re-read LATEST.json (default 300)
  NOUGEN_CAPTURE_FORWARD_URL  where captures go (e.g. https://blade.nougenai.com)
  NGS_FORWARD_TOKEN           X-NGS-Token for the forward target (falls back
                              to NGS_NODE_TOKEN)
"""
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Single-flight guard for the localize copy. Without it, every concurrent
#: request that arrived before the copy finished started its OWN copy of the
#: same 10.7GB file set over the same destination paths - observed live
#: 2026-09-01 00:26Z onward as hours of colliding "localizing snapshot file"
#: log lines with the node's HTTP wedged behind them.
_LOCALIZE_LOCK = threading.Lock()

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
            resolved = _maybe_localize(cand, str(stamp))
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


def _localize_enabled() -> bool:
    return os.environ.get("NOUGEN_SNAPSHOT_LOCALIZE", "1").strip().lower() not in (
        "0", "false", "no", "off")


def _maybe_localize(remote_dir: Path, snap_stamp: str) -> Path:
    """Copy the snapshot to local disk once per stamp; serve locally.

    Sequential bulk copy over the mount is fine (one-time, streaming);
    per-query random page reads are not (a cold 2-term FTS search exceeded
    280s). Verification: each file's size must match after copy; a short or
    failed copy falls back to the remote dir rather than serving a torn file.
    Old localized stamps are pruned to bound disk use.
    """
    if not _localize_enabled():
        return remote_dir
    cache_root = Path(os.environ.get("NOUGEN_SNAPSHOT_CACHE",
                                     str(Path(tempfile.gettempdir())
                                         / "nougen_snapshot_cache")))
    local = cache_root / snap_stamp
    done_marker = local / ".complete"
    if done_marker.exists():
        return local
    # Single-flight: exactly one caller copies; everyone else serves the
    # mount (slow but alive) until .complete appears. Blocking here would
    # wedge every request behind a multi-GB copy - which is precisely how
    # the unlocked version failed.
    if not _LOCALIZE_LOCK.acquire(blocking=False):
        return remote_dir
    try:
        if done_marker.exists():
            return local
        local.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        total = 0
        for src in sorted(remote_dir.iterdir()):
            if not src.is_file():
                continue
            dst = local / src.name
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                continue
            logger.info("localizing snapshot file %s (%.0fMB)...",
                        src.name, src.stat().st_size / 1e6)
            part = local / (src.name + ".part")
            shutil.copyfile(src, part)
            if part.stat().st_size != src.stat().st_size:
                raise OSError(f"short copy of {src.name}")
            part.replace(dst)  # atomic: readers never see a torn file
            total += dst.stat().st_size
        done_marker.write_text("ok", encoding="utf-8")
        logger.info("snapshot %s localized: %.2fGB in %.0fs",
                    snap_stamp, total / 1e9, time.time() - t0)
        # prune older localized stamps
        for other in cache_root.iterdir():
            if other.is_dir() and other.name != snap_stamp:
                shutil.rmtree(other, ignore_errors=True)
        return local
    except OSError as exc:
        logger.error("snapshot localize failed (%s); serving from the mount "
                     "(SLOW but functional)", exc)
        return remote_dir
    finally:
        _LOCALIZE_LOCK.release()


def prewarm() -> None:
    """Start the localize copy in a daemon thread at process start, so the
    copy happens once at boot instead of inside the first unlucky request."""
    if not (enabled() and _localize_enabled()):
        return

    def _run():
        try:
            d = snapshot_dir()
            logger.info("snapshot prewarm resolved: %s", d)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("snapshot prewarm failed: %s", exc)

    threading.Thread(target=_run, name="snapshot-prewarm", daemon=True).start()


# Boot-time prewarm: importing this module on a snapshot-mode node begins the
# copy immediately. Requests arriving before it finishes serve the mount.
prewarm()


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
