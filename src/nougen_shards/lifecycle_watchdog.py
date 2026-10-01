"""Watchdog for the durable message lifecycle: it makes ACK != DONE enforce itself.

The lifecycle (claim_lifecycle + codex_pipe) records who owns a message, for how long,
and what they have proved. Nothing ran it, so three failures went unnoticed:

* a worker disappeared: its lease expired but the message stayed "claimed" forever;
* a worker kept heartbeating without doing anything: the lease renews, so expiry never fires;
* an agent acked an actionable message and never took it: nobody was woken.

sweep() closes all three, in this order:

1. expired leases are reclaimed and the old worker is fenced (lease 0, new epoch on the next claim);
2. claims that are alive but have made no progress (no checkpoint) for no_progress_s are
   reclaimed the same way: a heartbeat proves a process exists, a checkpoint proves work;
3. actionable messages acked but unclaimed for longer than dispatch_grace_s are reported
   and, if a wake function is given, the lane is nudged, at most once per grace window.

Reclaimed messages return to ACKED/pending in the JSON record, so every pending view shows
them as claimable again. dry_run reports all of it and changes nothing.

Metrics are part of the report: the "ghost agent" count (acked, actionable, unclaimed) and
its oldest age are the numbers that say whether the fleet is being driven or only notified.
"""
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from . import codex_pipe
from .claim_lifecycle import ClaimLifecycleManager

DEFAULT_DISPATCH_GRACE_S = 300
DEFAULT_NO_PROGRESS_S = 900

Wake = Callable[[Dict[str, Any]], bool]


def wake_text(entry: Dict[str, Any]) -> str:
    minutes = max(1, int(round(float(entry.get("age_s", 0)) / 60)))
    mid = entry["message_id"]
    return (f"[LIFECYCLE WATCHDOG] message {mid} was acknowledged {minutes} min ago but nobody has claimed it. "
            f"An ACK is a receipt, not work. Run `nougen live take-msg {mid}` and execute it, or "
            f"`nougen live cancel-msg {mid} <reason>` if it is not needed.")


def _delivered(result: Any) -> bool:
    """Did a NouGenMsgBus.live_ping actually reach a live lane?

    live_ping returns results keyed by lane (claude_pipes / antigravity / codex), not one flat
    field. A message that was only "saved" to an inbox file has NOT woken anyone, so it does not
    count; any one lane accepting it is enough."""
    if not isinstance(result, dict) or "skipped" in result:
        return False
    for lane in result.values():
        if not isinstance(lane, dict):
            continue
        if lane.get("delivered") or lane.get("status") in ("delivered", "queued"):
            return True
    return False


def default_wake(entry: Dict[str, Any]) -> bool:
    """Nudge the lane that acknowledged the message, over NouGenMsg. True only if a live lane took it."""
    from .nougenmsg import NouGenMsgBus  # pylint: disable=import-outside-toplevel
    return _delivered(NouGenMsgBus.live_ping(entry.get("consumer") or "codex", wake_text(entry)))


def _parse_iso(value: Any) -> Optional[float]:
    try:
        return datetime.fromisoformat(str(value)).astimezone(timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _records(inbox: Optional[str]) -> List[Dict[str, Any]]:
    """Every lifecycle record across the candidate inboxes, one per message id."""
    import json  # pylint: disable=import-outside-toplevel
    seen: Dict[str, Dict[str, Any]] = {}
    for root in codex_pipe._candidate_inbox_dirs(inbox=inbox):  # pylint: disable=protected-access
        folder = root / "lifecycle"
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            mid = record.get("message_id")
            if mid and mid not in seen:
                seen[mid] = record
    return list(seen.values())


def _unclaimed_since(record: Dict[str, Any]) -> Optional[float]:
    history = record.get("history") or []
    return _parse_iso(history[-1].get("at")) if history else None


def sweep(*, inbox: Optional[str] = None, now: Optional[float] = None,
          dispatch_grace_s: int = DEFAULT_DISPATCH_GRACE_S, no_progress_s: int = DEFAULT_NO_PROGRESS_S,
          wake: Optional[Wake] = None, dry_run: bool = False,
          manager: Optional[ClaimLifecycleManager] = None) -> Dict[str, Any]:
    """One watchdog pass. See the module docstring."""
    now = time.time() if now is None else now
    mgr = manager or ClaimLifecycleManager()
    report: Dict[str, Any] = {"dry_run": dry_run, "reclaimed": [], "stalled": [], "needs_claim": [],
                              "woken": [], "wake_failed": []}

    # 1. expired leases
    expired = mgr.find_expired_leases()
    if expired and not dry_run:
        mgr.detect_and_reclaim_stale()
    for item in expired:
        report["reclaimed"].append({"msg_id": item["msg_id"], "previous_lane": item["previous_lane"],
                                    "epoch": item["epoch"], "reason": "lease expired"})
        if not dry_run:
            codex_pipe.release_claim(item["msg_id"], f"lease expired for {item['previous_lane']}", inbox=inbox)

    # 2. alive but not progressing
    for item in mgr.detect_stalled(no_progress_s, now=now):
        entry = {"msg_id": item["msg_id"], "agent_lane": item["agent_lane"], "epoch": item["epoch"],
                 "idle_seconds": round(item["idle_seconds"], 1), "progress_count": item["progress_count"]}
        report["stalled"].append(entry)
        if not dry_run:
            reason = f"no progress for {int(item['idle_seconds'])}s ({item['progress_count']} checkpoints)"
            if mgr.reclaim_stalled(item["msg_id"], item["epoch"], reason):
                codex_pipe.release_claim(item["msg_id"], reason, inbox=inbox)

    # 3. acked, actionable, nobody took it
    pending_total = unclaimed_total = 0
    oldest = 0.0
    for record in _records(inbox):
        if not record.get("pending_execution"):
            continue
        pending_total += 1
        if record.get("state") != "ACKED":
            continue
        unclaimed_total += 1
        since = _unclaimed_since(record)
        age = max(0.0, now - since) if since is not None else 0.0
        oldest = max(oldest, age)
        if age <= dispatch_grace_s:
            continue
        history = record.get("history") or []
        entry = {"message_id": record["message_id"], "age_s": round(age, 1),
                 "consumer": (history[0].get("consumer") if history else None) or "codex",
                 "wake_count": int(record.get("wake_count") or 0)}
        report["needs_claim"].append(entry)
        if wake is None or dry_run:
            continue
        last_woken = record.get("last_woken_at")
        if last_woken is not None and now - float(last_woken) < dispatch_grace_s:
            continue
        try:
            delivered = wake(entry)
        except Exception as exc:  # a dead pipe must not stop the sweep
            report["wake_failed"].append({"message_id": entry["message_id"], "error": str(exc)})
            continue
        if delivered:
            codex_pipe.note_wake(entry["message_id"], now, inbox=inbox)
            report["woken"].append(entry["message_id"])
        else:
            report["wake_failed"].append({"message_id": entry["message_id"], "error": "wake was not delivered"})

    report["metrics"] = {
        "pending_total": pending_total,
        "unclaimed_total": unclaimed_total,
        "oldest_unclaimed_age_s": round(oldest, 1),
        "stalled_count": len(report["stalled"]),
        "reclaimed_count": len(report["reclaimed"]),
        "needs_claim_count": len(report["needs_claim"]),
    }
    return report


def run_loop(*, every_s: int = 60, iterations: Optional[int] = None,
             sleep: Callable[[float], Any] = time.sleep, **sweep_kwargs) -> List[Dict[str, Any]]:
    """Sweep repeatedly. `iterations=None` runs until interrupted (Ctrl-C returns what ran)."""
    reports: List[Dict[str, Any]] = []
    try:
        while iterations is None or len(reports) < iterations:
            reports.append(sweep(**sweep_kwargs))
            if iterations is not None and len(reports) >= iterations:
                break
            sleep(every_s)
    except KeyboardInterrupt:
        pass
    return reports
