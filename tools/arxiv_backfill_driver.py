"""Run arxiv_gap_backfill.py over a long date range, one sub-window at a time.

Why a driver instead of one big run: arXiv's export API hard-fails past
`start`=10000 (measured 2026-07-26), so a 75k-result range must be split into
date sub-windows. It also 429s on sustained bursts, and a single long-lived
process that dies mid-range loses its place. This driver walks fixed calendar
sub-windows as separate invocations, so each window's writes are durable and a
throttled window can be retried without touching the others.

Everything is env-resolved (Rule 0.2) — no window count, page size, or delay is
baked in:
  NOUGEN_ARXIV_DRIVER_START / _END   date range (default: current year to today)
  NOUGEN_ARXIV_DRIVER_SPLIT_DAY      day-of-month that splits each month (15)
  NOUGEN_ARXIV_DRIVER_PAUSE_S        cooldown between windows (20)
  NOUGEN_ARXIV_DRIVER_RETRIES        attempts per window (3)
  plus every var arxiv_gap_backfill.py already honors (PAGE_SIZE, RATE_DELAY...)
"""
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "arxiv_gap_backfill.py")


def _env(name, default):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


SPLIT_DAY = int(_env("NOUGEN_ARXIV_DRIVER_SPLIT_DAY", "15"))
PAUSE_S = float(_env("NOUGEN_ARXIV_DRIVER_PAUSE_S", "20"))
RETRIES = int(_env("NOUGEN_ARXIV_DRIVER_RETRIES", "3"))
# Preflight: arXiv rate-limits by IP and sends NO Retry-After header (verified
# 2026-07-26 — a 429 carries no timing hint at all), so the only way to know it
# has forgiven us is to ask. Once throttled, every in-process retry just deepens
# the hole; wait for a single cheap request to succeed before resuming bulk work.
PREFLIGHT_URL = _env("NOUGEN_ARXIV_PREFLIGHT_URL",
                     "https://export.arxiv.org/api/query"
                     "?search_query=cat:cs.AI&start=0&max_results=1")
PREFLIGHT_WAIT_S = float(_env("NOUGEN_ARXIV_PREFLIGHT_WAIT_S", "300"))
PREFLIGHT_MAX_S = float(_env("NOUGEN_ARXIV_PREFLIGHT_MAX_S", "10800"))
PREFLIGHT_TIMEOUT_S = float(_env("NOUGEN_ARXIV_PREFLIGHT_TIMEOUT_S", "45"))


def month_windows(start, end):
    """Semi-monthly windows clipped to [start, end].

    Sized so each stays well under the API offset ceiling: the lane runs
    ~360 papers/day across 8 categories, so ~15 days is ~5.4k — comfortably
    below the 10k wall with headroom for busy weeks.
    """
    out = []
    d = start.replace(day=1)
    while d <= end:
        if d.month == 12:
            next_month = d.replace(year=d.year + 1, month=1)
        else:
            next_month = d.replace(month=d.month + 1)
        month_end = next_month - datetime.timedelta(days=1)
        for a, b in ((d, d.replace(day=SPLIT_DAY)),
                     (d.replace(day=SPLIT_DAY) + datetime.timedelta(days=1), month_end)):
            a, b = max(a, start), min(b, end)
            if a <= b:
                out.append((a, b))
        d = next_month
    return out


def api_ready():
    """One cheap request: True only on a real 200 with a body."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        PREFLIGHT_URL,
        headers={"User-Agent": _env("NOUGEN_ARXIV_UA",
                                    "NouGenAi-Orchestrator/4.0 (dave@whovisions.com)")})
    try:
        with urllib.request.urlopen(req, timeout=PREFLIGHT_TIMEOUT_S) as r:
            return r.status == 200 and bool(r.read(64))
    except Exception as e:
        print(f"    preflight: not ready ({type(e).__name__}: {e})", flush=True)
        return False


def wait_for_api(reason):
    """Block until arXiv answers again, or give up after PREFLIGHT_MAX_S.

    Returns True if the API came back. Deliberately polls slowly: a throttled
    IP is made worse by eager retries, and one request per interval is nothing.
    """
    import time
    if api_ready():
        return True
    waited = 0.0
    print(f"    arXiv unavailable ({reason}); waiting up to {PREFLIGHT_MAX_S}s",
          flush=True)
    while waited < PREFLIGHT_MAX_S:
        time.sleep(PREFLIGHT_WAIT_S)
        waited += PREFLIGHT_WAIT_S
        if api_ready():
            print(f"    arXiv recovered after {waited:.0f}s", flush=True)
            return True
        print(f"    still throttled at {waited:.0f}s", flush=True)
    return False


def main():
    today = datetime.date.today()
    start = datetime.date.fromisoformat(
        _env("NOUGEN_ARXIV_DRIVER_START", today.replace(month=1, day=1).isoformat()))
    end = datetime.date.fromisoformat(
        _env("NOUGEN_ARXIV_DRIVER_END", today.isoformat()))

    windows = month_windows(start, end)
    print(f"driver: {len(windows)} window(s) over {start}..{end}, "
          f"pause {PAUSE_S}s, {RETRIES} attempt(s) each", flush=True)

    totals = {"shards_written": 0, "daily_docs_written": 0,
              "shards_skipped_existing": 0, "daily_docs_skipped_existing": 0,
              "total_available": 0, "scanned": 0}
    failed, truncated = [], []

    if not wait_for_api("startup preflight"):
        print(json.dumps({"error": "arXiv API never became available",
                          "windows_completed": 0, **totals}), flush=True)
        return 2

    for i, (a, b) in enumerate(windows, 1):
        label = f"{a}..{b}"
        for attempt in range(1, RETRIES + 1):
            print(f"[{i}/{len(windows)}] {label} attempt {attempt}", flush=True)
            proc = subprocess.run(
                [sys.executable, TARGET, "--start", a.isoformat(), "--end", b.isoformat()],
                capture_output=True, text=True)
            # The script's last stdout line is its JSON summary.
            summary = None
            for ln in reversed((proc.stdout or "").strip().splitlines()):
                if ln.startswith("{"):
                    try:
                        summary = json.loads(ln)
                    except ValueError:
                        summary = None
                    break
            if summary and "error" not in summary:
                for k in totals:
                    v = summary.get(k) or 0
                    if isinstance(v, int) and v > 0:
                        totals[k] += v
                if summary.get("truncated"):
                    truncated.append(label)
                print(f"[{i}/{len(windows)}] {label} OK "
                      f"+{summary.get('shards_written', 0)} shards "
                      f"+{summary.get('daily_docs_written', 0)} docs "
                      f"(skipped {summary.get('shards_skipped_existing', 0)})", flush=True)
                break
            err = (summary or {}).get("error") or (proc.stderr or "").strip().splitlines()[-1:] or ["no output"]
            print(f"[{i}/{len(windows)}] {label} FAIL attempt {attempt}: {err}", flush=True)
            if attempt == RETRIES:
                failed.append(label)
            else:
                # A failed window almost always means we are throttled, so wait
                # for the API to actually answer again instead of retrying into
                # a wall on a fixed timer.
                if not wait_for_api(f"window {label} failed"):
                    print("    giving up: API stayed unavailable", flush=True)
                    failed.append(label)
                    break
                cool = PAUSE_S * (2 ** attempt)
                print(f"    cooling {cool}s before retry", flush=True)
                __import__("time").sleep(cool)
        __import__("time").sleep(PAUSE_S)

    result = {"windows": len(windows), "failed_windows": failed,
              "truncated_windows": truncated, **totals}
    print(json.dumps(result), flush=True)
    # Honest exit code: any window that never landed makes this a partial run.
    return 2 if (failed or truncated) else 0


if __name__ == "__main__":
    sys.exit(main())
