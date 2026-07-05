"""Open Engine task queue: ticket-level cross-agent work coordination.

Extends the session-level handoff registry with per-task semantics so agents
from different providers (claude-cli, gemini, codex, ollama, openrouter) can
delegate work to each other mid-session instead of only at session end:

- claim locks   — an atomic UPDATE guarantees two agents never work one task
- status lanes  — todo -> working -> needs_input -> done (or cancelled)
- needs-input   — on ambiguity the agent parks the task with the exact
                  blocking question instead of guessing; a human (or another
                  agent) answers on the ticket and the task re-enters todo
- receipts      — a task cannot reach done without stating what was done and
                  what evidence proves it

Tasks live in the same SQLite index as handoffs (handoffs.db, WAL mode), so
the existing rebuild/reconcile tooling and the .handoffs directory remain the
single system of record. A human-readable markdown ledger for each task is
kept under .handoffs/queue/.
"""

import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from rich.panel import Panel
from rich.table import Table

from . import handoff
from .handoff import (
    _get_db_connection,
    _log_context_event,
    _make_console,
    detect_current_agent,
)


def _queue_dir():
    # Resolved lazily so NOUGEN_HANDOFF_DIR overrides and test monkeypatching
    # of handoff.HANDOFF_DIR keep the queue ledger next to the handoff index.
    return handoff.HANDOFF_DIR / "queue"

OPEN_TASK_STATUSES = {"todo", "working", "needs_input"}
TERMINAL_TASK_STATUSES = {"done", "cancelled"}


def _now() -> str:
    return datetime.now().isoformat()


def _acting_agent(agent: Optional[str] = None) -> str:
    return (agent or os.environ.get("NOUGEN_AGENT") or detect_current_agent()).lower()


def init_task_db() -> None:
    """Create the agent_tasks table inside the shared handoff index."""
    conn = _get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_tasks (
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                instructions TEXT,
                owner TEXT,
                created_by TEXT,
                status TEXT NOT NULL DEFAULT 'todo',
                claimed_by TEXT,
                claimed_at TEXT,
                sources TEXT,
                allowed_actions TEXT,
                stop_conditions TEXT,
                definition_of_done TEXT,
                blocking_question TEXT,
                answer TEXT,
                answered_by TEXT,
                answered_at TEXT,
                receipt_done TEXT,
                receipt_not_done TEXT,
                receipt_evidence TEXT,
                handoff_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                done_at TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_tasks_owner_status "
            "ON agent_tasks(owner, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_tasks_status "
            "ON agent_tasks(status)"
        )
        conn.commit()
    finally:
        conn.close()


def _task_md_path(task_id: str):
    return _queue_dir() / f"task_{task_id}.md"


def _append_task_md(task_id: str, title: str, lines: List[str]) -> None:
    """Append an event to the task's markdown ledger (best-effort)."""
    try:
        _queue_dir().mkdir(parents=True, exist_ok=True)
        with open(_task_md_path(task_id), "a", encoding="utf-8") as f:
            f.write(f"\n## {title} — {_now()}\n")
            for line in lines:
                f.write(f"- {line}\n")
    except Exception:
        pass


def _fetch_task(conn, task_id: str) -> Optional[Dict]:
    row = conn.execute(
        "SELECT * FROM agent_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    return dict(row) if row else None


def get_task(task_id: str) -> Optional[Dict]:
    init_task_db()
    conn = _get_db_connection()
    try:
        return _fetch_task(conn, task_id)
    finally:
        conn.close()


def add_task(
    title: str,
    instructions: str = "",
    owner: Optional[str] = None,
    created_by: Optional[str] = None,
    sources: str = "",
    allowed_actions: str = "",
    stop_conditions: str = "",
    definition_of_done: str = "",
    handoff_id: Optional[str] = None,
) -> str:
    """Create a self-contained ticket. Returns the task_id.

    A good ticket carries: what needs to happen (instructions), who owns it
    (owner lane), the background that matters (sources), what the agent can
    do (allowed_actions), where it must stop (stop_conditions), and what it
    has to show when done (definition_of_done).
    """
    init_task_db()
    creator = _acting_agent(created_by)
    task_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    now = _now()
    conn = _get_db_connection()
    try:
        conn.execute("""
            INSERT INTO agent_tasks (
                task_id, title, instructions, owner, created_by, status,
                sources, allowed_actions, stop_conditions, definition_of_done,
                handoff_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id, title, instructions, (owner or "").lower() or None,
            creator, sources, allowed_actions, stop_conditions,
            definition_of_done, handoff_id, now, now,
        ))
        conn.commit()
    finally:
        conn.close()

    _append_task_md(task_id, "Created", [
        f"Title: {title}",
        f"By: `{creator}`",
        f"Owner lane: `{owner or 'any'}`",
        f"Instructions: {instructions or 'none'}",
        f"Definition of done: {definition_of_done or 'none'}",
    ])
    _log_context_event(
        "TASK_CREATED",
        f"Task {task_id} created by {creator} for {owner or 'any'}: {title}",
        {"task_id": task_id, "owner": owner, "created_by": creator},
    )
    return task_id


def claim_task(
    task_id: Optional[str] = None,
    agent: Optional[str] = None,
) -> Optional[Dict]:
    """Atomically claim a task and move it to 'working'.

    The UPDATE ... WHERE status='todo' guard is the claim lock: under WAL,
    exactly one agent's update matches, so concurrent claimers cannot both
    win. Without task_id, claims the oldest eligible task for this agent's
    lane (owner matches the agent, or owner is unset).
    """
    init_task_db()
    receiver = _acting_agent(agent)
    now = _now()
    conn = _get_db_connection()
    try:
        if task_id is None:
            row = conn.execute("""
                SELECT task_id FROM agent_tasks
                WHERE status = 'todo' AND (owner IS NULL OR owner = ?)
                ORDER BY created_at ASC LIMIT 1
            """, (receiver,)).fetchone()
            if not row:
                return None
            task_id = row["task_id"]

        cur = conn.execute("""
            UPDATE agent_tasks
            SET status = 'working', claimed_by = ?, claimed_at = ?, updated_at = ?
            WHERE task_id = ? AND status = 'todo'
        """, (receiver, now, now, task_id))
        conn.commit()
        if cur.rowcount != 1:
            return None  # lost the race, or task not claimable
        task = _fetch_task(conn, task_id)
    finally:
        conn.close()

    _append_task_md(task_id, "Claimed", [
        f"By: `{receiver}`",
        "Status: `todo` → `working`",
    ])
    _log_context_event(
        "TASK_CLAIMED",
        f"Task {task_id} claimed by {receiver}",
        {"task_id": task_id, "claimed_by": receiver},
    )
    return task


def block_task(
    task_id: str,
    question: str,
    agent: Optional[str] = None,
) -> bool:
    """Park a working task in 'needs_input' with the exact blocking question.

    The agent does not guess: it records what decision it needs, and the
    audit trail stays on the ticket.
    """
    if not question.strip():
        return False
    init_task_db()
    receiver = _acting_agent(agent)
    now = _now()
    conn = _get_db_connection()
    try:
        cur = conn.execute("""
            UPDATE agent_tasks
            SET status = 'needs_input', blocking_question = ?, updated_at = ?
            WHERE task_id = ? AND status = 'working'
        """, (question, now, task_id))
        conn.commit()
        ok = cur.rowcount == 1
    finally:
        conn.close()
    if ok:
        _append_task_md(task_id, "Needs Input", [
            f"By: `{receiver}`",
            f"Blocking question: {question}",
        ])
        _log_context_event(
            "TASK_NEEDS_INPUT",
            f"Task {task_id} blocked by {receiver}: {question}",
            {"task_id": task_id, "question": question},
        )
    return ok


def answer_task(
    task_id: str,
    answer: str,
    agent: Optional[str] = None,
) -> bool:
    """Answer a needs_input task on the ticket; it re-enters 'todo' so the
    owner lane picks it up on its next heartbeat with the answer attached."""
    if not answer.strip():
        return False
    init_task_db()
    responder = _acting_agent(agent)
    now = _now()
    conn = _get_db_connection()
    try:
        cur = conn.execute("""
            UPDATE agent_tasks
            SET status = 'todo', answer = ?, answered_by = ?, answered_at = ?,
                claimed_by = NULL, claimed_at = NULL, updated_at = ?
            WHERE task_id = ? AND status = 'needs_input'
        """, (answer, responder, now, now, task_id))
        conn.commit()
        ok = cur.rowcount == 1
    finally:
        conn.close()
    if ok:
        _append_task_md(task_id, "Answered", [
            f"By: `{responder}`",
            f"Answer: {answer}",
            "Status: `needs_input` → `todo` (resumable)",
        ])
        _log_context_event(
            "TASK_ANSWERED",
            f"Task {task_id} answered by {responder}",
            {"task_id": task_id, "answered_by": responder},
        )
    return ok


def complete_task(
    task_id: str,
    receipt_done: str,
    receipt_evidence: str = "",
    receipt_not_done: str = "",
    agent: Optional[str] = None,
) -> bool:
    """Move a working task to 'done'. The receipt is mandatory: a task with
    no statement of what was done cannot land — receipts are how the next
    reader knows it got done without asking."""
    if not receipt_done.strip():
        return False
    init_task_db()
    receiver = _acting_agent(agent)
    now = _now()
    conn = _get_db_connection()
    try:
        cur = conn.execute("""
            UPDATE agent_tasks
            SET status = 'done', receipt_done = ?, receipt_evidence = ?,
                receipt_not_done = ?, done_at = ?, updated_at = ?
            WHERE task_id = ? AND status = 'working'
        """, (receipt_done, receipt_evidence, receipt_not_done, now, now, task_id))
        conn.commit()
        ok = cur.rowcount == 1
    finally:
        conn.close()
    if ok:
        _append_task_md(task_id, "Done — Receipt", [
            f"By: `{receiver}`",
            f"Did: {receipt_done}",
            f"Did not: {receipt_not_done or 'n/a'}",
            f"Evidence: {receipt_evidence or 'n/a'}",
        ])
        _log_context_event(
            "TASK_COMPLETED",
            f"Task {task_id} completed by {receiver}: {receipt_done}",
            {"task_id": task_id, "completed_by": receiver},
        )
    return ok


def cancel_task(task_id: str, reason: str = "", agent: Optional[str] = None) -> bool:
    init_task_db()
    receiver = _acting_agent(agent)
    now = _now()
    conn = _get_db_connection()
    try:
        cur = conn.execute("""
            UPDATE agent_tasks
            SET status = 'cancelled', receipt_not_done = ?, updated_at = ?
            WHERE task_id = ? AND status IN ('todo', 'working', 'needs_input')
        """, (reason, now, task_id))
        conn.commit()
        ok = cur.rowcount == 1
    finally:
        conn.close()
    if ok:
        _append_task_md(task_id, "Cancelled", [
            f"By: `{receiver}`",
            f"Reason: {reason or 'none given'}",
        ])
        _log_context_event(
            "TASK_CANCELLED",
            f"Task {task_id} cancelled by {receiver}: {reason}",
            {"task_id": task_id},
        )
    return ok


def list_tasks(
    owner: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict]:
    init_task_db()
    query = "SELECT * FROM agent_tasks WHERE 1=1"
    params: list = []
    if owner:
        query += " AND owner = ?"
        params.append(owner.lower())
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    conn = _get_db_connection()
    try:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------- rendering

_STATUS_STYLES = {
    "todo": "[yellow]todo[/yellow]",
    "working": "[cyan]working[/cyan]",
    "needs_input": "[red]needs_input[/red]",
    "done": "[green]done[/green]",
    "cancelled": "[dim]cancelled[/dim]",
}


def render_task_list(owner: Optional[str] = None, status: Optional[str] = None):
    console = _make_console()
    tasks = list_tasks(owner, status)
    if not tasks:
        console.print("[yellow]No tasks in the queue.[/yellow]")
        return
    table = Table(title="🎟️ Agent Task Queue")
    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="green")
    table.add_column("Owner", style="blue")
    table.add_column("Claimed By", style="magenta")
    table.add_column("Status", style="white")
    for t in tasks:
        table.add_row(
            t["task_id"],
            (t["title"] or "")[:60],
            t["owner"] or "any",
            t["claimed_by"] or "-",
            _STATUS_STYLES.get(t["status"], t["status"]),
        )
    console.print(table)


def render_task(task_id: str):
    console = _make_console()
    task = get_task(task_id)
    if not task:
        console.print(f"[red]No task found with id '{task_id}'.[/red]")
        return
    body = (
        f"[bold cyan]Title:[/bold cyan] {task['title']}\n"
        f"[bold cyan]Status:[/bold cyan] {task['status']}\n"
        f"[bold cyan]Owner lane:[/bold cyan] {task['owner'] or 'any'}\n"
        f"[bold cyan]Created by:[/bold cyan] {task['created_by']} at {task['created_at']}\n"
        f"[bold cyan]Claimed by:[/bold cyan] {task['claimed_by'] or '-'}\n"
        f"[bold cyan]Instructions:[/bold cyan] {task['instructions'] or 'none'}\n"
        f"[bold cyan]Sources:[/bold cyan] {task['sources'] or 'none'}\n"
        f"[bold cyan]Allowed actions:[/bold cyan] {task['allowed_actions'] or 'unrestricted'}\n"
        f"[bold cyan]Stop conditions:[/bold cyan] {task['stop_conditions'] or 'none'}\n"
        f"[bold cyan]Definition of done:[/bold cyan] {task['definition_of_done'] or 'none'}\n"
    )
    if task["blocking_question"]:
        body += f"[bold red]Blocking question:[/bold red] {task['blocking_question']}\n"
    if task["answer"]:
        body += (
            f"[bold green]Answer:[/bold green] {task['answer']} "
            f"(by {task['answered_by']} at {task['answered_at']})\n"
        )
    if task["receipt_done"]:
        body += (
            f"[bold green]Receipt — did:[/bold green] {task['receipt_done']}\n"
            f"[bold yellow]Receipt — did not:[/bold yellow] {task['receipt_not_done'] or 'n/a'}\n"
            f"[bold cyan]Evidence:[/bold cyan] {task['receipt_evidence'] or 'n/a'}\n"
        )
    console.print(Panel(body, title=f"🎟️ Task {task_id}", border_style="cyan"))


def smoke_test(agent: Optional[str] = None) -> bool:
    """Open Engine smoke test: create 'Say hello from the queue', claim it,
    complete it with a receipt, and verify the full lane transition."""
    console = _make_console()
    lane = _acting_agent(agent)
    console.print(f"[cyan]Queue smoke test as `{lane}`...[/cyan]")

    task_id = add_task(
        title="Say hello from the queue",
        instructions="Smoke test: claim this task and complete it with a receipt.",
        owner=lane,
        created_by=lane,
        definition_of_done="Task reaches status 'done' with a receipt.",
    )
    steps = {"created": True}
    steps["claimed"] = claim_task(task_id, agent=lane) is not None
    steps["completed"] = complete_task(
        task_id,
        receipt_done="Hello from the queue.",
        receipt_evidence="smoke_test transition todo→working→done",
        agent=lane,
    )
    final = get_task(task_id)
    steps["verified_done"] = bool(final and final["status"] == "done")

    passed = all(steps.values())
    for name, ok in steps.items():
        console.print(f"  {'✅' if ok else '❌'} {name}")
    console.print(
        f"[bold green]Queue smoke test PASSED ({task_id}).[/bold green]"
        if passed
        else f"[bold red]Queue smoke test FAILED ({task_id}).[/bold red]"
    )
    return passed
