"""Tests for the sharding progress visualizer (nougen_shards.shard_viz)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

from rich.console import Console

from nougen_shards import shard_viz as sv

FIXTURE = Path(__file__).parent / "fixtures" / "shard_run_sample.jsonl"


def _render_text(state: sv.RunState) -> str:
    console = Console(record=True, width=140, file=io.StringIO())
    console.print(sv.render(state))
    return console.export_text()


def test_replay_folds_every_candidate_to_its_judge_and_outcome():
    state = sv.replay(FIXTURE.read_text(encoding="utf-8").splitlines())

    assert state.model == "gemma4:cloud"
    assert state.identity == "example-node"
    assert state.chunk_total == 2
    assert [r.action for r in state.candidates] == ["CAPTURE", "SKIP", "AMEND", "RETRACT"]
    assert [r.status for r in state.candidates] == [
        "capture_attempted", "skipped", "amend_blocked", "retracted",
    ]
    assert state.counts() == {"CAPTURE": 1, "AMEND": 1, "RETRACT": 1, "SKIP": 1}
    assert state.failures() == 1  # amend_blocked


def test_chunk_progress_counts_only_finished_chunks_until_the_run_ends():
    state = sv.RunState()
    sv.apply_line(state, '{"phase": "distill", "chunk": 2, "chunks": 3, "characters": 10, "model": "m"}')
    assert state.chunks_done == 1  # chunk 2 is in flight

    state.finished_at = state.started
    assert state.chunks_done == 3


def test_unparseable_and_unknown_lines_are_logged_not_fatal():
    state = sv.RunState()
    sv.apply_line(state, "Traceback (most recent call last):")
    sv.apply_line(state, '{"something": "else"}')
    sv.apply_line(state, "   ")

    assert len(state.log) == 2
    assert state.candidates == []


def test_judge_without_a_gather_line_still_creates_a_row():
    state = sv.RunState()
    sv.apply_line(state, '{"phase": "judge", "title": "Orphan", "action": "CAPTURE", "reason": "r"}')

    assert [(r.title, r.action) for r in state.candidates] == [("Orphan", "CAPTURE")]


def test_rich_markup_in_titles_is_rendered_literally():
    state = sv.RunState()
    sv.apply_line(state, '{"phase": "gather", "chunk": 1, "candidate": 1, "title": "[bold]not markup[/bold]"}')

    text = _render_text(state)
    assert "[bold]not markup[/bold]" in text


def test_render_shows_the_run_at_a_glance():
    state = sv.replay(FIXTURE.read_text(encoding="utf-8").splitlines())

    text = _render_text(state)
    assert "Retention policy amendment" in text
    assert "amend_blocked" in text
    assert "failures 1" in text


def test_run_command_streams_a_child_process_to_completion():
    child = (
        "import json, sys\n"
        "print(json.dumps({'phase': 'distill', 'chunk': 1, 'chunks': 1, 'characters': 5, 'model': 'x'}), file=sys.stderr)\n"
        "print(json.dumps({'phase': 'judge', 'title': 'Child fact', 'action': 'CAPTURE', 'reason': 'r'}), file=sys.stderr)\n"
        "print(json.dumps({'candidate': {'title': 'Child fact'}, 'decision': {'action': 'CAPTURE', 'reason': 'r'}, "
        "'outcome': {'status': 'capture_attempted'}}))\n"
    )
    console = Console(file=io.StringIO(), force_terminal=False)

    code = sv.run_command([sys.executable, "-c", child], console, refresh=30.0)

    assert code == 0


def test_main_replay_returns_nonzero_when_a_write_failed(capsys):
    code = sv.main(["--replay", str(FIXTURE)])

    assert code == 1  # the fixture contains one blocked AMEND
    assert "Retention policy amendment" in capsys.readouterr().out


def test_main_requires_a_source():
    try:
        sv.main([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse to reject a bare invocation")


def test_render_ascii_fallback(capsys):
    state = sv.replay(FIXTURE.read_text(encoding="utf-8").splitlines())
    console = Console(record=True, width=80, file=io.StringIO(), force_terminal=True, legacy_windows=False)
    console.print(sv.render(state, ascii_mode=True))
    text = console.export_text()
    
    # ASCII box characters
    assert "+-" in text
    assert "| " in text or "|" in text
    assert "CAPTURE" in text
    assert "AMEND" in text


def test_render_80_columns():
    state = sv.replay(FIXTURE.read_text(encoding="utf-8").splitlines())
    console = Console(record=True, width=80, file=io.StringIO(), force_terminal=True)
    console.print(sv.render(state, ascii_mode=False))
    lines = console.export_text().splitlines()
    
    # Assert every line respects terminal width
    for line in lines:
        assert len(line) <= 80
