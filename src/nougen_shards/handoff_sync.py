"""Move handoff records between computers.

Triggers make a shared `.handoffs` directory actionable; this is what gets the
files there. The transport is plain git: the handoff directory becomes its own
small repository with its own remote, independent of the project repo (whose
`.gitignore` deliberately keeps handoffs out of source history).

Records are separate files per handoff, so two machines writing at the same
time normally merge without touching each other. When they do collide, the
merge is aborted and reported rather than guessed at — a silently mangled
handoff is worse than one that needs a human.

Arrival is the interesting half. A record that lands here from another box has
never fired its `created` triggers on this machine, so sync replays them for
newly-arrived remote records. That is what lets the Mac react to work the PC
finished while it was asleep.
"""

import json
import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import machine

STATUS_RANK = {
    "open": 0,
    "active": 1,
    "claimed": 1,
    "held": 1,
    "in_progress": 1,
    "started": 1,
    "blocked": 1,
    "acknowledged": 1,
    "acked": 1,
    "accepted": 1,
    "released": 2,
    "complete": 2,
    "completed": 2,
    "stale-complete": 2,
    "done": 2,
}


def status_rank(status: Optional[str]) -> int:
    """Integer rank for leg/handoff status."""
    if not status:
        return 0
    return STATUS_RANK.get(str(status).strip().lower(), 0)


def advance_status(local_status: Optional[str], remote_status: Optional[str]) -> str:
    """Leg status only advances (open->acked->done), never regresses to an older status."""
    r_local = status_rank(local_status)
    r_remote = status_rank(remote_status)
    if r_local > r_remote:
        return str(local_status)
    elif r_remote > r_local:
        return str(remote_status)
    else:
        return str(local_status or remote_status or "open")


def _event_dedupe_key(e: Dict[str, Any]) -> tuple:
    ev = str(e.get("event") or e.get("event_type") or e.get("state") or "").strip().lower()
    ag = str(e.get("agent") or "").strip().lower()
    ts = str(e.get("timestamp") or e.get("created_utc") or e.get("when") or "").strip()
    return (ev, ag, ts)


def union_events(
    local_events: Optional[List[Dict[str, Any]]],
    remote_events: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Union events across both copies, deduped by (event, agent, timestamp)."""
    merged_by_key: Dict[tuple, Dict[str, Any]] = {}
    key_order: List[tuple] = []
    for e in (local_events or []) + (remote_events or []):
        if not isinstance(e, dict):
            continue
        k = _event_dedupe_key(e)
        if k in merged_by_key:
            existing = merged_by_key[k]
            combined = dict(e)
            combined.update({key: val for key, val in existing.items() if val not in (None, "")})
            merged_by_key[k] = combined
        else:
            merged_by_key[k] = dict(e)
            key_order.append(k)

    def _sort_ts(k: tuple) -> str:
        item = merged_by_key[k]
        return str(item.get("timestamp") or item.get("created_utc") or item.get("when") or "")

    key_order.sort(key=_sort_ts)
    return [merged_by_key[k] for k in key_order]


def _checkpoint_dedupe_key(c: Dict[str, Any]) -> tuple:
    st = str(c.get("state") or c.get("event") or "").strip().lower()
    ag = str(c.get("agent") or "").strip().lower()
    ts = str(c.get("timestamp") or "").strip()
    msg = str(c.get("message") or "").strip()
    return (st, ag, ts, msg)


def union_checkpoints(
    local_cps: Optional[List[Dict[str, Any]]],
    remote_cps: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Union checkpoints across both copies, deduped."""
    merged_by_key: Dict[tuple, Dict[str, Any]] = {}
    key_order: List[tuple] = []
    for c in (local_cps or []) + (remote_cps or []):
        if not isinstance(c, dict):
            continue
        k = _checkpoint_dedupe_key(c)
        if k in merged_by_key:
            existing = merged_by_key[k]
            combined = dict(c)
            combined.update({key: val for key, val in existing.items() if val not in (None, "")})
            merged_by_key[k] = combined
        else:
            merged_by_key[k] = dict(c)
            key_order.append(k)

    def _sort_ts(k: tuple) -> str:
        item = merged_by_key[k]
        return str(item.get("timestamp") or "")

    key_order.sort(key=_sort_ts)
    return [merged_by_key[k] for k in key_order]


def merge_leg_records(
    local_data: Optional[Dict[str, Any]],
    remote_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge local and incoming/remote copies of a leg or handoff record.

    Invariants:
    1. Never drop relay events: union events across both copies (deduped by
       event+agent+timestamp).
    2. Leg status only advances (open->acked->done), never regresses to an older status.
    3. Checkpoints and acknowledgements made from either side survive.
    """
    if not local_data and not remote_data:
        return {}
    if not local_data:
        return dict(remote_data or {})
    if not remote_data:
        return dict(local_data or {})

    merged = dict(remote_data)

    # Preserve any local keys that remote does not have
    for k, v in local_data.items():
        if k in ("status", "events", "checkpoints", "orchestration"):
            continue
        if k not in merged or merged.get(k) in (None, "", []):
            if v not in (None, "", []):
                merged[k] = v

    # 1. Advance status: open -> acked -> done
    merged["status"] = advance_status(local_data.get("status"), remote_data.get("status"))

    # Preserve status metadata (e.g. ack, completion)
    for meta_key in (
        "acknowledged_by", "acknowledged_at", "acknowledged_on", "acknowledgement_note", "held_by",
        "completed_by", "completed_at", "completion_note", "released_utc",
        "blocked_by", "blocked_at", "blocked_on",
    ):
        val = local_data.get(meta_key) or remote_data.get(meta_key)
        if val not in (None, ""):
            merged[meta_key] = val

    # 2. Never drop relay events: union deduped by event+agent+timestamp
    has_events = "events" in local_data or "events" in remote_data
    if has_events:
        events = union_events(local_data.get("events"), remote_data.get("events"))
        status_word = str(merged["status"]).lower()
        if status_rank(status_word) >= 1:
            ack_agent = merged.get("acknowledged_by") or merged.get("held_by")
            ack_time = merged.get("acknowledged_at")
            if ack_agent:
                ack_present = any(
                    str(e.get("event") or "").lower() in ("ack", "acknowledged", "accepted")
                    for e in events
                )
                if not ack_present:
                    events.append({
                        "event": "ack" if "acked" in (str(local_data.get("status", "")).lower(), str(remote_data.get("status", "")).lower()) else "acknowledged",
                        "agent": str(ack_agent),
                        "timestamp": str(ack_time or datetime.now().isoformat()),
                    })
                    events = union_events(events, [])
        merged["events"] = events

    # 3. Checkpoints & orchestration
    local_orch = local_data.get("orchestration") or {}
    remote_orch = remote_data.get("orchestration") or {}
    has_orch = bool(local_orch or remote_orch)
    has_cps = "checkpoints" in local_data or "checkpoints" in remote_data

    if has_orch or has_cps:
        all_cps = union_checkpoints(
            (local_orch.get("checkpoints") if isinstance(local_orch, dict) else None) or local_data.get("checkpoints"),
            (remote_orch.get("checkpoints") if isinstance(remote_orch, dict) else None) or remote_data.get("checkpoints"),
        )
        if has_orch:
            merged_orch = dict(remote_orch) if isinstance(remote_orch, dict) else {}
            if isinstance(local_orch, dict):
                for ok, ov in local_orch.items():
                    if ok != "checkpoints" and ov not in (None, "", []):
                        merged_orch[ok] = ov
            if all_cps:
                merged_orch["checkpoints"] = all_cps
            merged["orchestration"] = merged_orch
        elif all_cps:
            merged["checkpoints"] = all_cps

    return merged


def down_sync(target_path: Path, incoming: Any) -> Dict[str, Any]:
    """Down-sync a record into target_path, merging with any existing local copy.

    Never drops relay events, unions events, and only advances leg status.
    """
    target_path = Path(target_path)
    if isinstance(incoming, Path):
        incoming_data = json.loads(incoming.read_text(encoding="utf-8"))
    elif isinstance(incoming, str):
        try:
            incoming_data = json.loads(incoming)
        except json.JSONDecodeError:
            incoming_data = json.loads(Path(incoming).read_text(encoding="utf-8"))
    elif isinstance(incoming, dict):
        incoming_data = incoming
    else:
        raise ValueError(f"Unsupported incoming type: {type(incoming)}")

    if target_path.exists():
        try:
            local_data = json.loads(target_path.read_text(encoding="utf-8"))
        except Exception:
            local_data = {}
        merged = merge_leg_records(local_data, incoming_data)
    else:
        merged = incoming_data

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged

# The derived index and the local trigger registry stay out of the synced set:
# handoffs.db is rebuildable from the JSON, and triggers.json is executable
# configuration — a rule arriving from another machine would run commands here.
DEFAULT_IGNORES = (
    # The ignore file itself stays untracked: every machine bootstraps its own
    # copy, and a shared tracked one is the single path guaranteed to collide
    # when two independently-created repos first merge.
    ".gitignore",
    "handoffs.db",
    "handoffs.db-wal",
    "handoffs.db-shm",
    "*.tmp",
    "triggers.json",
)
SHARED_TRIGGER_IGNORES = tuple(i for i in DEFAULT_IGNORES if i != "triggers.json")
REMOTE_NAME = "origin"
SYNC_BRANCH = "handoffs"


def _handoff_module():
    from . import handoff

    return handoff


def _git(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
    """Run one git command. Bounded, never raises."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"git {' '.join(args)} timed out"


def get_remote(handoff_dir: Path | None = None) -> str | None:
    """Configured sync remote: NOUGEN_HANDOFF_REMOTE, else the repo's own origin."""
    explicit = (os.environ.get("NOUGEN_HANDOFF_REMOTE") or "").strip()
    if explicit:
        return explicit
    directory = handoff_dir or _handoff_module().HANDOFF_DIR
    if not (directory / ".git").exists():
        return None
    code, out, _ = _git(["remote", "get-url", REMOTE_NAME], directory)
    return out or None if code == 0 else None


def write_sync_ignore(handoff_dir: Path, share_triggers: bool = False) -> None:
    ignores = SHARED_TRIGGER_IGNORES if share_triggers else DEFAULT_IGNORES
    body = (
        "# Managed by 'nougen handoff sync'.\n"
        "# The SQLite index is derived (rebuild-db); the trigger registry is\n"
        "# executable configuration and does not travel between machines by\n"
        "# default — pass --share-triggers if you intend to distribute rules.\n"
        + "\n".join(ignores)
        + "\n"
    )
    (handoff_dir / ".gitignore").write_text(body, encoding="utf-8")


def init_sync(
    remote: str | None = None,
    handoff_dir: Path | None = None,
    share_triggers: bool = False,
) -> dict:
    """Make the handoff directory a git repo pointed at a remote."""
    directory = handoff_dir or _handoff_module().HANDOFF_DIR
    directory.mkdir(parents=True, exist_ok=True)
    result: dict = {"dir": str(directory), "created": False, "remote": None}

    if not (directory / ".git").exists():
        code, _, err = _git(["init", "-b", SYNC_BRANCH], directory)
        if code != 0:
            result["error"] = err or "git init failed"
            return result
        result["created"] = True

    write_sync_ignore(directory, share_triggers)

    # An env-configured remote has to be written into the repo, not just
    # reported: every fetch and push below addresses it by name.
    remote = remote or (os.environ.get("NOUGEN_HANDOFF_REMOTE") or "").strip() or None
    if remote:
        code, _, _ = _git(["remote", "get-url", REMOTE_NAME], directory)
        action = "set-url" if code == 0 else "add"
        code, _, err = _git(["remote", action, REMOTE_NAME, remote], directory)
        if code != 0:
            result["error"] = err or "could not set remote"
            return result

    result["remote"] = get_remote(directory)
    return result


def _known_handoff_ids() -> set:
    """Ids already indexed here — anything else that appears arrived from elsewhere."""
    handoff = _handoff_module()
    ids = set()
    try:
        handoff.init_handoff_db()
        conn = handoff._get_db_connection()
        try:
            for row in conn.execute("SELECT handoff_id FROM handoff_records"):
                ids.add(row["handoff_id"])
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        # A missing or locked index just means nothing is known yet; the
        # arrival comparison degrades to "everything is new", never to a crash.
        pass
    return ids


def _replay_arrivals(known_ids: set) -> list[dict]:
    """Fire `created` triggers for records that just arrived from another box."""
    handoff = _handoff_module()
    fired: list[dict] = []
    for path in handoff.get_handoff_files():
        data = handoff._read_handoff(path)
        if not data:
            continue
        handoff_id = data.get("handoff_id") or path.stem
        if handoff_id in known_ids:
            continue
        if machine.is_local_record(data):
            # Written here (or by a pre-stamp agent) — its triggers already ran.
            continue
        fired.extend(handoff._fire_triggers("created", data, path))
    return fired


def _resolve_merge_conflicts(directory: Path) -> bool:
    """Resolve JSON and markdown conflicts in handoff/leg files during git merge.

    Parses both :2: (HEAD/local) and :3: (MERGE_HEAD/remote) copies of conflicted
    JSON records, merges them with merge_leg_records(), writes the result, and
    commits the merge.
    """
    code, out, _ = _git(["diff", "--name-only", "--diff-filter=U"], directory)
    if code != 0 or not out:
        return False
    unmerged = [line.strip() for line in out.splitlines() if line.strip()]
    if not unmerged:
        return False

    for rel_path in unmerged:
        file_path = directory / rel_path
        if rel_path.endswith(".json"):
            c2, local_raw, _ = _git(["show", f":2:{rel_path}"], directory)
            c3, remote_raw, _ = _git(["show", f":3:{rel_path}"], directory)
            if c2 != 0 and c3 == 0:
                _git(["add", rel_path], directory)
                continue
            elif c3 != 0 and c2 == 0:
                _git(["add", rel_path], directory)
                continue
            elif c2 != 0 and c3 != 0:
                return False

            try:
                local_data = json.loads(local_raw)
                remote_data = json.loads(remote_raw)
            except json.JSONDecodeError:
                return False

            merged = merge_leg_records(local_data, remote_data)
            file_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
            c_add, _, _ = _git(["add", rel_path], directory)
            if c_add != 0:
                return False

        elif rel_path.endswith(".md"):
            c2, local_md, _ = _git(["show", f":2:{rel_path}"], directory)
            c3, remote_md, _ = _git(["show", f":3:{rel_path}"], directory)
            chosen_md = local_md if (c2 == 0 and local_md) else (remote_md if c3 == 0 else "")
            file_path.write_text(chosen_md, encoding="utf-8")
            c_add, _, _ = _git(["add", rel_path], directory)
            if c_add != 0:
                return False
        else:
            return False

    # Verify no unmerged files remain
    code_rem, out_rem, _ = _git(["diff", "--name-only", "--diff-filter=U"], directory)
    if code_rem != 0 or out_rem.strip():
        return False

    # Complete the merge commit
    code_com, _, _ = _git(
        [
            "-c", f"user.name=nougen-{machine.host_label()}",
            "-c", "user.email=handoffs@nougen.local",
            "commit", "--no-edit",
        ],
        directory,
    )
    return code_com == 0


def sync(
    remote: str | None = None,
    push: bool = True,
    pull: bool = True,
    share_triggers: bool = False,
    replay: bool = True,
) -> dict:
    """Commit local handoffs, exchange them with the remote, react to arrivals."""
    handoff = _handoff_module()
    directory = handoff.HANDOFF_DIR
    report: dict = {
        "dir": str(directory),
        "host": machine.host_label(),
        "committed": False,
        "pulled": False,
        "pushed": False,
        "arrived": [],
        "fired": [],
        "errors": [],
    }

    # Publishing the wrong registry succeeds silently — it commits nothing,
    # pushes nothing, and reports pushed=True. Refuse both ways it happens.
    conflict = handoff.registry_conflict()
    if conflict:
        report["errors"].append(conflict)
        return report
    # An empty registry is legitimate on a machine joining the fleet — that is
    # how a new box receives its first records. It is only suspect if nothing
    # arrives either, which means this is the wrong directory.
    had_records = bool(handoff.get_handoff_files())

    setup = init_sync(remote, directory, share_triggers)
    if setup.get("error"):
        report["errors"].append(setup["error"])
        return report
    report["remote"] = setup.get("remote")

    # Commit whatever this machine has produced since the last sync.
    _git(["add", "-A"], directory)
    code, out, _ = _git(["status", "--porcelain"], directory)
    if out:
        stamp = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005 - matches the naive stamps on handoff records
        code, _, err = _git(
            [
                "-c", f"user.name=nougen-{machine.host_label()}",
                "-c", "user.email=handoffs@nougen.local",
                "commit", "-m", f"handoffs from {machine.host_label()} @ {stamp}",
            ],
            directory,
        )
        if code == 0:
            report["committed"] = True
        else:
            report["errors"].append(err or "commit failed")

    if not report["remote"]:
        report["errors"].append(
            "No sync remote configured. Set NOUGEN_HANDOFF_REMOTE or pass --remote."
        )
        return report

    known_ids = _known_handoff_ids()

    if pull:
        code, _, err = _git(["fetch", REMOTE_NAME, SYNC_BRANCH], directory, timeout=120)
        if code != 0:
            # An empty remote has no branch yet; that is a first push, not a failure.
            if "couldn't find remote ref" not in (err or "").lower():
                report["errors"].append(err or "fetch failed")
        else:
            # Each machine bootstraps its own repo, so the first merge joins two
            # unrelated roots — expected here, unlike in a source repository.
            code, _, err = _git(
                [
                    "merge", "--no-edit", "--allow-unrelated-histories",
                    f"{REMOTE_NAME}/{SYNC_BRANCH}",
                ],
                directory,
            )
            if code == 0:
                report["pulled"] = True
            else:
                if _resolve_merge_conflicts(directory):
                    report["pulled"] = True
                else:
                    _git(["merge", "--abort"], directory)
                    report["errors"].append(
                        "Merge conflict in handoff records — resolve by hand in "
                        f"{directory} (merge aborted, nothing was lost): {err}"
                    )

    if report["pulled"]:
        # The index is derived, so rebuild before anything reads state.
        handoff.rebuild_handoff_db()
        current = _known_handoff_ids()
        report["arrived"] = sorted(current - known_ids)
        if replay and report["arrived"]:
            report["fired"] = _replay_arrivals(known_ids)

    if push:
        if not had_records and not report["arrived"]:
            report["errors"].append(
                f"No handoff records in {directory}, and none arrived — refusing "
                "to report a push of an empty registry. If your records live in "
                "another checkout, set NOUGEN_HANDOFF_DIR to it."
            )
            return report
        # Nothing has ever been committed here — there is no HEAD to publish.
        code, _, _ = _git(["rev-parse", "--verify", "HEAD"], directory)
        if code != 0:
            report["errors"].append("Nothing to push yet — no handoff records here.")
            return report
        code, _, err = _git(
            ["push", "-u", REMOTE_NAME, f"HEAD:{SYNC_BRANCH}"], directory, timeout=120
        )
        if code == 0:
            report["pushed"] = True
        else:
            report["errors"].append(err or "push failed")

    return report
