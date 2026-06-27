"""Tests for billing cost computation, monthly reset, and usage metering."""
import sqlite3
import importlib
import pytest

import nougen_shards.billing as billing


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_HOME", str(tmp_path))
    importlib.reload(billing)
    billing.init_billing()
    yield
    importlib.reload(billing)


def test_compute_cost_free_model_is_zero():
    usage = {"prompt_tokens": 1000, "completion_tokens": 1000, "cached_tokens": 0}
    assert billing.compute_cost("google/gemma-4-31b-it:free", usage) == 0.0


def test_compute_cost_paid_model():
    # 1M input @ $3, 1M output @ $15 => $18.00
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "cached_tokens": 0}
    assert billing.compute_cost("anthropic/claude-3.5-sonnet", usage) == pytest.approx(18.0)


def test_compute_cost_cached_discount():
    # 1M prompt all cached @ 10% of $3 => $0.30
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0, "cached_tokens": 1_000_000}
    assert billing.compute_cost("anthropic/claude-3.5-sonnet", usage) == pytest.approx(0.30)


def test_log_usage_stores_cost_and_counts():
    token = "user-1"
    cost = billing.log_usage(token, "openrouter", "anthropic/claude-3.5-sonnet",
                             {"prompt_tokens": 1_000_000, "completion_tokens": 0,
                              "total_tokens": 1_000_000, "cached_tokens": 0})
    assert cost == pytest.approx(3.0)
    conn = sqlite3.connect(str(billing.BILLING_DB))
    conn.row_factory = sqlite3.Row
    log = conn.execute("SELECT * FROM usage_logs WHERE user_token = ?", (token,)).fetchone()
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_token = ?", (token,)).fetchone()
    conn.close()
    assert log["estimated_cost"] == pytest.approx(3.0)
    # usage is metered even with no pre-existing subscription row
    assert sub["used_this_month"] == 1_000_000
    assert sub["status"] == "inactive"


def test_total_tokens_fallback():
    token = "user-2"
    billing.log_usage(token, "openrouter", "x:free",
                      {"prompt_tokens": 10, "completion_tokens": 5})  # no total_tokens
    conn = sqlite3.connect(str(billing.BILLING_DB))
    conn.row_factory = sqlite3.Row
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_token = ?", (token,)).fetchone()
    conn.close()
    assert sub["used_this_month"] == 15


def test_monthly_reset():
    token = "user-3"
    billing.init_billing()
    conn = sqlite3.connect(str(billing.BILLING_DB))
    conn.execute(
        "INSERT INTO subscriptions (user_token, status, monthly_limit, used_this_month, last_reset) "
        "VALUES (?, 'active', 1000, 999, ?)",
        (token, "2000-01-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    # Stale period -> counter rolls over, user is active again (not over_limit)
    res = billing.check_subscription(token)
    assert res["status"] == "active"
    assert res["used"] == 0


def test_timestamp_is_clean_rfc3339():
    ts = billing._now_iso()
    assert ts.endswith("Z")
    assert "+00:00" not in ts
