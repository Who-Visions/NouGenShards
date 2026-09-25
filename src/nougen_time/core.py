"""Canonical wall-clock and elapsed-time APIs for the NouGen fleet.

Wall-clock values are UTC instants rendered in America/New_York for Dave.
    Naive ``datetime`` values and ISO timestamps without an offset are treated as
UTC for compatibility with existing NouGen records. New storage should use
aware UTC datetimes or the ``utc_iso`` field. Timestamp precision is one
microsecond; ISO inputs with more than six fractional digits are rejected rather
than silently truncated.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any
from zoneinfo import ZoneInfo

EASTERN_TZ = ZoneInfo("America/New_York")
UTC = timezone.utc
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_NS_PER_SECOND = 1_000_000_000
_NS_PER_MICROSECOND = 1_000
_NUMERIC_EPOCH = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)\Z")
_OVERPRECISION_ISO = re.compile(r"[Tt]\d{2}:\d{2}:\d{2}\.(\d{7,})")
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_WEEKDAYS_SHORT = tuple(day[:3] for day in _WEEKDAYS)
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


class InvalidTimestampError(ValueError):
    """Raised when a supplied timestamp is present but invalid or out of range."""


def _tz_abbreviation(dt: datetime) -> str:
    """Normalize Windows' long zone names; never guess the seasonal offset."""
    name = dt.tzname() or ""
    if " " in name:
        name = "".join(part[0] for part in name.split() if part and part[0].isalpha())
    if not name:
        raise RuntimeError("America/New_York did not provide a timezone name")
    return name


def _from_epoch_ns(epoch_ns: int) -> "NouGenInstant":
    try:
        # The public contract is microsecond precision. Quantize the integer
        # epoch once so the epoch and ISO views cannot disagree.
        utc_dt = _EPOCH + timedelta(microseconds=epoch_ns // _NS_PER_MICROSECOND)
        eastern_dt = utc_dt.astimezone(EASTERN_TZ)
    except (OverflowError, ValueError) as exc:
        raise InvalidTimestampError("timestamp is outside datetime's supported range") from exc
    return NouGenInstant(epoch_ns // _NS_PER_MICROSECOND, utc_dt, eastern_dt)


@dataclass(frozen=True)
class NouGenInstant:
    """One immutable instant with an integer epoch, UTC, and Eastern views."""

    unix_timestamp_us: int
    utc_dt: datetime = field(compare=False)
    eastern_dt: datetime = field(compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.unix_timestamp_us, bool) or not isinstance(self.unix_timestamp_us, int):
            raise InvalidTimestampError("unix_timestamp_us must be an integer")
        try:
            expected_utc = _EPOCH + timedelta(microseconds=self.unix_timestamp_us)
            expected_eastern = expected_utc.astimezone(EASTERN_TZ)
        except OverflowError as exc:
            raise InvalidTimestampError("timestamp is outside datetime's supported range") from exc
        if self.utc_dt.tzinfo is None or self.utc_dt.utcoffset() is None:
            raise InvalidTimestampError("utc_dt must be timezone-aware")
        if self.eastern_dt.tzinfo is None or self.eastern_dt.utcoffset() is None:
            raise InvalidTimestampError("eastern_dt must be timezone-aware")
        if self.utc_dt.utcoffset() != timedelta(0):
            raise InvalidTimestampError("utc_dt must have a zero UTC offset")
        if getattr(self.eastern_dt.tzinfo, "key", None) != "America/New_York":
            raise InvalidTimestampError("eastern_dt must use America/New_York")
        if self.utc_dt.astimezone(UTC) != expected_utc:
            raise InvalidTimestampError("utc_dt does not match unix_timestamp_us")
        if self.eastern_dt != expected_eastern:
            raise InvalidTimestampError("eastern_dt does not match unix_timestamp_us")

    @property
    def unix_timestamp(self) -> float:
        """Compatibility epoch seconds; use the integer fields for exact values."""
        return self.unix_timestamp_us / 1_000_000

    @property
    def unix_timestamp_ns(self) -> int:
        """Epoch nanoseconds aligned to the model's microsecond precision."""
        return self.unix_timestamp_us * _NS_PER_MICROSECOND

    @property
    def time_12h(self) -> str:
        hour = self.eastern_dt.hour % 12 or 12
        period = "AM" if self.eastern_dt.hour < 12 else "PM"
        return f"{hour}:{self.eastern_dt.minute:02d} {period}"

    @property
    def time_12h_sec(self) -> str:
        hour = self.eastern_dt.hour % 12 or 12
        period = "AM" if self.eastern_dt.hour < 12 else "PM"
        return f"{hour:02d}:{self.eastern_dt.minute:02d}:{self.eastern_dt.second:02d} {period}"

    @property
    def tz_abbr(self) -> str:
        return _tz_abbreviation(self.eastern_dt)

    @property
    def display(self) -> str:
        return f"{self.time_12h} {self.tz_abbr}"

    @property
    def display_full(self) -> str:
        weekday = _WEEKDAYS_SHORT[self.eastern_dt.weekday()]
        return f"{self.display} {weekday} {self.eastern_dt.month:02d}/{self.eastern_dt.day:02d}"

    @property
    def display_log(self) -> str:
        return (
            f"{self.eastern_dt.year:04d}-{self.eastern_dt.month:02d}-{self.eastern_dt.day:02d} "
            f"{self.time_12h_sec} {self.tz_abbr}"
        )

    @property
    def banner(self) -> str:
        weekday = _WEEKDAYS[self.eastern_dt.weekday()]
        month = _MONTHS[self.eastern_dt.month - 1]
        return (
            f"{self.time_12h_sec} {self.tz_abbr} ({weekday}, {month} "
            f"{self.eastern_dt.day:02d}, {self.eastern_dt.year:04d})"
        )

    @property
    def utc_iso(self) -> str:
        """Canonical UTC ISO-8601 value at the package's six-digit precision."""
        return self.utc_dt.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @property
    def paired(self) -> str:
        return f"{self.display_full} ({self.utc_iso})"

    def to_dict(self, version: str | None = None) -> dict[str, Any]:
        """Stable JSON representation; ``utc_iso`` is the canonical instant."""
        result: dict[str, Any] = {
            "unix_timestamp_ns": self.unix_timestamp_ns,
            "unix_timestamp_us": self.unix_timestamp_us,
            "unix_timestamp": self.unix_timestamp,
            "eastern_12h": self.time_12h,
            "eastern_display": self.display,
            "eastern_full": self.display_full,
            "banner": self.banner,
            "display_log": self.display_log,
            "utc_iso": self.utc_iso,
            "tz": self.tz_abbr,
        }
        if version is not None:
            result["version"] = version
        return result

    def __str__(self) -> str:
        return self.display


def now() -> NouGenInstant:
    """Read the adjustable system wall clock once and return that UTC instant."""
    return _from_epoch_ns((time.time_ns() // _NS_PER_MICROSECOND) * _NS_PER_MICROSECOND)


def monotonic_ns() -> int:
    """Return a monotonic counter for measuring durations, never a calendar time."""
    return time.monotonic_ns()


def from_timestamp(ts: int | float | Decimal) -> NouGenInstant:
    """Create an instant from finite Unix epoch seconds, rounded to microseconds."""
    if isinstance(ts, bool) or not isinstance(ts, (int, float, Decimal)):
        raise InvalidTimestampError("epoch seconds must be an int, float, or Decimal")
    try:
        seconds = Decimal(str(ts))
        if not seconds.is_finite():
            raise InvalidTimestampError("epoch seconds must be finite")
        epoch_us = int((seconds * 1_000_000).to_integral_value(rounding=ROUND_HALF_EVEN))
    except (InvalidOperation, ValueError, OverflowError) as exc:
        if isinstance(exc, InvalidTimestampError):
            raise
        raise InvalidTimestampError(f"invalid epoch seconds: {ts!r}") from exc
    return _from_epoch_ns(epoch_us * _NS_PER_MICROSECOND)


def _from_datetime(value: datetime) -> NouGenInstant:
    # Legacy NouGen records contain naive ISO values; the wire/storage contract
    # defines these as UTC. Convert via integer timedelta fields, not float epoch.
    utc_dt = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    delta = utc_dt - _EPOCH
    epoch_us = (
        (delta.days * 86_400 + delta.seconds) * _NS_PER_SECOND
    ) // _NS_PER_MICROSECOND + delta.microseconds
    return _from_epoch_ns(epoch_us * _NS_PER_MICROSECOND)


def parse(val: Any) -> NouGenInstant | None:
    """Parse an epoch or ISO-8601 timestamp.

    ``None``, empty strings, and ``?`` mean missing and return ``None``.
    Invalid present values raise :class:`InvalidTimestampError`. Naive ISO
    values are interpreted as UTC for compatibility with existing records.
    """
    if val is None or val == "" or val == "?":
        return None
    if isinstance(val, datetime):
        try:
            return _from_datetime(val)
        except (OverflowError, ValueError, OSError) as exc:
            raise InvalidTimestampError(f"invalid datetime: {val!r}") from exc
    if isinstance(val, bool):
        raise InvalidTimestampError("boolean is not a timestamp")
    if isinstance(val, (int, float, Decimal)):
        return from_timestamp(val)
    if not isinstance(val, str):
        raise InvalidTimestampError(f"unsupported timestamp type: {type(val).__name__}")

    text = val.strip()
    if not text or text == "?":
        return None
    if _NUMERIC_EPOCH.fullmatch(text):
        return from_timestamp(Decimal(text))

    fractional = _OVERPRECISION_ISO.search(text)
    if fractional:
        raise InvalidTimestampError("ISO timestamps support at most six fractional digits")

    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        return _from_datetime(datetime.fromisoformat(text))
    except (ValueError, OverflowError, OSError) as exc:
        raise InvalidTimestampError(f"invalid ISO-8601 timestamp: {val!r}") from exc


def format_display_time(val: Any, paired: bool = True) -> str:
    """Format a timestamp in Eastern Time; invalid input raises, missing is ``?``."""
    instant = parse(val)
    if instant is None:
        return "?"
    return instant.paired if paired else instant.display_full


def format_log_time(val: Any) -> str:
    """Format a log timestamp with Eastern wall time and its canonical UTC pair."""
    instant = parse(val)
    return f"{instant.display_log} ({instant.utc_iso})" if instant is not None else "?"
