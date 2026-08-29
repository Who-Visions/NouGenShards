"""Parity tests for the CLI semantic renderer.

The contract: a command builds ONE payload; `--json` dumps it and the human
view formats that same dict. So anything a terminal shows, a script can read,
and TTY styling never changes content -- only appearance.
"""
import io
import json
import re
import types

import pytest

from nougen_shards import cli


ANSI = re.compile(r"\033\[[0-9;]*m")


def _run(payload, plain, json_mode=False, tty=False, monkeypatch=None):
    buf = io.StringIO()
    buf.isatty = lambda: tty  # type: ignore[method-assign]
    args = types.SimpleNamespace(json=json_mode)
    cli.emit(payload, plain, args, stream=buf)
    return buf.getvalue()


def _plain(p, style):
    yield style(f"Period: {p['period']}", "1")
    yield f"Count: {p['count']}"


PAYLOAD = {"period": "week", "count": 7}


def test_json_mode_emits_every_payload_field():
    out = _run(PAYLOAD, _plain, json_mode=True)
    assert json.loads(out) == PAYLOAD


def test_plain_output_has_no_ansi_when_not_a_tty(monkeypatch):
    monkeypatch.delenv("NOUGEN_FORCE_COLOR", raising=False)
    out = _run(PAYLOAD, _plain, tty=False)
    assert "\033[" not in out, "redirected output must stay byte-clean for grep"
    assert "Period: week" in out


def test_tty_styling_changes_appearance_not_content(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    plain_out = _run(PAYLOAD, _plain, tty=False)
    tty_out = _run(PAYLOAD, _plain, tty=True)
    assert "\033[" in tty_out, "a real TTY should get styling"
    assert ANSI.sub("", tty_out) == plain_out


def test_no_color_env_is_honored(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    out = _run(PAYLOAD, _plain, tty=True)
    assert "\033[" not in out


def test_human_view_cannot_invent_a_field_json_lacks():
    """The renderer hands `plain` the payload and nothing else."""
    seen = {}

    def capture(p, style):
        seen["payload"] = p
        yield "x"

    _run(PAYLOAD, capture)
    assert seen["payload"] is PAYLOAD


def test_stats_json_carries_timeline_and_acceleration(monkeypatch):
    """Regression: both were terminal-only, so --json saw strictly less.

    A script asking for stats could not read the timeline or the growth rate
    that the same command printed to a human.
    """
    class FakeEngine:
        def get_growth_rate(self, period):
            return {"new_shards": 5, "total_shards": 50}

        def get_utility_delta(self, period):
            return 1.25

        def get_timeline(self, period):
            return "|##########|"

    monkeypatch.setattr(cli.history, "HistoryEngine", lambda: FakeEngine())

    buf = io.StringIO()
    buf.isatty = lambda: False  # type: ignore[method-assign]
    monkeypatch.setattr(cli.sys, "stdout", buf)

    cli.cmd_stats(types.SimpleNamespace(period="week", json=True))
    data = json.loads(buf.getvalue())

    assert data["timeline"] == "|##########|"
    assert data["acceleration_rate_pct"] == pytest.approx(10.0)
    assert data["growth"]["new_shards"] == 5
    assert data["utility_delta"] == 1.25


def test_stats_acceleration_is_null_not_a_crash_on_empty_memory(monkeypatch):
    """Zero total shards must not divide by zero."""
    class EmptyEngine:
        def get_growth_rate(self, period):
            return {"new_shards": 0, "total_shards": 0}

        def get_utility_delta(self, period):
            return 0.0

        def get_timeline(self, period):
            return ""

    monkeypatch.setattr(cli.history, "HistoryEngine", lambda: EmptyEngine())

    buf = io.StringIO()
    buf.isatty = lambda: False  # type: ignore[method-assign]
    monkeypatch.setattr(cli.sys, "stdout", buf)

    cli.cmd_stats(types.SimpleNamespace(period="week", json=True))
    assert json.loads(buf.getvalue())["acceleration_rate_pct"] is None
