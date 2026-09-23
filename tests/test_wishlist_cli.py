"""CLI-level tests for `nougen wishlist`: argument parsing, dispatch, and the
evidence-required refusal surfaced correctly at the CLI boundary (exit code,
not just a Python exception)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.cli import get_parser  # noqa: E402
from nougen_shards import wishlist as wl  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(wl, "default_state_path", lambda: tmp_path / "wishlist_state.json")


def _run(argv):
    """Parse and dispatch exactly the way cli.main()'s cmds-dict path does,
    without going through sys.argv/main()'s search-fallback branch."""
    from nougen_shards.cli import cmd_wishlist
    parser = get_parser()
    args = parser.parse_args(["wishlist"] + argv)
    cmd_wishlist(args)


def test_wishlist_registered_as_a_top_level_subcommand():
    parser = get_parser()
    subparsers_action = next(a for a in parser._actions
                             if a.__class__.__name__ == "_SubParsersAction")
    assert "wishlist" in subparsers_action.choices


def test_list_with_no_filters_shows_all_100(capsys):
    _run(["list"])
    out = capsys.readouterr().out
    assert "100 item(s)" in out


def test_list_json_is_valid_and_filtered_by_category(capsys):
    _run(["list", "--category", "F", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 10
    assert all(r["category"] == "F" for r in rows)


def test_show_unknown_item_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        _run(["show", "999"])
    assert exc.value.code != 0


def test_mark_landed_without_evidence_exits_nonzero_not_a_traceback(capsys):
    with pytest.raises(SystemExit) as exc:
        _run(["mark", "1", "--status", "landed"])
    assert exc.value.code == 1
    assert "refused" in capsys.readouterr().out.lower()


def test_mark_then_show_round_trips_through_the_cli(capsys):
    _run(["mark", "42", "--status", "landed", "--evidence", "PR#500", "--owner", "phoebus"])
    capsys.readouterr()
    _run(["show", "42", "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["status"] == "landed"
    assert doc["evidence"] == ["PR#500"]
    assert doc["owner"] == "phoebus"


def test_progress_json_sums_to_100(capsys):
    _run(["progress", "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert sum(p["total"] for p in doc["by_phase"].values()) == 100
    assert sum(c["total"] for c in doc["by_category"].values()) == 100


def test_no_subcommand_prints_usage_not_a_crash(capsys):
    import argparse
    from nougen_shards.cli import cmd_wishlist
    cmd_wishlist(argparse.Namespace(wishlist_command=None))
    assert "usage" in capsys.readouterr().out.lower()
