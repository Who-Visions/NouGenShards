"""Fleet fan-out: accounts are the unit, not keys and not lanes."""
import os
import sqlite3
import threading
import time

import pytest

from nougen_shards import fleet_keys


def _make_store(path, names):
    conn = sqlite3.connect(str(path))
    conn.execute("create table secrets (id integer primary key, secret_key text, "
                 "secret_value text, last_rotated text)")
    conn.executemany("insert into secrets (secret_key, secret_value) values (?, ?)",
                     [(n, f"value-for-{n}") for n in names])
    conn.commit()
    conn.close()


def _pool(spec):
    """Build a pool directly from {lane: [names]} without touching a vault."""
    pool = fleet_keys.FleetPool.__new__(fleet_keys.FleetPool)
    pool._lock = threading.Lock()
    pool._accounts = {}
    pool._cursor = 0
    for lane, names in spec.items():
        for name in names:
            acct_id = fleet_keys.account_of(name)
            acct = pool._accounts.setdefault(
                acct_id, fleet_keys.FleetAccount(account=acct_id))
            acct.creds.setdefault(lane, []).append(
                fleet_keys.FleetCredential(name=name, lane=lane,
                                           account=acct_id, value=f"v-{name}"))
    pool._order = sorted(pool._accounts)
    return pool


# --------------------------------------------------------------- identity ---

@pytest.mark.parametrize("name", [
    "OPENROUTER_KEY_SOMEONE_AT_GMAIL_COM",
    "OPENROUTER_KEY_SOMEONE_GMAIL_COM",
    "OPENROUTER_KEY_SOMEONE",
    "OPENROUTER_SOMEONE",
])
def test_every_spelling_of_one_account_collapses(name):
    """Four vault rows, one rate-limit budget. This is the whole point."""
    assert fleet_keys.account_of(name) == "someone"


def test_same_account_on_different_lanes_is_one_account():
    assert (fleet_keys.account_of("OPENROUTER_KEY_SOMEONE_AT_GMAIL_COM")
            == fleet_keys.account_of("HUGGINGFACE_KEY_SOMEONE_AT_GMAIL_COM")
            == fleet_keys.account_of("OLLAMA_KEY_SOMEONE_GMAIL_COM"))


def test_anonymous_tokens_share_one_identity():
    """A bare token carries no account; it must not look like a new one."""
    assert fleet_keys.account_of("OPENROUTER_API_KEY") == fleet_keys._ANONYMOUS_ACCOUNT
    assert fleet_keys.account_of("HF_TOKEN") == fleet_keys._ANONYMOUS_ACCOUNT


def test_custom_domain_collapses_only_when_declared(monkeypatch):
    monkeypatch.delenv("NOUGEN_ACCOUNT_DOMAINS", raising=False)
    monkeypatch.delenv("NOUGEN_ACCOUNT_ALIASES", raising=False)
    assert fleet_keys.account_of("OPENROUTER_KEY_SOMEONE_AT_EXAMPLE_COM") != "someone"
    monkeypatch.setenv("NOUGEN_ACCOUNT_DOMAINS", "example.com")
    assert fleet_keys.account_of("OPENROUTER_KEY_SOMEONE_AT_EXAMPLE_COM") == "someone"


def test_aliases_are_declared_never_guessed(monkeypatch):
    """Shorthand no rule could derive is collapsed only when declared."""
    monkeypatch.delenv("NOUGEN_ACCOUNT_ALIASES", raising=False)
    assert fleet_keys.account_of("OPENROUTER_SHORT") == "short"
    monkeypatch.setenv("NOUGEN_ACCOUNT_ALIASES", "short=longform")
    assert fleet_keys.account_of("OPENROUTER_SHORT") == "longform"


# -------------------------------------------------------------- discovery ---

def test_discovery_reads_every_store_and_dedupes(tmp_path, monkeypatch):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    _make_store(a, ["OPENROUTER_KEY_ONE", "OPENROUTER_KEY_SHARED"])
    _make_store(b, ["OPENROUTER_KEY_SHARED", "OPENROUTER_KEY_TWO"])
    monkeypatch.setenv("NOUGEN_SECRETS_DB_PATH", f"{a}{os.pathsep}{b}")
    names = fleet_keys.discover_key_names()["openrouter"]
    assert sorted(names) == ["OPENROUTER_KEY_ONE", "OPENROUTER_KEY_SHARED",
                             "OPENROUTER_KEY_TWO"]
    assert names.count("OPENROUTER_KEY_SHARED") == 1


def test_discovery_skips_non_credential_names(tmp_path, monkeypatch):
    db = tmp_path / "s.db"
    _make_store(db, ["HF_TOKEN", "HF_S3_ACCESS_KEY_ID", "HF_S3_SECRET_ACCESS_KEY",
                     "HF_SSH_KEY_SOMETHING", "HUGGINGFACE_KEY_REAL"])
    monkeypatch.setenv("NOUGEN_SECRETS_DB_PATH", str(db))
    assert sorted(fleet_keys.discover_key_names()["hf"]) == ["HF_TOKEN",
                                                              "HUGGINGFACE_KEY_REAL"]


def test_malformed_store_does_not_kill_discovery(tmp_path, monkeypatch):
    """A store mid-restore must not take a healthy one down with it."""
    good, bad = tmp_path / "good.db", tmp_path / "bad.db"
    _make_store(good, ["OPENROUTER_KEY_GOOD"])
    bad.write_bytes(b"this is not a sqlite database")
    monkeypatch.setenv("NOUGEN_SECRETS_DB_PATH", f"{bad}{os.pathsep}{good}")
    assert fleet_keys.discover_key_names()["openrouter"] == ["OPENROUTER_KEY_GOOD"]


def test_stores_are_globbed_from_a_declared_root(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    _make_store(root / "one.db", ["OPENROUTER_KEY_A"])
    _make_store(root / "two.db", ["OPENROUTER_KEY_B"])
    monkeypatch.delenv("NOUGEN_SECRETS_DB_PATH", raising=False)
    monkeypatch.delenv("NOUGEN_SECRETS_DB", raising=False)
    # Pin the roots: otherwise the developer's own convention directory joins
    # in and the assertion depends on whatever is vaulted on the test machine.
    monkeypatch.setattr(fleet_keys, "secret_roots", lambda: [root])
    assert sorted(fleet_keys.discover_key_names()["openrouter"]) == [
        "OPENROUTER_KEY_A", "OPENROUTER_KEY_B"]


def test_no_vault_at_all_is_a_valid_answer(tmp_path, monkeypatch):
    """A fresh install with an empty vault must degrade, not raise."""
    monkeypatch.delenv("NOUGEN_SECRETS_DB_PATH", raising=False)
    monkeypatch.delenv("NOUGEN_SECRETS_DB", raising=False)
    monkeypatch.setattr(fleet_keys, "secret_roots", lambda: [tmp_path / "nope"])
    assert fleet_keys.candidate_stores() == []
    assert fleet_keys.discover_key_names() == {}
    assert len(fleet_keys.FleetPool({})) == 0


# ---------------------------------------------------------------- fan-out ---

def test_four_rows_for_one_account_are_one_budget():
    """The trap: rotating rows would hammer one account four times."""
    pool = _pool({"openrouter": ["OPENROUTER_KEY_SOLO_AT_GMAIL_COM",
                                 "OPENROUTER_KEY_SOLO_GMAIL_COM",
                                 "OPENROUTER_KEY_SOLO", "OPENROUTER_SOLO"]})
    assert len(pool) == 1
    assert len(pool.fan_out("openrouter", 4)) == 1


def test_fan_out_returns_distinct_accounts():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A", "OPENROUTER_KEY_B",
                                 "OPENROUTER_KEY_C"]})
    got = pool.fan_out("openrouter", 3)
    assert len({c.account for c in got}) == 3


def test_fan_out_is_capped_by_accounts_not_width():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A", "OPENROUTER_KEY_B"]})
    assert len(pool.fan_out("openrouter", 50)) == 2


def test_cooling_removes_the_whole_account_not_one_row():
    """Cooling a row would just hand out a sibling name for the same budget."""
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A_AT_GMAIL_COM",
                                 "OPENROUTER_KEY_A_GMAIL_COM",
                                 "OPENROUTER_KEY_B"]})
    cred = next(c for c in pool.fan_out("openrouter", 9) if c.account == "a")
    pool.report_exhausted(cred, seconds=300)
    assert {c.account for c in pool.fan_out("openrouter", 9)} == {"b"}


def test_cooling_one_lane_leaves_the_account_usable_elsewhere():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A"], "ollama": ["OLLAMA_KEY_A"]})
    cred = pool.acquire("openrouter")
    pool.report_exhausted(cred, seconds=300)
    assert pool.acquire("openrouter") is None
    assert pool.acquire("ollama") is not None


def test_all_cooling_returns_none_not_an_exhausted_credential():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A", "OPENROUTER_KEY_B"]})
    for cred in pool.fan_out("openrouter", 2):
        pool.report_exhausted(cred, seconds=300)
    assert pool.acquire("openrouter") is None
    assert pool.fan_out("openrouter", 5) == []


def test_report_ok_clears_cooling():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A"]})
    cred = pool.acquire("openrouter")
    pool.report_exhausted(cred, seconds=300)
    assert pool.acquire("openrouter") is None
    pool.report_ok(cred)
    assert pool.acquire("openrouter") is not None


def test_cooling_expires():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A"]})
    pool.report_exhausted(pool.acquire("openrouter"), seconds=0.01)
    time.sleep(0.05)
    assert pool.acquire("openrouter") is not None


def test_acquire_rotates_across_accounts():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A", "OPENROUTER_KEY_B",
                                 "OPENROUTER_KEY_C"]})
    assert len({pool.acquire("openrouter").account for _ in range(3)}) == 3


# ----------------------------------------------------------------- safety ---

def test_repr_and_status_never_carry_the_secret():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A"]})
    cred = pool.acquire("openrouter")
    assert "v-OPENROUTER_KEY_A" not in repr(cred)
    assert "v-OPENROUTER_KEY_A" not in repr(pool.status())


def test_status_reports_accounts_and_credential_counts_separately():
    """Both numbers matter: rows are not budgets."""
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A_AT_GMAIL_COM",
                                 "OPENROUTER_KEY_A_GMAIL_COM",
                                 "OPENROUTER_KEY_B"]})
    lane = pool.status()["lanes"]["openrouter"]
    assert lane["accounts"] == 2 and lane["credentials"] == 3


def test_unknown_lane_is_rejected():
    pool = _pool({"openrouter": ["OPENROUTER_KEY_A"]})
    with pytest.raises(ValueError):
        pool.acquire("not-a-lane")


def test_endpoints_are_env_overridable(monkeypatch):
    monkeypatch.setenv("NOUGEN_OLLAMA_PROBE_URL", "https://example.invalid/probe")
    assert fleet_keys._lane_conf("ollama")["probe"] == "https://example.invalid/probe"


def test_alias_chains_are_flattened(monkeypatch):
    """`a=b` alongside `b=c` must resolve a -> c, or two spellings of one
    account still land in different buckets and the fan-out doubles up."""
    monkeypatch.setenv("NOUGEN_ACCOUNT_ALIASES", "a=b,b=c")
    assert fleet_keys.account_aliases()["a"] == "c"
    assert fleet_keys.account_of("OPENROUTER_A") == "c"


def test_alias_cycle_does_not_hang(monkeypatch):
    monkeypatch.setenv("NOUGEN_ACCOUNT_ALIASES", "a=b,b=a")
    resolved = fleet_keys.account_aliases()
    assert resolved["a"] in {"a", "b"} and resolved["b"] in {"a", "b"}


def test_many_keys_for_one_account_is_one_fan_out_slot():
    """A provider that lets an account mint many keys still has one budget."""
    names = [f"OPENROUTER_KEY_SOLO_GMAIL_COM_{i:02d}" for i in range(1, 13)]
    pool = _pool({"openrouter": names + ["OPENROUTER_KEY_OTHER_GMAIL_COM"]})
    assert len(pool) == 2
    assert len(pool.fan_out("openrouter", 20)) == 2

