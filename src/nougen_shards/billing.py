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
            monthly_limit INTEGER DEFAULT 1000000, -- 100k tokens default
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
            
        if row["status"] != "active":
            return {"status": row["status"], "message": "Subscription is not active."}
            
        if row["used_this_month"] >= row["monthly_limit"]:
            return {"status": "over_limit", "message": "Monthly token limit reached."}
            
        return {"status": "active", "used": row["used_this_month"], "limit": row["monthly_limit"]}
    finally:
        conn.close()

def log_usage(token: str, provider: str, model: str, usage: dict):
    """Meters the request and updates the subscription balance."""
    timestamp = datetime.now(timezone.utc).isoformat() + "Z"
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", 0)
    cached = usage.get("cached_tokens", 0)
    
    conn = sqlite3.connect(str(BILLING_DB))
    try:
        # 1. Log detailed record
        conn.execute("""
            INSERT INTO usage_logs (user_token, timestamp, provider, model, prompt_tokens, completion_tokens, total_tokens, cached_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (token, timestamp, provider, model, prompt, completion, total, cached))
        
        # 2. Update monthly balance
        conn.execute("""
            UPDATE subscriptions 
            SET used_this_month = used_this_month + ? 
            WHERE user_token = ?
        """, (total, token))
        
        conn.commit()
    finally:
        conn.close()
