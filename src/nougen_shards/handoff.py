import os
import sys
import json
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from . import machine

# Handoff notes live in <repo>/.handoffs by default. Override with NOUGEN_HANDOFF_DIR
# so the system works regardless of where it is installed or invoked from.


def _resolve_project_root() -> Path:
    """Repo root. parent^3 is right for a src/ checkout, but an installed copy
    lives under <venv>/Lib/site-packages, whose parent^3 is the venv's Lib —
    a handoff registry there is invisible to every other agent. When the module
    location is not a checkout, trust the repo the command was run from."""
    module_root = Path(__file__).resolve().parent.parent.parent
    if (module_root / "pyproject.toml").exists() or (module_root / ".git").exists():
        return module_root
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5, check=False)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except OSError:
        pass
    return module_root


PROJECT_ROOT = _resolve_project_root()
HANDOFF_DIR = Path(os.environ.get("NOUGEN_HANDOFF_DIR", PROJECT_ROOT / ".handoffs"))

_CONSOLE_CONFIGURED = False


def _make_console() -> Console:
    """Return a Rich Console safe for non-UTF-8 Windows terminals.

    The default cp1252 encoding on legacy Windows shells cannot represent
    emoji characters, which causes Rich to crash with UnicodeEncodeError.
    Reconfiguring stdout to UTF-8 with 'replace' error handling lets the
    output degrade gracefully instead of aborting mid-write.
    """
    global _CONSOLE_CONFIGURED
    if not _CONSOLE_CONFIGURED and sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
        _CONSOLE_CONFIGURED = True
    return Console()

AGENT_FOLDERS = {
    "gemini": "gemini handoffs",
    "claude": "claude handoffs",
    "claude-cli": "claude cli handoffs",
    "codex": "codex handoffs",
    "ollama": "ollama handoffs",
    "openrouter": "openrouter handoffs",
}

OPEN_STATUSES = {"open", "acknowledged", "in_progress", "blocked"}
HANDOFF_DB_NAME = "handoffs.db"


def _atomic_write_json(path: Path, data: dict) -> None:
    """Writes JSON via a temp file + atomic replace, so an interrupted or
    concurrent write can never leave a truncated handoff record on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _read_handoff(path: Path) -> Optional[Dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _append_markdown(path: Path, title: str, lines: List[str]) -> None:
    md_path = path.with_suffix(".md")
    if not md_path.exists():
        return
    try:
        with open(md_path, "a", encoding="utf-8") as f:
            f.write(f"\n## {title}\n")
            for line in lines:
                f.write(f"- {line}\n")
    except Exception:
        pass


def _find_handoff(
    agent: Optional[str] = None,
    handoff_id: Optional[str] = None,
    statuses: Optional[set] = None,
) -> tuple[Optional[Path], Optional[Dict]]:
    """Find a target handoff by id, or the newest handoff matching statuses."""
    for path in get_handoff_files(agent):
        data = _read_handoff(path)
        if not data:
            continue
        if handoff_id and data.get("handoff_id") != handoff_id:
            continue
        status = data.get("status") or "open"
        if statuses and status not in statuses:
            continue
        return path, data
    return None, None


def _ensure_orchestration(data: Dict, receiver: str, timestamp: str) -> Dict:
    orchestration = data.setdefault("orchestration", {})
    orchestration.setdefault(
        "run_id", f"{timestamp.replace(':', '').replace('.', '')}_{receiver}"
    )
    orchestration.setdefault("started_by", receiver)
    orchestration.setdefault("started_at", timestamp)
    orchestration.setdefault("checkpoints", [])
    return orchestration


def get_cwd_repo_root() -> Path | None:
    """The git root of the directory the command was actually run from."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip())


def registry_conflict() -> str | None:
    """Describe a registry the operator probably meant instead of this one.

    HANDOFF_DIR is derived from where the *module* lives, not where the command
    was run. Running the CLI from a worktree or a second clone therefore points
    it at that copy's `.handoffs` — which is usually empty — while the records
    the operator cares about sit in the checkout they are standing in. Syncing
    the empty one reports success and publishes nothing, which is worse than an
    error, so callers use this to refuse instead.

    An explicit NOUGEN_HANDOFF_DIR is always honoured: the operator has said
    which registry they mean.
    """
    if os.environ.get("NOUGEN_HANDOFF_DIR"):
        return None
    cwd_root = get_cwd_repo_root()
    if not cwd_root:
        return None
    try:
        if cwd_root.resolve() == PROJECT_ROOT.resolve():
            return None
    except OSError:
        return None
    candidate = cwd_root / ".handoffs"
    if not candidate.exists():
        return None
    if not any(candidate.rglob("handoff_*.json")):
        return None
    return (
        f"Registry mismatch: this CLI resolves handoffs to {HANDOFF_DIR}, but "
        f"the checkout you are in has records at {candidate}. Set "
        f"NOUGEN_HANDOFF_DIR to the one you mean."
    )


def get_handoff_db_path() -> Path:
    """Return the local SQLite index path for handoff records."""
    return HANDOFF_DIR / HANDOFF_DB_NAME


def _get_db_connection():
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(get_handoff_db_path()), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _add_missing_columns(conn, table: str, columns: dict[str, str]) -> None:
    """Add columns to an existing table, skipping the ones already there.

    Machine columns landed after databases existed in the wild; ALTER TABLE is
    cheap and lets an older index gain the fleet fields without a rebuild.
    """
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, decl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_handoff_db() -> None:
    """Initialize the local handoff/orchestration index."""
    conn = _get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS handoff_records (
                handoff_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                markdown_path TEXT,
                agent TEXT,
                status TEXT,
                goal TEXT,
                message TEXT,
                branch TEXT,
                session_id TEXT,
                created_at TEXT,
                acknowledged_by TEXT,
                acknowledged_at TEXT,
                completed_by TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                data_json TEXT NOT NULL,
                host TEXT,
                machine_id TEXT,
                platform TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS handoff_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handoff_id TEXT NOT NULL,
                checkpoint_index INTEGER NOT NULL,
                timestamp TEXT,
                agent TEXT,
                state TEXT NOT NULL,
                message TEXT,
                host TEXT,
                machine_id TEXT,
                FOREIGN KEY (handoff_id) REFERENCES handoff_records(handoff_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS handoff_trigger_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handoff_id TEXT,
                trigger_id TEXT NOT NULL,
                event TEXT NOT NULL,
                command TEXT,
                timestamp TEXT,
                host TEXT,
                machine_id TEXT,
                origin TEXT,
                status TEXT,
                exit_code INTEGER,
                stdout TEXT,
                stderr TEXT
            )
        """)
        _add_missing_columns(conn, "handoff_records", {
            "host": "TEXT", "machine_id": "TEXT", "platform": "TEXT",
        })
        _add_missing_columns(conn, "handoff_checkpoints", {
            "host": "TEXT", "machine_id": "TEXT",
        })
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_handoff_records_status "
            "ON handoff_records(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_handoff_records_agent "
            "ON handoff_records(agent)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_handoff_records_machine "
            "ON handoff_records(machine_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_handoff_checkpoints_handoff "
            "ON handoff_checkpoints(handoff_id, checkpoint_index)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_handoff_trigger_runs_handoff "
            "ON handoff_trigger_runs(handoff_id, timestamp)"
        )
        conn.commit()
    finally:
        conn.close()


def _record_trigger_run(record: dict) -> bool:
    """Persist one trigger execution so a remote fire is auditable after the fact."""
    try:
        init_handoff_db()
        conn = _get_db_connection()
        try:
            conn.execute("""
                INSERT INTO handoff_trigger_runs (
                    handoff_id, trigger_id, event, command, timestamp,
                    host, machine_id, origin, status, exit_code, stdout, stderr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.get("handoff_id"),
                record.get("trigger_id"),
                record.get("event"),
                record.get("command"),
                record.get("timestamp"),
                record.get("host"),
                record.get("machine_id"),
                record.get("origin"),
                record.get("status"),
                record.get("exit_code"),
                record.get("stdout"),
                record.get("stderr"),
            ))
            conn.commit()
        finally:
            conn.close()
        return True
    except (OSError, sqlite3.Error):
        return False


def get_trigger_runs(limit: int = 20, trigger_id: str | None = None) -> list[dict]:
    """Most recent trigger executions, newest first."""
    try:
        init_handoff_db()
        conn = _get_db_connection()
        try:
            if trigger_id:
                rows = conn.execute(
                    "SELECT * FROM handoff_trigger_runs WHERE trigger_id = ? "
                    "ORDER BY id DESC LIMIT ?",
                    (trigger_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM handoff_trigger_runs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        return []


def _fire_triggers(event: str, data: dict, path: Path) -> list[dict]:
    """Hand a state change to the trigger engine.

    Wrapped so trigger failures can never take down a handoff write — the note
    is the durable artifact, the automation is best-effort.
    """
    try:
        from . import handoff_triggers

        return handoff_triggers.fire(event, data, path)
    except Exception:  # noqa: BLE001 - the note is the durable artifact; no trigger failure may cost it
        return []


def _sync_handoff_to_db(path: Path, data: Dict) -> bool:
    """Mirror one handoff JSON record into SQLite for indexed orchestration."""
    try:
        init_handoff_db()
        conn = _get_db_connection()
        git_info = data.get("git") or {}
        orchestration = data.get("orchestration") or {}
        checkpoints = orchestration.get("checkpoints") or []
        now = datetime.now().isoformat()
        handoff_id = data.get("handoff_id") or path.stem
        record_machine = machine.record_machine(data)
        try:
            conn.execute("""
                INSERT INTO handoff_records (
                    handoff_id, path, markdown_path, agent, status, goal, message,
                    branch, session_id, created_at, acknowledged_by, acknowledged_at,
                    completed_by, completed_at, updated_at, data_json,
                    host, machine_id, platform
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(handoff_id) DO UPDATE SET
                    path=excluded.path,
                    markdown_path=excluded.markdown_path,
                    agent=excluded.agent,
                    status=excluded.status,
                    goal=excluded.goal,
                    message=excluded.message,
                    branch=excluded.branch,
                    session_id=excluded.session_id,
                    created_at=excluded.created_at,
                    acknowledged_by=excluded.acknowledged_by,
                    acknowledged_at=excluded.acknowledged_at,
                    completed_by=excluded.completed_by,
                    completed_at=excluded.completed_at,
                    updated_at=excluded.updated_at,
                    data_json=excluded.data_json,
                    host=excluded.host,
                    machine_id=excluded.machine_id,
                    platform=excluded.platform
            """, (
                handoff_id,
                str(path),
                str(path.with_suffix(".md")),
                data.get("agent"),
                data.get("status") or "open",
                data.get("goal"),
                data.get("message"),
                git_info.get("branch"),
                data.get("session_id"),
                data.get("timestamp"),
                data.get("acknowledged_by"),
                data.get("acknowledged_at"),
                data.get("completed_by"),
                data.get("completed_at"),
                now,
                json.dumps(data, sort_keys=True),
                record_machine.get("host"),
                record_machine.get("machine_id"),
                record_machine.get("platform"),
            ))
            conn.execute(
                "DELETE FROM handoff_checkpoints WHERE handoff_id = ?",
                (handoff_id,),
            )
            for index, checkpoint in enumerate(checkpoints):
                conn.execute("""
                    INSERT INTO handoff_checkpoints (
                        handoff_id, checkpoint_index, timestamp, agent, state, message,
                        host, machine_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    handoff_id,
                    index,
                    checkpoint.get("timestamp"),
                    checkpoint.get("agent"),
                    checkpoint.get("state") or "unknown",
                    checkpoint.get("message"),
                    checkpoint.get("host"),
                    checkpoint.get("machine_id"),
                ))
            conn.commit()
        finally:
            conn.close()
        return True
    except (OSError, sqlite3.Error):
        return False


def _handoff_context_metadata(path: Path, data: Dict, **extra: object) -> Dict:
    """Build compact NouGenContext metadata without storing the full handoff."""
    git_info = data.get("git") or {}
    record_machine = machine.record_machine(data)
    metadata = {
        "handoff_id": data.get("handoff_id") or path.stem,
        "path": str(path),
        "agent": data.get("agent"),
        "status": data.get("status"),
        "goal": data.get("goal"),
        "branch": git_info.get("branch"),
        "handoff_db_path": str(get_handoff_db_path()),
        "host": record_machine.get("host"),
        "machine_id": record_machine.get("machine_id"),
        "origin": machine.record_origin(data),
    }
    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def _log_context_event(event_type: str, content: str, metadata: Optional[Dict] = None) -> None:
    """Mirror handoff state into NouGenContext without making handoffs depend on it."""
    try:
        from . import nougen_context

        nougen_context.init_context_db(clean_slate=False)
        nougen_context.log_event(event_type, content, metadata or {})
    except Exception:
        return


def rebuild_handoff_db(agent: Optional[str] = None) -> int:
    """Rebuild the SQLite index from handoff JSON files."""
    init_handoff_db()
    count = 0
    for path in get_handoff_files(agent):
        data = _read_handoff(path)
        if data and _sync_handoff_to_db(path, data):
            count += 1
    _log_context_event(
        "HANDOFF_DB_REBUILT",
        f"Handoff DB rebuilt with {count} indexed record(s).",
        {
            "agent_filter": agent,
            "count": count,
            "handoff_db_path": str(get_handoff_db_path()),
        },
    )
    return count


def get_active_brain_dir() -> Optional[Path]:
    """Locates the directory holding the current session's task.md /
    implementation_plan.md. Defaults to the Gemini Antigravity brain layout but
    can point anywhere via NOUGEN_HANDOFF_TASKS_DIR, so Claude/Codex/other agents
    can supply their own task tracking instead of being locked out."""
    override = os.environ.get("NOUGEN_HANDOFF_TASKS_DIR")
    if override:
        p = Path(override)
        return p if p.exists() else None
    brain_root = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    if not brain_root.exists():
        return None
    dirs = [d for d in brain_root.iterdir() if d.is_dir() and len(d.name) == 36]
    if not dirs:
        return None
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs[0]


def detect_current_agent() -> str:
    """Detects the current agent type. An explicit NOUGEN_AGENT env var always
    wins; otherwise we infer from known environment markers."""
    explicit = os.environ.get("NOUGEN_AGENT")
    if explicit:
        return explicit.strip().lower()
    # Claude Code CLI is its own lane ("claude-cli"), distinct from the
    # API/Antigravity "claude" lane. The CLI sets an explicit marker, a stronger
    # signal than a stray GEMINI/GOOGLE key exported in the same shell — so check
    # it BEFORE generic API-key detection or CLI handoffs misroute.
    if (
        os.environ.get("CLAUDECODE")
        or os.environ.get("CLAUDE_CODE")
        or os.environ.get("CLAUDE_CODE_ENTRYPOINT")
    ):
        return "claude-cli"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    active_brain = get_active_brain_dir()
    if active_brain and "antigravity" in str(active_brain).lower():
        return "gemini"
    return "generic"


def parse_task_md(task_path: Path) -> Dict:
    """Parses task.md and returns lists of completed, in-progress, and pending tasks."""
    completed = []
    in_progress = []
    pending = []
    if not task_path.exists():
        return {"completed": [], "in_progress": [], "pending": []}

    try:
        with open(task_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("- [x]"):
                    completed.append(line[5:].strip())
                elif line.startswith("- [/]"):
                    in_progress.append(line[5:].strip())
                elif line.startswith("- [ ]"):
                    pending.append(line[5:].strip())
    except Exception:
        pass

    return {"completed": completed, "in_progress": in_progress, "pending": pending}


def get_git_status() -> Dict:
    """Retrieves git status, branch name, and recent commits."""
    status = {"branch": "unknown", "changes": [], "commits": []}
    try:
        # Branch
        res_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
            timeout=10,
        )
        if res_branch.returncode == 0:
            status["branch"] = res_branch.stdout.strip()

        # Porcelain changes
        res_status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
            timeout=10,
        )
        if res_status.returncode == 0:
            for line in res_status.stdout.splitlines():
                if line.strip():
                    status["changes"].append(line.strip())

        # Commits
        res_commits = subprocess.run(
            ["git", "log", "-n", "3", "--oneline"],
            capture_output=True,
            text=True,
            check=False,
            cwd=PROJECT_ROOT,
            timeout=10,
        )
        if res_commits.returncode == 0:
            for line in res_commits.stdout.splitlines():
                if line.strip():
                    status["commits"].append(line.strip())
    except Exception:
        pass
    return status


def create_handoff(
    message: str = "", agent: Optional[str] = None, goal: Optional[str] = None, compact: bool = True
) -> Optional[Path]:
    console = _make_console()
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)

    if not agent:
        agent = detect_current_agent()

    target_folder = HANDOFF_DIR
    if agent.lower() in AGENT_FOLDERS:
        target_folder = HANDOFF_DIR / AGENT_FOLDERS[agent.lower()]
    target_folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    git_info = get_git_status()
    branch = git_info["branch"].replace("/", "_").replace("\\", "_")

    # Task tracking (Gemini Antigravity brain layout by default; override via
    # NOUGEN_HANDOFF_TASKS_DIR). An explicitly passed goal always takes precedence.
    brain_dir = get_active_brain_dir()
    tasks = {"completed": [], "in_progress": [], "pending": []}
    if brain_dir:
        tasks = parse_task_md(brain_dir / "task.md")
        if not goal:
            plan_path = brain_dir / "implementation_plan.md"
            if plan_path.exists():
                try:
                    with open(plan_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("# "):
                                goal = line[2:].strip()
                                break
                except Exception:
                    pass
    if not goal:
        goal = "No active goal recorded. Pass --goal to set one."

    # Phase 2: Pointer Compaction (The Arbitrage Sharpener)
    # If compact mode is enabled, we condense the task lists into a single summary block
    # for the handoff metadata, saving context tokens for the next session.
    compact_tasks = tasks
    if compact:
        total_count = len(tasks["completed"]) + len(tasks["in_progress"]) + len(tasks["pending"])
        summary_note = f"Semantic Anchor: {len(tasks['completed'])}/{total_count} tasks completed."
        if tasks["in_progress"]:
            summary_note += f" ACTIVE: {', '.join(tasks['in_progress'][:3])}"
        compact_tasks = {"summary": summary_note, "raw_count": total_count}

    # The machine stamp is part of the identity of the record, not decoration:
    # two boxes working the same branch produce the same timestamp+branch id, so
    # the host is folded into the id (and the filename) to keep records from
    # colliding once handoffs are synced between computers.
    identity = machine.machine_identity(repo_root=PROJECT_ROOT)
    host_slug = "".join(
        c if c.isalnum() or c in "-_" else "-" for c in identity["host"]
    ).strip("-") or "host"
    record_slug = f"{timestamp}_{host_slug}_{branch}"

    handoff_data = {
        "handoff_id": record_slug,
        "timestamp": datetime.now().isoformat(),
        "goal": goal,
        "message": message,
        "git": git_info,
        "tasks": compact_tasks if compact else tasks,
        "session_id": brain_dir.name if brain_dir else "unknown",
        "agent": agent.lower(),
        "machine": identity,
        "status": "open",
        "acknowledged_by": None,
        "acknowledged_at": None,
    }

    # Save JSON file (atomic: temp + replace prevents truncated records)
    json_path = target_folder / f"handoff_{record_slug}.json"
    try:
        _atomic_write_json(json_path, handoff_data)
    except Exception as e:
        console.print(f"[red]Error saving handoff JSON: {e}[/red]")
        return None

    # Save Markdown file
    md_path = target_folder / f"handoff_{record_slug}.md"
    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# 🤝 Agent Handoff: {branch} @ {timestamp}\n\n")
            f.write(f"**Agent**: `{agent.upper()}`\n")
            f.write(
                f"**Machine**: `{identity['host']}` "
                f"({identity['os']} / {identity['arch']}, id `{identity['machine_id']}`)\n"
            )
            f.write(f"**Goal**: {goal}\n")
            if message:
                f.write(f"**Notes**: {message}\n")
            f.write(f"**Session ID**: `{handoff_data['session_id']}`\n\n")

            f.write("## 📋 Checklist Status\n")
            total = (
                len(tasks["completed"])
                + len(tasks["in_progress"])
                + len(tasks["pending"])
            )
            if total > 0:
                f.write(
                    f"- **Progress**: {len(tasks['completed'])} / {total} tasks completed ({len(tasks['completed'])/total*100:.1f}%)\n"
                )
            if tasks["in_progress"]:
                f.write("\n### ⏳ In Progress\n")
                for t in tasks["in_progress"]:
                    f.write(f"- [ ] {t}\n")
            if tasks["pending"]:
                f.write("\n### ⏹️ Pending\n")
                for t in tasks["pending"]:
                    f.write(f"- [ ] {t}\n")
            if tasks["completed"]:
                f.write("\n### ✅ Completed\n")
                for t in tasks["completed"]:
                    f.write(f"- [x] {t}\n")

            f.write("\n## 🛠️ Repository Status\n")
            f.write(f"- **Active Branch**: `{git_info['branch']}`\n")
            if git_info["changes"]:
                f.write("\n### 📂 Uncommitted Changes\n")
                for change in git_info["changes"]:
                    f.write(f"- `{change}`\n")
            else:
                f.write("- ✨ No uncommitted changes.\n")

            if git_info["commits"]:
                f.write("\n### 📜 Recent Commits\n")
                for commit in git_info["commits"]:
                    f.write(f"- `{commit}`\n")
    except Exception as e:
        console.print(f"[red]Error saving handoff Markdown: {e}[/red]")
        return None

    db_synced = _sync_handoff_to_db(json_path, handoff_data)
    _log_context_event(
        "HANDOFF_CREATED",
        (
            f"Handoff {handoff_data['handoff_id']} created for "
            f"{agent}: {handoff_data['goal']}"
        ),
        _handoff_context_metadata(json_path, handoff_data, db_synced=db_synced),
    )
    fired = _fire_triggers("created", handoff_data, json_path)
    console.print(
        f"[bold green]🤝 Handoff created successfully for {agent.upper()} "
        f"on {identity['host']}![/bold green]"
    )
    console.print(f"- Metadata: [yellow]{json_path}[/yellow]")
    console.print(f"- Summary: [yellow]{md_path}[/yellow]")
    _print_trigger_results(console, fired)
    return json_path


def _print_trigger_results(console: Console, fired: list[dict]) -> None:
    """Surface trigger activity inline — silent automation is unreviewable."""
    for record in fired:
        status = record.get("status")
        colour = {
            "ok": "green", "background": "cyan", "dry-run": "yellow",
        }.get(status, "red")
        exit_code = record.get("exit_code")
        detail = "" if exit_code in (None, 0) else f" (exit {exit_code})"
        console.print(
            f"[{colour}]⚡ trigger {record.get('trigger_id')} → {status}{detail}[/{colour}]"
        )


def get_handoff_files(agent: Optional[str] = None) -> List[Path]:
    if not HANDOFF_DIR.exists():
        return []

    files = []
    if agent and agent.lower() in AGENT_FOLDERS:
        agent_dir = HANDOFF_DIR / AGENT_FOLDERS[agent.lower()]
        if agent_dir.exists():
            files.extend(agent_dir.glob("handoff_*.json"))
    else:
        # Search all subdirectories plus root
        files.extend(HANDOFF_DIR.glob("handoff_*.json"))
        for folder in AGENT_FOLDERS.values():
            subdir = HANDOFF_DIR / folder
            if subdir.exists():
                files.extend(subdir.glob("handoff_*.json"))

    return sorted(files, key=_handoff_sort_key, reverse=True)


def _handoff_sort_key(path: Path) -> tuple:
    """Order records by when they were WRITTEN, not when the file was touched.

    File mtimes describe this clone, not the fleet. A fresh clone stamps every
    record with the checkout time, `handoff sync` restamps whatever it pulled,
    and any write — an ack, a checkpoint — jumps that record to the front. So
    the "latest handoff" could change without a single new handoff existing,
    and two machines running `handoff read` against the same registry could
    legitimately disagree about which record is newest.

    The record's own timestamp is the same on every machine. mtime stays as the
    tiebreaker for records that predate the field or carry an unparseable one,
    so ordering degrades rather than raising.
    """
    data = _read_handoff(path)
    stamp = str((data or {}).get("timestamp") or "")
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (stamp, mtime)


def start_orchestration(
    agent: Optional[str] = None,
    message: str = "",
    handoff_id: Optional[str] = None,
) -> Optional[Path]:
    """Claim a handoff and open a durable orchestration run around it."""
    console = _make_console()
    target_path, data = _find_handoff(agent, handoff_id, OPEN_STATUSES)
    if not target_path or not data:
        console.print("[yellow]No open handoff found to orchestrate.[/yellow]")
        return None

    receiver = (os.environ.get("NOUGEN_AGENT") or detect_current_agent()).lower()
    timestamp = datetime.now().isoformat()
    if (data.get("status") or "open") == "open":
        data["acknowledged_by"] = receiver
        data["acknowledged_at"] = timestamp
        if message:
            data["acknowledgement_note"] = message

    stamp = machine.machine_stamp()
    orchestration = _ensure_orchestration(data, receiver, timestamp)
    orchestration.setdefault("started_on", stamp)
    orchestration["checkpoints"].append({
        "timestamp": timestamp,
        "agent": receiver,
        "state": "started",
        "message": message,
        **stamp,
    })
    data["status"] = "in_progress"
    data["acknowledged_on"] = stamp
    _atomic_write_json(target_path, data)
    db_synced = _sync_handoff_to_db(target_path, data)
    _log_context_event(
        "HANDOFF_ORCHESTRATION_STARTED",
        (
            f"Handoff {data.get('handoff_id', target_path.stem)} "
            f"orchestration started by {receiver}: {message or 'started'}"
        ),
        _handoff_context_metadata(
            target_path,
            data,
            db_synced=db_synced,
            run_id=orchestration.get("run_id"),
            checkpoint_count=len(orchestration["checkpoints"]),
        ),
    )
    _append_markdown(target_path, "Orchestration Started", [
        f"By: `{receiver.upper()}`",
        f"On: `{stamp['host']}`",
        f"At: {timestamp}",
        f"Run ID: `{orchestration['run_id']}`",
        f"Note: {message or 'started'}",
    ])
    fired = _fire_triggers("started", data, target_path)
    console.print(
        f"[bold green]Orchestration started for "
        f"{data.get('handoff_id', target_path.stem)} by {receiver.upper()} "
        f"on {stamp['host']}.[/bold green]"
    )
    _print_trigger_results(console, fired)
    return target_path


def checkpoint_orchestration(
    agent: Optional[str] = None,
    message: str = "",
    handoff_id: Optional[str] = None,
    state: str = "in_progress",
) -> Optional[Path]:
    """Append an orchestration checkpoint to a handoff record."""
    console = _make_console()
    if state not in {"in_progress", "blocked", "complete"}:
        console.print(f"[red]Invalid orchestration state '{state}'.[/red]")
        return None

    target_path, data = _find_handoff(agent, handoff_id, OPEN_STATUSES)
    if not target_path or not data:
        console.print("[yellow]No active handoff found for checkpoint.[/yellow]")
        return None

    receiver = (os.environ.get("NOUGEN_AGENT") or detect_current_agent()).lower()
    timestamp = datetime.now().isoformat()
    stamp = machine.machine_stamp()
    orchestration = _ensure_orchestration(data, receiver, timestamp)
    orchestration["checkpoints"].append({
        "timestamp": timestamp,
        "agent": receiver,
        "state": state,
        "message": message,
        **stamp,
    })
    data["status"] = state
    if state == "complete":
        data["completed_by"] = receiver
        data["completed_at"] = timestamp
        data["completed_on"] = stamp
    elif state == "blocked":
        data["blocked_by"] = receiver
        data["blocked_at"] = timestamp
        data["blocked_on"] = stamp

    if "events" in data and isinstance(data["events"], list):
        data["events"].append({
            "event": state,
            "agent": receiver,
            "timestamp": timestamp,
            "message": message or state,
        })

    _atomic_write_json(target_path, data)
    db_synced = _sync_handoff_to_db(target_path, data)
    context_event_type = {
        "blocked": "HANDOFF_ORCHESTRATION_BLOCKED",
        "complete": "HANDOFF_ORCHESTRATION_COMPLETED",
    }.get(state, "HANDOFF_ORCHESTRATION_CHECKPOINT")
    _log_context_event(
        context_event_type,
        (
            f"Handoff {data.get('handoff_id', target_path.stem)} "
            f"orchestration checkpoint by {receiver} as {state}: "
            f"{message or state}"
        ),
        _handoff_context_metadata(
            target_path,
            data,
            db_synced=db_synced,
            state=state,
            checkpoint_count=len(orchestration["checkpoints"]),
            run_id=orchestration.get("run_id"),
        ),
    )
    _append_markdown(target_path, "Orchestration Checkpoint", [
        f"By: `{receiver.upper()}`",
        f"On: `{stamp['host']}`",
        f"At: {timestamp}",
        f"State: `{state}`",
        f"Note: {message or state}",
    ])
    event = {"complete": "completed", "blocked": "blocked"}.get(state, "checkpoint")
    fired = _fire_triggers(event, data, target_path)
    console.print(
        f"[bold green]Checkpoint recorded for "
        f"{data.get('handoff_id', target_path.stem)} as {state} "
        f"on {stamp['host']}.[/bold green]"
    )
    _print_trigger_results(console, fired)
    return target_path


def complete_orchestration(
    agent: Optional[str] = None,
    message: str = "",
    handoff_id: Optional[str] = None,
) -> Optional[Path]:
    """Mark an orchestration run complete."""
    return checkpoint_orchestration(agent, message, handoff_id, state="complete")


def acknowledge_handoff(
    agent: Optional[str] = None,
    message: str = "",
    handoff_id: Optional[str] = None,
) -> Optional[Path]:
    """Marks a handoff as received — the read-back / forcing function that makes
    the transfer of responsibility unambiguous. By default acknowledges the most
    recent still-open handoff; pass handoff_id to target a specific one, or
    --agent to filter by the agent that created it."""
    console = _make_console()
    files = get_handoff_files(agent)
    if not files:
        console.print("[yellow]No handoff records found to acknowledge.[/yellow]")
        return None

    target_path: Optional[Path] = None
    skipped: list = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if handoff_id:
            if data.get("handoff_id") == handoff_id:
                target_path = p
                break
        elif data.get("status", "open") == "open":
            target_path = p
            break
        elif not skipped:
            # The newest record is spoken for. Remember who has it — the reason
            # matters more than the fact when explaining what happened next.
            skipped.append(data)

    # Refuse to silently claim something other than what `handoff read` just
    # showed. `read` displays the newest record; a bare `ack` walks past it to
    # the newest still-OPEN one. When another agent claims a record between
    # those two commands — seconds, with several agents on one registry — the
    # operator sees a success line naming a handoff they never looked at, and
    # the only clue is an id they have no reason to be reading closely.
    # Stopping costs one `--id` flag. Guessing costs a wrongly-claimed record
    # on a registry the whole fleet trusts.
    if target_path is not None and skipped and not handoff_id:
        holder = skipped[0]
        console.print(
            f"[yellow]The most recent handoff is already acknowledged by "
            f"{(holder.get('acknowledged_by') or '?').upper()} at "
            f"{holder.get('acknowledged_at', '?')}.[/yellow]"
        )
        console.print(
            f"[dim]Not claiming a different one on your behalf. To take the "
            f"next open handoff:[/dim]\n"
            f"    nougen handoff ack --id "
            f"{_read_handoff(target_path).get('handoff_id', '<id>')}"
        )
        return None

    if target_path is None:
        if handoff_id:
            console.print(f"[red]No handoff found with id '{handoff_id}'.[/red]")
        else:
            console.print("[yellow]All handoffs are already acknowledged.[/yellow]")
        return None

    # An acknowledgement is a read-back: it tells the fleet someone OTHER than
    # the author has picked the work up. Acking your own record asserts that
    # about yourself, and the state it leaves behind is indistinguishable from
    # a real claim — the next machine to look sees a handoff that has been
    # taken, and moves on.
    #
    # Caught by doing it: reading a leg back to check it had synced, running a
    # bare `ack` to test the targeting fix, and silently claiming the message
    # that had just been written for another box. Refusing costs a flag when
    # someone genuinely means it; not refusing costs a handoff nobody delivers.
    if not handoff_id:
        candidate = _read_handoff(target_path) or {}
        author = (candidate.get("agent") or "").lower()
        receiver_now = (os.environ.get("NOUGEN_AGENT") or detect_current_agent()).lower()
        # Positive proof only: the record must carry an id equal to this box's.
        # is_local_record() treats an unstamped record as local — the right
        # default for triggers, wrong here, because it would make every
        # pre-stamping handoff written by an agent of the same name unclaimable.
        # Refuse when we know, not when we cannot tell.
        recorded_id = machine.record_machine(candidate).get("machine_id")
        same_box = bool(recorded_id) and recorded_id == machine.machine_id()
        if author and author == receiver_now and same_box:
            console.print(
                f"[yellow]The newest open handoff was written by this agent on "
                f"this machine ({author} @ {machine.host_label()}).[/yellow]"
            )
            console.print(
                "[dim]Acknowledging your own handoff would mark it claimed for "
                "everyone else. If you mean it, name it:[/dim]\n"
                f"    nougen handoff ack --id {candidate.get('handoff_id', '<id>')}"
            )
            return None

    receiver = (os.environ.get("NOUGEN_AGENT") or detect_current_agent()).lower()
    stamp = machine.machine_stamp()
    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
        data["status"] = "acknowledged"
        data["acknowledged_by"] = receiver
        data["acknowledged_at"] = datetime.now().isoformat()
        data["acknowledged_on"] = stamp
        if message:
            data["acknowledgement_note"] = message
        if "events" in data and isinstance(data["events"], list):
            data["events"].append({
                "event": "ack",
                "agent": receiver,
                "timestamp": data["acknowledged_at"],
                "note": message or "",
            })
        _atomic_write_json(target_path, data)
        db_synced = _sync_handoff_to_db(target_path, data)
        _log_context_event(
            "HANDOFF_ACKNOWLEDGED",
            (
                f"Handoff {data.get('handoff_id', target_path.stem)} "
                f"acknowledged by {receiver}: {message or 'acknowledged'}"
            ),
            _handoff_context_metadata(target_path, data, db_synced=db_synced),
        )
    except Exception as e:
        console.print(f"[red]Error acknowledging handoff: {e}[/red]")
        return None

    # Append acknowledgement to the markdown sibling, if present.
    md_path = target_path.with_suffix(".md")
    if md_path.exists():
        try:
            with open(md_path, "a", encoding="utf-8") as f:
                f.write("\n## ✅ Acknowledged\n")
                f.write(f"- **By**: `{receiver.upper()}`\n")
                f.write(f"- **On**: `{stamp['host']}`\n")
                f.write(f"- **At**: {data['acknowledged_at']}\n")
                if message:
                    f.write(f"- **Note**: {message}\n")
        except Exception:
            pass

    fired = _fire_triggers("acknowledged", data, target_path)
    console.print(
        f"[bold green]✅ Handoff {data.get('handoff_id', target_path.stem)} "
        f"acknowledged by {receiver.upper()} on {stamp['host']}.[/bold green]"
    )
    _print_trigger_results(console, fired)
    return target_path


def compute_live_status(data: dict, git_info: dict | None = None) -> str:
    """Pure function: derive the live status for a handoff record.

    Rules (evaluated in order):
    1. Human-set terminal/in-flight states are respected as-is:
       acknowledged, in_progress, blocked, complete.
    2. If stored status is "open" (or missing) AND tasks are 100% done
       AND the git tree is clean  →  "stale-complete".
    3. Otherwise mirror the stored status.

    Never mutates files or DB.
    """
    stored = (data.get("status") or "open").lower()

    # Human-set states that should not be auto-overridden
    if stored in {"acknowledged", "in_progress", "blocked", "complete"}:
        return stored

    # Check whether every task is done
    tasks = data.get("tasks") or {}
    all_done = False

    # Compact form: {"summary": "Semantic Anchor: N/N tasks completed.", ...}
    summary = tasks.get("summary", "")
    if summary:
        import re as _re
        m = _re.search(r"(\d+)/(\d+)\s+tasks? completed", summary, _re.IGNORECASE)
        if m and m.group(1) == m.group(2) and int(m.group(2)) > 0:
            all_done = True
        # Also accept explicit completed-marker patterns
        if not all_done and "all tasks completed" in summary.lower():
            all_done = True
    else:
        # Full task lists
        completed = tasks.get("completed", [])
        in_progress = tasks.get("in_progress", [])
        pending = tasks.get("pending", [])
        total = len(completed) + len(in_progress) + len(pending)
        if total > 0 and len(completed) == total:
            all_done = True

    if not all_done:
        return stored

    # Check git cleanliness
    effective_git = git_info if git_info is not None else (data.get("git") or {})
    changes = effective_git.get("changes", [])
    if changes:
        return stored  # dirty tree — not stale-complete

    return "stale-complete"


def reconcile_handoffs(
    agent: Optional[str] = None, write: bool = False
) -> dict:
    """Compute live status across all handoffs.

    Returns counts: total, open, in_progress, blocked, stale_complete, actionable.
    When write=True, persists resolved status to JSON + DB for stale-complete
    handoffs only (all other stored statuses are left untouched).
    Default write=False — mutation-gated.
    """
    counts: dict = {
        "total": 0,
        "open": 0,
        "in_progress": 0,
        "blocked": 0,
        "acknowledged": 0,
        "complete": 0,
        "stale_complete": 0,
        "actionable": 0,
    }
    live_git = get_git_status()

    for path in get_handoff_files(agent):
        data = _read_handoff(path)
        if not data:
            continue
        counts["total"] += 1
        stored = (data.get("status") or "open").lower()
        live = compute_live_status(data, live_git)

        # Map hyphenated live status to underscore bucket key
        bucket = live.replace("-", "_") if live.replace("-", "_") in counts else "open"
        counts[bucket] = counts.get(bucket, 0) + 1
        if live in {"open", "in_progress", "blocked"}:
            counts["actionable"] += 1

        if write and live == "stale-complete" and stored != "stale-complete":
            data["status"] = "stale-complete"
            try:
                _atomic_write_json(path, data)
                _sync_handoff_to_db(path, data)
            except Exception:
                pass  # resilience: skip individual failures

    return counts


def handoff_feed(agent: Optional[str] = None, limit: int = 25) -> List[Dict]:
    """Structured relay feed — the same records `list_handoffs` prints, as data.

    Used by the HUD's Relay panel. Returns newest-first, already resolved to
    live status so the caller doesn't need git context of its own.
    """
    files = get_handoff_files(agent)
    if not files:
        return []

    live_git = get_git_status()
    feed: List[Dict] = []
    for p in files[:max(0, limit)]:
        data = _read_handoff(p)
        if not data:
            continue
        tasks = data.get("tasks", {}) or {}
        done = len(tasks.get("completed", []) or [])
        total = done + len(tasks.get("in_progress", []) or []) + len(tasks.get("pending", []) or [])
        stored = (data.get("status") or "open").lower()
        feed.append({
            "id": data.get("id") or p.stem,
            "timestamp": data.get("timestamp", ""),
            "agent": data.get("agent", "generic"),
            "machine": (data.get("machine") or {}).get("host") if isinstance(data.get("machine"), dict)
                       else data.get("machine", ""),
            "branch": (data.get("git") or {}).get("branch", "") if isinstance(data.get("git"), dict) else "",
            "goal": data.get("goal", ""),
            "tasks_done": done,
            "tasks_total": total,
            "status": stored,
            "live_status": compute_live_status(data, live_git),
            "acknowledged_by": data.get("acknowledged_by") or "",
        })
    return feed


def list_handoffs(agent: Optional[str] = None):
    console = _make_console()
    files = get_handoff_files(agent)
    if not files:
        console.print("[yellow]No handoff records found.[/yellow]")
        return

    live_git = get_git_status()

    table = Table(title="🤖 Agent Handoff History")
    table.add_column("Timestamp", style="cyan", no_wrap=True)
    table.add_column("Agent", style="blue")
    table.add_column("Machine", style="blue")
    table.add_column("Branch", style="magenta")
    table.add_column("Active Goal", style="green")
    table.add_column("Tasks", style="yellow", justify="right")
    table.add_column("Status", style="white")

    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            t = data["tasks"]
            total = len(t.get("completed", [])) + len(t.get("in_progress", [])) + len(t.get("pending", []))
            pct = f"{len(t.get('completed', []))}/{total}" if total > 0 else "0/0"
            # For compact tasks (summary string), show raw_count if present
            if "summary" in t and total == 0:
                raw = t.get("raw_count", "?")
                pct = f"?/{raw}"
            dt = datetime.fromisoformat(data["timestamp"]).strftime("%Y-%m-%d %H:%M")
            agent_name = data.get("agent", "generic").upper()
            stored = (data.get("status") or "open").lower()
            live = compute_live_status(data, live_git)
            # Build display string, show arrow when live differs from stored
            suffix = f" →{live}" if live != stored else ""
            if live == "acknowledged":
                ack_by = (data.get("acknowledged_by") or "?").upper()
                status_disp = f"[green]✅ {ack_by}[/green]"
            elif live == "in_progress":
                status_disp = f"[cyan]in_progress{suffix}[/cyan]"
            elif live == "complete":
                status_disp = f"[green]complete{suffix}[/green]"
            elif live == "blocked":
                status_disp = f"[red]blocked{suffix}[/red]"
            elif live == "stale-complete":
                status_disp = f"[dim green]stale-complete ({stored}→stale-complete)[/dim green]"
            else:
                status_disp = f"[yellow]🟡 open{suffix}[/yellow]"
            record_host = machine.record_machine(data).get("host") or "unknown"
            # A remote record describes a tree that does not exist here — mark it
            # so nobody reads the branch/dirty-file list as local truth.
            host_disp = (
                record_host
                if machine.is_local_record(data)
                else f"[magenta]{record_host} ⇢[/magenta]"
            )
            table.add_row(
                dt, agent_name, host_disp, data["git"]["branch"],
                data["goal"], pct, status_disp,
            )
        except Exception:
            pass

    console.print(table)


def show_latest_handoff(agent: Optional[str] = None):
    console = _make_console()
    files = get_handoff_files(agent)
    if not files:
        console.print("[yellow]No handoff records found.[/yellow]")
        return

    latest_path = files[0]
    try:
        with open(latest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        git_info = data["git"]
        tasks = data["tasks"]
        agent_name = data.get("agent", "generic").upper()

        stored = (data.get("status") or "open").lower()
        live = compute_live_status(data, git_info)
        live_marker = f" [dim](live: {live})[/dim]" if live != stored else ""

        # Acknowledgement status (the read-back state)
        if live == "acknowledged":
            ack_line = (
                f"[bold green]Status:[/bold green] ✅ acknowledged by "
                f"{(data.get('acknowledged_by') or '?').upper()} "
                f"at {data.get('acknowledged_at', '?')}{live_marker}\n"
            )
        elif live == "stale-complete":
            ack_line = (
                f"[bold green]Status:[/bold green] [dim green]stale-complete[/dim green] "
                f"(stored: {stored} → live: stale-complete)\n"
            )
        elif live in {"in_progress", "blocked", "complete"}:
            orchestration = data.get("orchestration") or {}
            checkpoints = orchestration.get("checkpoints") or []
            ack_line = (
                f"[bold green]Status:[/bold green] {live}{live_marker}\n"
                f"[bold cyan]Run ID:[/bold cyan] {orchestration.get('run_id', '?')}\n"
                f"[bold cyan]Checkpoints:[/bold cyan] {len(checkpoints)}\n"
            )
        else:
            ack_line = f"[bold yellow]Status:[/bold yellow] 🟡 OPEN{live_marker} — run `nougen handoff ack` to claim it\n"

        # Where it was written matters as much as who wrote it: the branch and
        # uncommitted files below only exist on that machine.
        record_host = machine.record_machine(data)
        origin = machine.record_origin(data)
        machine_line = (
            f"[bold cyan]Machine:[/bold cyan] {record_host.get('host', 'unknown')}"
            f" ({record_host.get('os', 'unknown OS')})"
        )
        if origin == "remote":
            machine_line += (
                f" [magenta]⇢ REMOTE — written elsewhere, "
                f"you are on {machine.host_label()}[/magenta]"
            )
        else:
            # Same box under another name. Worth saying — one computer counted
            # as two is how a fleet total quietly doubles — but it is not a
            # claim about where the record came from.
            alias = machine.record_alias_warning(data)
            if alias:
                machine_line += f" [yellow]⇢ {alias}[/yellow]"
        machine_line += "\n"

        # Format handoff details into rich panels
        summary = (
            f"[bold cyan]Timestamp:[/bold cyan] {data['timestamp']}\n"
            f"[bold cyan]Agent:[/bold cyan] {agent_name}\n"
            f"{machine_line}"
            f"[bold cyan]Goal:[/bold cyan] {data['goal']}\n"
            f"[bold cyan]Session ID:[/bold cyan] {data['session_id']}\n"
            f"[bold cyan]Notes:[/bold cyan] {data.get('message', 'None')}\n"
            f"{ack_line}"
        )
        console.print(
            Panel(summary, title="🤝 Latest Agent Handoff Summary", border_style="cyan")
        )

        # Checklist
        checklist = ""
        if "summary" in tasks:
            checklist += f"[bold yellow]Task Summary:[/bold yellow] {tasks['summary']}\n"
            if "raw_count" in tasks:
                checklist += f"[bold cyan]Total Tasks:[/bold cyan] {tasks['raw_count']}\n"
        else:
            completed = tasks.get("completed", [])
            in_progress = tasks.get("in_progress", [])
            pending = tasks.get("pending", [])
            total = len(completed) + len(in_progress) + len(pending)
            if total > 0:
                checklist += f"[bold yellow]Completion Rate:[/bold yellow] {len(completed)}/{total} ({len(completed)/total*100:.1f}%)\n\n"
            if in_progress:
                checklist += "[bold orange3]⏳ In Progress:[/bold orange3]\n"
                for t in in_progress:
                    checklist += f"  - {t}\n"
            if pending:
                checklist += "\n[bold red]⏹️ Pending:[/bold red]\n"
                for t in pending:
                    checklist += f"  - {t}\n"
            if completed:
                checklist += "\n[bold green]✅ Completed:[/bold green]\n"
                for t in completed[:5]:  # Show top 5 to avoid spam
                    checklist += f"  - {t}\n"
                if len(completed) > 5:
                    checklist += f"  ... and {len(completed) - 5} more.\n"
        console.print(
            Panel(
                checklist or "No tasks defined.",
                title="📋 Task Checklist",
                border_style="yellow",
            )
        )

        # Repository Status
        repo = f"[bold cyan]Active Branch:[/bold cyan] {git_info['branch']}\n"
        if git_info["changes"]:
            repo += "\n[bold orange3]📂 Uncommitted Changes:[/bold orange3]\n"
            for change in git_info["changes"]:
                repo += f"  - {change}\n"
        else:
            repo += "\n✨ No uncommitted changes.\n"

        if git_info["commits"]:
            repo += "\n[bold green]📜 Recent Commits:[/bold green]\n"
            for commit in git_info["commits"]:
                repo += f"  - {commit}\n"

        console.print(Panel(repo, title="🛠️ Repository Status", border_style="magenta"))

    except Exception as e:
        console.print(f"[red]Error loading handoff details: {e}[/red]")


def list_machines(agent: str | None = None) -> list[dict]:
    """Summarize every computer that has written a handoff here.

    This is the fleet roster: which boxes participate, when each was last seen,
    and which agents run on them. Derived from the records themselves so it
    cannot drift out of sync with reality.
    """
    seen: dict[str, dict] = {}
    for path in get_handoff_files(agent):
        data = _read_handoff(path)
        if not data:
            continue
        record_host = machine.record_machine(data)
        machine_key = record_host.get("machine_id") or "unknown"
        # Attribution follows the host name, not the id: fleet tooling that
        # stamps only a name still names a machine. A record with neither is
        # genuinely unattributed once records travel — claiming it as this
        # box's own would let a bulk import from elsewhere read as local work.
        identified = (record_host.get("host") or "unknown") != "unknown"
        # Keyed on the full identity, not the id alone: a relabelled box is a
        # distinct participant and must not be merged into one row.
        key = f"{machine_key}@{record_host.get('host', 'unknown')}"
        entry = seen.setdefault(key, {
            "machine_id": machine_key,
            "host": record_host.get("host", "unknown"),
            "os": record_host.get("os", "unknown"),
            "arch": record_host.get("arch", "unknown"),
            "is_self": identified and machine.is_local_record(data),
            "attributed": identified,
            "agents": set(),
            "handoffs": 0,
            "last_seen": data.get("timestamp"),
            "open": 0,
        })
        entry["handoffs"] += 1
        if data.get("agent"):
            entry["agents"].add(data["agent"])
        if (data.get("status") or "open") in OPEN_STATUSES:
            entry["open"] += 1
        stamp = data.get("timestamp") or ""
        if stamp > (entry["last_seen"] or ""):
            entry["last_seen"] = stamp

    machines = []
    for entry in seen.values():
        entry["agents"] = sorted(entry["agents"])
        machines.append(entry)
    return sorted(machines, key=lambda m: m.get("last_seen") or "", reverse=True)


def show_machines(agent: str | None = None) -> None:
    console = _make_console()
    machines = list_machines(agent)
    identity = machine.machine_identity(repo_root=PROJECT_ROOT)
    console.print(
        f"[bold cyan]This machine:[/bold cyan] {identity['host']} "
        f"({identity['os']} / {identity['arch']}) id [yellow]{identity['machine_id']}[/yellow]"
    )
    if not machines:
        console.print("[yellow]No handoff records yet — no fleet to report.[/yellow]")
        return

    table = Table(title="🖥️ Fleet — machines seen in handoffs")
    table.add_column("Machine", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("OS", style="blue")
    table.add_column("Agents", style="green")
    table.add_column("Handoffs", style="yellow", justify="right")
    table.add_column("Open", style="yellow", justify="right")
    table.add_column("Last seen", style="magenta")
    for entry in machines:
        if not entry.get("attributed", True):
            label = "[dim]unattributed (pre-identity)[/dim]"
        else:
            label = entry["host"] + (
                " [dim](this box)[/dim]" if entry["is_self"] else ""
            )
        last = (entry.get("last_seen") or "")[:16].replace("T", " ")
        table.add_row(
            label,
            entry["machine_id"],
            entry["os"],
            ", ".join(a.upper() for a in entry["agents"]) or "-",
            str(entry["handoffs"]),
            str(entry["open"]),
            last,
        )
    console.print(table)


def watch_handoffs(
    agent: Optional[str] = None,
    interval: float = 5.0,
    write: bool = False,
) -> None:
    """Opt-in live watcher: re-runs reconcile every `interval` seconds and
    prints a rich table of live status counts.  Never auto-starts on import.
    Pass write=True to persist stale-complete resolutions each cycle.
    Exit cleanly with Ctrl+C.
    """
    import time

    console = _make_console()
    console.print(
        f"[bold cyan]Watching handoffs[/bold cyan] "
        f"(agent={agent or 'all'}, interval={interval}s, write={write}). "
        "Press Ctrl+C to stop."
    )
    try:
        while True:
            counts = reconcile_handoffs(agent=agent, write=write)
            table = Table(title="Handoff Live Status")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", style="yellow", justify="right")
            for key, val in counts.items():
                table.add_row(key, str(val))
            console.print(table)
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("[bold yellow]Watcher stopped.[/bold yellow]")


def push_handoff_to_space(agent: Optional[str] = None, handoff_id: Optional[str] = None):
    """Pushes the target local handoff to the Hugging Face Space sync endpoint."""
    console = _make_console()
    if not agent:
        agent = detect_current_agent()

    target_path, data = _find_handoff(agent, handoff_id, None)
    if not target_path or not data:
        console.print("[red]Error: No handoff found to push.[/red]")
        return

    handoff_id = data.get("handoff_id") or target_path.stem

    # Resolve Space URL
    space_url = os.environ.get("HF_SPACE_URL", "https://whovisions-nga-hgf-space.hf.space").rstrip("/")

    # Resolve Token
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
    if not token:
        try:
            from . import keymaker
            token = keymaker.get_secret("HUGGINGFACE_API_KEY")
        except Exception:
            pass

    if not token:
        console.print("[red]Error: HUGGINGFACE_API_KEY not found in vault or environment.[/red]")
        return

    payload = {
        "agent": agent,
        "handoff_id": handoff_id,
        "data": data
    }

    url = f"{space_url}/sync/push"
    req_body = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    import urllib.request
    from urllib.error import URLError, HTTPError

    console.print(f"[*] Pushing handoff [yellow]{handoff_id}[/yellow] to [cyan]{url}[/cyan]...")

    try:
        req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("status") == "ok":
                console.print("[bold green]✅ Handoff synced to Space successfully![/bold green]")
            else:
                console.print(f"[red]Sync failed: {body}[/red]")
    except HTTPError as e:
        console.print(f"[red]HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')}[/red]")
    except URLError as e:
        console.print(f"[red]Network Error: {e.reason}[/red]")
    except Exception as e:
        console.print(f"[red]Unexpected Error: {e}[/red]")


def pull_handoff_from_space(agent: Optional[str] = None):
    """Pulls the latest handoff from the Hugging Face Space sync endpoint and indexes it locally."""
    console = _make_console()
    if not agent:
        agent = detect_current_agent()

    # Resolve Space URL
    space_url = os.environ.get("HF_SPACE_URL", "https://whovisions-nga-hgf-space.hf.space").rstrip("/")

    # Resolve Token
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
    if not token:
        try:
            from . import keymaker
            token = keymaker.get_secret("HUGGINGFACE_API_KEY")
        except Exception:
            pass

    if not token:
        console.print("[red]Error: HUGGINGFACE_API_KEY not found in vault or environment.[/red]")
        return

    url = f"{space_url}/sync/pull?agent={agent}"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    import urllib.request
    from urllib.error import URLError, HTTPError

    console.print(f"[*] Pulling latest handoff for [yellow]{agent}[/yellow] from [cyan]{url}[/cyan]...")

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

            handoff_id = data.get("handoff_id")
            if not handoff_id:
                console.print("[red]Error: Invalid handoff data received.[/red]")
                return

            # Write handoff file locally
            target_folder = HANDOFF_DIR
            if agent.lower() in AGENT_FOLDERS:
                target_folder = HANDOFF_DIR / AGENT_FOLDERS[agent.lower()]
            target_folder.mkdir(parents=True, exist_ok=True)

            json_path = target_folder / f"handoff_{handoff_id}.json"
            if json_path.exists():
                local_data = _read_handoff(json_path) or {}
                from .handoff_sync import merge_leg_records
                data = merge_leg_records(local_data, data)
            _atomic_write_json(json_path, data)

            # Reconstruct Sibling Markdown file
            md_path = target_folder / f"handoff_{handoff_id}.md"
            git_info = data.get("git", {})
            tasks = data.get("tasks", {})
            goal = data.get("goal", "No active goal.")
            message = data.get("message", "")

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# 🤝 Agent Handoff: {git_info.get('branch', 'unknown')} (Synced from Space)\n\n")
                f.write(f"**Agent**: `{agent.upper()}`\n")
                f.write(f"**Goal**: {goal}\n")
                if message:
                    f.write(f"**Notes**: {message}\n")
                f.write(f"**Session ID**: `{data.get('session_id', 'unknown')}`\n\n")

                f.write("## 📋 Checklist Status (Compact)\n")
                if "summary" in tasks:
                    f.write(f"- {tasks['summary']}\n")
                else:
                    completed = tasks.get("completed", [])
                    in_progress = tasks.get("in_progress", [])
                    pending = tasks.get("pending", [])
                    total = len(completed) + len(in_progress) + len(pending)
                    if total > 0:
                        f.write(f"- **Progress**: {len(completed)} / {total} tasks completed\n")
                    if in_progress:
                        f.write("\n### ⏳ In Progress\n")
                        for t in in_progress:
                            f.write(f"- [ ] {t}\n")

                f.write("\n## 🛠️ Repository Status\n")
                f.write(f"- **Active Branch**: `{git_info.get('branch', 'unknown')}`\n")

            # Rebuild handoff DB to index it
            db_synced = _sync_handoff_to_db(json_path, data)
            _log_context_event(
                "HANDOFF_PULLED",
                f"Handoff {handoff_id} pulled from Space and written to {json_path}.",
                _handoff_context_metadata(json_path, data, db_synced=db_synced),
            )

            console.print(f"[bold green]✅ Handoff {handoff_id} pulled and indexed successfully![/bold green]")
            console.print(f"- Metadata: [yellow]{json_path}[/yellow]")
            console.print(f"- Summary: [yellow]{md_path}[/yellow]")

    except HTTPError as e:
        if e.code == 404:
            console.print(f"[yellow]No handoffs found on Space for agent '{agent}'.[/yellow]")
        else:
            console.print(f"[red]HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')}[/red]")
    except URLError as e:
        console.print(f"[red]Network Error: {e.reason}[/red]")
    except Exception as e:
        console.print(f"[red]Unexpected Error: {e}[/red]")
