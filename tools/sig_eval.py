#!/usr/bin/env python3
"""Regression battery for the owner-origin signature path (_agy_live_delivery).

Converged byte-for-byte with the sibling node 2026-09-03: four length-prefixed fields
(goal, nonce, timestamp, body) joined with "|", HMAC-SHA256, hex lowercase.
Rerun after ANY change to canonical_signing_input or
verify_user_origin_signature — two verifiers that drift apart make a signed
leg pass on one node and fail on the other, which is the exact friction this
whole path exists to remove.

Runs against an isolated nonce store so it never touches production state.

Usage: NOUGEN_USER_ORIGIN_TOKEN=<token> python3 sig_eval.py
       (resolve the token the way the launch wrappers do; never paste it)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="sig_eval_")
os.environ["NOUGEN_USED_NONCES_FILE"] = os.path.join(_TMP, "nonces.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _agy_live_delivery as m  # noqa: E402

TOKEN = os.environ.get("NOUGEN_USER_ORIGIN_TOKEN", "")
WORKED_EXAMPLE = b"13:restart relay|2:n1|10:1788433000|12:do the thing"


def sign(goal: str, nonce: str, ts: str, body: str) -> str:
    return hmac.new(TOKEN.encode(), m.canonical_signing_input(goal, nonce, ts, body), hashlib.sha256).hexdigest()


def verify(goal, body, nonce, ts, sig):
    return m.verify_user_origin_signature(goal, body, nonce, sig, timestamp=ts)


def main() -> int:
    if not TOKEN:
        print("NOUGEN_USER_ORIGIN_TOKEN not set")
        return 2
    g, b = "test goal", "the real instruction body"
    now = str(int(time.time()))
    stale = str(int(time.time()) - 1000)
    future = str(int(time.time()) + 600)
    results = []

    def case(name, expected, got):
        results.append((name, expected, got, expected == got))

    case("worked example byte-exact", True,
         m.canonical_signing_input("restart relay", "n1", "1788433000", "do the thing") == WORKED_EXAMPLE)
    case("fresh correct -> verified", "user_verified", verify(g, b, "n-1", now, sign(g, "n-1", now, b)))
    case("replay same nonce -> rejected", "user_claimed_unverified", verify(g, b, "n-1", now, sign(g, "n-1", now, b)))
    case("stale ts -> rejected", "user_claimed_unverified", verify(g, b, "n-2", stale, sign(g, "n-2", stale, b)))
    # The one that makes eviction GENUINELY safe (the sibling node): a stale leg must
    # not consume its nonce, or an attacker pre-poisons the store against a
    # nonce the owner is about to use — replay defence turned into DoS.
    case("expired leg did NOT burn nonce (reuses fresh) -> verified", "user_verified",
         verify(g, b, "n-2", now, sign(g, "n-2", now, b)))
    case("future ts -> rejected", "user_claimed_unverified", verify(g, b, "n-3", future, sign(g, "n-3", future, b)))
    case("ts edited under kept sig -> rejected", "user_claimed_unverified", verify(g, b, "n-4", now, sign(g, "n-4", stale, b)))
    case("bad sig did NOT burn nonce (reuses good) -> verified", "user_verified",
         verify(g, b, "n-4", now, sign(g, "n-4", now, b)))
    case("body swapped -> rejected", "user_claimed_unverified", verify(g, "attacker body", "n-5", now, sign(g, "n-5", now, b)))
    case("goal swapped -> rejected", "user_claimed_unverified", verify("evil goal", b, "n-6", now, sign(g, "n-6", now, b)))
    case("delimiter confusion -> rejected", "user_claimed_unverified", verify("a|b", b, "c", now, sign("a", "b|c", now, b)))
    case("missing ts -> rejected", "user_claimed_unverified", m.verify_user_origin_signature(g, b, "n-7", sign(g, "n-7", now, b)))
    case("non-integer ts -> rejected", "user_claimed_unverified", verify(g, b, "n-8", "soon", sign(g, "n-8", "soon", b)))
    case("garbage sig -> rejected", "user_claimed_unverified", verify(g, b, "n-9", now, "0" * 64))

    ok = 0
    for name, expected, got, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name}" + ("" if passed else f"   (expected {expected!r}, got {got!r})"))
        ok += passed
    print(f"\n{ok}/{len(results)} passed")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
