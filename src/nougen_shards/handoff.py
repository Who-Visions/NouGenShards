import os
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Handoff notes live in <repo>/.handoffs by default. Override with NOUGEN_HANDOFF_DIR
# so the system works regardless of where it is installed or invoked from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HANDOFF_DIR = Path(os.environ.get("NOUGEN_HANDOFF_DIR", PROJECT_ROOT / ".handoffs"))

AGENT_FOLDERS = {
    "gemini": "gemini handoffs",
    "claude": "claude handoffs",
    "codex": "codex handoffs",
    "ollama": "ollama handoffs",
    "openrouter": "openrouter handoffs",
}


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
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    if os.environ.get("CLAUDE_CODE") or os.environ.get("ANTHROPIC_API_KEY"):
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
    message: str = "", agent: Optional[str] = None, goal: Optional[str] = None
) -> Optional[Path]:
    console = Console()
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

    handoff_data = {
        "handoff_id": f"{timestamp}_{branch}",
        "timestamp": datetime.now().isoformat(),
        "goal": goal,
        "message": message,
        "git": git_info,
        "tasks": tasks,
        "session_id": brain_dir.name if brain_dir else "unknown",
        "agent": agent.lower(),
        "status": "open",
        "acknowledged_by": None,
        "acknowledged_at": None,
    }

    # Save JSON file (atomic: temp + replace prevents truncated records)
    json_path = target_folder / f"handoff_{timestamp}_{branch}.json"
    try:
        _atomic_write_json(json_path, handoff_data)
    except Exception as e:
        console.print(f"[red]Error saving handoff JSON: {e}[/red]")
        return None

    # Save Markdown file
    md_path = target_folder / f"handoff_{timestamp}_{branch}.md"
    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# 🤝 Agent Handoff: {branch} @ {timestamp}\n\n")
            f.write(f"**Agent**: `{agent.upper()}`\n")
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

    console.print(f"[bold green]🤝 Handoff created successfully for {agent.upper()}![/bold green]")
    console.print(f"- Metadata: [yellow]{json_path}[/yellow]")
    console.print(f"- Summary: [yellow]{md_path}[/yellow]")
    return json_path


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

    return sorted(
        files,
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def acknowledge_handoff(
    agent: Optional[str] = None,
    message: str = "",
    handoff_id: Optional[str] = None,
) -> Optional[Path]:
    """Marks a handoff as received — the read-back / forcing function that makes
    the transfer of responsibility unambiguous. By default acknowledges the most
    recent still-open handoff; pass handoff_id to target a specific one, or
    --agent to filter by the agent that created it."""
    console = Console()
    files = get_handoff_files(agent)
    if not files:
        console.print("[yellow]No handoff records found to acknowledge.[/yellow]")
        return None

    target_path: Optional[Path] = None
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

    if target_path is None:
        if handoff_id:
            console.print(f"[red]No handoff found with id '{handoff_id}'.[/red]")
        else:
            console.print("[yellow]All handoffs are already acknowledged.[/yellow]")
        return None

    receiver = (os.environ.get("NOUGEN_AGENT") or detect_current_agent()).lower()
    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
        data["status"] = "acknowledged"
        data["acknowledged_by"] = receiver
        data["acknowledged_at"] = datetime.now().isoformat()
        if message:
            data["acknowledgement_note"] = message
        _atomic_write_json(target_path, data)
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
                f.write(f"- **At**: {data['acknowledged_at']}\n")
                if message:
                    f.write(f"- **Note**: {message}\n")
        except Exception:
            pass

    console.print(
        f"[bold green]✅ Handoff {data.get('handoff_id', target_path.stem)} "
        f"acknowledged by {receiver.upper()}.[/bold green]"
    )
    return target_path


def list_handoffs(agent: Optional[str] = None):
    console = Console()
    files = get_handoff_files(agent)
    if not files:
        console.print("[yellow]No handoff records found.[/yellow]")
        return

    table = Table(title="🤖 Agent Handoff History")
    table.add_column("Timestamp", style="cyan", no_wrap=True)
    table.add_column("Agent", style="blue")
    table.add_column("Branch", style="magenta")
    table.add_column("Active Goal", style="green")
    table.add_column("Tasks", style="yellow", justify="right")
    table.add_column("Status", style="white")

    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            t = data["tasks"]
            total = len(t["completed"]) + len(t["in_progress"]) + len(t["pending"])
            pct = f"{len(t['completed'])}/{total}" if total > 0 else "0/0"
            dt = datetime.fromisoformat(data["timestamp"]).strftime("%Y-%m-%d %H:%M")
            agent_name = data.get("agent", "generic").upper()
            if data.get("status") == "acknowledged":
                ack_by = (data.get("acknowledged_by") or "?").upper()
                status_disp = f"[green]✅ {ack_by}[/green]"
            else:
                status_disp = "[yellow]🟡 open[/yellow]"
            table.add_row(dt, agent_name, data["git"]["branch"], data["goal"], pct, status_disp)
        except Exception:
            pass

    console.print(table)


def show_latest_handoff(agent: Optional[str] = None):
    console = Console()
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

        # Acknowledgement status (the read-back state)
        if data.get("status") == "acknowledged":
            ack_line = (
                f"[bold green]Status:[/bold green] ✅ acknowledged by "
                f"{(data.get('acknowledged_by') or '?').upper()} "
                f"at {data.get('acknowledged_at', '?')}\n"
            )
        else:
            ack_line = "[bold yellow]Status:[/bold yellow] 🟡 OPEN — run `nougen handoff ack` to claim it\n"

        # Format handoff details into rich panels
        summary = (
            f"[bold cyan]Timestamp:[/bold cyan] {data['timestamp']}\n"
            f"[bold cyan]Agent:[/bold cyan] {agent_name}\n"
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
        total = (
            len(tasks["completed"])
            + len(tasks["in_progress"])
            + len(tasks["pending"])
        )
        if total > 0:
            checklist += f"[bold yellow]Completion Rate:[/bold yellow] {len(tasks['completed'])}/{total} ({len(tasks['completed'])/total*100:.1f}%)\n\n"
        if tasks["in_progress"]:
            checklist += "[bold orange3]⏳ In Progress:[/bold orange3]\n"
            for t in tasks["in_progress"]:
                checklist += f"  - {t}\n"
        if tasks["pending"]:
            checklist += "\n[bold red]⏹️ Pending:[/bold red]\n"
            for t in tasks["pending"]:
                checklist += f"  - {t}\n"
        if tasks["completed"]:
            checklist += "\n[bold green]✅ Completed:[/bold green]\n"
            for t in tasks["completed"][:5]:  # Show top 5 to avoid spam
                checklist += f"  - {t}\n"
            if len(tasks["completed"]) > 5:
                checklist += f"  ... and {len(tasks['completed']) - 5} more.\n"
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
