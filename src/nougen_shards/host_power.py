"""Host power awareness — CPU ceiling control around dispatch, and host-death correlation.

Two capabilities, one reason to live in NouGen:

1. **Dispatch guard.** NouGen is the only component that knows heavy local work is
   coming *before* it arrives — it is what dispatches local model inference. A host
   whose power delivery is marginal (no battery, aging adapter, undersized PSU) sags
   under the current transient that inference causes. Raising the CPU ceiling only
   for the duration of the work, and letting the floor drop the rest of the time,
   is something only the dispatcher can do with the right timing.

2. **Host-death correlation.** Nothing records an abrupt host power-off: the process
   dies mid-instruction, so no shutdown hook fires and no log entry is written by us.
   But every shard carries a timestamp, and the OS records its own unexpected-shutdown
   events. Joining those two timelines answers "what was running when the host died"
   without needing any crash telemetry that does not exist.

Platform: the control surface is Windows-only (`powercfg` / `Get-WinEvent`). Everything
here degrades to a documented no-op elsewhere — importing this module, calling the
guard, or asking for status must never raise on an unsupported host.

Rule 0.2: the active power scheme GUID is *probed at runtime*, never hardcoded. A
hardcoded GUID silently edits the wrong power plan the moment a user switches plans.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from . import core


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


# All environment-shaped. Ceilings/floors are percentages of max processor state.
POWER_SHELL = os.environ.get("NOUGEN_POWER_SHELL", "powershell")
POWER_TIMEOUT_S = _env_int("NOUGEN_POWER_TIMEOUT_S", 25)
# Ceiling applied *during* dispatch, and the floor to idle back down to afterwards.
DISPATCH_CEILING_PCT = _env_int("NOUGEN_POWER_DISPATCH_CEILING_PCT", 100)
DISPATCH_FLOOR_PCT = _env_int("NOUGEN_POWER_DISPATCH_FLOOR_PCT", 5)
# Correlation window: how far back to look, and how long before a death counts as
# "what was running".
SHUTDOWN_LOOKBACK_DAYS = _env_int("NOUGEN_SHUTDOWN_LOOKBACK_DAYS", 30)
SHUTDOWN_WINDOW_MIN = _env_int("NOUGEN_SHUTDOWN_WINDOW_MIN", 30)

_SUBGROUP = "SUB_PROCESSOR"
_CEILING_SETTING = "PROCTHROTTLEMAX"
_FLOOR_SETTING = "PROCTHROTTLEMIN"

# Unexpected-shutdown event ids. 41 = Kernel-Power (rebooted without clean shutdown),
# 6008 = EventLog's own "previous shutdown was unexpected" record.
_SHUTDOWN_EVENT_IDS = (41, 6008)


class PowerUnsupported(RuntimeError):
    """Raised only by explicit setters; probes return a reason instead."""


def _run_ps(script: str) -> tuple[int, str, str]:
    """Run a PowerShell snippet. Returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            [POWER_SHELL, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=POWER_TIMEOUT_S, check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)


def is_supported() -> tuple[bool, str]:
    """(supported, reason). Never raises — callers branch on the bool."""
    if not sys.platform.startswith("win"):
        return False, f"host power control is Windows-only (platform={sys.platform})"
    code, out, _ = _run_ps("powercfg /getactivescheme")
    if code != 0 or "GUID" not in out:
        return False, "powercfg unavailable or returned no active scheme"
    return True, "ok"


def active_scheme() -> Optional[str]:
    """Probe the ACTIVE power scheme GUID. Never hardcode this (Rule 0.2)."""
    code, out, _ = _run_ps("powercfg /getactivescheme")
    if code != 0:
        return None
    match = re.search(r"([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})", out)
    return match.group(1) if match else None


def _read_setting(guid: str, setting: str) -> Optional[int]:
    """Read one AC processor setting as a percentage."""
    code, out, _ = _run_ps(f"powercfg /query {guid} {_SUBGROUP} {setting}")
    if code != 0:
        return None
    match = re.search(r"Current AC Power Setting Index:\s*(0x[0-9a-fA-F]+|\d+)", out)
    if not match:
        return None
    raw = match.group(1)
    return int(raw, 16) if raw.lower().startswith("0x") else int(raw)


def status() -> dict:
    """Live power state. Always returns a dict; `supported` says whether to trust it."""
    supported, reason = is_supported()
    if not supported:
        return {"supported": False, "reason": reason}
    guid = active_scheme()
    if not guid:
        return {"supported": False, "reason": "could not resolve active scheme GUID"}
    return {
        "supported": True,
        "scheme_guid": guid,
        "ceiling_pct": _read_setting(guid, _CEILING_SETTING),
        "floor_pct": _read_setting(guid, _FLOOR_SETTING),
    }


def set_cpu_range(ceiling_pct: int, floor_pct: Optional[int] = None) -> dict:
    """Apply AC ceiling (and optionally floor) to the ACTIVE scheme.

    Returns the post-write probed state so the caller can verify rather than assume
    the write landed.
    """
    supported, reason = is_supported()
    if not supported:
        raise PowerUnsupported(reason)
    guid = active_scheme()
    if not guid:
        raise PowerUnsupported("could not resolve active scheme GUID")

    parts = [f"powercfg /setacvalueindex {guid} {_SUBGROUP} {_CEILING_SETTING} {int(ceiling_pct)}"]
    if floor_pct is not None:
        parts.append(f"powercfg /setacvalueindex {guid} {_SUBGROUP} {_FLOOR_SETTING} {int(floor_pct)}")
    # /setactive is what commits the staged values to the running scheme.
    parts.append(f"powercfg /setactive {guid}")
    code, _, err = _run_ps("; ".join(parts))
    if code != 0:
        raise PowerUnsupported(f"powercfg write failed: {err.strip()[:200]}")
    return status()


@contextmanager
def dispatch_guard(ceiling_pct: Optional[int] = None,
                   floor_pct: Optional[int] = None,
                   enabled: bool = True) -> Iterator[dict]:
    """Raise the CPU ceiling for the duration of heavy work, then restore it.

    Restores the values that were *actually captured* on entry — never a assumed
    default, which would silently rewrite a power plan the operator had tuned. The
    restore runs in `finally`, so an exception inside the block cannot strand the
    host at a modified ceiling.

    A power tweak must never take down the work it wraps: if anything about the
    power surface fails, this yields an explanatory dict and runs the body anyway.
    """
    if not enabled:
        yield {"applied": False, "reason": "guard disabled by caller"}
        return
    supported, reason = is_supported()
    if not supported:
        yield {"applied": False, "reason": reason}
        return

    before = status()
    prior_ceiling, prior_floor = before.get("ceiling_pct"), before.get("floor_pct")
    if prior_ceiling is None:
        yield {"applied": False, "reason": "could not read prior ceiling; refusing to write"}
        return

    try:
        set_cpu_range(
            DISPATCH_CEILING_PCT if ceiling_pct is None else ceiling_pct,
            DISPATCH_FLOOR_PCT if floor_pct is None else floor_pct,
        )
    except PowerUnsupported as exc:
        yield {"applied": False, "reason": str(exc)}
        return

    try:
        yield {"applied": True, "restored_to": {"ceiling": prior_ceiling, "floor": prior_floor}}
    finally:
        try:
            set_cpu_range(prior_ceiling, prior_floor)
        except PowerUnsupported:
            # Deliberately swallowed: the wrapped work has already completed (or
            # raised), and masking its outcome with a power-restore error would be
            # strictly worse. Surface it via status() on the next call instead.
            pass


def shutdown_events(days: Optional[int] = None) -> dict:
    """Unexpected host shutdowns in the lookback window.

    Timestamps are returned in **UTC** to match shard timestamps. Get-WinEvent yields
    local time; converting in PowerShell avoids guessing the host offset in Python.

    Returns `queried=False` when the query itself failed, so an empty list is
    distinguishable from a host that genuinely had no shutdowns. An empty result is
    not self-evidently healthy (HARDENING invariant 4).
    """
    window = SHUTDOWN_LOOKBACK_DAYS if days is None else days
    supported, reason = is_supported()
    if not supported:
        return {"queried": False, "reason": reason, "events": []}

    ids = ",".join(str(i) for i in _SHUTDOWN_EVENT_IDS)
    script = f"""
$ErrorActionPreference='SilentlyContinue'
$since=(Get-Date).AddDays(-{int(window)})
$ev = Get-WinEvent -FilterHashtable @{{LogName='System';StartTime=$since;Id={ids}}}
$out = foreach ($e in $ev) {{
  $p = $e.Properties
  [pscustomobject]@{{
    utc      = $e.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    id       = $e.Id
    bugcheck = if ($e.Id -eq 41 -and $p.Count -gt 9)  {{ [string]$p[9].Value  }} else {{ '' }}
    button   = if ($e.Id -eq 41 -and $p.Count -gt 6)  {{ [string]$p[6].Value  }} else {{ '' }}
    thermal  = if ($e.Id -eq 41 -and $p.Count -gt 13) {{ [string]$p[13].Value }} else {{ '' }}
  }}
}}
@($out) | ConvertTo-Json -Compress -Depth 3
"""
    code, out, err = _run_ps(script)
    if code != 0:
        return {"queried": False, "reason": err.strip()[:200], "events": []}
    text = out.strip()
    if not text:
        return {"queried": True, "events": [], "lookback_days": window}
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        return {"queried": False, "reason": f"unparseable event JSON: {exc}", "events": []}
    if isinstance(parsed, dict):
        parsed = [parsed]

    events = []
    for item in parsed:
        flags = {k: str(item.get(k, "")).lower() == "true" for k in ("bugcheck", "button", "thermal")}
        events.append({
            "utc": item.get("utc"),
            "event_id": item.get("id"),
            **flags,
            # Rail loss = the OS saw no explanation: not a crash, not the power
            # button, not a firmware thermal trip. That is the signature of the
            # machine simply losing power.
            "unexplained_rail_loss": (
                item.get("id") == 41 and not any(flags.values())
            ),
        })
    events.sort(key=lambda e: e["utc"] or "", reverse=True)
    collapsed = _collapse_paired(events)
    return {"queried": True, "events": collapsed, "raw_events": events,
            "lookback_days": window, "count": len(collapsed),
            "raw_count": len(events)}


def _collapse_paired(events: list) -> list:
    """Collapse the multiple log records a single host death emits into one death.

    One abrupt power-off writes BOTH a Kernel-Power 41 and an EventLog 6008, seconds
    apart, and a dirty boot can repeat them. Counting log records instead of deaths
    roughly doubles the number and makes the host look twice as sick as it is.
    Records within the pairing window are folded into the earliest one, keeping the
    41's cause flags (6008 carries none).
    """
    pair_window = timedelta(seconds=_env_int("NOUGEN_SHUTDOWN_PAIR_WINDOW_S", 120))
    deaths: list = []
    for event in sorted(events, key=lambda e: e["utc"] or ""):
        at = _parse_utc(event.get("utc"))
        if at is None:
            continue
        if deaths:
            prev_at = _parse_utc(deaths[-1]["utc"])
            if prev_at is not None and at - prev_at <= pair_window:
                merged = deaths[-1]
                merged["record_ids"].append(event["event_id"])
                # Cause flags only ever come from the 41 record; never let a
                # flagless 6008 erase an explanation the 41 supplied.
                for flag in ("bugcheck", "button", "thermal"):
                    merged[flag] = merged[flag] or event[flag]
                merged["unexplained_rail_loss"] = (
                    41 in merged["record_ids"]
                    and not any(merged[f] for f in ("bugcheck", "button", "thermal"))
                )
                continue
        deaths.append({**event, "record_ids": [event["event_id"]]})
    deaths.sort(key=lambda e: e["utc"] or "", reverse=True)
    return deaths


def shard_window_base_rate(days: int, window_min: int) -> dict:
    """What fraction of ALL windows in the lookback period contain vault activity.

    Without this, "no shards before the death" is uninterpretable: if vault writes
    are sparse, finding none in any given window is exactly what chance predicts.
    The silent-death count only means something compared against this baseline.
    """
    if not core.GLOBAL_DIR.exists() or window_min <= 0:
        return {"computed": False, "reason": "vault unavailable or bad window"}
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    span_min = days * 24 * 60
    total_windows = max(1, span_min // window_min)

    occupied = set()
    for db in sorted(core.GLOBAL_DIR.glob("nougen_shards_*.db")):
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=core.DB_TIMEOUT) as conn:
                cur = conn.execute(
                    "SELECT timestamp FROM shards WHERE timestamp >= ? AND timestamp <= ?",
                    (_sql_stamp(start), _sql_stamp(end)),
                )
                for (stamp,) in cur:
                    at = _parse_utc(stamp)
                    if at is not None:
                        occupied.add(int((at - start).total_seconds() // (window_min * 60)))
        except sqlite3.Error:
            continue
    return {
        "computed": True,
        "windows_total": total_windows,
        "windows_with_activity": len(occupied),
        "active_fraction": len(occupied) / total_windows,
    }


def _parse_utc(stamp: Optional[str]) -> Optional[datetime]:
    """Parse an event/shard UTC stamp, with or without a fractional part.

    Event stamps carry milliseconds, shard stamps carry microseconds. Both are
    accepted so the join keeps its precision rather than rounding to the second.
    """
    if not stamp:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(stamp, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _sql_stamp(moment: datetime) -> str:
    """Format a bound to match stored shard stamps exactly (microseconds + Z).

    Shard timestamps are compared as TEXT, so the bound must carry the same shape
    as the stored value. A bound truncated to whole seconds silently drops any
    shard written in the final fractional second of the window.
    """
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _shards_between(start_utc: datetime, end_utc: datetime, limit: int = 12) -> list:
    """Shards captured in a UTC window, across every DB in the resolved vault."""
    rows = []
    if not core.GLOBAL_DIR.exists():
        return rows
    lo, hi = _sql_stamp(start_utc), _sql_stamp(end_utc)
    for db in sorted(core.GLOBAL_DIR.glob("nougen_shards_*.db")):
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=core.DB_TIMEOUT) as conn:
                cur = conn.execute(
                    "SELECT timestamp, event_type, title FROM shards "
                    "WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT ?",
                    (lo, hi, limit),
                )
                rows.extend({"utc": r[0], "event_type": r[1], "title": r[2]} for r in cur)
        except sqlite3.Error:
            continue
    rows.sort(key=lambda r: r["utc"], reverse=True)
    return rows[:limit]


def correlate(days: Optional[int] = None, window_min: Optional[int] = None) -> dict:
    """Join host-death events against vault activity immediately preceding them.

    Answers "what was NouGen doing when the host died" using only data that already
    exists — no crash telemetry required, because none is collected.

    Correlation is not causation and the sample is small; `sample_size` travels with
    every result so no caller can quietly promote this to a hardware verdict
    (Rule 0.2 #5 wants a second, independent confirmation).
    """
    win = SHUTDOWN_WINDOW_MIN if window_min is None else window_min
    found = shutdown_events(days)
    if not found.get("queried"):
        return {"queried": False, "reason": found.get("reason"), "deaths": []}

    deaths = []
    for event in found["events"]:
        if not event.get("utc"):
            continue
        at = _parse_utc(event["utc"])
        if at is None:
            continue
        preceding = _shards_between(at - timedelta(minutes=win), at)
        deaths.append({
            "utc": event["utc"],
            "event_id": event["event_id"],
            "unexplained_rail_loss": event["unexplained_rail_loss"],
            "shards_before": preceding,
            "silent": not preceding,
        })

    unexplained = sum(1 for d in deaths if d["unexplained_rail_loss"])
    silent = sum(1 for d in deaths if d["silent"])
    base = shard_window_base_rate(found.get("lookback_days") or SHUTDOWN_LOOKBACK_DAYS, win)

    # Expected silent count if deaths were independent of vault activity. If observed
    # silence matches the baseline, the deaths tell you nothing about workload — the
    # vault is simply quiet most of the time.
    verdict = "insufficient data"
    expected_silent = None
    if base.get("computed") and deaths:
        expected_silent = (1.0 - base["active_fraction"]) * len(deaths)
        if base["active_fraction"] >= 0.99:
            verdict = "vault almost always active — silence would be meaningful, and there was none"
        elif silent >= expected_silent - 0.5:
            verdict = ("silence is at or above chance — deaths show NO association with "
                       "vault activity; this does not implicate workload")
        else:
            verdict = ("deaths precede vault activity more often than chance — workload "
                       "association worth investigating")

    return {
        "queried": True,
        "vault": core.vault_report(),
        "lookback_days": found.get("lookback_days"),
        "window_min": win,
        "sample_size": len(deaths),
        "log_records": found.get("raw_count"),
        "unexplained_rail_loss": unexplained,
        "silent_deaths": silent,
        "expected_silent_by_chance": expected_silent,
        "base_rate": base,
        "verdict": verdict,
        "deaths": deaths,
    }


def boot_report() -> dict:
    """What this boot can tell us about the *previous* shutdown.

    NouGen cannot observe its own death — the process dies mid-instruction and no
    shutdown hook fires. But at the next boot the OS has already written the verdict,
    and NouGen runs at startup. Startup is therefore the only moment a host death can
    be turned into a durable record, and it is the first moment the machine can speak
    again. This is the read half; `record_boot()` is the write half.
    """
    supported, reason = is_supported()
    if not supported:
        return {"supported": False, "reason": reason}

    script = """
$ErrorActionPreference='SilentlyContinue'
$os = Get-CimInstance Win32_OperatingSystem
[pscustomobject]@{
  boot_utc = $os.LastBootUpTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
  now_utc  = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
} | ConvertTo-Json -Compress
"""
    code, out, err = _run_ps(script)
    if code != 0 or not out.strip():
        return {"supported": False, "reason": (err or "boot query returned nothing").strip()[:200]}
    try:
        info = json.loads(out.strip())
    except ValueError as exc:
        return {"supported": False, "reason": f"unparseable boot JSON: {exc}"}

    boot_at, now_at = _parse_utc(info.get("boot_utc")), _parse_utc(info.get("now_utc"))
    uptime_s = int((now_at - boot_at).total_seconds()) if (boot_at and now_at) else None

    # Which death record belongs to THIS boot?
    #
    # Not "the newest one before boot" — that is backwards. Windows cannot log an
    # abrupt power loss while it is happening, so it writes the Kernel-Power 41
    # record *after* the machine comes back up, describing the shutdown that
    # preceded this boot. Its timestamp therefore lands a few seconds AFTER
    # LastBootUpTime. Filtering to `<= boot` skips the very record that explains
    # this boot and silently attributes the previous one instead.
    #
    # The record for this boot is the one nearest boot time, allowing a short
    # window on either side: slightly before (clock skew) or shortly after (the
    # normal case, once the event log service is up).
    found = shutdown_events()
    prior = None
    if found.get("queried") and boot_at:
        skew = timedelta(seconds=_env_int("NOUGEN_BOOT_SKEW_S", 120))
        post = timedelta(seconds=_env_int("NOUGEN_BOOT_POST_WINDOW_S", 600))
        candidates = []
        for death in found["events"]:
            at = _parse_utc(death.get("utc"))
            if at is None:
                continue
            if (boot_at - skew) <= at <= (boot_at + post):
                candidates.append((abs((at - boot_at).total_seconds()), death))
        if candidates:
            prior = min(candidates, key=lambda pair: pair[0])[1]

    return {
        "supported": True,
        "boot_utc": info.get("boot_utc"),
        "uptime_s": uptime_s,
        "previous_shutdown_clean": prior is None,
        "previous_death": prior,
        "deaths_in_lookback": found.get("count"),
    }


def record_boot(dry_run: bool = False) -> dict:
    """Capture a shard for an unclean previous shutdown. Safe to call every boot.

    Idempotent by construction: the shard body is keyed to the death's exact
    timestamp, so `core.capture()`'s content-hash dedup rejects a second write for
    the same death. Startup code that reruns — or a machine that reboots twice
    without a death in between — cannot pollute the vault with duplicates.
    """
    report = boot_report()
    if not report.get("supported"):
        return {"recorded": False, "reason": report.get("reason")}
    if report["previous_shutdown_clean"]:
        return {"recorded": False, "reason": "previous shutdown was clean", "clean": True}

    death = report["previous_death"]
    cause = ("unexplained rail loss" if death["unexplained_rail_loss"]
             else "bugcheck" if death["bugcheck"]
             else "power button" if death["button"]
             else "thermal shutdown" if death["thermal"]
             else "unexpected shutdown")
    title = f"Host death {death['utc']} — {cause}"
    body = (
        f"Unexpected host shutdown recorded at next boot.\n\n"
        f"Death (UTC): {death['utc']}\n"
        f"Cause: {cause}\n"
        f"Log records: {death.get('record_ids')}\n"
        f"Flags: bugcheck={death['bugcheck']} power_button={death['button']} "
        f"thermal={death['thermal']}\n"
        f"Booted at: {report['boot_utc']}\n"
        f"Deaths in lookback window: {report['deaths_in_lookback']}\n\n"
        "Captured at startup because a host power loss leaves no trace of its own: "
        "the process dies mid-instruction, so no shutdown hook fires and nothing is "
        "written at the time. The next boot is the first moment this is recordable. "
        "An unexplained rail loss means the OS saw no cause — not a crash, not the "
        "power button, not a firmware thermal trip — which is the signature of the "
        "machine simply losing power."
    )
    if dry_run:
        return {"recorded": False, "dry_run": True, "title": title, "cause": cause}
    captured = core.capture("ERROR", title, body, ["host-death", "power", "boot", "telemetry"])
    return {"recorded": bool(captured), "title": title, "cause": cause,
            "reason": None if captured else "already recorded (dedup)"}


def format_correlation(report: dict) -> str:
    """Human-readable correlation summary for the CLI."""
    if not report.get("queried"):
        return f"host power: query failed — {report.get('reason', 'unknown reason')}"

    n = report["sample_size"]
    if n == 0:
        return (f"No unexpected shutdowns in the last {report['lookback_days']}d. "
                "(Query ran successfully — this is a real absence, not a failed lookup.)")

    base = report.get("base_rate", {})
    lines = [
        f"Host deaths: {n} in {report['lookback_days']}d "
        f"({report['unexplained_rail_loss']} unexplained rail loss) "
        f"— collapsed from {report.get('log_records')} log records",
        f"Vault: {report['vault']['vault_dir']} ({report['vault']['shard_count']} shards)",
        f"Window: {report['window_min']} min before each death",
        f"Silent deaths (no vault activity in window): {report['silent_deaths']}/{n}",
    ]
    if base.get("computed"):
        lines.append(
            f"Baseline: {base['windows_with_activity']}/{base['windows_total']} windows "
            f"({base['active_fraction']:.1%}) contain vault activity at all"
        )
        if report.get("expected_silent_by_chance") is not None:
            lines.append(
                f"Expected silent by chance: {report['expected_silent_by_chance']:.1f}/{n}"
            )
    lines.append(f"VERDICT: {report.get('verdict')}")
    lines.append("")
    for death in report["deaths"][:10]:
        tag = "rail-loss" if death["unexplained_rail_loss"] else f"id={death['event_id']}"
        lines.append(f"  {death['utc']}  [{tag}]")
        if death["silent"]:
            lines.append("      (no shards captured in window — NouGen was idle)")
        for shard in death["shards_before"][:3]:
            lines.append(f"      {shard['utc']}  {shard['event_type']}  {shard['title'][:64]}")
    if n < 5:
        lines.append("")
        lines.append(f"NOTE: sample_size={n} is too small to call a pattern.")
    return "\n".join(lines)
