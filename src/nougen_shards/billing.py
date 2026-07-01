"""
NouGenShards Billing and Usage Metering.
Handles subscription status and token counting for the Cloud Gateway.
"""
import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime, timezone

# Configuration for the Node
NOUGEN_HOME = Path(os.environ.get("NOUGEN_HOME", Path.home() / ".nougen"))
BILLING_DB = NOUGEN_HOME / "billing.db"

# Estimated provider list prices in USD per 1M tokens: (input, output).
# Operator-configurable: override via NOUGEN_PRICING_JSON (a JSON object of
# {model_substring: [input_per_mtok, output_per_mtok]}). Unknown models and any
# ":free" model cost 0.0 so usage is never over-billed.
_DEFAULT_PRICING = {
    ":free": (0.0, 0.0),
    "claude-3.5-sonnet": (3.0, 15.0),
    "claude-3-opus": (15.0, 75.0),
    "claude-3-haiku": (0.25, 1.25),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.5, 10.0),
}


def _load_pricing() -> dict:
    pricing = dict(_DEFAULT_PRICING)
    raw = os.environ.get("NOUGEN_PRICING_JSON")
    if raw:
        try:
            for key, val in json.loads(raw).items():
                pricing[key.lower()] = (float(val[0]), float(val[1]))
        except (ValueError, TypeError, KeyError, IndexError):
            pass
    return pricing


def _price_for(model: str) -> tuple:
    m = (model or "").lower()
    pricing = _load_pricing()
    # Match the most specific (longest) key first so a broad key that happens to
    # be inserted earlier can't shadow a more specific one (dict order isn't a
    # correctness guarantee for pricing).
    for key in sorted(pricing, key=len, reverse=True):
        if key in m:
            return pricing[key]
    return (0.0, 0.0)


def compute_cost(model: str, usage: dict) -> float:
    """Estimate USD cost for a request. Cached (read) prompt tokens are billed
    at 10% of the input rate; free/unknown models cost 0.0."""
    in_price, out_price = _price_for(model)
    prompt = usage.get("prompt_tokens", 0) or 0
    completion = usage.get("completion_tokens", 0) or 0
    cached = min(usage.get("cached_tokens", 0) or 0, prompt)
    billable_prompt = prompt - cached
    cost = (
        (billable_prompt / 1_000_000) * in_price
        + (cached / 1_000_000) * in_price * 0.1
        + (completion / 1_000_000) * out_price
    )
    return round(cost, 8)


def _now_iso() -> str:
    # tz-aware UTC already yields +00:00; normalize to a single trailing Z.
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _period_key(iso_ts: str) -> str:
    """'YYYY-MM' billing period from an ISO timestamp ('' if unparseable)."""
    return iso_ts[:7] if iso_ts else ""

def init_billing():
    """Initializes the billing and usage substrate."""
    NOUGEN_HOME.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(BILLING_DB))
    cursor = conn.cursor()
    
    # Usage table (Module 20: Quantify Intelligence)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_token TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            cached_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0.0
        );
    """)
    
    # Subscription table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_token TEXT PRIMARY KEY,
            status TEXT DEFAULT 'active', -- active, inactive, over_limit
            monthly_limit INTEGER DEFAULT 1000000, -- 1M tokens default
            used_this_month INTEGER DEFAULT 0,
            last_reset TEXT NOT NULL
        );
    """)
    
    conn.commit()
    conn.close()

def check_subscription(token: str) -> dict:
    """Verifies user status and usage limits."""
    if not BILLING_DB.exists():
        init_billing()
        
    conn = sqlite3.connect(str(BILLING_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM subscriptions WHERE user_token = ?", (token,)).fetchone()
        if not row:
            # First time user? Default to active for testing, or inactive for production
            # (Module 10: Fail Closed)
            return {"status": "inactive", "message": "No active subscription found."}

        # Roll over the monthly counter when the billing period changes.
        used = row["used_this_month"]
        status = row["status"]
        if _period_key(row["last_reset"]) != _period_key(_now_iso()):
            # New billing period: reset the monthly counter. `status` is only ever
            # 'active'/'inactive' in storage ('over_limit' is a computed response,
            # never persisted), so there is no stored block to clear here.
            conn.execute(
                "UPDATE subscriptions SET used_this_month = 0, last_reset = ? WHERE user_token = ?",
                (_now_iso(), token),
            )
            conn.commit()
            used = 0

        if status != "active":
            return {"status": status, "message": "Subscription is not active."}

        if used >= row["monthly_limit"]:
            return {"status": "over_limit", "message": "Monthly token limit reached."}

        return {"status": "active", "used": used, "limit": row["monthly_limit"]}
    finally:
        conn.close()

def log_usage(token: str, provider: str, model: str, usage: dict) -> float:
    """Meters the request, stores the estimated cost, and updates the monthly
    balance. Returns the estimated USD cost of the request."""
    if not BILLING_DB.exists():
        init_billing()

    timestamp = _now_iso()
    prompt = usage.get("prompt_tokens", 0) or 0
    completion = usage.get("completion_tokens", 0) or 0
    # Fall back to prompt+completion when the provider omits total_tokens.
    total = usage.get("total_tokens") or (prompt + completion)
    cached = usage.get("cached_tokens", 0) or 0
    cost = compute_cost(model, usage)

    conn = sqlite3.connect(str(BILLING_DB))
    try:
        # 1. Log detailed record (now including the estimated cost)
        conn.execute("""
            INSERT INTO usage_logs (user_token, timestamp, provider, model, prompt_tokens, completion_tokens, total_tokens, cached_tokens, estimated_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (token, timestamp, provider, model, prompt, completion, total, cached, cost))

        # 2. Update monthly balance. Ensure a subscription row exists so usage is
        #    always counted; new rows are 'inactive' to preserve fail-closed auth.
        cur = conn.execute("""
            UPDATE subscriptions
            SET used_this_month = used_this_month + ?
            WHERE user_token = ?
        """, (total, token))
        if cur.rowcount == 0:
            conn.execute("""
                INSERT INTO subscriptions (user_token, status, used_this_month, last_reset)
                VALUES (?, 'inactive', ?, ?)
            """, (token, total, timestamp))

        conn.commit()
    finally:
        conn.close()
    return cost
