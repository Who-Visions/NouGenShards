"""Ask each provider whether the key you stored still works.

A vault full of keys tells you what you once had, not what still works. Keys get
revoked, rotated, hit a spend cap, or were pasted wrong the first time — and
none of that is visible from the vault, because a dead key and a live one are
the same string in a database.

That is not theoretical. Setting NouGenQ's OpenRouter secret meant choosing from
fifteen stored OpenRouter keys across several accounts; the first one tried
returned 401. Setting it blind would have shipped a dead key into an inference
path, where it surfaces as a user-facing failure rather than a config error.

## What it never does

Print, log, return, or transmit a secret value. Each check sends the key to the
provider it belongs to and nowhere else, and reports a twelve-hex-character
SHA-256 fingerprint so two vaults can be compared without either revealing
anything. The fingerprint is the same one keymaker already uses for audit.

## What a failure means

    LIVE        the provider accepted it
    DEAD        the provider rejected it — 401/403. Rotate or remove it.
    UNKNOWN     could not tell: no network, a 5xx, a timeout. NOT a verdict.

UNKNOWN is deliberately distinct from DEAD. Reporting an unreachable provider
as a dead key would send someone rotating a credential that is fine, and the
whole value here is that the answer can be trusted.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

#: How to ask each provider "is this key good?" — the cheapest authenticated
#: endpoint each one offers, chosen so a check costs nothing and returns no
#: user data. Nothing here generates tokens.
@dataclass(frozen=True)
class Probe:
    label: str
    url: str
    header: Callable[[str], dict]
    note: str = ""


PROBES: dict[str, Probe] = {
    "OPENROUTER_API_KEY": Probe(
        "OpenRouter", "https://openrouter.ai/api/v1/key",
        lambda k: {"Authorization": f"Bearer {k}"},
        "returns the key's own limits — no model call"),
    "HUGGINGFACE_API_KEY": Probe(
        "Hugging Face", "https://huggingface.co/api/whoami-v2",
        lambda k: {"Authorization": f"Bearer {k}"},
        "identity endpoint"),
    "OPENAI_API_KEY": Probe(
        "OpenAI", "https://api.openai.com/v1/models",
        lambda k: {"Authorization": f"Bearer {k}"},
        "model list"),
    "ANTHROPIC_API_KEY": Probe(
        "Anthropic", "https://api.anthropic.com/v1/models",
        lambda k: {"x-api-key": k, "anthropic-version": "2023-06-01"},
        "model list"),
    "GOOGLE_API_KEY": Probe(
        "Google / Gemini", "https://generativelanguage.googleapis.com/v1beta/models",
        lambda k: {"x-goog-api-key": k},
        "model list"),
}

LIVE, DEAD, UNKNOWN, NO_PROBE = "LIVE", "DEAD", "UNKNOWN", "NO PROBE"


@dataclass(frozen=True)
class Result:
    key: str
    label: str
    status: str
    detail: str
    fingerprint: str

    @property
    def actionable(self) -> bool:
        """Only DEAD asks the operator to do something."""
        return self.status == DEAD


def fingerprint(value: str) -> str:
    """Twelve hex of SHA-256 — the same audit id keymaker uses.

    Enough to tell two keys apart and to match one vault against another,
    reversible into nothing.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _probe(probe: Probe, secret: str, timeout: float) -> tuple[str, str]:
    """One request. Returns (status, detail) and never the secret."""
    request = urllib.request.Request(probe.url, headers=probe.header(secret))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return LIVE, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return DEAD, f"HTTP {exc.code} — rejected"
        if exc.code == 429:
            # Rate limited means the key was RECOGNISED. That is a live key
            # being throttled, and calling it dead would be exactly wrong.
            return LIVE, "HTTP 429 — rate limited, but authenticated"
        return UNKNOWN, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return UNKNOWN, f"unreachable: {type(exc).__name__}"
    except Exception as exc:  # pragma: no cover — defensive
        return UNKNOWN, f"{type(exc).__name__}"


def check_key(key: str, secret: str, timeout: float = 10.0) -> Result:
    """Validate one stored secret against the provider it belongs to."""
    fp = fingerprint(secret)
    probe = PROBES.get(key)
    if probe is None:
        return Result(key, key, NO_PROBE,
                      "no validation endpoint defined for this key", fp)
    if not secret.strip():
        return Result(key, probe.label, DEAD, "stored value is empty", fp)
    status, detail = _probe(probe, secret, timeout)
    return Result(key, probe.label, status, detail, fp)


def check_all(secrets: dict[str, str], timeout: float = 10.0,
              workers: int = 6) -> list[Result]:
    """Check every stored key, concurrently.

    Concurrent because these are independent network calls and a serial pass
    over a vault with fifteen keys is a minute of staring at nothing — the same
    mistake that made shard capture take 48 seconds.
    """
    if not secrets:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_key, k, v, timeout): k
                   for k, v in secrets.items()}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    order = {DEAD: 0, UNKNOWN: 1, NO_PROBE: 2, LIVE: 3}
    return sorted(results, key=lambda r: (order.get(r.status, 9), r.key))


def format_report(results: list[Result], as_json: bool = False) -> str:
    """Render results. Dead keys first, because they are the only ones to act on."""
    if as_json:
        return json.dumps([r.__dict__ for r in results], indent=2)
    if not results:
        return "No keys in the vault."

    mark = {LIVE: "OK  ", DEAD: "DEAD", UNKNOWN: "??  ", NO_PROBE: "--  "}
    width = max(len(r.key) for r in results)
    lines = [f"{mark.get(r.status, '?')} {r.key:<{width}}  {r.fingerprint}  "
             f"{r.label} — {r.detail}" for r in results]

    dead = [r for r in results if r.status == DEAD]
    unknown = [r for r in results if r.status == UNKNOWN]
    lines.append("")
    lines.append(f"{len(results)} key(s): {sum(1 for r in results if r.status == LIVE)} live, "
                 f"{len(dead)} dead, {len(unknown)} unverified")
    if dead:
        lines.append("Dead keys are rejected by the provider — rotate or remove them.")
    if unknown:
        lines.append("Unverified is not dead: the provider could not be reached. "
                     "Nothing to do until it can.")
    return "\n".join(lines)
