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

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import machine

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


def _git(args: List[str], cwd: Path, timeout: int = 60) -> Tuple[int, str, str]:
    """Run one git command. Bounded, never raises."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"git {' '.join(args)} timed out"


def get_remote(handoff_dir: Optional[Path] = None) -> Optional[str]:
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
    remote: Optional[str] = None,
    handoff_dir: Optional[Path] = None,
    share_triggers: bool = False,
) -> Dict:
    """Make the handoff directory a git repo pointed at a remote."""
    directory = handoff_dir or _handoff_module().HANDOFF_DIR
    directory.mkdir(parents=True, exist_ok=True)
    result: Dict = {"dir": str(directory), "created": False, "remote": None}

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
    except Exception:
        pass
    return ids


def _replay_arrivals(known_ids: set) -> List[Dict]:
    """Fire `created` triggers for records that just arrived from another box."""
    handoff = _handoff_module()
    fired: List[Dict] = []
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


def sync(
    remote: Optional[str] = None,
    push: bool = True,
    pull: bool = True,
    share_triggers: bool = False,
    replay: bool = True,
) -> Dict:
    """Commit local handoffs, exchange them with the remote, react to arrivals."""
    handoff = _handoff_module()
    directory = handoff.HANDOFF_DIR
    report: Dict = {
        "dir": str(directory),
        "host": machine.host_label(),
        "committed": False,
        "pulled": False,
        "pushed": False,
        "arrived": [],
        "fired": [],
        "errors": [],
    }

    setup = init_sync(remote, directory, share_triggers)
    if setup.get("error"):
        report["errors"].append(setup["error"])
        return report
    report["remote"] = setup.get("remote")

    # Commit whatever this machine has produced since the last sync.
    _git(["add", "-A"], directory)
    code, out, _ = _git(["status", "--porcelain"], directory)
    if out:
        stamp = datetime.now().isoformat(timespec="seconds")
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
