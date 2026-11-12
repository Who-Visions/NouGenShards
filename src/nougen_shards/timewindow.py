"""Natural time phrases -> a concrete UTC window the vault can be queried by.

"recall march" means "what happened in March", not "find the word march".
A text search for a month name finds surnames and footnotes; a time window
finds the month. This module turns the phrases people actually type into
[start, end) ISO-8601 UTC bounds that compare directly against the shards
`timestamp` column. Any year, any month, any day, down to the minute:

    march / march 2026 / 2026-03 / mar 2024      calendar month
    2026 / q1 2026 / q3                          year, quarter
    2026-03-19 / march 19 2026 / 19 march        one day
    2026-03-19 14:05 / 2026-03-19T14:05:30Z      one minute (or that second)
    march 19 2026 7:47pm / today at 19:47        one minute
    7pm yesterday / yesterday 7pm                one hour
    this morning / this afternoon / tonight      part of a day
    today / yesterday / this week / last week / this month / last month
    last 30 minutes / past 2 hours / last 7 days / last 3 months
    march..may 2026 / 2026-03-01 to 2026-04-15   explicit ranges
    between 7pm and 8pm yesterday / 7-8pm        ranges with times

Boundaries are taken in the caller's zone (tz arg, else NOUGEN_TZ, else
UTC) so "yesterday" is the user's yesterday, then expressed in UTC.
Nothing here guesses: an unparseable phrase returns None and the caller
says so, instead of inventing a window.
"""
from __future__ import annotations

import calendar
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

_PARTS = {  # local-hour spans for parts of a day
    "morning": (5, 12), "afternoon": (12, 17), "evening": (17, 21),
    "night": (21, 24), "tonight": (18, 24),
}
_UNIT_SECONDS = {"minute": 60, "min": 60, "hour": 3600, "hr": 3600, "day": 86400, "week": 604800}

Span = Tuple[datetime, datetime]   # naive local datetimes, [start, end)


@dataclass(frozen=True)
class Window:
    start_utc: str          # inclusive, ISO-8601 Z
    end_utc: str            # exclusive, ISO-8601 Z
    label: str              # human label, e.g. "March 2026", "2026-03-19 14:05"
    interpreted_as: str     # how the phrase was read, for the model to repeat
    tz: str

    def as_dict(self) -> dict:
        return {"start_utc": self.start_utc, "end_utc": self.end_utc, "label": self.label,
                "interpreted_as": self.interpreted_as, "tz": self.tz}


def _zone(tz: Optional[str]) -> ZoneInfo:
    name = (tz or os.environ.get("NOUGEN_TZ") or "UTC").strip()
    try:
        return ZoneInfo(name)
    except Exception:  # pylint: disable=broad-except
        return ZoneInfo("UTC")


def _iso(dt: datetime, zone: ZoneInfo) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d)


def _month_span(y: int, m: int) -> Span:
    first = _day(y, m, 1)
    nxt = _day(y + 1, 1, 1) if m == 12 else _day(y, m + 1, 1)
    return first, nxt


def _most_recent_year_for_month(m: int, today: datetime) -> int:
    # "march" in November 2026 is March 2026; "december" in November 2026 is
    # December 2025 - the month must already have started to be recalled.
    return today.year if m <= today.month else today.year - 1


def _norm(phrase: str) -> str:
    q = re.sub(r"\s+", " ", str(phrase or "").strip().lower())
    q = re.sub(r"^(recall|remember|what happened|show me|browse)\s+", "", q)
    q = re.sub(r"^(in|from|during|for|on|at|around|the)\s+", "", q).strip()
    q = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", q)          # 19th -> 19
    q = re.sub(r"\b(\d{1,2})\s*(am|pm)\b", r"\1\2", q)       # 7 pm -> 7pm
    q = re.sub(r"\b(\d{1,2}:\d{2})\s*(am|pm)\b", r"\1\2", q)
    return q


# ---- clock times -------------------------------------------------------------

def _parse_clock(tok: str) -> Optional[Tuple[int, int, Optional[int], int]]:
    """'7pm' '19:47' '7:47pm' '14:05:30' -> (hour, minute, second|None, seconds-of-precision)."""
    tok = tok.strip().lower()
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm)?", tok)
    if not m:
        if tok == "noon":
            return 12, 0, None, 3600
        if tok == "midnight":
            return 0, 0, None, 3600
        return None
    h = int(m[1]); mi = int(m[2]) if m[2] else None; s = int(m[3]) if m[3] else None
    if m[4]:
        if h == 12:
            h = 0
        if m[4] == "pm":
            h += 12
    elif mi is None:
        return None   # a bare number is not a time
    if not (0 <= h < 24 and (mi is None or 0 <= mi < 60) and (s is None or 0 <= s < 60)):
        return None
    prec = 1 if s is not None else (60 if mi is not None else 3600)
    return h, (mi or 0), s, prec


def _with_clock(day_start: datetime, clock) -> Span:
    h, mi, s, prec = clock
    start = day_start.replace(hour=h, minute=mi, second=s or 0)
    return start, start + timedelta(seconds=prec)


# ---- day-ish anchors (naive local) -------------------------------------------

def _anchor_day(tok: str, today: datetime) -> Optional[Tuple[datetime, str]]:
    """'today' 'yesterday' 'tomorrow' '2026-03-19' 'march 19 2026' '19 march' -> (midnight, label)."""
    t = tok.strip()
    if t == "today":
        return today, today.strftime("%Y-%m-%d")
    if t == "yesterday":
        d = today - timedelta(days=1); return d, d.strftime("%Y-%m-%d")
    if t == "tomorrow":
        d = today + timedelta(days=1); return d, d.strftime("%Y-%m-%d")
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        d = _day(int(m[1]), int(m[2]), int(m[3])); return d, d.strftime("%Y-%m-%d")
    m = re.fullmatch(rf"({_MONTH_RE})\.?\s+(\d{{1,2}})(?:,?\s+(\d{{4}}))?", t)
    if m:
        mon = MONTHS[m[1]]; year = int(m[3]) if m[3] else _most_recent_year_for_month(mon, today)
        d = _day(year, mon, int(m[2])); return d, d.strftime("%Y-%m-%d")
    m = re.fullmatch(rf"(\d{{1,2}})\s+({_MONTH_RE})\.?(?:,?\s+(\d{{4}}))?", t)
    if m:
        mon = MONTHS[m[2]]; year = int(m[3]) if m[3] else _most_recent_year_for_month(mon, today)
        d = _day(year, mon, int(m[1])); return d, d.strftime("%Y-%m-%d")
    return None


def _parse_point(tok: str, today: datetime) -> Optional[Tuple[Span, str, str]]:
    """One endpoint or whole phrase -> (span, label, how). Handles month/year/quarter/day/day+time."""
    tok = tok.strip()
    # ISO datetime: 2026-03-19T14:05[:30][Z]  or  2026-03-19 14:05
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[t ](\d{1,2}:\d{2}(?::\d{2})?)z?", tok)
    if m:
        a = _anchor_day(m[1], today); c = _parse_clock(m[2])
        if a and c:
            sp = _with_clock(a[0], c)
            return sp, sp[0].strftime("%Y-%m-%d %H:%M" + (":%S" if c[3] == 1 else "")), "that exact " + ("second" if c[3] == 1 else "minute")
    m = re.fullmatch(r"(\d{4})-(\d{2})", tok)
    if m:
        sp = _month_span(int(m[1]), int(m[2])); return sp, sp[0].strftime("%B %Y"), "that calendar month"
    m = re.fullmatch(r"(\d{4})", tok)
    if m:
        y = int(m[1]); return (_day(y, 1, 1), _day(y + 1, 1, 1)), str(y), "that calendar year"
    m = re.fullmatch(r"q([1-4])(?:\s+(\d{4}))?", tok)
    if m:
        qn = int(m[1])
        year = int(m[2]) if m[2] else (today.year if (qn - 1) * 3 + 1 <= today.month else today.year - 1)
        s = _day(year, (qn - 1) * 3 + 1, 1)
        e = _day(year + 1, 1, 1) if qn == 4 else _day(year, qn * 3 + 1, 1)
        return (s, e), f"Q{qn} {year}", f"calendar quarter Q{qn} {year}"
    m = re.fullmatch(rf"({_MONTH_RE})\.?(?:,?\s+(\d{{4}}))?", tok)
    if m:
        mon = MONTHS[m[1]]
        if m[2]:
            sp = _month_span(int(m[2]), mon); return sp, sp[0].strftime("%B %Y"), "that calendar month"
        sp = _month_span(_most_recent_year_for_month(mon, today), mon)
        return sp, sp[0].strftime("%B %Y"), f"that calendar month (no year given; most recent {sp[0].strftime('%B')} that has started)"
    # day [+ time] in either order: "march 19 2026 7:47pm", "7pm yesterday", "today at 19:47"
    for pat in (r"(.+?)\s+(?:at\s+)?(\S+)", r"(\S+)\s+(.+)"):
        m = re.fullmatch(pat, tok)
        if m:
            for day_tok, clock_tok in ((m[1], m[2]), (m[2], m[1])):
                a = _anchor_day(day_tok, today); c = _parse_clock(clock_tok)
                if a and c:
                    sp = _with_clock(a[0], c)
                    unit = {1: "second", 60: "minute", 3600: "hour"}[c[3]]
                    return sp, sp[0].strftime("%Y-%m-%d %H:%M" + (":%S" if c[3] == 1 else "")), f"that {unit} ({a[1]} in the caller's zone)"
                part = _PARTS.get(clock_tok.strip())
                if a and part:
                    sp = (a[0].replace(hour=part[0]), a[0] + timedelta(hours=part[1]))
                    return sp, f"{a[1]} {clock_tok.strip()}", f"{clock_tok.strip()} of {a[1]} ({part[0]:02d}:00-{part[1]:02d}:00 local)"
    a = _anchor_day(tok, today)
    if a:
        return (a[0], a[0] + timedelta(days=1)), a[1], "that single day"
    if tok in _PARTS:  # "this morning", "tonight"
        p = _PARTS[tok]
        return (today.replace(hour=p[0]), today + timedelta(hours=p[1])), f"today {tok}", f"{tok} of today ({p[0]:02d}:00-{p[1]:02d}:00 local)"
    c = _parse_clock(tok)   # bare "7pm" / "19:47" -> that time today
    if c:
        sp = _with_clock(today, c)
        return sp, sp[0].strftime("%Y-%m-%d %H:%M"), "that time today (no day given)"
    return None


def parse_window(phrase: str, *, now: Optional[datetime] = None, tz: Optional[str] = None) -> Optional[Window]:
    zone = _zone(tz)
    now_local = (now or datetime.now(timezone.utc)).astimezone(zone).replace(tzinfo=None)
    today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    q = _norm(phrase)
    if not q:
        return None

    def done(sp: Span, label: str, how: str) -> Optional[Window]:
        s, e = sp
        if e <= s:
            return None
        return Window(_iso(s, zone), _iso(e, zone), label, how, str(zone))

    q = re.sub(r"^this\s+(morning|afternoon|evening|night)$", r"\1", q)
    if q in ("this week", "week"):
        s = today - timedelta(days=today.weekday())
        return done((s, s + timedelta(days=7)), f"week of {s.date()}", "this calendar week (Mon-Sun)")
    if q == "last week":
        s = today - timedelta(days=today.weekday() + 7)
        return done((s, s + timedelta(days=7)), f"week of {s.date()}", "last calendar week (Mon-Sun)")
    if q in ("this month", "month"):
        sp = _month_span(today.year, today.month); return done(sp, sp[0].strftime("%B %Y"), "this calendar month")
    if q == "last month":
        y, mth = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        sp = _month_span(y, mth); return done(sp, sp[0].strftime("%B %Y"), "last calendar month")
    if q in ("this year", "year"):
        return done((_day(today.year, 1, 1), _day(today.year + 1, 1, 1)), str(today.year), "this calendar year")
    if q == "last year":
        return done((_day(today.year - 1, 1, 1), _day(today.year, 1, 1)), str(today.year - 1), "last calendar year")
    if q in ("now", "this hour", "hour"):
        s = now_local.replace(minute=0, second=0, microsecond=0)
        return done((s, s + timedelta(hours=1)), s.strftime("%Y-%m-%d %H:00"), "the current hour")
    if q in ("this minute", "minute"):
        s = now_local.replace(second=0, microsecond=0)
        return done((s, s + timedelta(minutes=1)), s.strftime("%Y-%m-%d %H:%M"), "the current minute")

    # Rolling: "last 30 minutes", "past 2 hours", "last 7 days", "last 3 months", "last hour".
    m = re.fullmatch(r"(?:last|past|previous)\s+(?:(\d+)\s+)?(minutes?|mins?|hours?|hrs?|days?|weeks?|months?)", q)
    if m:
        n = int(m[1]) if m[1] else 1
        unit = m[2].rstrip("s")
        if unit == "month":
            y, mth = today.year, today.month - n
            while mth <= 0:
                mth += 12; y -= 1
            s = today.replace(year=y, month=mth, day=min(today.day, calendar.monthrange(y, mth)[1]))
            e = today + timedelta(days=1)
        elif unit in ("day", "week"):
            s = today - timedelta(seconds=n * _UNIT_SECONDS[unit]); e = today + timedelta(days=1)
        else:
            e = now_local.replace(microsecond=0); s = e - timedelta(seconds=n * _UNIT_SECONDS[unit])
        fmt = "%Y-%m-%d %H:%M" if unit in ("minute", "min", "hour", "hr") else "%Y-%m-%d"
        return done((s, e), f"{s.strftime(fmt)} .. {e.strftime(fmt)}", f"the {n} {m[2]} ending now")

    # Explicit ranges. A bare '-' only separates when spaced (or between two
    # clock times like 7-8pm), or it eats the dashes inside ISO dates.
    m = re.fullmatch(r"(?:between\s+)?(.+?)(?:\s*\.\.\s*|\s+(?:to|through|until|thru|and)\s+|\s+-\s+)(.+)", q) \
        or re.fullmatch(r"(?:between\s+)?(\d{1,2}(?::\d{2})?(?:am|pm)?)-(\d{1,2}(?::\d{2})?(?:am|pm)?)(?:\s+(.+))?", q)
    if m:
        a, b = m[1], m[2]
        tail = m[3] if m.lastindex and m.lastindex >= 3 and m[3] else ""
        # "between 7pm and 8pm yesterday": the day on the right applies to both.
        day_hint = ""
        mb = re.fullmatch(r"(\S+)\s+(.+)", b)
        if mb and _parse_clock(mb[1]) and _anchor_day(mb[2], today):
            b, day_hint = mb[1], mb[2]
        if tail:
            day_hint = tail
        # "7-8pm" / "between 7 and 8pm": the left clock inherits the right's am/pm.
        ms = re.fullmatch(r"(\d{1,2}(?::\d{2})?)(am|pm)", b)
        if ms and re.fullmatch(r"\d{1,2}(?::\d{2})?", a):
            a = a + ms[2]
        if day_hint:
            a, b = f"{a} {day_hint}", f"{b} {day_hint}"
        elif _parse_clock(a) and _parse_clock(b):
            a, b = f"{a} today", f"{b} today"
        # "march..may 2026": the year on the right applies to the left.
        yh = re.search(r"(\d{4})$", b)
        if yh and not re.search(r"\d{4}", a) and not _parse_clock(a.split()[-1]):
            a = f"{a} {yh[1]}"
        pa, pb = _parse_point(a, today), _parse_point(b, today)
        if pa and pb:
            # A clock-precise right endpoint is exclusive at its START
            # ("7pm to 8pm" ends at 20:00); a day/month endpoint is inclusive.
            fine_b = (pb[0][1] - pb[0][0]) < timedelta(days=1)
            s, e = pa[0][0], (pb[0][0] if fine_b else pb[0][1])
            if s >= e:
                return None
            fine = (e - s) < timedelta(days=1) or fine_b
            fmt = "%Y-%m-%d %H:%M" if fine else "%Y-%m-%d"
            end_label = e if fine else e - timedelta(days=1)
            return done((s, e), f"{s.strftime(fmt)} .. {end_label.strftime(fmt)}", f"range from '{m[1]}' through '{m[2]}'")

    p = _parse_point(q, today)
    if p:
        return done(*p)
    return None


def looks_temporal(phrase: str) -> bool:
    """Cheap pre-check so callers can route 'recall march' to the window lane."""
    return parse_window(phrase, now=datetime.now(timezone.utc)) is not None
