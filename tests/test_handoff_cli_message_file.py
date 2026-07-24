"""CLI-layer coverage for `nougen handoff --message-file/-M`.

Why this file exists: the documented handoff bug lives in the *shell/arg* layer,
not in the Python API. cmd.exe ends an argument at the first newline, so a
templated multi-line note passed via `-m` silently landed as its first heading
only (measured: a 2,600-char note wrote 19 chars); POSIX/PowerShell double
quoting separately expanded `$3`/`$4` inside currency figures. `-M` is the
documented mitigation, and it can only be exercised through argparse +
`cli.cmd_handoff` — calling `handoff.create_handoff()` with a clean Python
string bypasses every line of code where the bug lives.

Every test here drives the real parser (`cli.get_parser().parse_args`) and the
real dispatcher, and writes into a throwaway NOUGEN_HANDOFF_DIR — never the
shared `.handoffs` registry.
"""

import json
import sys
from pathlib import Path

import pytest

import nougen_shards.cli as cli
from nougen_shards import handoff, nougen_context


# A realistic templated note: >1000 chars, several `##` headings, non-ASCII
# section markers, and an embedded currency figure. This is exactly the shape
# of payload that the shell layer used to destroy.
TEMPLATED_NOTE = (
    "## \U0001f534 Active Incidents\n"
    "- None. Runtime previously ignited; current status unverified.\n"
    "\n"
    "## \U0001f7e1 Ongoing Investigations\n"
    "- Handoff writer regression: multi-line notes truncated to their first heading\n"
    "  when passed through cmd.exe via -m. Root cause is the shell argument\n"
    "  terminator, not the writer, so the fix is --message-file.\n"
    "- Currency mangling: POSIX double quoting expanded $3/$4 as capture groups,\n"
    "  turning the reconciled claim total $3,922.07 into a figure missing its\n"
    "  leading digits. Verified against the source ledger before re-recording.\n"
    "\n"
    "## \U0001f4cb Recent Changes\n"
    "- Added CLI-layer coverage for --message-file / -M so the mitigation cannot\n"
    "  be gutted without a red test.\n"
    "- Reconciled claim total: $3,922.07 across 14 line items.\n"
    "- Rebuilt the handoff index after every write.\n"
    "\n"
    "## ⚠️ Known Issues & Workarounds\n"
    "- Never pass a templated note via -m; the note must be written to a UTF-8\n"
    "  file first and handed over with -M <path>.\n"
    "- Tabs\tand trailing whitespace inside a section must survive verbatim.\n"
    "\n"
    "## \U0001f4c5 Upcoming Events\n"
    "- Full-suite acceptance run before the next release freeze.\n"
)


@pytest.fixture(autouse=True)
def throwaway_handoff_dir(tmp_path, monkeypatch):
    """Redirect every handoff write into a throwaway directory.

    Both the env var and the already-bound module constant are set: the module
    resolves NOUGEN_HANDOFF_DIR at import time, so the env var alone would not
    protect the shared registry.
    """
    hdir = tmp_path / "throwaway_handoffs"
    hdir.mkdir()
    monkeypatch.setenv("NOUGEN_HANDOFF_DIR", str(hdir))
    monkeypatch.setattr(handoff, "HANDOFF_DIR", hdir)
    monkeypatch.setattr(
        nougen_context, "SESSION_DB_PATH", str(hdir / "context_session.db")
    )
    yield hdir


def _run_cli(argv):
    """Parse a real argv and dispatch it, exactly as `main()` does."""
    args = cli.get_parser().parse_args(argv)
    return cli.cmd_handoff(args)


def _written_notes(hdir: Path):
    """Return the message body of every handoff JSON under the throwaway dir."""
    return [
        json.loads(p.read_text(encoding="utf-8"))["message"]
        for p in sorted(hdir.rglob("handoff_*.json"))
    ]


def test_message_file_content_reaches_handoff_byte_for_byte(
    throwaway_handoff_dir, tmp_path
):
    """-M reads the file as UTF-8 and the whole note lands in the handoff.

    This is the regression the `-m` path could not survive: the note is >1000
    chars, spans five `##` sections, and carries a currency figure.
    """
    note_file = tmp_path / "note.md"
    note_file.write_text(TEMPLATED_NOTE, encoding="utf-8")
    assert len(TEMPLATED_NOTE) > 1000, "guard: the fixture note must be large"

    _run_cli(
        ["handoff", "create", "-a", "claude-cli", "-g", "Prove -M", "-M", str(note_file)]
    )

    notes = _written_notes(throwaway_handoff_dir)
    assert len(notes) == 1, f"expected exactly one handoff, got {len(notes)}"
    stored = notes[0]

    # Byte-for-byte: not "contains", not "starts with", not a length heuristic.
    assert stored == TEMPLATED_NOTE
    # And the specific things the shell layer used to eat, named explicitly so a
    # partial regression names itself.
    assert stored.count("## ") == 5
    assert "$3,922.07" in stored
    assert "\U0001f534" in stored, "UTF-8 section marker must survive the read"
    assert "Tabs\tand" in stored


def test_message_file_overrides_inline_message(throwaway_handoff_dir, tmp_path):
    """-M wins over -m when both are supplied.

    -m is the truncating path, so if both are given the file must be the source
    of truth; a handoff carrying the -m value means the override was dropped.
    """
    note_file = tmp_path / "note.md"
    note_file.write_text(TEMPLATED_NOTE, encoding="utf-8")

    _run_cli(
        [
            "handoff",
            "create",
            "-a",
            "claude-cli",
            "-m",
            "## Active Incidents",  # what cmd.exe leaves behind
            "-M",
            str(note_file),
        ]
    )

    notes = _written_notes(throwaway_handoff_dir)
    assert len(notes) == 1
    stored = notes[0]
    assert stored == TEMPLATED_NOTE
    assert stored != "## Active Incidents"
    assert stored.count("## ") == 5


def test_message_file_survives_argparse_short_and_long_flags(
    throwaway_handoff_dir, tmp_path
):
    """--message-file and -M are the same option and both reach the writer."""
    note_file = tmp_path / "note.md"
    note_file.write_text(TEMPLATED_NOTE, encoding="utf-8")

    _run_cli(["handoff", "create", "-a", "gemini", "--message-file", str(note_file)])
    _run_cli(["handoff", "create", "-a", "codex", "-M", str(note_file)])

    notes = _written_notes(throwaway_handoff_dir)
    assert len(notes) == 2
    assert all(n == TEMPLATED_NOTE for n in notes)


def test_missing_message_file_errors_to_stderr_without_silent_fallback(
    throwaway_handoff_dir, tmp_path, capsys
):
    """An unreadable -M path fails loudly instead of writing an empty handoff.

    A silent fallback is the worst outcome: the agent believes it handed off,
    and the next session inherits a blank note.
    """
    missing = tmp_path / "does_not_exist" / "note.md"
    assert not missing.exists()

    rc = _run_cli(["handoff", "create", "-a", "claude-cli", "-M", str(missing)])

    assert rc, "a failed --message-file read must return a non-zero exit code"
    assert rc != 0

    err = capsys.readouterr().err
    assert "message-file" in err
    assert str(missing) in err

    # No silent fallback: nothing may be written when the note could not be read.
    assert _written_notes(throwaway_handoff_dir) == []


def test_unreadable_message_file_directory_errors_cleanly(
    throwaway_handoff_dir, tmp_path, capsys
):
    """Passing a directory to -M is an OSError, not a crash or a blank note."""
    a_directory = tmp_path / "not_a_file"
    a_directory.mkdir()

    rc = _run_cli(["handoff", "create", "-a", "claude-cli", "-M", str(a_directory)])

    assert rc
    assert rc != 0
    assert "message-file" in capsys.readouterr().err
    assert _written_notes(throwaway_handoff_dir) == []


def test_message_file_applies_to_note_taking_actions_beyond_create(
    throwaway_handoff_dir, tmp_path
):
    """-M feeds the note to ack/checkpoint too, not just create.

    cmd_handoff rewrites args.message before dispatch, so every action that
    takes a note inherits the mitigation; that contract is what is asserted.
    """
    note_file = tmp_path / "ack.md"
    ack_note = "## Taking Over\n- Read the prior handoff\n- Claim total $3,922.07 verified\n"
    note_file.write_text(ack_note, encoding="utf-8")

    _run_cli(["handoff", "create", "-a", "gemini", "-m", "ready", "-g", "G"])
    _run_cli(["handoff", "ack", "-M", str(note_file)])

    records = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(throwaway_handoff_dir.rglob("handoff_*.json"))
    ]
    acked = [r for r in records if r.get("status") == "acknowledged"]
    assert len(acked) == 1, "the -M note must have reached the ack path"
    assert acked[0]["acknowledgement_note"] == ack_note
