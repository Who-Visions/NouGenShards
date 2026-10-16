#!/usr/bin/env python3
"""Live Rich visualizer for sharding runs.

The griot sharder (tools/nougen_griot_sharder.py) reports its work as JSON lines:

    stderr  {"phase": "identity" | "distill" | "gather" | "judge", ...}
    stdout  {"candidate": {...}, "decision": {...}, "outcome": {...}}

This module turns that stream into a live terminal view: chunk progress, each
candidate as it is gathered, the persistence decision the judge made, and what
actually happened when the decision was carried out.

    python -m nougen_shards.shard_viz -- python tools/nougen_griot_sharder.py notes.md
    python -m nougen_shards.shard_viz --replay run.jsonl
    python tools/nougen_griot_sharder.py notes.md 2>&1 | python -m nougen_shards.shard_viz --stdin
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Any, IO, Iterable, Optional

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

ACTION_STYLE = {
    "CAPTURE": "bold green",
    "AMEND": "bold cyan",
    "RETRACT": "bold yellow",
    "SKIP": "dim",
}
# Outcome statuses containing any of these are failures, not progress.
FAILURE_MARKERS = ("blocked", "invalid", "unknown", "error", "failed")
MAX_ROWS = 14
LOG_LINES = 8


@dataclass
class CandidateRow:
    chunk: int
    title: str
    action: str = "pending"
    reason: str = ""
    status: str = ""


@dataclass
class RunState:
    model: str = ""
    identity: str = ""
    chunk_total: int = 0
    chunk_current: int = 0
    candidates: list[CandidateRow] = field(default_factory=list)
    log: deque[Text] = field(default_factory=lambda: deque(maxlen=LOG_LINES))
    started: float = field(default_factory=time.monotonic)
    finished_at: Optional[float] = None
    exit_code: Optional[int] = None
    replay: bool = False

    @property
    def chunks_done(self) -> int:
        if self.finished_at is not None:
            return self.chunk_total
        return max(self.chunk_current - 1, 0)

    def elapsed(self) -> float:
        return (self.finished_at or time.monotonic()) - self.started

    def note(self, message: str, style: str = "") -> None:
        prefix = "" if self.replay else f"+{self.elapsed():6.1f}s  "
        self.log.append(Text(f"{prefix}{message}", style=style))

    def add_row(self, chunk: int, title: str) -> CandidateRow:
        row = CandidateRow(chunk=chunk, title=title)
        self.candidates.append(row)
        return row

    def open_row(self, title: str, *, awaiting_judge: bool) -> Optional[CandidateRow]:
        """Most recent row for this title still waiting for judge or outcome."""
        for row in reversed(self.candidates):
            if row.title != title:
                continue
            if awaiting_judge and row.action == "pending":
                return row
            if not awaiting_judge and not row.status:
                return row
        return None

    def counts(self) -> dict[str, int]:
        return {a: sum(1 for r in self.candidates if r.action == a) for a in ACTION_STYLE}

    def failures(self) -> int:
        return sum(1 for r in self.candidates if status_style(r.status) == "bold red")


def status_style(status: str) -> str:
    s = status.lower()
    if not s or s == "unreported":
        return "dim"
    if any(marker in s for marker in FAILURE_MARKERS):
        return "bold red"
    if s == "skipped":
        return "dim"
    if s == "dry_run":
        return "yellow"
    return "green"


def _identity_label(fleet: Any) -> str:
    if isinstance(fleet, dict):
        for key in ("node", "host", "name", "identity"):
            if fleet.get(key):
                return str(fleet[key])
        return "ok"
    return "ok" if fleet else "unknown"


def _apply_phase(state: RunState, event: dict[str, Any]) -> None:
    phase = event["phase"]
    if phase == "identity":
        state.identity = _identity_label(event.get("fleet"))
        state.note(f"identity verified ({state.identity})", "dim")
    elif phase == "distill":
        state.model = str(event.get("model", state.model))
        state.chunk_total = int(event.get("chunks") or state.chunk_total)
        state.chunk_current = int(event.get("chunk") or 0)
        state.note(
            f"distilling chunk {state.chunk_current}/{state.chunk_total} "
            f"({event.get('characters', '?')} chars)",
            "cyan",
        )
    elif phase == "gather":
        title = str(event.get("title", "untitled"))
        state.add_row(int(event.get("chunk") or state.chunk_current), title)
        state.note(f"gathered: {title}")
    elif phase == "judge":
        title = str(event.get("title", "untitled"))
        action = str(event.get("action", "")).upper()
        row = state.open_row(title, awaiting_judge=True) or state.add_row(state.chunk_current, title)
        row.action = action or "pending"
        row.reason = str(event.get("reason", ""))
        state.note(f"judged {action or '?'}: {title}", ACTION_STYLE.get(action, ""))
    else:
        state.note(f"phase {phase}", "dim")


def _apply_result(state: RunState, event: dict[str, Any]) -> None:
    candidate = event.get("candidate") if isinstance(event.get("candidate"), dict) else {}
    decision = event.get("decision") if isinstance(event.get("decision"), dict) else {}
    outcome = event.get("outcome")
    title = str(candidate.get("title", "untitled"))
    status = str(outcome.get("status", "")) if isinstance(outcome, dict) else ""
    status = status or "unreported"

    row = state.open_row(title, awaiting_judge=False) or state.add_row(state.chunk_current, title)
    action = str(decision.get("action", "")).upper()
    if action:
        row.action = action
    if not row.reason:
        row.reason = str(decision.get("reason", ""))
    row.status = status
    state.note(f"{status}: {title}", status_style(status))


def apply_line(state: RunState, line: str) -> None:
    """Fold one line of sharder output into the run state. Unknown lines are logged, not fatal."""
    text = line.strip()
    if not text:
        return
    try:
        event = json.loads(text)
    except ValueError:
        state.note(text, "dim")
        return
    if not isinstance(event, dict):
        state.note(text, "dim")
    elif "phase" in event:  # checked first: gather events also carry a "candidate" (an index)
        _apply_phase(state, event)
    elif isinstance(event.get("candidate"), dict):
        _apply_result(state, event)
    else:
        state.note(text, "dim")


def _header(state: RunState) -> Panel:
    line = Text.assemble(
        ("model ", "dim"), (state.model or "?", "bold"),
        ("    fleet ", "dim"), (state.identity or "waiting", "bold"),
        ("    replay" if state.replay else f"    elapsed {state.elapsed():.1f}s", "dim"),
    )
    return Panel(line, title="shard run", border_style="cyan", box=box.ROUNDED)


def _progress(state: RunState) -> Table:
    total = state.chunk_total or 0
    done = state.chunks_done
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(style="dim", no_wrap=True)
    grid.add_column(ratio=1)
    grid.add_column(justify="right", no_wrap=True)
    grid.add_row("chunks", ProgressBar(total=max(total, 1), completed=done), f"{done}/{total}")
    counts = state.counts()
    judged = Text.assemble(*[
        item
        for action, style in ACTION_STYLE.items()
        for item in ((f"{action} ", style), (f"{counts[action]}   ", "bold"))
    ])
    grid.add_row("judged", judged, f"{len(state.candidates)} total")
    return grid


def _candidates(state: RunState) -> Table:
    table = Table(box=box.SIMPLE_HEAD, expand=True, show_edge=False)
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("chunk", justify="right", style="dim", no_wrap=True)
    table.add_column("title", ratio=3, overflow="ellipsis", no_wrap=True)
    table.add_column("judge", no_wrap=True)
    table.add_column("outcome", no_wrap=True)
    table.add_column("reason", ratio=2, overflow="ellipsis", no_wrap=True, style="dim")

    if not state.candidates:
        table.add_row("", "", Text("no candidates yet", style="dim"), "", "", "")

    start = max(len(state.candidates) - MAX_ROWS, 0)
    for number, row in enumerate(state.candidates[start:], start=start + 1):
        table.add_row(
            str(number),
            str(row.chunk) if row.chunk else "-",
            Text(row.title),
            Text(row.action, style=ACTION_STYLE.get(row.action, "dim italic")),
            Text(row.status or "-", style=status_style(row.status)),
            Text(row.reason),
        )
    if start:
        table.caption = Text(f"{start} earlier candidate(s) not shown", style="dim")
    return table


def _events(state: RunState) -> Panel:
    body: Group | Text = Group(*state.log) if state.log else Text("waiting for the sharder...", style="dim")
    return Panel(body, title="events", border_style="dim", box=box.ROUNDED)


def _footer(state: RunState) -> Text:
    if state.finished_at is None:
        return Text("running...", style="dim")
    counts = state.counts()
    parts = [
        ("finished  ", "bold"),
        (f"{len(state.candidates)} candidates  ", ""),
    ]
    for action, style in ACTION_STYLE.items():
        parts.append((f"{action} {counts[action]}  ", style))
    failures = state.failures()
    parts.append((f"failures {failures}  ", "bold red" if failures else "dim"))
    if state.exit_code is not None:
        parts.append((f"exit {state.exit_code}  ", "bold red" if state.exit_code else "dim"))
    if not state.replay:
        parts.append((f"{state.elapsed():.1f}s", "dim"))
    return Text.assemble(*parts)


def render(state: RunState) -> Group:
    return Group(_header(state), _progress(state), _candidates(state), _events(state), _footer(state))


def _pump(stream: IO[str], queue: "Queue[tuple[str, Optional[str]]]", tag: str) -> None:
    try:
        for line in stream:
            queue.put((tag, line))
    finally:
        queue.put((tag, None))


def _consume(
    state: RunState,
    queue: "Queue[tuple[str, Optional[str]]]",
    sources: int,
    console: Console,
    refresh: float,
    proc: Optional[subprocess.Popen] = None,
) -> None:
    with Live(render(state), console=console, refresh_per_second=refresh) as live:
        while sources:
            try:
                _, line = queue.get(timeout=0.25)
            except Empty:
                live.update(render(state))
                continue
            if line is None:
                sources -= 1
            else:
                apply_line(state, line)
            live.update(render(state))
        if proc is not None:
            state.exit_code = proc.wait()
        state.finished_at = time.monotonic()
        live.update(render(state))


def run_command(cmd: list[str], console: Console, refresh: float = 8.0) -> int:
    """Run a sharder command, rendering its stderr and stdout as they arrive."""
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    queue: "Queue[tuple[str, Optional[str]]]" = Queue()
    for stream, tag in ((proc.stdout, "out"), (proc.stderr, "err")):
        threading.Thread(target=_pump, args=(stream, queue, tag), daemon=True).start()

    state = RunState()
    _consume(state, queue, sources=2, console=console, refresh=refresh, proc=proc)
    return state.exit_code or 0


def replay(lines: Iterable[str]) -> RunState:
    """Fold a saved run log into a finished state, with no clock."""
    state = RunState(replay=True)
    for line in lines:
        apply_line(state, line)
    state.finished_at = state.started
    return state


def main(argv: Optional[list[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw:
        sep = raw.index("--")
        own, cmd = raw[:sep], raw[sep + 1:]
    else:
        own, cmd = raw, []

    parser = argparse.ArgumentParser(
        prog="python -m nougen_shards.shard_viz",
        description="Live Rich view of a sharding run. Give a command after -- to run it, "
        "or use --replay / --stdin with a saved JSON-lines log.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--replay", metavar="FILE", type=Path, help="render a saved run log once")
    source.add_argument("--stdin", action="store_true", help="render a run log piped on stdin")
    parser.add_argument("--refresh", type=float, default=8.0, help="redraws per second (default 8)")
    args = parser.parse_args(own)

    console = Console()
    if args.replay:
        with args.replay.open(encoding="utf-8", errors="replace") as fh:
            state = replay(fh)
        console.print(render(state))
        return 1 if state.failures() else 0

    if args.stdin:
        queue: "Queue[tuple[str, Optional[str]]]" = Queue()
        threading.Thread(target=_pump, args=(sys.stdin, queue, "in"), daemon=True).start()
        _consume(RunState(), queue, sources=1, console=console, refresh=args.refresh)
        return 0

    if not cmd:
        parser.error("give a command after --, or use --replay FILE / --stdin")
    return run_command(cmd, console, args.refresh)


if __name__ == "__main__":
    raise SystemExit(main())
