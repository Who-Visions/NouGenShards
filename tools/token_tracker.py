#!/usr/bin/env python3
"""Claude Code & Antigravity token tracker.

Aggregates token usage from:
1. Claude Code JSONL logs under ~/.claude/projects/
2. Antigravity active sessions queried via internal loopback RPC
3. Antigravity JSONL logs under ~/.gemini/antigravity/brain/ and ~/.gemini/antigravity-cli/brain/ (fallback/archived)
"""
import glob
import json
import os
import sys
import subprocess
import re
import urllib.request
import ssl
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import datetime as _dtm

DAYS = 2
MONTH = None
BY_PROVIDER = False
RANGE_START = None
RANGE_END = None
COMPARE_N = None
LANES = False

# argparse CLI: preserves the legacy positional days arg and --month / --by-provider,
# and adds dynamic ranges (--days/--weeks/--start/--end) + a --compare period diff.
# Skipped for the --demo-tc subcommand, and when IMPORTED (e.g. hi_token_tracker.py
# imports this module for its helpers; we must not consume that process's argv or
# trigger argparse's --help/exit during import).
if "--demo-tc" not in sys.argv and __name__ == "__main__":
    import argparse as _ap

    _parser = _ap.ArgumentParser(
        prog="token_tracker.py",
        formatter_class=_ap.RawDescriptionHelpFormatter,
        description=(
            "Cross-provider token usage monitor. Reports input / output / cache-read / "
            "reasoning tokens by company (Claude Code, Google Antigravity, OpenAI Codex, "
            "Gemini CLI, + Fleet ledger) and by day, over any range you ask for."
        ),
        epilog=(
            "ranges (most specific wins: --start/--end > --month > --compare > --weeks > --days > positional)\n"
            "  token_tracker.py                                    last 2 days (default)\n"
            "  token_tracker.py 7                                  last 7 days (legacy positional)\n"
            "  token_tracker.py --days 7                           last 7 days\n"
            "  token_tracker.py --weeks 2                          last 14 days\n"
            "  token_tracker.py --month 2026-06                    a calendar month\n"
            "  token_tracker.py --start 2026-06-11 --end 2026-06-18   explicit inclusive range\n"
            "  token_tracker.py --compare 7                        last 7d vs prior 7d, per company\n"
            "  token_tracker.py 7 --by-provider                   group the Fleet ledger by provider\n"
            "\nenv: TOKEN_TRACKER_CUTOFF=<iso8601> overrides the lower bound."
        ),
    )
    _parser.add_argument("days_pos", nargs="?", type=int, default=None,
                         help="legacy positional: days back from now (default 2)")
    _parser.add_argument("--days", type=int, default=None, help="days back from now")
    _parser.add_argument("--weeks", type=int, default=None, help="weeks back from now (7*N days)")
    _parser.add_argument("--start", metavar="YYYY-MM-DD", default=None,
                         help="explicit window start, inclusive")
    _parser.add_argument("--end", metavar="YYYY-MM-DD", default=None,
                         help="explicit window end, inclusive (default = now)")
    _parser.add_argument("--month", metavar="YYYY-MM", default=None,
                         help="restrict the window to a calendar month")
    _parser.add_argument("--compare", type=int, metavar="N", default=None,
                         help="compare the last N days vs the prior N days, per company")
    _parser.add_argument("--lanes", action="store_true",
                         help="full analytics dashboard: 24h/WTD/MTD/QTD/HTD/YTD comparisons + records (highest day/week/month/streak)")
    _parser.add_argument("--by-provider", action="store_true",
                         help="group the Fleet usage ledger rows by provider")
    _a, _ = _parser.parse_known_args()

    MONTH = _a.month
    BY_PROVIDER = _a.by_provider
    RANGE_START = _a.start
    RANGE_END = _a.end
    COMPARE_N = _a.compare
    LANES = _a.lanes

    if _a.days is not None:
        DAYS = _a.days
    elif _a.weeks is not None:
        DAYS = _a.weeks * 7
    elif _a.days_pos is not None:
        DAYS = _a.days_pos

    # --compare widens the collection window so both periods are gathered (>= 2N days).
    if COMPARE_N is not None and COMPARE_N > 0:
        DAYS = max(DAYS, COMPARE_N * 2)
    if LANES:
        DAYS = max(DAYS, 760)   # load full available history for the analytics dashboard

PROJECTS = os.path.expanduser(os.path.join("~", ".claude", "projects"))

ANTIGRAVITY_BRAIN_DIRS = [
    os.path.expanduser(os.path.join("~", ".gemini", "antigravity", "brain")),
    os.path.expanduser(os.path.join("~", ".gemini", "antigravity-cli", "brain")),
    os.path.expanduser(os.path.join("~", ".gemini", "antigravity-ide", "brain")),
    os.path.expanduser(os.path.join("~", ".gemini", "antigravity-backup", "brain"))
]

CODEX_STATE = os.path.expanduser(os.path.join("~", ".codex", "state_5.sqlite"))

# Fleet usage ledger: forward token accounting for local Ollama/Gemma, OpenRouter,
# HF and other lanes that otherwise write no token telemetry to disk. Written by
# fleet_usage_proxy.py + the instrumented fleet clients (see Sol-Ai/).
FLEET_USAGE_LEDGER = os.environ.get(
    "FLEET_USAGE_LEDGER",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault", "fleet_usage.jsonl"),
)

KEYS = ("input_tokens", "output_tokens",
        "cache_creation_input_tokens", "cache_read_input_tokens", "reasoning_tokens")

NOW = datetime.now(timezone.utc).astimezone()

if RANGE_START or RANGE_END:
    local_tz = datetime.now().astimezone().tzinfo
    CUTOFF = (
        datetime.fromisoformat(RANGE_START).replace(tzinfo=local_tz)
        if RANGE_START else (NOW - timedelta(days=DAYS))
    )
    if RANGE_END:
        # end is inclusive -> extend to the end of that calendar day
        LIMIT_UPPER = datetime.fromisoformat(RANGE_END).replace(tzinfo=local_tz) + timedelta(days=1)
    else:
        try:
            LIMIT_UPPER = datetime.max.replace(tzinfo=timezone.utc).astimezone()
        except OSError:
            LIMIT_UPPER = datetime(3000, 1, 1, tzinfo=timezone.utc).astimezone()
elif MONTH:
    try:
        parts = MONTH.split("-")
        year = int(parts[0])
        month = int(parts[1])
        start_dt = datetime(year, month, 1)
        if month == 12:
            end_dt = datetime(year + 1, 1, 1)
        else:
            end_dt = datetime(year, month + 1, 1)
        # Convert to local timezone
        local_tz = datetime.now().astimezone().tzinfo
        CUTOFF = start_dt.replace(tzinfo=local_tz)
        LIMIT_UPPER = end_dt.replace(tzinfo=local_tz)
    except Exception as e:
        print(f"Error parsing --month {MONTH}: {e}")
        sys.exit(1)
else:
    cutoff_env = os.environ.get("TOKEN_TRACKER_CUTOFF")
    CUTOFF = datetime.fromisoformat(cutoff_env) if cutoff_env else (NOW - timedelta(days=DAYS))
    try:
        LIMIT_UPPER = datetime.max.replace(tzinfo=timezone.utc).astimezone()
    except OSError:
        LIMIT_UPPER = datetime(3000, 1, 1, tzinfo=timezone.utc).astimezone()

ALL_INVOCATIONS = []

MODEL_MAP = {
    'MODEL_PLACEHOLDER_M132': 'gemini-3.5-flash-high',
    'MODEL_PLACEHOLDER_M131': 'gemini-3.5-flash-medium',
    'MODEL_PLACEHOLDER_M130': 'gemini-3.5-flash-low',
    'MODEL_PLACEHOLDER_M37': 'gemini-3.1-pro-high',
    'MODEL_PLACEHOLDER_M36': 'gemini-3.1-pro-low',
    'MODEL_PLACEHOLDER_M18': 'gemini-3-flash',
    'MODEL_PLACEHOLDER_M8': 'gemini-3-pro-high',
    'MODEL_PLACEHOLDER_M7': 'gemini-3-pro-low',
    'MODEL_PLACEHOLDER_M9': 'gemini-3-pro-image',
    'MODEL_PLACEHOLDER_M26': 'claude-opus-4-6-thinking',
    'MODEL_PLACEHOLDER_M35': 'claude-sonnet-4-6-thinking',
    'MODEL_PLACEHOLDER_M12': 'claude-opus-4-5-thinking',
    'MODEL_OPENAI_GPT_OSS_120B_MEDIUM': 'gpt-oss-120b-medium',
    'MODEL_CLAUDE_4_5_SONNET': 'claude-sonnet-4-5',
    'MODEL_CLAUDE_4_5_SONNET_THINKING': 'claude-sonnet-4-5-thinking',

    # New models from gemini_api_models.json
    'models/gemini-2.5-flash': 'gemini-2.5-flash',
    'models/gemini-2.5-pro': 'gemini-2.5-pro',
    'models/gemini-2.0-flash': 'gemini-2.0-flash',
    'models/gemini-2.0-flash-001': 'gemini-2.0-flash-001',
    'models/gemini-2.0-flash-lite-001': 'gemini-2.0-flash-lite-001',
    'models/gemini-2.0-flash-lite': 'gemini-2.0-flash-lite',
    'models/gemini-2.5-flash-preview-tts': 'gemini-2.5-flash-preview-tts',
    'models/gemini-2.5-pro-preview-tts': 'gemini-2.5-pro-preview-tts',
    'models/gemma-3-1b-it': 'gemma-3-1b-it',
    'models/gemma-3-4b-it': 'gemma-3-4b-it',
    'models/gemma-3-12b-it': 'gemma-3-12b-it',
    'models/gemma-3-27b-it': 'gemma-3-27b-it',
    'models/gemma-3n-e4b-it': 'gemma-3n-e4b-it',
    'models/gemma-3n-e2b-it': 'gemma-3n-e2b-it',
    'models/gemma-4-26b-a4b-it': 'gemma-4-26b-a4b-it',
    'models/gemma-4-31b-it': 'gemma-4-31b-it',
    'models/gemini-flash-latest': 'gemini-flash-latest',
    'models/gemini-flash-lite-latest': 'gemini-flash-lite-latest',
    'models/gemini-pro-latest': 'gemini-pro-latest',
    'models/gemini-2.5-flash-lite': 'gemini-2.5-flash-lite',
    'models/gemini-2.5-flash-image': 'nano-banana',
    'models/gemini-3-pro-preview': 'gemini-3-pro-preview',
    'models/gemini-3-flash-preview': 'gemini-3-flash-preview',
    'models/gemini-3.1-pro-preview': 'gemini-3.1-pro-preview',
    'models/gemini-3.1-pro-preview-customtools': 'gemini-3.1-pro-preview-customtools',
    'models/gemini-3.1-flash-lite-preview': 'gemini-3.1-flash-lite-preview',
    'models/gemini-3-pro-image-preview': 'nano-banana-pro',
    'models/nano-banana-pro-preview': 'nano-banana-pro',
    'models/gemini-3.1-flash-image-preview': 'nano-banana-2',
    'models/lyria-3-clip-preview': 'lyria-3-clip-preview',
    'models/lyria-3-pro-preview': 'lyria-3-pro-preview',
    'models/gemini-robotics-er-1.5-preview': 'gemini-robotics-er-1.5-preview',
    'models/gemini-2.5-computer-use-preview-10-2025': 'gemini-2.5-computer-use-preview-10-2025',
    'models/deep-research-pro-preview-12-2025': 'deep-research-pro-preview-12-2025',
    'models/gemini-embedding-001': 'gemini-embedding-001',
    'models/gemini-embedding-2-preview': 'gemini-embedding-2-preview',
    'models/aqa': 'aqa',
    'models/imagen-4.0-generate-001': 'imagen-4',
    'models/imagen-4.0-ultra-generate-001': 'imagen-4-ultra',
    'models/imagen-4.0-fast-generate-001': 'imagen-4-fast',
    'models/veo-2.0-generate-001': 'veo-2',
    'models/veo-3.0-generate-001': 'veo-3',
    'models/veo-3.0-fast-generate-001': 'veo-3-fast',
    'models/veo-3.1-generate-preview': 'veo-3.1',
    'models/veo-3.1-fast-generate-preview': 'veo-3.1-fast',
    'models/veo-3.1-lite-generate-preview': 'veo-3.1-lite',
    'models/gemini-2.5-flash-native-audio-latest': 'gemini-2.5-flash-native-audio-latest',
    'models/gemini-2.5-flash-native-audio-preview-09-2025': 'gemini-2.5-flash-native-audio-preview-09-2025',
    'models/gemini-2.5-flash-native-audio-preview-12-2025': 'gemini-2.5-flash-native-audio-preview-12-2025',
    'models/gemini-3.1-flash-live-preview': 'gemini-3.1-flash-live-preview',
}

def resolve_model(model_id):
    if not model_id:
        return "unknown"
    if model_id.startswith("models/"):
        model_id = model_id[7:]
    if model_id in MODEL_MAP:
        return MODEL_MAP[model_id]
    if model_id.startswith("MODEL_PLACEHOLDER_"):
        num = model_id.split("_")[-1]
        return f"gemini-{num.lower()}"
    return model_id


# --- Per-model pricing (USD per million tokens) -----------------------------
# Tuple = (input, output, cache_read, source). reasoning bills at the output
# rate; cache_creation bills at 1.25x input (the 5-minute cache-write tier).
#
# Claude rates are first-party list prices from claude.com/pricing.
# Everything tagged EST is an ESTIMATE with no first-party source wired in —
# treat those as tunable knobs, not ground truth, and correct them as real
# invoices arrive. The point of this table is an HONEST reference bill, not an
# impressive one: cache-reads are priced as cache-reads, not as fresh input.
DOC = "doc"   # first-party documented list price (any vendor)
EST = "est"
MODEL_PRICING = {
    # ---- Claude: first-party list prices ----
    "claude-fable-5":             (10.00, 50.00, 1.000, DOC),
    "claude-opus-4-8":            (5.00, 25.00, 0.500, DOC),
    "claude-opus-4-7":            (5.00, 25.00, 0.500, DOC),
    "claude-opus-4-6":            (5.00, 25.00, 0.500, DOC),
    "claude-opus-4-6-thinking":   (5.00, 25.00, 0.500, DOC),
    "claude-opus-4-5":            (5.00, 25.00, 0.500, DOC),
    "claude-opus-4-5-thinking":   (5.00, 25.00, 0.500, DOC),
    "claude-sonnet-4-6":          (3.00, 15.00, 0.300, DOC),
    "claude-sonnet-4-6-thinking": (3.00, 15.00, 0.300, DOC),
    "claude-sonnet-4-5":          (3.00, 15.00, 0.300, DOC),
    "claude-sonnet-4-5-20250929": (3.00, 15.00, 0.300, DOC),
    "claude-sonnet-4-5-thinking": (3.00, 15.00, 0.300, DOC),
    "claude-haiku-4-5":           (1.00, 5.00, 0.100, DOC),
    # ---- Gemini: first-party list prices (ai.google.dev/gemini-api/docs/pricing) ----
    # Flash thinking tiers (high/medium/low) share one standard price.
    "gemini-3.5-flash-high":      (1.50, 9.00, 0.15, DOC),
    "gemini-3.5-flash-medium":    (1.50, 9.00, 0.15, DOC),
    "gemini-3.5-flash-low":       (1.50, 9.00, 0.15, DOC),
    "gemini-3.5-pro":             (2.00, 12.00, 0.20, DOC),
    "gemini-3.5-pro-preview":     (2.00, 12.00, 0.20, EST),
    "gemini-3.5-flash":           (1.50, 9.00, 0.15, DOC),
    "gemini-3.5-flash-preview":   (1.50, 9.00, 0.15, EST),
    # Gemini 3.1 Pro standard, <=200k-token prompt tier.
    "gemini-3.1-pro-high":        (2.00, 12.00, 0.20, DOC),
    "gemini-3.1-pro-low":         (2.00, 12.00, 0.20, DOC),
    # Gemini 3 Flash Preview standard (the actual heavy Antigravity model).
    "gemini-3-flash-preview":     (0.50, 3.00, 0.05, DOC),
    "gemini-3-flash":             (0.50, 3.00, 0.05, DOC),
    # ---- Gemini CLI models (seen in ~/.gemini/tmp/*/chats logs) ----
    # 3.1 Pro preview shares the documented 3.1-pro standard tier.
    "gemini-3.1-pro-preview":     (2.00, 12.00, 0.20, DOC),
    "gemini-3.1-pro-preview-customtools": (2.00, 12.00, 0.20, DOC),
    # 3 Pro preview: no first-party row wired in yet -> estimate at pro tier.
    "gemini-3-pro-preview":       (2.00, 12.00, 0.20, EST),
    # 2.5 family: first-party list prices (<=200k tier).
    "gemini-2.5-pro":             (1.25, 10.00, 0.31, DOC),
    "gemini-2.5-flash":           (0.30, 2.50, 0.075, DOC),
    # 2.0 family: first-party list prices
    "gemini-2.0-flash":           (0.075, 0.30, 0.01875, DOC),
    "gemini-2.0-flash-lite":      (0.0375, 0.15, 0.009375, DOC),
    "gemini-2.0-pro":             (0.80, 3.20, 0.20, DOC),
    # Flash-lite tiers: estimate, no first-party row confirmed here.
    "gemini-3.1-flash-lite":          (0.10, 0.40, 0.01, EST),
    "gemini-3.1-flash-lite-preview":  (0.10, 0.40, 0.01, EST),
    # ---- OpenAI: first-party list prices (cached input -> cache_read) ----
    "gpt-5.6-sol-ultra":          (5.00, 30.00, 0.50, DOC),
    "gpt-5.6-sol":                (5.00, 30.00, 0.50, DOC),
    "gpt-5.6-terra":              (2.50, 15.00, 0.25, DOC),
    "gpt-5.6-luna":               (1.00, 6.00, 0.10, DOC),
    "gpt-5.5":                    (5.00, 30.00, 0.50, DOC),
    "gpt-5.4":                    (2.50, 15.00, 0.25, DOC),
    "gpt-5.4-mini":               (0.75, 4.50, 0.075, DOC),
    "gpt-5-codex-mini":           (0.75, 4.50, 0.075, EST),
    "gpt-5.1-codex-mini":         (0.75, 4.50, 0.075, EST),
    # gpt-oss is open-weights; Dave runs it free via OpenRouter/local. Nominal host est.
    "gpt-oss-120b-medium":        (0.10, 0.40, 0.010, EST),
}
# Unknown model: conservative estimate so the bill never silently reads $0.
DEFAULT_PRICING = (1.00, 4.00, 0.100, EST)


# Local Ollama/Gemma models and OpenRouter ':free' routes cost $0 — they are
# tracked for VOLUME, not spend (the fleet enforces a hard-free policy).
FREE_LOCAL_MODELS = {
    "dav1d:e2b", "sol-ai:e4b", "kaedra:e4b", "iris-ai:e4b",
    "gemma4-aggressive:e4b", "gemma4-aggressive:e2b", "gemma2:2b", "gemma:2b",
}


def price_for(model_name):
    """Resolve (input, output, cache_read, source) for a model, ignoring the
    ' (estimated)' suffix the Antigravity fallback parser appends."""
    key = (model_name or "").replace(" (estimated)", "").strip()
    # Free lanes: local Ollama/Gemma + OpenRouter ':free' routes.
    if key.endswith(":free") or key in FREE_LOCAL_MODELS:
        return (0.0, 0.0, 0.0, DOC)
    return MODEL_PRICING.get(key, DEFAULT_PRICING)


def model_bill(model_name, d):
    """Honest API-equivalent cost (USD) for one model's token bucket.

    Cache-reads are billed at their discounted rate, cache-creation at 1.25x
    input, and reasoning at the output rate — the way a real invoice prices
    them. Returns (cost_usd, source_tag).
    """
    inp, out, cache_read, src = price_for(model_name)
    cost = (
        d.get("input_tokens", 0) * inp
        + d.get("cache_creation_input_tokens", 0) * inp * 1.25
        + d.get("cache_read_input_tokens", 0) * cache_read
        + (d.get("output_tokens", 0) + d.get("reasoning_tokens", 0)) * out
    ) / 1_000_000
    return cost, src

def parse_ts(rec):
    if not rec or not isinstance(rec, dict):
        return None
    ts = rec.get("timestamp") or rec.get("created_at") or rec.get("startTime") or rec.get("start_time")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return None

def usage_of(rec):
    msg = rec.get("message")
    u = msg.get("usage") if isinstance(msg, dict) else None
    if u is None:
        u = rec.get("usage")
    return u if isinstance(u, dict) else None

def model_of(rec):
    msg = rec.get("message")
    if isinstance(msg, dict) and msg.get("model"):
        return msg["model"]
    return rec.get("model") or "unknown"

def fmt(n):
    return f"{n:,}"

def cols(d):
    return (d["input_tokens"], d["output_tokens"],
            d["cache_creation_input_tokens"], d["cache_read_input_tokens"], d["reasoning_tokens"])

# --- Parse Claude Code Logs ---
def parse_claude():
    files = glob.glob(os.path.join(PROJECTS, "**", "*.jsonl"), recursive=True)
    by_day = defaultdict(lambda: defaultdict(int))
    by_model = defaultdict(lambda: defaultdict(int))
    totals = defaultdict(int)
    records = 0
    seen = set()

    for f in files:
        try:
            fh = open(f, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                u = usage_of(rec)
                if not u:
                    continue
                ts = parse_ts(rec)
                if ts is None or ts < CUTOFF or ts > LIMIT_UPPER:
                    continue
                uid = rec.get("uuid")
                if uid is not None:
                    if uid in seen:
                        continue
                    seen.add(uid)
                day = ts.strftime("%Y-%m-%d")
                model = model_of(rec)
                for k in KEYS:
                    v = int(u.get(k) or 0)
                    by_day[day][k] += v
                    by_model[model][k] += v
                    totals[k] += v
                
                it = int(u.get("input_tokens") or 0)
                ot = int(u.get("output_tokens") or 0)
                cc = int(u.get("cache_creation_input_tokens") or 0)
                cr = int(u.get("cache_read_input_tokens") or 0)
                rt = int(u.get("reasoning_tokens") or 0)
                
                ALL_INVOCATIONS.append({
                    "timestamp": ts,
                    "source": "Claude Code",
                    "model": model,
                    "input_tokens": it,
                    "output_tokens": ot,
                    "cache_creation": cc,
                    "cache_read": cr,
                    "reasoning": rt,
                    "exact": True,
                    "session_id": rec.get("project_name") or (f.split(os.sep)[-2] if len(f.split(os.sep)) >= 2 else "unknown_project"),
                    "source_file": os.path.basename(f)
                })
                records += 1
    return by_day, by_model, totals, len(files), records

# --- RPC Locator ---
def locate_antigravity_rpc():
    candidates = []
    # 1. WMIC process detection
    try:
        cmd = 'wmic process get ProcessId,CommandLine /FORMAT:CSV'
        output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
        for line in output.splitlines():
            line = line.strip()
            if not line or "wmic" in line:
                continue
            if "language_server" in line.lower() and "--csrf_token" in line:
                parts = line.split(',')
                if len(parts) >= 3:
                    pid_str = parts[-1].strip()
                    cmd_line = ",".join(parts[1:-1])
                    try:
                        pid = int(pid_str)
                    except ValueError:
                        continue
                    token_match = re.search(r'--csrf_token\s+([a-f0-9-]+)', cmd_line)
                    if token_match:
                        candidates.append({"pid": pid, "token": token_match.group(1)})
    except Exception:
        pass

    # 2. PowerShell fallback process detection
    if not candidates:
        try:
            cmd = 'powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like \'*language_server*\' } | Select-Object ProcessId, CommandLine | ConvertTo-Json"'
            output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
            if output.strip():
                data = json.loads(output)
                if isinstance(data, dict):
                    data = [data]
                for p in data:
                    pid = p.get("ProcessId")
                    cmd_line = p.get("CommandLine") or ""
                    token_match = re.search(r'--csrf_token\s+([a-f0-9-]+)', cmd_line)
                    if pid and token_match:
                        candidates.append({"pid": pid, "token": token_match.group(1)})
        except Exception:
            pass

    verified_conns = []
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for cand in candidates:
        pid = cand["pid"]
        token = cand["token"]
        ports = []
        try:
            output = subprocess.check_output("netstat -ano", shell=True).decode('utf-8', errors='ignore')
            for line in output.splitlines():
                if "LISTENING" in line and str(pid) in line.split()[-1]:
                    parts = line.split()
                    port_match = re.search(r':(\d+)$', parts[1])
                    if port_match:
                        ports.append(int(port_match.group(1)))
        except Exception:
            pass
            
        for port in set(ports):
            url = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/Heartbeat"
            req = urllib.request.Request(
                url,
                data=json.dumps({"uuid": "00000000-0000-0000-0000-000000000000"}).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "Connect-Protocol-Version": "1",
                    "X-Codeium-Csrf-Token": token
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=1.5) as resp:
                    if resp.status == 200:
                        verified_conns.append((port, token))
            except Exception:
                pass
    return verified_conns

# --- Parse Antigravity Logs & RPC ---
def parse_antigravity():
    by_day = defaultdict(lambda: defaultdict(int))
    by_model = defaultdict(lambda: defaultdict(int))
    totals = defaultdict(int)
    records = 0
    active_cascade_ids = set()
    rpc_scanned_invocations = 0

    # 1. Attempt RPC Retrieval
    rpc_conns = locate_antigravity_rpc()
    for port, token in rpc_conns:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Get active trajectories
        url_traj = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetAllCascadeTrajectories"
        req_traj = urllib.request.Request(
            url_traj,
            data=json.dumps({}).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Connect-Protocol-Version": "1",
                "X-Codeium-Csrf-Token": token
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req_traj, context=ctx, timeout=3) as resp:
                traj_data = json.loads(resp.read().decode('utf-8'))
                summaries = traj_data.get("trajectorySummaries", {})
                for cascade_id in summaries.keys():
                    active_cascade_ids.add(cascade_id)
                    
                    # Query metadata
                    url_meta = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectoryGeneratorMetadata"
                    req_meta = urllib.request.Request(
                        url_meta,
                        data=json.dumps({"cascadeId": cascade_id}).encode('utf-8'),
                        headers={
                            "Content-Type": "application/json",
                            "Connect-Protocol-Version": "1",
                            "X-Codeium-Csrf-Token": token
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req_meta, context=ctx, timeout=3) as resp_meta:
                        meta_data = json.loads(resp_meta.read().decode('utf-8'))
                        for item in meta_data.get("generatorMetadata", []):
                            chat_model = item.get("chatModel", {})
                            usage = chat_model.get("usage", {})
                            if not usage:
                                continue
                            
                            it = int(usage.get("inputTokens") or usage.get("input_token_count") or usage.get("prompt_token_count") or usage.get("prompt_eval_count") or 0)
                            ot = int(usage.get("outputTokens") or usage.get("output_token_count") or usage.get("eval_count") or 0)
                            cc = int(usage.get("cacheCreationInputTokens") or usage.get("cacheWriteTokens") or 0)
                            cr = int(usage.get("cachedContentTokenCount") or usage.get("cached_content_token_count") or usage.get("cacheReadTokens") or 0)
                            rt = int(usage.get("reasoning_tokens") or usage.get("thinking_tokens") or usage.get("reasoning_output_tokens") or 0)
                            model_id = chat_model.get("model") or usage.get("model") or "unknown"
                            model_name = resolve_model(model_id)
                            
                            ts_str = chat_model.get("chatStartMetadata", {}).get("createdAt")
                            ts = None
                            if ts_str:
                                try:
                                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone()
                                except Exception:
                                    pass
                                    
                            if ts and CUTOFF <= ts <= LIMIT_UPPER:
                                day = ts.strftime("%Y-%m-%d")
                                by_day[day]["input_tokens"] += it
                                by_day[day]["output_tokens"] += ot
                                by_day[day]["cache_creation_input_tokens"] += cc
                                by_day[day]["cache_read_input_tokens"] += cr
                                by_day[day]["reasoning_tokens"] += rt
                                by_model[model_name]["input_tokens"] += it
                                by_model[model_name]["output_tokens"] += ot
                                by_model[model_name]["cache_creation_input_tokens"] += cc
                                by_model[model_name]["cache_read_input_tokens"] += cr
                                by_model[model_name]["reasoning_tokens"] += rt
                                totals["input_tokens"] += it
                                totals["output_tokens"] += ot
                                totals["cache_creation_input_tokens"] += cc
                                totals["cache_read_input_tokens"] += cr
                                totals["reasoning_tokens"] += rt
                                ALL_INVOCATIONS.append({
                                    "timestamp": ts,
                                    "source": "Antigravity (RPC)",
                                    "model": model_name,
                                    "input_tokens": it,
                                    "output_tokens": ot,
                                    "cache_creation": cc,
                                    "cache_read": cr,
                                    "reasoning": rt,
                                    "exact": True,
                                    "session_id": cascade_id,
                                    "source_file": "RPC"
                                })
                                rpc_scanned_invocations += 1
                                records += 1
        except Exception:
            pass

    # 2. File-based Fallback for closed/archived sessions
    files = []
    for brain_dir in ANTIGRAVITY_BRAIN_DIRS:
        if os.path.exists(brain_dir):
            for root, dirs, filenames in os.walk(brain_dir):
                for filename in filenames:
                    if filename == "transcript.jsonl":
                        files.append(os.path.join(root, filename))

    seen = set()
    fallback_transcripts_scanned = 0
    fallback_invocations_estimated = 0

    for f in files:
        parts = os.path.normpath(f).split(os.sep)
        conv_id = parts[-4] if len(parts) >= 4 else "unknown_conv"
        
        # Skip active sessions that were already queried via RPC
        if conv_id in active_cascade_ids:
            continue
            
        try:
            fh = open(f, encoding="utf-8", errors="ignore")
        except OSError:
            continue
            
        fallback_transcripts_scanned += 1
        with fh:
            accumulated_chars = 0
            last_model_call_accumulated_chars = 0
            current_model = "gemini-3-flash-preview"  # Default fallback (most Antigravity sessions)
            for idx, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # Check for model setting changes (only in user input or system generated blocks)
                content = rec.get("content") or ""
                # More specific regex to ensure we are in a settings change block
                match = re.search(r"<USER_SETTINGS_CHANGE>\s*The user changed setting `Model Selection` from .*? to (.*?)(?:\.\s|\.$|$)", content)
                if match:
                    model_candidate = match.group(1).strip()
                    name_lower = model_candidate.lower()
                    if "gemini 3.5 flash (high)" in name_lower:
                        current_model = "gemini-3.5-flash-high"
                    elif "gemini 3.5 flash (medium)" in name_lower:
                        current_model = "gemini-3.5-flash-medium"
                    elif "gemini 3.5 flash (low)" in name_lower:
                        current_model = "gemini-3.5-flash-low"
                    elif "gemini 3.5 pro" in name_lower:
                        current_model = "gemini-3.5-pro"
                    elif "gemini 3.5 flash" in name_lower:
                        current_model = "gemini-3.5-flash"
                    elif "gemini 3.1 pro (high)" in name_lower:
                        current_model = "gemini-3.1-pro-high"
                    elif "gemini 3.1 pro (low)" in name_lower:
                        current_model = "gemini-3.1-pro-low"
                    elif "claude sonnet 4.6" in name_lower:
                        current_model = "claude-sonnet-4-6-thinking"
                    elif "claude opus 4.6" in name_lower:
                        current_model = "claude-opus-4-6-thinking"
                    elif "gpt-5.6 sol" in name_lower or "gpt 5.6 sol" in name_lower:
                        current_model = "gpt-5.6-sol"
                    elif "gpt-5.6 terra" in name_lower or "gpt 5.6 terra" in name_lower:
                        current_model = "gpt-5.6-terra"
                    elif "gpt-5.6 luna" in name_lower or "gpt 5.6 luna" in name_lower:
                        current_model = "gpt-5.6-luna"
                    elif "gpt-oss 120b" in name_lower or "gpt-oss 128b" in name_lower:
                        current_model = "gpt-oss-120b-medium"
                    elif "gemini 3 flash" in name_lower:
                        current_model = "gemini-3-flash-preview"
                    elif "gemini 3" in name_lower:
                        current_model = "gemini-3-flash-preview"
                    else:
                        current_model = model_candidate

                ts = parse_ts(rec)
                if ts is None or ts < CUTOFF or ts > LIMIT_UPPER:
                    continue
                
                thinking = rec.get("thinking") or ""
                tool_calls = str(rec.get("tool_calls") or "")
                step_chars = len(content) + len(thinking) + len(tool_calls)
                
                source = rec.get("source")
                step_type = rec.get("type")
                
                # Deduplicate step calls
                step_uid = f"{conv_id}_{idx}"
                if step_uid in seen:
                    continue
                seen.add(step_uid)
                
                if source == "MODEL" and step_type == "PLANNER_RESPONSE":
                    # Estimate token usage
                    ot = max(1, step_chars // 4)
                    total_in = (accumulated_chars // 4) + 6000
                    
                    if last_model_call_accumulated_chars > 0:
                        cr = (last_model_call_accumulated_chars // 4) + 6000
                        it = max(0, total_in - cr)
                    else:
                        cr = 0
                        it = total_in
                        
                    last_model_call_accumulated_chars = accumulated_chars + step_chars
                    
                    day = ts.strftime("%Y-%m-%d")
                    model = f"{current_model} (estimated)"
                    
                    by_day[day]["input_tokens"] += it
                    by_day[day]["output_tokens"] += ot
                    by_day[day]["cache_read_input_tokens"] += cr
                    
                    by_model[model]["input_tokens"] += it
                    by_model[model]["output_tokens"] += ot
                    by_model[model]["cache_read_input_tokens"] += cr
                    
                    totals["input_tokens"] += it
                    totals["output_tokens"] += ot
                    totals["cache_read_input_tokens"] += cr
                    
                    ALL_INVOCATIONS.append({
                        "timestamp": ts,
                        "source": "Antigravity (Fallback)",
                        "model": model,
                        "input_tokens": it,
                        "output_tokens": ot,
                        "cache_creation": 0,
                        "cache_read": cr,
                        "reasoning": 0,
                        "exact": False,
                        "session_id": conv_id,
                        "source_file": os.path.basename(f)
                    })
                    fallback_invocations_estimated += 1
                    records += 1
                
                accumulated_chars += step_chars
                
    total_transcripts_scanned = len(active_cascade_ids) + fallback_transcripts_scanned
    return by_day, by_model, totals, total_transcripts_scanned, records, len(active_cascade_ids), rpc_scanned_invocations, fallback_invocations_estimated

# --- Parse Codex Logs ---
def parse_codex():
    by_day = defaultdict(lambda: defaultdict(int))
    by_model = defaultdict(lambda: defaultdict(int))
    totals = defaultdict(int)
    records = 0
    sessions_scanned = 0

    if not os.path.exists(CODEX_STATE):
        return by_day, by_model, totals, 0, 0

    try:
        conn = sqlite3.connect(CODEX_STATE)
        cursor = conn.cursor()
        
        # Query threads updated since cutoff
        cutoff_ts = int(CUTOFF.timestamp())
        cursor.execute("SELECT model, rollout_path FROM threads WHERE updated_at > ? AND rollout_path IS NOT NULL;", (cutoff_ts,))
        rows = cursor.fetchall()
        
        for model_name, rollout_path in rows:
            if not os.path.exists(rollout_path):
                continue
            
            sessions_scanned += 1
            try:
                with open(rollout_path, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try:
                            rec = json.loads(line)
                        except: continue
                        
                        if rec.get("type") == "event_msg":
                            payload = rec.get("payload") or {}
                            if payload.get("type") == "token_count":
                                info = payload.get("info") or {}
                                usage = info.get("last_token_usage") or {}
                                if not usage: continue
                                
                                it = int(usage.get("input_tokens") or 0)
                                ot = int(usage.get("output_tokens") or 0)
                                cr = int(usage.get("cached_input_tokens") or 0)
                                rt = int(usage.get("reasoning_output_tokens") or 0)
                                
                                ts_str = rec.get("timestamp")
                                ts = None
                                if ts_str:
                                    try:
                                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone()
                                    except: pass
                                
                                if ts and CUTOFF <= ts <= LIMIT_UPPER:
                                    day = ts.strftime("%Y-%m-%d")
                                    by_day[day]["input_tokens"] += it
                                    by_day[day]["output_tokens"] += ot
                                    by_day[day]["cache_read_input_tokens"] += cr
                                    by_day[day]["reasoning_tokens"] += rt
                                    
                                    by_model[model_name]["input_tokens"] += it
                                    by_model[model_name]["output_tokens"] += ot
                                    by_model[model_name]["cache_read_input_tokens"] += cr
                                    by_model[model_name]["reasoning_tokens"] += rt
                                    
                                    totals["input_tokens"] += it
                                    totals["output_tokens"] += ot
                                    totals["cache_read_input_tokens"] += cr
                                    totals["reasoning_tokens"] += rt
                                    ALL_INVOCATIONS.append({
                                        "timestamp": ts,
                                        "source": "OpenAI Codex",
                                        "model": model_name,
                                        "input_tokens": it,
                                        "output_tokens": ot,
                                        "cache_creation": 0,
                                        "cache_read": cr,
                                        "reasoning": rt,
                                        "exact": True,
                                        "session_id": rollout_path.split(os.sep)[-2] if os.sep in rollout_path else "rollout",
                                        "source_file": os.path.basename(rollout_path)
                                    })
                                    records += 1
            except:
                continue
        conn.close()
    except:
        pass
        
    return by_day, by_model, totals, sessions_scanned, records


def codex_native_total():
    """Codex's OWN lifetime counter: SUM(threads.tokens_used), windowed to the
    report range by thread updated_at. This is the figure behind Codex's
    `/usage` display -- a cross-check on our granular rollout parse. Thread-level
    granularity (coarser than per-event), so treat as an order-of-magnitude
    validator, not a row-exact match. Returns (thread_count, total_tokens)."""
    if not os.path.exists(CODEX_STATE):
        return 0, 0
    try:
        conn = sqlite3.connect(CODEX_STATE)
        lo = int(CUTOFF.timestamp())
        hi = int(LIMIT_UPPER.timestamp())
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(tokens_used), 0) FROM threads "
            "WHERE updated_at > ? AND updated_at <= ?",
            (lo, hi),
        ).fetchone()
        conn.close()
        return int(row[0] or 0), int(row[1] or 0)
    except Exception:
        return 0, 0


# --- Parse Gemini CLI chat logs (estimated; no exact token telemetry on disk) ---
# The Gemini CLI stores conversations under ~/.gemini/tmp/<project>/chats/ as
# either a single .json file with a messages[] array, or .jsonl one msg/line.
# These hold message TEXT only -- there is no usageMetadata/token telemetry
# recorded -- so tokens are ESTIMATED via the same chars/4 heuristic the
# Antigravity fallback uses. This is the ONLY source for pre-May 2026 Gemini
# activity (the Antigravity brain transcripts only go back to ~2026-05-19).
GEMINI_CLI_CHAT_GLOBS = [
    os.path.expanduser(os.path.join("~", ".gemini", "tmp", "*", "chats", "*.json")),
    os.path.expanduser(os.path.join("~", ".gemini", "tmp", "*", "chats", "*.jsonl")),
    os.path.expanduser(os.path.join("~", ".gemini", "tmp", "*", "chats", "*", "*.jsonl")),
]


def _gemini_text(content):
    """Flatten a CLI message 'content' (str | list[{text}] | dict) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict):
                out.append(str(p.get("text") or p.get("content") or ""))
            else:
                out.append(str(p))
        return "".join(out)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return str(content or "")


def parse_gemini_cli():
    by_day = defaultdict(lambda: defaultdict(int))
    by_model = defaultdict(lambda: defaultdict(int))
    totals = defaultdict(int)
    records = 0
    scanned_files = 0
    exact_cnt = 0
    est_cnt = 0

    files = []
    for g in GEMINI_CLI_CHAT_GLOBS:
        files.extend(glob.glob(g))
    files = sorted(set(files))

    cutoff_date = CUTOFF.date() - timedelta(days=1)
    limit_date = LIMIT_UPPER.date() + timedelta(days=1)
    local_tz = datetime.now().astimezone().tzinfo

    for f in files:
        basename = os.path.basename(f)
        match = re.search(r"session-(\d{4}-\d{2}-\d{2})", basename)
        if not match:
            continue
        try:
            file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue

        if not (cutoff_date <= file_date <= limit_date):
            continue

        messages_by_id = {}
        session_start_time = None

        try:
            if f.endswith(".json"):
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    data = json.load(fh)
                    session_start_time = parse_ts(data)
                    for m in data.get("messages", []):
                        if "id" in m:
                            messages_by_id[m["id"]] = m
            else:  # .jsonl, one message per line
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        if rec.get("startTime") and not session_start_time:
                            session_start_time = parse_ts(rec)
                        if "id" in rec:
                            messages_by_id[rec["id"]] = rec
        except Exception:
            continue

        if not messages_by_id:
            continue

        if not session_start_time:
            session_start_time = datetime.combine(file_date, datetime.min.time()).replace(tzinfo=local_tz)

        def get_msg_time(item):
            msg = item[1]
            ts = parse_ts(msg)
            return ts.timestamp() if ts else 0

        sorted_messages = [msg for msg_id, msg in sorted(messages_by_id.items(), key=get_msg_time)]

        session_chars = 0
        previous_session_chars = 0
        scanned_files += 1

        # Propagate model selection within session
        current_model = "gemini-3-flash-preview"
        for msg in sorted_messages:
            m_id = msg.get("model")
            if m_id and m_id != "unknown":
                current_model = m_id
                break

        for msg in sorted_messages:
            role = (msg.get("type") or msg.get("role") or "").lower()
            if role in ("user", "human"):
                text = _gemini_text(msg.get("content") if msg.get("content") is not None else msg.get("text"))
                session_chars += len(text)
            elif role in ("gemini", "model", "assistant"):
                ts = parse_ts(msg) or session_start_time
                text = _gemini_text(msg.get("content") if msg.get("content") is not None else msg.get("text"))
                step_chars = len(text)
                
                if not (CUTOFF <= ts <= LIMIT_UPPER):
                    session_chars += step_chars + len(str(msg.get("thoughts") or ""))
                    continue

                model_id = msg.get("model")
                if not model_id or model_id == "unknown":
                    model_name = resolve_model(current_model)
                else:
                    model_name = resolve_model(model_id)
                    current_model = model_id

                tokens = msg.get("tokens")
                has_exact = False
                if tokens and isinstance(tokens, dict):
                    it = int(tokens.get("input") or 0)
                    ot = int(tokens.get("output") or 0)
                    cr = int(tokens.get("cached") or 0)
                    rt = int(tokens.get("thoughts") or 0)
                    if it > 0 or ot > 0:
                        has_exact = True

                if has_exact:
                    exact = True
                    exact_cnt += 1
                else:
                    exact = False
                    est_cnt += 1
                    total_in = (session_chars // 4) + 6000
                    if previous_session_chars > 0:
                        cr = (previous_session_chars // 4) + 6000
                        it = max(0, total_in - cr)
                    else:
                        cr = 0
                        it = total_in
                    ot = max(1, step_chars // 4)
                    rt = len(str(msg.get("thoughts") or "")) // 4

                day = ts.strftime("%Y-%m-%d")
                model_label = model_name if exact else f"{model_name} (estimated)"

                by_day[day]["input_tokens"] += it
                by_day[day]["output_tokens"] += ot
                by_day[day]["cache_read_input_tokens"] += cr
                by_day[day]["reasoning_tokens"] += rt

                by_model[model_label]["input_tokens"] += it
                by_model[model_label]["output_tokens"] += ot
                by_model[model_label]["cache_read_input_tokens"] += cr
                by_model[model_label]["reasoning_tokens"] += rt

                totals["input_tokens"] += it
                totals["output_tokens"] += ot
                totals["cache_read_input_tokens"] += cr
                totals["reasoning_tokens"] += rt

                parts = os.path.normpath(f).split(os.sep)
                proj_name = parts[-3] if len(parts) >= 3 else "unknown_project"

                ALL_INVOCATIONS.append({
                    "timestamp": ts,
                    "source": "Gemini CLI",
                    "model": model_label,
                    "input_tokens": it,
                    "output_tokens": ot,
                    "cache_creation": 0,
                    "cache_read": cr,
                    "reasoning": rt,
                    "exact": exact,
                    "session_id": proj_name,
                    "source_file": basename
                })
                records += 1
                previous_session_chars = session_chars
                session_chars += step_chars + len(str(msg.get("thoughts") or ""))

    return by_day, by_model, totals, scanned_files, records, exact_cnt, est_cnt


# --- Parse Fleet Usage Ledger (forward, EXACT: local Ollama/Gemma, OpenRouter, HF) ---
# Append-only JSONL written by fleet_usage_proxy.py + instrumented fleet clients.
# Each line: {timestamp, provider, lane, model, input_tokens, output_tokens,
# cached_tokens, reasoning_tokens, source}. These are exact counts from each
# lane's own API response (ollama prompt_eval_count/eval_count; OpenRouter usage).
def parse_fleet_usage():
    by_day = defaultdict(lambda: defaultdict(int))
    by_model = defaultdict(lambda: defaultdict(int))
    totals = defaultdict(int)
    records = 0

    if not os.path.exists(FLEET_USAGE_LEDGER):
        return by_day, by_model, totals, records

    try:
        fh = open(FLEET_USAGE_LEDGER, encoding="utf-8", errors="ignore")
    except OSError:
        return by_day, by_model, totals, records

    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_ts(rec)
            if ts is None or ts < CUTOFF or ts > LIMIT_UPPER:
                continue

            provider = rec.get("provider") or "Fleet"
            model = rec.get("model") or "unknown"
            it = int(rec.get("input_tokens") or 0)
            ot = int(rec.get("output_tokens") or 0)
            cr = int(rec.get("cached_tokens") or 0)
            rt = int(rec.get("reasoning_tokens") or 0)

            day = ts.strftime("%Y-%m-%d")
            by_day[day]["input_tokens"] += it
            by_day[day]["output_tokens"] += ot
            by_day[day]["cache_read_input_tokens"] += cr
            by_day[day]["reasoning_tokens"] += rt

            by_model[model]["input_tokens"] += it
            by_model[model]["output_tokens"] += ot
            by_model[model]["cache_read_input_tokens"] += cr
            by_model[model]["reasoning_tokens"] += rt

            totals["input_tokens"] += it
            totals["output_tokens"] += ot
            totals["cache_read_input_tokens"] += cr
            totals["reasoning_tokens"] += rt

            ALL_INVOCATIONS.append({
                "timestamp": ts,
                "source": f"Fleet:{provider}",
                "model": model,
                "input_tokens": it,
                "output_tokens": ot,
                "cache_creation": 0,
                "cache_read": cr,
                "reasoning": rt,
                "exact": True,
                "session_id": rec.get("lane") or "fleet",
                "source_file": os.path.basename(FLEET_USAGE_LEDGER),
            })
            records += 1

    return by_day, by_model, totals, records


def compute_and_print_split(invocations, title):
    exact_tok = 0
    est_tok = 0
    exact_cost = 0.0
    est_cost = 0.0
    
    for inv in invocations:
        it = inv.get("input_tokens", 0)
        ot = inv.get("output_tokens", 0)
        cc = inv.get("cache_creation", 0)
        cr = inv.get("cache_read", 0)
        rt = inv.get("reasoning", 0)
        tot = it + ot + cc + cr + rt
        
        cost, _ = model_bill(inv["model"], {
            "input_tokens": it,
            "cache_creation_input_tokens": cc,
            "cache_read_input_tokens": cr,
            "output_tokens": ot,
            "reasoning_tokens": rt
        })
        
        if inv.get("exact", True):
            exact_tok += tot
            exact_cost += cost
        else:
            est_tok += tot
            est_cost += cost
            
    blended_tok = exact_tok + est_tok
    blended_cost = exact_cost + est_cost
    confidence = (exact_tok / blended_tok * 100) if blended_tok > 0 else 100.0
    
    print(f"--- Exact vs Estimated Split ({title}) ---")
    print(f"Tracked floor (observable):         {fmt(blended_tok)} (is_lower_bound: true)")
    print(f"Exact tokens:                       {fmt(exact_tok)}")
    print(f"Estimated tokens:                   {fmt(est_tok)}")
    print(f"Confidence (within telemetry):      {confidence:.1f}%")
    print(f"True lifetime usage:                >= {fmt(blended_tok)}")
    print()
    print(f"Exact shadow cost:                  ${exact_cost:,.2f}")
    print(f"Estimated shadow cost:              ${est_cost:,.2f}")
    print(f"Blended shadow cost:                ${blended_cost:,.2f}")
    print("----------------------------------------------------------------------\n")


def get_cache_label(share):
    if share >= 0.95:
        return "Excellent"
    elif share >= 0.85:
        return "Good"
    elif share >= 0.60:
        return "Warning"
    else:
        return "Cold context leak"


def print_cache_health_report(invocations):
    print("======================================================================")
    print("CACHE HEALTH SCORE REPORT")
    print("======================================================================")
    
    # 1. By Model
    print("--- By Model Cache Health ---")
    model_stats = defaultdict(lambda: {"input": 0, "total": 0, "cache_read": 0})
    for inv in invocations:
        m = inv["model"]
        total = inv["input_tokens"] + inv["output_tokens"] + inv["cache_creation"] + inv["cache_read"] + inv["reasoning"]
        model_stats[m]["input"] += inv["input_tokens"]
        model_stats[m]["total"] += total
        model_stats[m]["cache_read"] += inv["cache_read"]
        
    for m, stats in sorted(model_stats.items()):
        total = stats["total"]
        if total == 0:
            continue
        share = stats["cache_read"] / total
        label = get_cache_label(share)
        print(f"  Model: {m:<30} | Share: {share*100:5.1f}% | Label: {label:<20}")
        if stats["input"] > 250000 or share < 0.85:
            warn_reasons = []
            if stats["input"] > 250000:
                warn_reasons.append(f"input_tokens > 250,000 ({fmt(stats['input'])})")
            if share < 0.85:
                warn_reasons.append(f"cache_share < 85% ({share*100:.1f}%)")
            print(f"    [WARNING] {', '.join(warn_reasons)}")
            
    # 2. By Session (Top 10)
    print("\n--- Top 10 Sessions Cache Health ---")
    session_stats = defaultdict(lambda: {"input": 0, "total": 0, "cache_read": 0, "source": ""})
    for inv in invocations:
        s = inv["session_id"]
        total = inv["input_tokens"] + inv["output_tokens"] + inv["cache_creation"] + inv["cache_read"] + inv["reasoning"]
        session_stats[s]["input"] += inv["input_tokens"]
        session_stats[s]["total"] += total
        session_stats[s]["cache_read"] += inv["cache_read"]
        session_stats[s]["source"] = inv["source"]
        
    sorted_sessions = sorted(session_stats.items(), key=lambda x: -x[1]["total"])[:10]
    for s, stats in sorted_sessions:
        total = stats["total"]
        if total == 0:
            continue
        share = stats["cache_read"] / total
        label = get_cache_label(share)
        source = stats["source"]
        print(f"  Session: {s:<30} ({source:<15}) | Share: {share*100:5.1f}% | Label: {label:<20}")
        if stats["input"] > 250000 or share < 0.85:
            warn_reasons = []
            if stats["input"] > 250000:
                warn_reasons.append(f"input_tokens > 250,000 ({fmt(stats['input'])})")
            if share < 0.85:
                warn_reasons.append(f"cache_share < 85% ({share*100:.1f}%)")
            print(f"    [WARNING] {', '.join(warn_reasons)}")
    print()


def get_model_bucket(model_name):
    m_clean = model_name.replace(" (estimated)", "").strip().lower()
    
    if "opus" in m_clean:
        if "thinking" in m_clean:
            return "premium_reasoning"
        return "premium_cloud"
    elif "thinking" in m_clean:
        return "premium_reasoning"
    elif "pro" in m_clean:
        return "standard_cloud"
    elif "flash-high" in m_clean:
        return "standard_cloud"
    elif "flash-low" in m_clean:
        return "cheap_cloud"
    elif "flash" in m_clean or "haiku" in m_clean or "lite" in m_clean:
        return "cheap_cloud"
    elif "gpt-5.5" in m_clean or "gpt-5.4" in m_clean:
        if "mini" in m_clean:
            return "cheap_cloud"
        return "premium_cloud"
    elif "gpt-oss" in m_clean:
        return "cheap_or_local"
    elif "gemma" in m_clean or "local" in m_clean or "ollama" in m_clean:
        return "local_free"
    
    inp, out, cr, src = price_for(model_name)
    if inp >= 5.0:
        return "premium_cloud"
    elif inp >= 1.5:
        return "standard_cloud"
    elif inp > 0.0:
        return "cheap_cloud"
    else:
        return "local_free"


def print_model_class_buckets(invocations):
    buckets = {
        "Premium cloud usage": {"tokens": 0, "cost": 0.0},
        "Standard cloud usage": {"tokens": 0, "cost": 0.0},
        "Cheap cloud usage": {"tokens": 0, "cost": 0.0},
        "Local/free usage": {"tokens": 0, "cost": 0.0}
    }
    
    for inv in invocations:
        m = inv["model"]
        total = inv["input_tokens"] + inv["output_tokens"] + inv["cache_creation"] + inv["cache_read"] + inv["reasoning"]
        cost, _ = model_bill(m, {
            "input_tokens": inv["input_tokens"],
            "cache_creation_input_tokens": inv["cache_creation"],
            "cache_read_input_tokens": inv["cache_read"],
            "output_tokens": inv["output_tokens"],
            "reasoning_tokens": inv["reasoning"]
        })
        
        cls = get_model_bucket(m)
        if cls in ("premium_cloud", "premium_reasoning"):
            b = "Premium cloud usage"
        elif cls == "standard_cloud":
            b = "Standard cloud usage"
        elif cls in ("cheap_cloud", "cheap_or_local"):
            b = "Cheap cloud usage"
        else:
            b = "Local/free usage"
            
        buckets[b]["tokens"] += total
        buckets[b]["cost"] += cost
        
    print("======================================================================")
    print("MODEL CLASS BUCKETS REPORT")
    print("======================================================================")
    for name, data in buckets.items():
        print(f"{name:<25} total {fmt(data['tokens']):>16} tokens   ${data['cost']:,.2f}")
    print()


def print_top_hogs(invocations):
    sorted_inv = sorted(invocations, key=lambda x: -x.get("input_tokens", 0))[:20]
    
    print("======================================================================")
    print("Top 20 Token Hogs")
    print("======================================================================")
    for idx, inv in enumerate(sorted_inv, 1):
        ts = inv.get("timestamp")
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown"
        source = inv.get("source", "unknown")
        model = inv.get("model", "unknown")
        exact_str = "exact" if inv.get("exact", True) else "estimated"
        it = inv.get("input_tokens", 0)
        ot = inv.get("output_tokens", 0)
        cr = inv.get("cache_read", 0)
        tot = it + ot + inv.get("cache_creation", 0) + cr + inv.get("reasoning", 0)
        sess = inv.get("session_id", "unknown")
        
        print(f"{idx:2d}. [{ts_str}] {source} | {model} | {exact_str}")
        print(f"    input: {fmt(it):<12} | output: {fmt(ot):<12} | cache-read: {fmt(cr):<12} | total: {fmt(tot)}")
        print(f"    session/transcript path: {sess}")
    print()


def print_route_recommendations(invocations):
    print("======================================================================")
    print("Recommended routing changes:")
    print("======================================================================")
    print("- Move repeated vault scans to local/cheap agents.")
    print("- Keep Claude Opus reserved for final synthesis and arbitration.")
    print("- Compress Antigravity handoffs before replaying long sessions.")
    print("- Investigate 2026-06-16 Antigravity input spike.")
    print("======================================================================")


# --- Main Reporting ---
print(f"\n======================================================================")
if RANGE_START or RANGE_END:
    print(f"Token usage monitor — range {CUTOFF:%Y-%m-%d} -> {LIMIT_UPPER - timedelta(days=1):%Y-%m-%d}")
    print(f"window: {CUTOFF:%Y-%m-%d %H:%M} -> {LIMIT_UPPER:%Y-%m-%d %H:%M} {NOW:%Z}")
elif MONTH:
    print(f"Token usage monitor — Month: {MONTH}")
    print(f"window: {CUTOFF:%Y-%m-%d %H:%M} -> {LIMIT_UPPER:%Y-%m-%d %H:%M} {NOW:%Z}")
elif COMPARE_N:
    print(f"Token usage monitor — compare last {COMPARE_N}d vs prior {COMPARE_N}d (collecting {DAYS} days)")
    print(f"window: {CUTOFF:%Y-%m-%d %H:%M} -> {NOW:%Y-%m-%d %H:%M} {NOW:%Z}")
else:
    print(f"Token usage monitor — last {DAYS} day(s)")
    print(f"window: {CUTOFF:%Y-%m-%d %H:%M} -> {NOW:%Y-%m-%d %H:%M} {NOW:%Z}")
print(f"scope:  [EVIDENCE-SCOPED OBSERVABLE FLOOR | TRUE USAGE >= TRACKED TOTALS]")
print(f"======================================================================\n")

# 1. Claude Code report
c_day, c_model, c_totals, c_files, c_records = parse_claude()
print(f"--- Claude Code ---")
print(f"Transcripts scanned: {c_files}   Usage records: {c_records}\n")
hdr = f"{'Day':<12}{'input':>14}{'output':>14}{'cache-read':>16}{'reasoning':>14}"
print(hdr)
print("-" * len(hdr))
for day in sorted(c_day):
    i, o, cc, cr, rt = cols(c_day[day])
    print(f"{day:<12}{fmt(i):>14}{fmt(o):>14}{fmt(cr):>16}{fmt(rt):>14}")
print("-" * len(hdr))
ti, to, tcc, tcr, trt = cols(c_totals)
print(f"{'TOTAL':<12}{fmt(ti):>14}{fmt(to):>14}{fmt(tcr):>16}{fmt(trt):>14}\n")

# 2. Antigravity report
a_day, a_model, a_totals, a_files, a_records, active_cnt, rpc_cnt, est_cnt = parse_antigravity()
print(f"--- Google Antigravity (Hybrid RPC & Estimation) [! partial - Antigravity retention starts ~2026-05-19; pre-May encrypted] ---")
print(f"Sessions scanned: {a_files} ({active_cnt} active via RPC + {a_files - active_cnt} fallback from disk)")
print(f"Invocations tracked: {a_records} ({rpc_cnt} exact via RPC + {est_cnt} estimated fallback)\n")
hdr_ag = f"{'Day':<12}{'input':>14}{'output':>14}{'cache-read':>16}{'reasoning':>14}"
print(hdr_ag)
print("-" * len(hdr_ag))
for day in sorted(a_day):
    i, o, cc, cr, rt = cols(a_day[day])
    print(f"{day:<12}{fmt(i):>14}{fmt(o):>14}{fmt(cr):>16}{fmt(rt):>14}")
print("-" * len(hdr_ag))
tai, tao, tacc, tacr, tart = cols(a_totals)
print(f"{'TOTAL':<12}{fmt(tai):>14}{fmt(tao):>14}{fmt(tacr):>16}{fmt(tart):>14}\n")
compute_and_print_split([inv for inv in ALL_INVOCATIONS if inv["source"].startswith("Antigravity")], "Antigravity")

# 3. Codex report
cx_day, cx_model, cx_totals, cx_files, cx_records = parse_codex()
print(f"--- OpenAI Codex (Granular Rollout Parsing) ---")
print(f"Sessions scanned: {cx_files}   Usage events: {cx_records}\n")
hdr_cx = f"{'Day':<12}{'input':>14}{'output':>14}{'cache-read':>16}{'reasoning':>14}"
print(hdr_cx)
print("-" * len(hdr_cx))
for day in sorted(cx_day):
    i, o, cc, cr, rt = cols(cx_day[day])
    print(f"{day:<12}{fmt(i):>14}{fmt(o):>14}{fmt(cr):>16}{fmt(rt):>14}")
print("-" * len(hdr_cx))
txi, txo, txcc, txcr, txrt = cols(cx_totals)
print(f"{'TOTAL':<12}{fmt(txi):>14}{fmt(txo):>14}{fmt(txcr):>16}{fmt(txrt):>14}")
# Cross-check our rollout parse against Codex's OWN native counter. Compare like
# with like: Codex's tokens_used excludes cache-reads, so validate against our
# non-cache billable tokens (input w/CC + output + reasoning), and note cache
# separately rather than inflating the delta.
cx_nthreads, cx_native = codex_native_total()
cx_billable = txi + txo + txrt
if cx_native:
    delta = (cx_billable - cx_native) / cx_native * 100
    print(f"  cross-check: Codex native (threads.tokens_used) {fmt(cx_native)} across {cx_nthreads} threads "
          f"| our billable (in+out+reasoning, no cache) {fmt(cx_billable)} | delta {delta:+.0f}% "
          f"(+{fmt(txcr)} cache-read tracked separately)")
print()

# 3b. Gemini CLI report (Hybrid Exact & Estimation; pre-May fills here)
gc_day, gc_model, gc_totals, gc_files, gc_records, gc_exact, gc_est = parse_gemini_cli()
print(f"--- Gemini CLI (Hybrid Exact & Estimation) ---")
print(f"Sessions scanned: {gc_files}   Invocations tracked: {gc_records} ({gc_exact} exact + {gc_est} estimated)\n")
hdr_gc = f"{'Day':<12}{'input':>14}{'output':>14}{'cache-read':>16}{'reasoning':>14}"
print(hdr_gc)
print("-" * len(hdr_gc))
for day in sorted(gc_day):
    i, o, cc, cr, rt = cols(gc_day[day])
    print(f"{day:<12}{fmt(i):>14}{fmt(o):>14}{fmt(cr):>16}{fmt(rt):>14}")
print("-" * len(hdr_gc))
tgi, tgo, tgcc, tgcr, tgrt = cols(gc_totals)
print(f"{'TOTAL':<12}{fmt(tgi):>14}{fmt(tgo):>14}{fmt(tgcr):>16}{fmt(tgrt):>14}\n")
compute_and_print_split([inv for inv in ALL_INVOCATIONS if inv["source"] == "Gemini CLI"], "Gemini CLI")

# 3d. Fleet Usage Ledger (forward, exact: local Ollama/Gemma, OpenRouter, HF)
fl_day, fl_model, fl_totals, fl_records = parse_fleet_usage()
print(f"--- Fleet Usage Ledger (Local Ollama/Gemma + OpenRouter + HF) ---")
print(f"Invocations tracked: {fl_records} (exact, from each lane's API response)\n")
hdr_fl = f"{'Day':<12}{'input':>14}{'output':>14}{'cache-read':>16}{'reasoning':>14}"
print(hdr_fl)
print("-" * len(hdr_fl))
for day in sorted(fl_day):
    i, o, cc, cr, rt = cols(fl_day[day])
    print(f"{day:<12}{fmt(i):>14}{fmt(o):>14}{fmt(cr):>16}{fmt(rt):>14}")
print("-" * len(hdr_fl))
tfi, tfo, tfcc, tfcr, tfrt = cols(fl_totals)
print(f"{'TOTAL':<12}{fmt(tfi):>14}{fmt(tfo):>14}{fmt(tfcr):>16}{fmt(tfrt):>14}\n")

# 4. Model Breakdown
all_models = defaultdict(lambda: defaultdict(int))
for m, d in c_model.items():
    for k, v in d.items():
        all_models[m][k] += v
for m, d in a_model.items():
    for k, v in d.items():
        all_models[m][k] += v
for m, d in cx_model.items():
    for k, v in d.items():
        all_models[m][k] += v
for m, d in gc_model.items():
    for k, v in d.items():
        all_models[m][k] += v
for m, d in fl_model.items():
    for k, v in d.items():
        all_models[m][k] += v

# Robustness: normalize any None/empty model name across every record so the
# cross-source aggregates (model breakdown, blended split, cache health, top
# hogs, route recs) can sort/price model keys without crashing on None.
for _inv in ALL_INVOCATIONS:
    if not _inv.get("model"):
        _inv["model"] = "(unknown)"

# Same guard for the pre-aggregated model breakdown dict.
if None in all_models:
    _none_d = all_models.pop(None)
    for _k, _v in _none_d.items():
        all_models["(unknown)"][_k] += _v

if all_models:
    print("--- By Model Breakdown ---")
    mw = max(len(str(m)) for m in all_models)
    grand_total_tokens = 0
    grand_total_cost = 0.0
    grand_total_cold = 0.0
    total_cache_reads = 0
    used_estimate = False
    for model in sorted(all_models, key=lambda m: -sum(all_models[m].values())):
        i, o, cc, cr, rt = cols(all_models[model])
        total = i + o + cc + cr + rt
        grand_total_tokens += total
        total_cache_reads += cr
        cost, src = model_bill(model, all_models[model])
        grand_total_cost += cost
        # Cold-boot: every input-side token (input + cache-creation + cache-read)
        # charged at full fresh-input rate; reasoning billed as output.
        inp_rate, out_rate, _crr, _s = price_for(model)
        grand_total_cold += ((i + cc + cr) * inp_rate + (o + rt) * out_rate) / 1_000_000
        if src == EST:
            used_estimate = True
        tag = "~" if src == EST else " "
        print(f"  {model:<{mw}}  total {fmt(total):>16}   "
              f"(in {fmt(i + cc)}, out {fmt(o)}, cache-read {fmt(cr)}, reasoning {fmt(rt)})  {tag}${cost:,.2f}")

    # --- Honest API-equivalent shadow bill --------------------------------------
    # What these tokens WOULD have cost at first-party API list prices, with
    # cache-reads priced as cache-reads (not as fresh input) and reasoning as
    # output. This is a hypothetical reference point, NOT money saved: on flat-
    # rate subscriptions this volume was never going to be bought at API rates,
    # so there is no "arbitrage" sum being pocketed. Naive (all-tokens x flat-
    # rate) math overstates this several-fold because cache-reads dominate the
    # token count but bill at ~10% of input.
    #
    # Set AI_MONTHLY_SUBSCRIPTION_USD to print your real spend alongside it.
    sub_cost = float(os.environ.get("AI_MONTHLY_SUBSCRIPTION_USD", "0") or 0)
    cache_share = (total_cache_reads / grand_total_tokens * 100) if grand_total_tokens else 0

    print(f"\n======================================================================")
    print(f"API-EQUIVALENT SHADOW BILL  (hypothetical reference, NOT realized savings)")
    print(f"======================================================================")
    print(f"Realistic cost (cache-reads billed as cache): ${grand_total_cost:,.2f}")
    print(f"COLD-BOOT cost (no cache, every token fresh): ${grand_total_cold:,.2f}")
    print(f"What caching saved vs cold-boot:              ${grand_total_cold - grand_total_cost:,.2f}")
    if used_estimate:
        print(f"  ~ = model priced from an estimate, not a first-party doc")
    print(f"Cache-reads as share of all tokens:         {cache_share:.1f}%  "
          f"(billed ~10% of input - why naive math inflates)")
    if sub_cost > 0:
        print(f"Your actual subscription spend:             ${sub_cost:,.2f}")
    print(f"----------------------------------------------------------------------")
    print(f"This is the price you DIDN'T pay by using flat-rate plans, not a sum")
    print(f"you earned. Treat it as a usage gauge, not a savings account.")
    print(f"======================================================================\n")
    
    compute_and_print_split(ALL_INVOCATIONS, "Blended Report")
    print_cache_health_report(ALL_INVOCATIONS)
    print_model_class_buckets(ALL_INVOCATIONS)
    print_top_hogs(ALL_INVOCATIONS)
    print_route_recommendations(ALL_INVOCATIONS)
    
    if BY_PROVIDER:
        # Group invocations by provider/company
        provider_stats = defaultdict(lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation": 0,
            "cache_read": 0,
            "reasoning": 0,
            "cost": 0.0,
            "count": 0
        })
        for inv in ALL_INVOCATIONS:
            source = inv["source"]
            if "Claude Code" in source:
                company = "Anthropic (Claude Code)"
            elif source.startswith("Fleet:"):
                prov = source.split(":", 1)[1]
                if "Ollama" in prov:
                    company = "Local (Ollama/Gemma)"
                elif "OpenRouter" in prov:
                    company = "OpenRouter (free)"
                elif "HF" in prov or "HuggingFace" in prov:
                    company = "HuggingFace (free)"
                else:
                    company = f"Fleet ({prov})"
            elif "Gemini CLI" in source:
                company = "Google (Gemini CLI)"
            elif "Antigravity" in source:
                company = "Google (Antigravity)"
            elif "Codex" in source or "OpenAI" in source:
                company = "OpenAI (Codex)"
            else:
                company = "Unknown"
                
            it = inv.get("input_tokens", 0)
            ot = inv.get("output_tokens", 0)
            cc = inv.get("cache_creation", 0)
            cr = inv.get("cache_read", 0)
            rt = inv.get("reasoning", 0)
            
            d = {
                "input_tokens": it,
                "cache_creation_input_tokens": cc,
                "cache_read_input_tokens": cr,
                "output_tokens": ot,
                "reasoning_tokens": rt
            }
            cost, _ = model_bill(inv["model"], d)
            
            c_stats = provider_stats[company]
            c_stats["input_tokens"] += it
            c_stats["output_tokens"] += ot
            c_stats["cache_creation"] += cc
            c_stats["cache_read"] += cr
            c_stats["reasoning"] += rt
            c_stats["cost"] += cost
            c_stats["count"] += 1
            
        print("======================================================================")
        print("BY-PROVIDER SUMMARY REPORT")
        print("======================================================================")
        hdr_prov = f"{'Provider/Company':<30}{'Invocations':>12}{'Input (w/CC)':>16}{'Output':>14}{'Cache Read':>16}{'Reasoning':>14}{'Cost':>12}"
        print(hdr_prov)
        print("-" * len(hdr_prov))
        
        total_inv = 0
        total_in = 0
        total_out = 0
        total_cr = 0
        total_rt = 0
        total_cost = 0.0
        
        _ordered = ["Anthropic (Claude Code)", "Google (Antigravity)", "Google (Gemini CLI)",
                    "OpenAI (Codex)", "Local (Ollama/Gemma)", "OpenRouter (free)", "HuggingFace (free)"]
        _provider_order = _ordered + [c for c in provider_stats if c not in _ordered]
        for company in _provider_order:
            if company not in provider_stats:
                continue
            c_stats = provider_stats[company]
            inv_cnt = c_stats["count"]
            it = c_stats["input_tokens"] + c_stats["cache_creation"]
            ot = c_stats["output_tokens"]
            cr = c_stats["cache_read"]
            rt = c_stats["reasoning"]
            cost = c_stats["cost"]
            
            total_inv += inv_cnt
            total_in += it
            total_out += ot
            total_cr += cr
            total_rt += rt
            total_cost += cost
            
            print(f"{company:<30}{fmt(inv_cnt):>12}{fmt(it):>16}{fmt(ot):>14}{fmt(cr):>16}{fmt(rt):>14}  ${cost:10.2f}")
            
        print("-" * len(hdr_prov))
        print(f"{'TOTAL':<30}{fmt(total_inv):>12}{fmt(total_in):>16}{fmt(total_out):>14}{fmt(total_cr):>16}{fmt(total_rt):>14}  ${total_cost:10.2f}")
        print("======================================================================\n")

print()


# =============================================================================
# C4AI Token Counter Integration (vendored minimal core)
# Source: https://github.com/C4AI/token-counter
# Attribution: C4AI token-counter (MIT). Folded here so token_tracker.py
# stays a single-file import with no external package required for basic use.
# The C4AI token-counter counts tokenizer tokens in local files or HuggingFace
# datasets, producing distribution stats (total, mean, median, IQR, P95, P99,
# stddev) and optional Markdown/JSON reports. It uses HuggingFace tokenizers
# (default: Qwen/Qwen3-1.7B-Base) and supports Parquet/JSONL inputs.
# =============================================================================

import bisect
import math
import time as _time
from dataclasses import dataclass, field as _field
from typing import Any, Dict, Iterable, Iterator, List, Optional


# ---------------------------------------------------------------------------
# TokenCountStats â€” ported minimal subset from token_counter.reporting
# ---------------------------------------------------------------------------

@dataclass
class TokenCountStats:
    """Accumulates per-document token counts and derives distribution stats.

    Mirrors the public contract of C4AI token_counter.reporting.TokenCountStats
    so that callers can swap in the full library when available.
    """
    total_tokens: int = 0
    documents_processed: int = 0
    rows_seen: int = 0
    null_field_rows: int = 0
    empty_text_rows: int = 0
    non_string_rows_coerced: int = 0
    # Distribution tracking (sorted list for percentile computation)
    _lengths: List[int] = _field(default_factory=list, repr=False)
    started_at_epoch: Optional[float] = None
    completed_at_epoch: Optional[float] = None
    wall_time: float = 0.0

    def observe_document(self, *, text: str, token_length: int) -> None:
        self.total_tokens += token_length
        self.documents_processed += 1
        bisect.insort(self._lengths, token_length)

    @property
    def mean_tokens(self) -> Optional[float]:
        if not self._lengths:
            return None
        return self.total_tokens / len(self._lengths)

    def _percentile(self, p: float) -> Optional[float]:
        n = len(self._lengths)
        if n == 0:
            return None
        idx = p * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        frac = idx - lo
        return self._lengths[lo] + frac * (self._lengths[hi] - self._lengths[lo])

    @property
    def median_tokens(self) -> Optional[float]:
        return self._percentile(0.50)

    @property
    def p95_tokens(self) -> Optional[float]:
        return self._percentile(0.95)

    @property
    def p99_tokens(self) -> Optional[float]:
        return self._percentile(0.99)

    @property
    def stddev_tokens(self) -> Optional[float]:
        n = len(self._lengths)
        if n < 2:
            return None
        mu = self.total_tokens / n
        return math.sqrt(sum((x - mu) ** 2 for x in self._lengths) / (n - 1))

    @property
    def iqr_tokens(self) -> Optional[float]:
        p25 = self._percentile(0.25)
        p75 = self._percentile(0.75)
        if p25 is None or p75 is None:
            return None
        return p75 - p25

    def distribution_summary(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "documents_processed": self.documents_processed,
            "mean": self.mean_tokens,
            "median": self.median_tokens,
            "iqr": self.iqr_tokens,
            "p95": self.p95_tokens,
            "p99": self.p99_tokens,
            "stddev": self.stddev_tokens,
        }

    def to_checkpoint_state(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "documents_processed": self.documents_processed,
            "rows_seen": self.rows_seen,
            "null_field_rows": self.null_field_rows,
            "empty_text_rows": self.empty_text_rows,
            "non_string_rows_coerced": self.non_string_rows_coerced,
            "lengths": self._lengths,
            "started_at_epoch": self.started_at_epoch,
            "completed_at_epoch": self.completed_at_epoch,
            "wall_time": self.wall_time,
        }

    @classmethod
    def from_checkpoint_state(cls, state: Dict[str, Any]) -> "TokenCountStats":
        obj = cls()
        obj.total_tokens = state.get("total_tokens", 0)
        obj.documents_processed = state.get("documents_processed", 0)
        obj.rows_seen = state.get("rows_seen", 0)
        obj.null_field_rows = state.get("null_field_rows", 0)
        obj.empty_text_rows = state.get("empty_text_rows", 0)
        obj.non_string_rows_coerced = state.get("non_string_rows_coerced", 0)
        obj._lengths = list(state.get("lengths", []))
        obj.started_at_epoch = state.get("started_at_epoch")
        obj.completed_at_epoch = state.get("completed_at_epoch")
        obj.wall_time = state.get("wall_time", 0.0)
        return obj


# ---------------------------------------------------------------------------
# Core counting helpers â€” ported from token_counter.cli
# ---------------------------------------------------------------------------

DEFAULT_TC_MODEL = "Qwen/Qwen3-1.7B-Base"
DEFAULT_TC_BATCH_SIZE = 256


def _tc_token_lengths(tokenizer: Any, texts: List[str]) -> List[int]:
    """Return per-text token lengths using the given HuggingFace tokenizer."""
    if not texts:
        return []
    try:
        encoded = tokenizer(texts, add_special_tokens=False, return_attention_mask=False)
        input_ids = encoded["input_ids"] if isinstance(encoded, dict) else encoded.input_ids
        return [len(ids) for ids in input_ids]
    except Exception:
        return [len(tokenizer.encode(t, add_special_tokens=False)) for t in texts]


def _tc_load_tokenizer(model: str, *, trust_remote_code: bool = False) -> Any:
    """Load a HuggingFace AutoTokenizer. Raises ImportError if transformers absent."""
    from transformers import AutoTokenizer  # type: ignore
    return AutoTokenizer.from_pretrained(model, trust_remote_code=trust_remote_code)


def count_tokens_in_texts(
    texts: Iterable[str],
    *,
    model: str = DEFAULT_TC_MODEL,
    batch_size: int = DEFAULT_TC_BATCH_SIZE,
    trust_remote_code: bool = False,
    tokenizer: Any = None,
) -> TokenCountStats:
    """Count tokenizer tokens across an iterable of strings.

    This is the primary programmatic entry-point folded in from C4AI
    token-counter. It accepts any iterable of strings â€” files, dataset rows,
    in-memory lists â€” and returns a TokenCountStats with full distribution stats.

    Parameters
    ----------
    texts:
        Iterable of raw text strings to tokenize.
    model:
        HuggingFace tokenizer model. Default: Qwen/Qwen3-1.7B-Base.
    batch_size:
        Documents per tokenizer batch for throughput.
    trust_remote_code:
        Pass to AutoTokenizer.from_pretrained.
    tokenizer:
        Pre-loaded tokenizer object (skips loading if provided).

    Returns
    -------
    TokenCountStats
        Distribution stats including total_tokens, mean, median, p95, p99.
    """
    if tokenizer is None:
        tokenizer = _tc_load_tokenizer(model, trust_remote_code=trust_remote_code)

    stats = TokenCountStats()
    stats.started_at_epoch = _time.time()
    batch: List[str] = []

    def _flush() -> None:
        if not batch:
            return
        lengths = _tc_token_lengths(tokenizer, batch)
        for text, length in zip(batch, lengths):
            stats.observe_document(text=text, token_length=length)
        batch.clear()

    for raw in texts:
        stats.rows_seen += 1
        if raw is None:
            stats.null_field_rows += 1
            continue
        if not isinstance(raw, str):
            stats.non_string_rows_coerced += 1
            raw = str(raw)
        if raw == "":
            stats.empty_text_rows += 1
        batch.append(raw)
        if len(batch) >= batch_size:
            _flush()

    _flush()
    stats.completed_at_epoch = _time.time()
    stats.wall_time = max(0.0, stats.completed_at_epoch - stats.started_at_epoch)
    return stats


def count_tokens_in_file(
    path: str,
    *,
    field: str = "text",
    file_fmt: str = "jsonl",
    model: str = DEFAULT_TC_MODEL,
    batch_size: int = DEFAULT_TC_BATCH_SIZE,
    max_docs: Optional[int] = None,
    trust_remote_code: bool = False,
    tokenizer: Any = None,
) -> TokenCountStats:
    """Count tokens in a local JSONL, plain-text, or Parquet file.

    For JSONL: each line is parsed as JSON and the ``field`` key is extracted.
    For plain-text (file_fmt='text'): each line is treated as one document.
    For Parquet (file_fmt='parquet'): requires pandas + pyarrow.

    Parameters
    ----------
    path:
        Absolute or relative path to the input file.
    field:
        Key to extract from each JSON object (JSONL/Parquet only).
    file_fmt:
        'jsonl', 'text', or 'parquet'.
    model:
        HuggingFace tokenizer model.
    batch_size:
        Documents per tokenizer batch.
    max_docs:
        Stop after processing this many documents.
    trust_remote_code:
        Passed to the tokenizer loader.
    tokenizer:
        Pre-loaded tokenizer to reuse across calls.

    Returns
    -------
    TokenCountStats
        Populated distribution stats object.
    """
    import pathlib as _pathlib
    p = _pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    def _iter() -> Iterator[str]:
        count = 0
        if file_fmt == "jsonl":
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        val = row.get(field, "")
                    except json.JSONDecodeError:
                        val = line
                    yield val if isinstance(val, str) else str(val)
                    count += 1
                    if max_docs is not None and count >= max_docs:
                        return
        elif file_fmt == "text":
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    yield line.rstrip("\n")
                    count += 1
                    if max_docs is not None and count >= max_docs:
                        return
        elif file_fmt == "parquet":
            try:
                import pandas as pd  # type: ignore
            except ImportError:
                raise ImportError("pandas required for parquet support: pip install pandas pyarrow")
            df = pd.read_parquet(path, columns=[field])
            for val in df[field]:
                yield val if isinstance(val, str) else str(val)
                count += 1
                if max_docs is not None and count >= max_docs:
                    return
        else:
            raise ValueError(f"Unsupported format: {file_fmt}. Use 'jsonl', 'text', or 'parquet'.")

    return count_tokens_in_texts(
        _iter(),
        model=model,
        batch_size=batch_size,
        trust_remote_code=trust_remote_code,
        tokenizer=tokenizer,
    )


def print_token_distribution_report(
    stats: TokenCountStats, *, title: str = "Token Distribution"
) -> None:
    """Print a compact distribution summary to stdout.

    Mirrors the summary block from C4AI token-counter Markdown reports.
    """
    d = stats.distribution_summary()
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)
    print(f"  Total tokens      : {d['total_tokens']:,}")
    print(f"  Documents         : {d['documents_processed']:,}")
    if d["mean"] is not None:
        print(f"  Mean              : {d['mean']:,.1f}")
    if d["median"] is not None:
        print(f"  Median            : {d['median']:,.1f}")
    if d["iqr"] is not None:
        print(f"  IQR               : {d['iqr']:,.1f}")
    if d["p95"] is not None:
        print(f"  P95               : {d['p95']:,.1f}")
    if d["p99"] is not None:
        print(f"  P99               : {d['p99']:,.1f}")
    if d["stddev"] is not None:
        print(f"  Std Dev           : {d['stddev']:,.1f}")
    print(sep)


# ---------------------------------------------------------------------------
# __main__ demo â€” runs when invoked as: python token_tracker.py --demo-tc <path>
# Existing default invocation (DAYS arg) is unaffected.
# ---------------------------------------------------------------------------

if __name__ == "__main__" and "--demo-tc" in sys.argv:
    import argparse as _argparse

    _p = _argparse.ArgumentParser(
        description="C4AI token-counter demo (vendored into token_tracker.py)"
    )
    _p.add_argument("--demo-tc", metavar="PATH", help="File to count tokens in")
    _p.add_argument("--field", default="text", help="JSON field to extract (JSONL/Parquet)")
    _p.add_argument(
        "--format", default="jsonl", choices=["jsonl", "text", "parquet"],
        dest="file_fmt", help="Input format"
    )
    _p.add_argument("--model", default=DEFAULT_TC_MODEL, help="HuggingFace tokenizer model")
    _p.add_argument("--max-docs", type=int, default=None, help="Max documents to process")
    _args = _p.parse_args()

    print(f"[token-counter demo] Loading tokenizer: {_args.model}")
    print(f"[token-counter demo] Input: {_args.demo_tc}  format={_args.file_fmt}  field={_args.field}")
    _tc_stats = count_tokens_in_file(
        _args.demo_tc,
        field=_args.field,
        file_fmt=_args.file_fmt,
        model=_args.model,
        max_docs=_args.max_docs,
    )
    print_token_distribution_report(_tc_stats, title=f"Token Distribution -- {_args.demo_tc}")
    print(f"\n[token-counter demo] Wall time: {_tc_stats.wall_time:.2f}s")


# ---------------------------------------------------------------------------
# --compare N : last N days vs the prior N days, per company (additive summary).
# Reads the already-collected ALL_INVOCATIONS; the window was widened to >= 2N days
# at parse time so both periods are present. Runs after the normal report.
# ---------------------------------------------------------------------------
if __name__ == "__main__" and COMPARE_N:
    _n = COMPARE_N
    _mid = NOW - timedelta(days=_n)
    _lo = NOW - timedelta(days=_n * 2)

    def _company(src):
        return (src or "unknown").split(" (")[0].split(":")[0].strip()

    def _toks(inv):
        return (inv.get("input_tokens", 0) + inv.get("output_tokens", 0)
                + inv.get("cache_creation", 0) + inv.get("cache_read", 0)
                + inv.get("reasoning", 0))

    _cur = defaultdict(int)
    _prev = defaultdict(int)
    for _inv in ALL_INVOCATIONS:
        _ts = _inv.get("timestamp")
        if _ts is None:
            continue
        if _ts >= _mid:
            _cur[_company(_inv.get("source"))] += _toks(_inv)
        elif _ts >= _lo:
            _prev[_company(_inv.get("source"))] += _toks(_inv)

    _companies = sorted(set(_cur) | set(_prev), key=lambda c: -(_cur[c] + _prev[c]))
    _sep = "-" * 70
    print()
    print("=" * 70)
    print(f"Period comparison — last {_n}d vs prior {_n}d (total tokens, by company)")
    print(f"  last {_n}d : {_mid:%Y-%m-%d} -> {NOW:%Y-%m-%d}")
    print(f"  prior {_n}d: {_lo:%Y-%m-%d} -> {_mid:%Y-%m-%d}")
    print("=" * 70)
    print(f"{'Company':<22}{'prior ' + str(_n) + 'd':>16}{'last ' + str(_n) + 'd':>16}{'delta':>12}")
    print(_sep)
    _tc = _tp = 0
    for _c in _companies:
        _p = _prev[_c]
        _cu = _cur[_c]
        _tc += _cu
        _tp += _p
        _d = f"{(_cu - _p) / _p * 100:+.0f}%" if _p else ("new" if _cu else "-")
        print(f"{_c:<22}{_p:>16,}{_cu:>16,}{_d:>12}")
    print(_sep)
    _dt = f"{(_tc - _tp) / _tp * 100:+.0f}%" if _tp else "-"
    print(f"{'TOTAL':<22}{_tp:>16,}{_tc:>16,}{_dt:>12}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# --lanes : full analytics dashboard. Period comparisons (24h / week / month /
# quarter / half / year, each "to-date" vs the same elapsed offset into the
# prior period) plus records (highest day/week/month + longest & current
# streak). One pass builds a per-day series; every lane is date math on it.
# Drafted on gemma4:31b-cloud (free lane); boundary math reviewed by Coach.
# ---------------------------------------------------------------------------
def print_analytics_dashboard(invocations, now):
    def humanize(n):
        n = int(n)
        if n == 0:
            return "0"
        for unit, val in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
            if abs(n) >= val:
                return f"{n / val:.2f}{unit}"
        return str(n)

    def delta(this, last):
        if last == 0:
            return "new" if this > 0 else "-"
        return f"{(this - last) / last:+.0%}"

    today = now.date()
    day_sums = defaultdict(int)
    records = []
    for inv in invocations:
        ts = inv.get("timestamp")
        if ts is None:
            continue
        toks = sum(inv.get(k, 0) for k in
                   ("input_tokens", "output_tokens", "cache_creation", "cache_read", "reasoning"))
        day_sums[ts.date()] += toks
        records.append((ts, toks))

    if not records:
        print("no data")
        return None

    def dsum(lo, hi):  # inclusive day-range sum over the per-day series
        total = 0
        cur = lo
        while cur <= hi:
            total += day_sums.get(cur, 0)
            cur += _dtm.timedelta(days=1)
        return total

    lanes = []
    # 24h rolling (timestamp precision)
    lanes.append(("this 24h / prior 24h",
                  sum(t for ts, t in records if now - _dtm.timedelta(hours=24) <= ts < now),
                  sum(t for ts, t in records if now - _dtm.timedelta(hours=48) <= ts < now - _dtm.timedelta(hours=24))))
    # week-to-date (Mon start)
    ws = today - _dtm.timedelta(days=today.weekday())
    off = (today - ws).days
    lanes.append(("this week / last week", dsum(ws, today),
                  dsum(ws - _dtm.timedelta(days=7), ws - _dtm.timedelta(days=7 - off))))
    # month-to-date
    ms = today.replace(day=1)
    off = (today - ms).days
    lme = ms - _dtm.timedelta(days=1)
    lms = lme.replace(day=1)
    lanes.append(("this month / last month", dsum(ms, today),
                  dsum(lms, min(lms + _dtm.timedelta(days=off), lme))))
    # quarter-to-date (3mo)
    qm = ((today.month - 1) // 3) * 3 + 1
    qs = _dtm.date(today.year, qm, 1)
    off = (today - qs).days
    pqs = _dtm.date(today.year if qm > 1 else today.year - 1, qm - 3 if qm > 1 else 10, 1)
    lanes.append(("this quarter / last (3mo)", dsum(qs, today),
                  dsum(pqs, min(pqs + _dtm.timedelta(days=off), qs - _dtm.timedelta(days=1)))))
    # half-to-date (6mo)
    hm = 1 if today.month <= 6 else 7
    hs = _dtm.date(today.year, hm, 1)
    off = (today - hs).days
    phs = _dtm.date(today.year if hm > 1 else today.year - 1, hm - 6 if hm > 1 else 7, 1)
    lanes.append(("this half / last (6mo)", dsum(hs, today),
                  dsum(phs, min(phs + _dtm.timedelta(days=off), hs - _dtm.timedelta(days=1)))))
    # year-to-date
    ys = _dtm.date(today.year, 1, 1)
    off = (today - ys).days
    lys = _dtm.date(today.year - 1, 1, 1)
    lanes.append(("this year / last year", dsum(ys, today),
                  dsum(lys, min(lys + _dtm.timedelta(days=off), _dtm.date(today.year - 1, 12, 31)))))

    print(f"{'Lane':<28}{'this':>14}{'prior':>14}{'delta':>9}")
    print("-" * 65)
    for name, t, l in lanes:
        print(f"{name:<28}{humanize(t):>14}{humanize(l):>14}{delta(t, l):>9}")

    print()
    print("Records (full history)")
    print("-" * 65)
    md = max(day_sums, key=day_sums.get)
    print(f"  Highest Day:    {md} ({humanize(day_sums[md])})")
    weeks, months = defaultdict(int), defaultdict(int)
    for d, v in day_sums.items():
        weeks[d.isocalendar()[:2]] += v
        months[(d.year, d.month)] += v
    mw = max(weeks, key=weeks.get)
    print(f"  Highest Week:   {mw[0]}-W{mw[1]:02d} ({humanize(weeks[mw])})")
    mm = max(months, key=months.get)
    print(f"  Highest Month:  {mm[0]}-{mm[1]:02d} ({humanize(months[mm])})")

    dates = sorted(day_sums)
    best = cur = 0
    bstart = bend = tstart = dates[0]
    cd = dates[0]
    while cd <= dates[-1]:
        if day_sums.get(cd, 0) > 0:
            if cur == 0:
                tstart = cd
            cur += 1
            if cur > best:
                best, bstart, bend = cur, tstart, cd
        else:
            cur = 0
        cd += _dtm.timedelta(days=1)
    cstreak = 0
    cd = today if day_sums.get(today, 0) > 0 else today - _dtm.timedelta(days=1)
    while day_sums.get(cd, 0) > 0:
        cstreak += 1
        cd -= _dtm.timedelta(days=1)
    print(f"  Longest Streak: {best} days ({bstart}..{bend})")
    print(f"  Current Streak: {cstreak} days")
    return None


if __name__ == "__main__" and LANES:
    print()
    print("=" * 70)
    print(f"Token usage analytics  (history through {NOW:%Y-%m-%d})")
    print("=" * 70)
    print_analytics_dashboard(ALL_INVOCATIONS, NOW)

