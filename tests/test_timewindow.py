"""'recall march' is a time window, not a word search - any month, year, day, minute."""
from datetime import datetime, timezone

import pytest

from nougen_shards import timewindow as tw

NOW = datetime(2026, 11, 8, 1, 7, 30, tzinfo=timezone.utc)  # Sat 2026-11-07 20:07:30 EST
NY = "America/New_York"


def w(phrase, tz="UTC"):
    return tw.parse_window(phrase, now=NOW, tz=tz)


def span(phrase, tz="UTC"):
    win = w(phrase, tz)
    assert win is not None, phrase
    return win.start_utc, win.end_utc


@pytest.mark.parametrize("phrase", ["march", "March", "recall march", "in march", "mar", "March."])
def test_bare_month_is_most_recent_started(phrase):
    win = w(phrase)
    assert (win.start_utc, win.end_utc) == ("2026-03-01T00:00:00Z", "2026-04-01T00:00:00Z")
    assert win.label == "March 2026" and "no year given" in win.interpreted_as


def test_future_month_rolls_back_a_year():
    assert w("december").label == "December 2025"


@pytest.mark.parametrize("phrase,label", [
    ("march 2026", "March 2026"), ("2026-03", "March 2026"), ("March, 2026", "March 2026"),
    ("feb 2019", "February 2019"), ("2031-07", "July 2031"), ("sept 2025", "September 2025"),
])
def test_any_month_any_year(phrase, label):
    assert w(phrase).label == label


def test_days_years_quarters():
    assert span("2026-03-19") == ("2026-03-19T00:00:00Z", "2026-03-20T00:00:00Z")
    assert w("march 19 2026").label == "2026-03-19"
    assert w("19 march 2026").label == "2026-03-19"
    assert w("march 19th").label == "2026-03-19"
    assert span("2026") == ("2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z")
    assert span("1999") == ("1999-01-01T00:00:00Z", "2000-01-01T00:00:00Z")
    assert span("q1 2026") == ("2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")
    assert w("q4").label == "Q4 2026"


def test_minutes_and_seconds():
    assert span("2026-03-19 14:05") == ("2026-03-19T14:05:00Z", "2026-03-19T14:06:00Z")
    assert span("2026-03-19T14:05:30Z") == ("2026-03-19T14:05:30Z", "2026-03-19T14:05:31Z")
    assert span("march 19 2026 7:47pm", NY) == ("2026-03-19T23:47:00Z", "2026-03-19T23:48:00Z")  # EDT
    assert span("today at 19:47", NY) == ("2026-11-08T00:47:00Z", "2026-11-08T00:48:00Z")      # EST
    assert span("7pm yesterday", NY) == ("2026-11-07T00:00:00Z", "2026-11-07T01:00:00Z")        # one hour
    assert span("yesterday 7:47pm", NY) == ("2026-11-07T00:47:00Z", "2026-11-07T00:48:00Z")
    assert w("19:47", NY).label == "2026-11-07 19:47"   # bare clock = today in the user's zone
    assert span("noon today") == ("2026-11-08T12:00:00Z", "2026-11-08T13:00:00Z")


def test_rolling_windows_to_the_minute():
    assert span("last 30 minutes") == ("2026-11-08T00:37:30Z", "2026-11-08T01:07:30Z")
    assert span("past 2 hours") == ("2026-11-07T23:07:30Z", "2026-11-08T01:07:30Z")
    assert span("last hour") == ("2026-11-08T00:07:30Z", "2026-11-08T01:07:30Z")
    assert span("this hour") == ("2026-11-08T01:00:00Z", "2026-11-08T02:00:00Z")
    assert span("this minute") == ("2026-11-08T01:07:00Z", "2026-11-08T01:08:00Z")
    assert w("last 7 days").start_utc == "2026-11-01T00:00:00Z"
    assert w("last 3 months").start_utc == "2026-08-08T00:00:00Z"


def test_relative_phrases_use_callers_zone():
    win = w("yesterday", tz=NY)   # 01:07Z Nov 8 is still Nov 7 in New York
    assert win.label == "2026-11-06" and win.start_utc == "2026-11-06T05:00:00Z"
    assert w("last week").label == "week of 2026-10-26"
    assert w("last month").label == "October 2026"
    assert span("this morning", NY) == ("2026-11-07T10:00:00Z", "2026-11-07T17:00:00Z")
    assert span("tonight", NY) == ("2026-11-07T23:00:00Z", "2026-11-08T05:00:00Z")


def test_ranges():
    assert span("march..may 2026") == ("2026-03-01T00:00:00Z", "2026-06-01T00:00:00Z")
    assert span("2026-03-01 to 2026-04-15") == ("2026-03-01T00:00:00Z", "2026-04-16T00:00:00Z")
    assert span("between 7pm and 8pm yesterday") == ("2026-11-07T19:00:00Z", "2026-11-07T20:00:00Z")
    assert span("7-8pm") == ("2026-11-08T19:00:00Z", "2026-11-08T20:00:00Z")
    assert span("2026-03-19 14:05 to 2026-03-19 14:20") == ("2026-03-19T14:05:00Z", "2026-03-19T14:20:00Z")
    assert span("19:00 - 19:30 today") == ("2026-11-08T19:00:00Z", "2026-11-08T19:30:00Z")
    assert w("8pm to 7pm") is None   # empty windows refuse, not invert


@pytest.mark.parametrize("phrase", ["", "marral", "the gemini upgrade", "banana", "25:99", "13pm"])
def test_non_temporal_returns_none_never_guesses(phrase):
    assert w(phrase) is None
