"""Fan work out across ACCOUNTS, not across providers.

The clients in `models_client` each bind ONE credential - `OpenRouterClient`
reads `OPENROUTER_API_KEY`, and that is the only key it will ever use. An
operator who has registered several accounts for a lane gets no benefit from
any of them: one account's rate limit stalls the lane while every other
working credential sits idle beside it.

THE UNIT OF PARALLELISM IS THE ACCOUNT, NOT THE KEY AND NOT THE LANE.

Rate limits are enforced per account per provider. A vault typically holds the
same account under several names - a bare form, an `_AT_GMAIL_COM` form, a
`_GMAIL_COM` form - and the same account often appears on more than one
provider. Treating each vault row as an independent credential is the trap
this module exists to avoid: a pool that "rotates" through four rows belonging
to one account hammers that account four times while believing it is spreading
load, and the 429 arrives just as fast as with a single key.

So credentials are grouped into accounts first. Rotation walks ACCOUNTS.
`fan_out()` returns credentials from DISTINCT accounts, which is what makes
concurrent work safe: N workers on N accounts is N independent budgets, while
N workers on one account is one budget being hit N times harder.

Cooling is per (account, lane). A rate limit on one provider says nothing
about that account's standing with another, and nothing about other accounts.

Rule 0.2 shapes every lookup: nothing about the fleet is hardcoded. Store
locations, lane endpoints, name patterns, the account-suffix vocabulary and
the backoff window all resolve from the environment first, then from a runtime
probe, and only then from a constant. Key NAMES are discovered by querying the
vault, never listed in code, so a newly registered account joins the rotation
with no code change. An install with an empty vault yields no accounts, which
is a valid answer rather than an error.

Secrets are handled by name. No value is logged, placed in a repr, or included
in an exception message.

Typical use - sequential::

    pool = FleetPool()
    cred = pool.acquire("openrouter")
    if cred is not None:
        try:
            ...call the API with cred.value...
            pool.report_ok(cred)
        except RateLimited:
            pool.report_exhausted(cred)   # cools this account+lane only

Typical use - parallel, one worker per account::

    for cred in pool.fan_out("openrouter", width=8):
        submit(worker, cred)              # 8 distinct accounts, 8 budgets
"""
from __future__ import annotations

import os
import random
import re
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

#: Lane definitions. The probe URL is a cheap authenticated GET used to decide
#: whether a credential works - never a generation call. Endpoints are
#: env-overridable because vendors move them, and a probe pointed at a
#: wrong-but-plausible path returns the same failure for EVERY key, which is
#: indistinguishable from every key being dead. Verify a probe URL against one
#: known-good credential before believing a lane-wide failure.
_LANE_DEFAULTS = {
    "openrouter": {
        "probe": "https://openrouter.ai/api/v1/key",
        "base": "https://openrouter.ai/api/v1",
        "prefixes": ("OPENROUTER_KEY_", "OPENROUTER_"),
    },
    "ollama": {
        "probe": "https://ollama.com/api/tags",
        "base": "https://ollama.com/v1",
        "prefixes": ("OLLAMA_KEY_", "OLLAMA_"),
    },
    "hf": {
        "probe": "https://huggingface.co/api/whoami-v2",
        "base": "https://api-inference.huggingface.co/models",
        "prefixes": ("HUGGINGFACE_KEY_", "HUGGINGFACE_", "HF_KEY_", "HF_"),
    },
}

#: Names that match a lane prefix but are NOT bearer credentials. Object-store
#: pairs, SSH keys, endpoints and namespaces live in the same vault and would
#: otherwise be handed to an HTTP client as an Authorization header.
_NON_CREDENTIAL_MARKERS = ("_S3_", "_SSH_", "_ENDPOINT", "_NAMESPACE",
                           "_REGION", "_ACCESS_KEY_ID", "_MODELS", "_HOST")

#: Mail-domain suffixes stripped when reducing a key name to an account id.
#: Env-overridable: an operator whose accounts sit on their own domain adds it
#: once rather than patching this list. Without the right vocabulary here the
#: SAME account under two spellings looks like two accounts, and the fan-out
#: quietly doubles up on one budget.
_DEFAULT_ACCOUNT_SUFFIXES = ("AT_GMAIL_COM", "GMAIL_COM",
                             "AT_OUTLOOK_COM", "OUTLOOK_COM",
                             "AT_ICLOUD_COM", "ICLOUD_COM",
                             "AT_PROTON_ME", "PROTON_ME")

#: Bare names that carry no account identity - a lone `HF_TOKEN` or
#: `OPENROUTER_API_KEY`. They are grouped under one shared id so they are not
#: mistaken for several independent accounts.
_ANONYMOUS_TOKENS = ("API_KEY", "API_TOKEN", "TOKEN", "KEY", "")
_ANONYMOUS_ACCOUNT = "default"


def _env_list(name: str) -> List[str]:
    raw = os.environ.get(name, "").strip()
    return [p for p in (s.strip() for s in raw.split(os.pathsep)) if p]


def account_aliases() -> Dict[str, str]:
    """Operator-declared shorthand -> canonical account id.

    Mail-domain stripping collapses the mechanical spellings of one account,
    but not an operator's private shorthand: a vault may hold the same account
    as a full handle, an abbreviation and an initialism, and no rule can
    derive that those are the same person. Guessing would be worse than not
    trying - a wrong merge silently doubles up on one budget, and a wrong
    split silently under-uses the fleet.

    So the mapping is declared, never inferred, and it stays out of this
    package. Set `NOUGEN_ACCOUNT_ALIASES` to a comma-separated list of
    `shorthand=canonical` pairs::

        NOUGEN_ACCOUNT_ALIASES="cw=contact,c_who=contact,dm=dmeralus"

    Anything not declared keeps its own identity, which is the safe default:
    treating one account as two costs throughput, while treating two accounts
    as one costs a rate limit.
    """
    out: Dict[str, str] = {}
    raw = os.environ.get("NOUGEN_ACCOUNT_ALIASES", "")
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        short, _, canon = pair.partition("=")
        short, canon = short.strip().lower(), canon.strip().lower()
        if short and canon:
            out[short] = canon
    # Flatten chains: a declared `a=b` alongside `b=c` must resolve a -> c, or
    # two spellings of one account still land in different buckets. Bounded so
    # a declared cycle cannot hang the caller.
    for short in list(out):
        seen = {short}
        target = out[short]
        while target in out and target not in seen and len(seen) < 32:
            seen.add(target)
            target = out[target]
        out[short] = target
    return out


def account_suffixes() -> List[str]:
    extra = [s.upper().replace("@", "AT_").replace(".", "_")
             for s in _env_list("NOUGEN_ACCOUNT_DOMAINS")]
    out = []
    for s in list(extra) + list(_DEFAULT_ACCOUNT_SUFFIXES):
        out.append(s)
        if not s.startswith("AT_"):
            out.append("AT_" + s)
    # Longest first so `AT_GMAIL_COM` wins over `GMAIL_COM`.
    return sorted(set(out), key=len, reverse=True)


def secret_roots() -> List[Path]:
    """Directories that may hold keymaker stores, most-specific first.

    `NOUGEN_SECRETS_DIRS` is a pathsep-separated list, so an operator whose
    vault lives somewhere this package has never heard of declares it once
    instead of patching code. The package's own convention directory is
    appended last and may simply not exist.
    """
    roots = [Path(p) for p in _env_list("NOUGEN_SECRETS_DIRS")]
    roots.append(Path.home() / ".nougen" / "secrets")
    return roots


def candidate_stores() -> List[Path]:
    """Every keymaker store to search, discovered rather than assumed.

    An operator may hold more than one store: stores share a schema but not
    their contents, so a credential written through one is invisible to the
    other and a pool reading a single file can silently miss most of the
    fleet. Every store found is searched; which one is authoritative is the
    operator's decision, not this module's.
    """
    explicit = _env_list("NOUGEN_SECRETS_DB_PATH")
    if explicit:
        return [Path(p) for p in explicit]
    single = os.environ.get("NOUGEN_SECRETS_DB")
    if single:
        return [Path(single)]

    pattern = os.environ.get("NOUGEN_SECRETS_DB_GLOB", "*.db")
    found: List[Path] = []
    for root in secret_roots():
        try:
            if not root.is_dir():
                continue
            for path in sorted(root.glob(pattern)):
                if path.is_file() and path not in found:
                    found.append(path)
        except OSError:
            continue
    return found


def _lane_conf(lane: str) -> dict:
    if lane not in _LANE_DEFAULTS:
        raise ValueError(f"unknown lane {lane!r}; known: {sorted(_LANE_DEFAULTS)}")
    conf = dict(_LANE_DEFAULTS[lane])
    up = lane.upper()
    conf["probe"] = os.environ.get(f"NOUGEN_{up}_PROBE_URL", conf["probe"])
    conf["base"] = os.environ.get(f"NOUGEN_{up}_BASE_URL", conf["base"])
    return conf


def lane_of(name: str) -> Optional[str]:
    """Which lane a vault key belongs to, or None."""
    up = name.upper()
    if any(bad in up for bad in _NON_CREDENTIAL_MARKERS):
        return None
    best: Optional[str] = None
    best_len = -1
    for lane, conf in _LANE_DEFAULTS.items():
        for prefix in conf["prefixes"]:
            if up.startswith(prefix) and len(prefix) > best_len:
                best, best_len = lane, len(prefix)
    if best:
        return best
    # Some vaults label a key by account first, e.g. `<ACCOUNT>_OLLAMA_KEY`.
    for lane in _LANE_DEFAULTS:
        token = "HUGGINGFACE" if lane == "hf" else lane.upper()
        if token in up:
            return lane
    return None


def account_of(name: str) -> str:
    """Reduce a vault key name to the account identity that owns it.

    `OPENROUTER_KEY_SOMEONE_AT_GMAIL_COM`, `OPENROUTER_KEY_SOMEONE_GMAIL_COM`
    and `OPENROUTER_SOMEONE` all name ONE account and therefore ONE rate-limit
    budget. Collapsing them is what keeps a fan-out honest.
    """
    up = name.upper().strip("_")
    lane = lane_of(name)
    prefixes = list(_LANE_DEFAULTS[lane]["prefixes"]) if lane else []
    for prefix in sorted(prefixes, key=len, reverse=True):
        if up.startswith(prefix):
            up = up[len(prefix):]
            break
    else:
        for lane_name, conf in _LANE_DEFAULTS.items():
            token = "HUGGINGFACE" if lane_name == "hf" else lane_name.upper()
            up = up.replace("_" + token + "_KEY", "").replace("_" + token, "")
    # A numeric suffix distinguishes several keys issued to ONE account, which
    # is common where a provider lets an account mint many keys. They share
    # that account's budget, so the index must not fork the identity - and it
    # has to come off BEFORE the mail-domain strip, or the domain no longer
    # sits at the end of the string and never matches.
    up = re.sub(r"_\d{1,3}$", "", up).strip("_")
    for suffix in account_suffixes():
        if up.endswith("_" + suffix):
            up = up[: -(len(suffix) + 1)]
            break
        if up == suffix:
            up = ""
            break
    up = up.strip("_")
    # Check for a bare anonymous token BEFORE trimming a trailing `_KEY`, or
    # `API_KEY` loses its tail and becomes the invented account "api".
    if up in _ANONYMOUS_TOKENS:
        return _ANONYMOUS_ACCOUNT
    up = re.sub(r"_(API_KEY|API_TOKEN|TOKEN|KEY)$", "", up).strip("_")
    if up in _ANONYMOUS_TOKENS:
        return _ANONYMOUS_ACCOUNT
    ident = up.lower()
    # Operator-declared aliases run last, so they can collapse shorthand that
    # no mechanical rule could have known was the same account.
    return account_aliases().get(ident, ident)


@dataclass
class FleetCredential:
    """One vault row. `value` is the secret; everything else is safe to log."""
    name: str
    lane: str
    account: str
    value: str = field(repr=False)

    def __repr__(self) -> str:  # never leak the value through a traceback
        return (f"FleetCredential(name={self.name!r}, lane={self.lane!r}, "
                f"account={self.account!r})")


@dataclass
class FleetAccount:
    """One rate-limit budget holder, with whatever lanes it is registered on."""
    account: str
    creds: Dict[str, List[FleetCredential]] = field(default_factory=dict)
    cooling: Dict[str, float] = field(default_factory=dict)

    def lanes(self) -> List[str]:
        return sorted(self.creds)

    def available_on(self, lane: str) -> bool:
        return bool(self.creds.get(lane)) and time.time() >= self.cooling.get(lane, 0.0)


def _cooldown_seconds() -> float:
    try:
        return float(os.environ.get("NOUGEN_FLEET_COOLDOWN_S", "900"))
    except ValueError:
        return 900.0


def _peel(name: str) -> Optional[str]:
    """Read one secret value, trying the package keymaker then the peel helper."""
    try:
        from . import keymaker
        value = keymaker.get_secret(name)
        if value:
            return value
    except Exception:
        pass
    try:
        for extra in _env_list("NOUGEN_KEYMAKER_PATH") or [
                str(Path.home() / ".nougen" / "bin")]:
            if extra not in sys.path:
                sys.path.insert(0, extra)
        import keymaker_peel  # type: ignore
    except Exception:
        return None
    for store in candidate_stores():
        if not store.exists():
            continue
        try:
            rows = keymaker_peel.load(name, db=store)
        except Exception:
            continue
        if rows:
            return rows[0][1]
    return None


def discover_key_names() -> Dict[str, List[str]]:
    """Every credential name in the vault, grouped by lane."""
    out: Dict[str, List[str]] = {}
    seen = set()
    for store in candidate_stores():
        if not store.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{store.as_posix()}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            rows = conn.execute("select secret_key from secrets").fetchall()
        except sqlite3.Error:
            # A store that is malformed or mid-restore must not take the pool
            # down with it; another store may be perfectly healthy.
            continue
        finally:
            conn.close()
        for (name,) in rows:
            if name in seen:
                continue
            lane = lane_of(name)
            if lane is None:
                continue
            seen.add(name)
            out.setdefault(lane, []).append(name)
    return out


class FleetPool:
    """Accounts, and the credentials each one holds, rotated account-first."""

    def __init__(self, names_by_lane: Optional[Dict[str, List[str]]] = None):
        self._lock = threading.Lock()
        self._accounts: Dict[str, FleetAccount] = {}
        self._order: List[str] = []
        self._cursor = 0
        self._load(names_by_lane)

    def _load(self, names_by_lane: Optional[Dict[str, List[str]]]) -> None:
        discovered = names_by_lane if names_by_lane is not None else discover_key_names()
        for lane, names in discovered.items():
            for name in names:
                value = _peel(name)
                if not value:
                    continue
                acct_id = account_of(name)
                acct = self._accounts.setdefault(acct_id, FleetAccount(account=acct_id))
                acct.creds.setdefault(lane, []).append(
                    FleetCredential(name=name, lane=lane, account=acct_id, value=value))
        # Shuffle once: a fixed start would march every process through the
        # same first account, concentrating a fleet-wide burst on one budget.
        self._order = list(self._accounts)
        random.shuffle(self._order)

    def __len__(self) -> int:
        return len(self._accounts)

    def accounts_on(self, lane: str) -> List[str]:
        return [a for a in self._order if self._accounts[a].creds.get(lane)]

    def available_accounts(self, lane: str) -> List[str]:
        return [a for a in self._order if self._accounts[a].available_on(lane)]

    def acquire(self, lane: str) -> Optional[FleetCredential]:
        """One credential from the next available ACCOUNT, or None."""
        _lane_conf(lane)
        with self._lock:
            n = len(self._order)
            for offset in range(n):
                acct = self._accounts[self._order[(self._cursor + offset) % n]]
                if acct.available_on(lane):
                    self._cursor = (self._cursor + offset + 1) % max(n, 1)
                    return acct.creds[lane][0]
        return None

    def fan_out(self, lane: str, width: int) -> List[FleetCredential]:
        """Up to `width` credentials, each from a DISTINCT account.

        This is the safe unit of concurrency: N credentials from N accounts is
        N independent budgets. Taking N credentials from one account would be
        one budget hit N times harder, which is the trap this module exists to
        avoid, so the list is capped by the number of available accounts and
        may be shorter than `width` - including empty.
        """
        _lane_conf(lane)
        if width <= 0:
            return []
        out: List[FleetCredential] = []
        with self._lock:
            n = len(self._order)
            for offset in range(n):
                if len(out) >= width:
                    break
                acct = self._accounts[self._order[(self._cursor + offset) % n]]
                if acct.available_on(lane):
                    out.append(acct.creds[lane][0])
            if out:
                self._cursor = (self._cursor + len(out)) % max(n, 1)
        return out

    def report_ok(self, cred: FleetCredential) -> None:
        with self._lock:
            acct = self._accounts.get(cred.account)
            if acct:
                acct.cooling.pop(cred.lane, None)

    def report_exhausted(self, cred: FleetCredential,
                         seconds: Optional[float] = None) -> None:
        """Cool ONE account on ONE lane.

        Not the credential: every vault row for this account shares its
        budget, so cooling a single row would just hand out a sibling name for
        the same exhausted account. Not the lane either: other accounts are
        unaffected, and this account may be perfectly fine elsewhere.
        """
        with self._lock:
            acct = self._accounts.get(cred.account)
            if acct:
                acct.cooling[cred.lane] = time.time() + (
                    _cooldown_seconds() if seconds is None else seconds)

    def status(self) -> Dict[str, object]:
        """Account ids and counts only - safe to log or return from a tool."""
        with self._lock:
            lanes: Dict[str, Dict[str, object]] = {}
            for lane in _LANE_DEFAULTS:
                on = [a for a in self._order if self._accounts[a].creds.get(lane)]
                if not on:
                    continue
                lanes[lane] = {
                    "accounts": len(on),
                    "available": sum(1 for a in on
                                     if self._accounts[a].available_on(lane)),
                    "credentials": sum(len(self._accounts[a].creds[lane]) for a in on),
                    "cooling": [a for a in on
                                if not self._accounts[a].available_on(lane)],
                }
            return {"accounts": len(self._accounts), "lanes": lanes}
