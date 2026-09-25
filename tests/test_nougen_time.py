from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import pytest

import nougen_time.core as time_core
from nougen_time import (
    InvalidTimestampError,
    NouGenInstant,
    format_display_time,
    format_log_time,
    from_timestamp,
    monotonic_ns,
    now,
    parse,
)


def test_wall_clock_reads_once_and_is_microsecond_aligned(monkeypatch):
    monkeypatch.setattr(time_core.time, "time_ns", lambda: 1_790_360_436_123_456_789)
    instant = now()
    assert instant.unix_timestamp_ns == 1_790_360_436_123_456_000
    assert instant.utc_dt.microsecond == 123_456
    assert instant.utc_iso == "2026-09-25T18:20:36.123456Z"


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        ("2026-03-08T06:59:59Z", "1:59 AM EST"),
        ("2026-03-08T07:00:00Z", "3:00 AM EDT"),
        ("2026-11-01T05:30:00Z", "1:30 AM EDT"),
        ("2026-11-01T06:30:00Z", "1:30 AM EST"),
    ],
)
def test_dst_boundaries_render_the_correct_eastern_offset(utc, expected):
    assert parse(utc).display == expected


def test_repeated_fall_hour_is_two_distinct_instants():
    daylight = parse("2026-11-01T05:30:00Z")
    standard = parse("2026-11-01T06:30:00Z")
    assert daylight.eastern_dt.hour == standard.eastern_dt.hour == 1
    assert daylight.eastern_dt.fold == 0
    assert standard.eastern_dt.fold == 1
    assert daylight.unix_timestamp_us != standard.unix_timestamp_us


def test_explicit_offsets_normalize_to_the_same_utc_instant():
    eastern = parse("2026-01-01T02:00:00+02:00")
    utc = parse("2026-01-01T00:00:00Z")
    assert eastern.utc_iso == utc.utc_iso


def test_naive_iso_datetime_has_documented_utc_semantics():
    assert parse("2026-01-01T00:00:00").utc_iso == "2026-01-01T00:00:00.000000Z"
    assert parse(datetime(2026, 1, 1)).utc_iso == "2026-01-01T00:00:00.000000Z"


def test_missing_and_invalid_values_are_distinct():
    assert parse(None) is None
    assert parse("") is None
    assert format_display_time(None) == "?"
    for value in (
        "not a timestamp",
        "NaN",
        "2026-01-01T00:00:00.1234567Z",
        True,
        float("nan"),
        float("inf"),
        object(),
    ):
        with pytest.raises(InvalidTimestampError):
            parse(value)


def test_out_of_datetime_range_is_a_domain_error():
    with pytest.raises(InvalidTimestampError):
        from_timestamp(Decimal("999999999999999999999999"))


def test_rounding_and_iso_precision_are_consistent():
    even_down = from_timestamp(Decimal("0.0000005"))
    even_up = from_timestamp(Decimal("0.0000015"))
    assert even_down.unix_timestamp_us == 0
    assert even_up.unix_timestamp_us == 2
    assert even_up.utc_iso == "1970-01-01T00:00:00.000002Z"
    assert even_up.unix_timestamp_ns == 2_000


def test_instant_rejects_inconsistent_views():
    good = from_timestamp(0)
    with pytest.raises(InvalidTimestampError):
        NouGenInstant(1, good.utc_dt, good.eastern_dt)


def test_instant_rejects_wrong_eastern_zone():
    good = from_timestamp(0)
    with pytest.raises(InvalidTimestampError):
        NouGenInstant(good.unix_timestamp_us, good.utc_dt, good.utc_dt)


def test_formatting_is_locale_independent_and_pairs_utc():
    instant = parse("2026-09-25T18:20:36Z")
    assert instant.display_full == "2:20 PM EDT Fri 09/25"
    assert format_display_time(instant.utc_iso) == "2:20 PM EDT Fri 09/25 (2026-09-25T18:20:36.000000Z)"
    assert format_log_time(instant.utc_iso) == "2026-09-25 02:20:36 PM EDT (2026-09-25T18:20:36.000000Z)"


def test_duration_clock_is_separate_and_monotonic(monkeypatch):
    readings = iter((10, 11))
    monkeypatch.setattr(time_core.time, "monotonic_ns", lambda: next(readings))
    assert monotonic_ns() == 10
    assert monotonic_ns() == 11


def test_module_cli_json_has_one_canonical_payload(capsys):
    from nougen_time.__main__ import main

    assert main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "0.2.0"
    assert payload["utc_iso"].endswith("Z")
    assert payload["unix_timestamp_ns"] == payload["unix_timestamp_us"] * 1_000


def test_nougen_cli_time_command_reuses_the_canonical_json_schema(capsys):
    from argparse import Namespace
    from nougen_shards.cli import cmd_time

    cmd_time(Namespace(json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == "0.2.0"
    assert payload["utc_iso"].endswith("Z")
    assert payload["unix_timestamp_ns"] == payload["unix_timestamp_us"] * 1_000


def test_sibling_relay_package_is_current_when_checkout_is_available():
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    outpost_root = repo_root.parent
    canonical = outpost_root / "NouGen" / "src" / "nougen_time"
    relay_mirror = outpost_root / "NouGenRelay" / "src" / "nougen_time"
    if not canonical.is_dir() or not relay_mirror.is_dir():
        pytest.skip("both sibling repository checkouts are required for package parity")
    for name in ("README.md", "__init__.py", "__main__.py", "core.py"):
        assert (canonical / name).read_bytes() == (relay_mirror / name).read_bytes()
