"""Validate the dam 10x and prove it cannot block ordinary work.

Two questions, separately answered:
  1. Is it stable?  -> run the suite 10 times, watch for flakes.
  2. Does it block? -> exercise every path an operator could hit on THIS
     machine, which currently has a genuinely broken TLS substrate.

Blocking is the failure mode that matters. A gate that stops the owner from
working is worse than the fault it guards against.
"""
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, "src")

from nougen_shards.dam import Preflight, PreflightFailure  # noqa: E402
from nougen_shards.dam.dam import Dam  # noqa: E402
from nougen_shards.dam.store import LocalDamStore  # noqa: E402

# The interpreter running this script. Hardcoding an absolute path named
# the operator and the layout of their disk in a public repo, which is
# what tests/test_published_surface.py exists to catch.
PY = sys.executable
KEY = b"\x07" * 32
HMAC = b"\x08" * 32


def down(op, payload):
    return {"status": 503}


def up(op, payload):
    return {"status": 200, "shard_ref": "shard:1", "db_index": 2}


print("=" * 66)
print("PART 1 — stability: 10 consecutive full runs")
print("=" * 66)
results = []
for i in range(1, 11):
    t0 = time.monotonic()
    p = subprocess.run(
        [PY, "-m", "pytest", "tests/test_shard_capture_dam.py",
         "tests/test_dam_preflight.py", "-q", "-p", "no:randomly"],
        capture_output=True, text=True)
    tail = [l for l in p.stdout.strip().splitlines() if l.strip()][-1]
    ok = p.returncode == 0
    results.append(ok)
    print(f"  run {i:2d}  {'PASS' if ok else 'FAIL'}  "
          f"{time.monotonic()-t0:5.2f}s  {tail[:60]}")

print(f"\n  {sum(results)}/10 runs passed"
      f"{'  — no flakes' if all(results) else '  — FLAKY, investigate'}")

print()
print("=" * 66)
print("PART 2 — non-blocking: can this thing stop the owner working?")
print("=" * 66)

checks = []


def check(name, condition, detail=""):
    checks.append(bool(condition))
    print(f"  {'OK  ' if condition else 'BLOCK'} {name}")
    if detail:
        print(f"        {detail}")


# 1. Default construction must not require arming at all.
d = Dam(LocalDamStore(tempfile.mkdtemp()), key=KEY, lane="l", hmac_key=HMAC)
check("default Dam() is armed without preflight", d.armed is True,
      "require_preflight defaults False — existing callers unaffected")

# 2. Default dam accepts a healthy write.
r = d.submit("shards_capture", {"title": "t", "content": "c"}, up)
check("healthy write succeeds on default dam", r["captured"] is True)

# 3. Default dam spools during an outage without any arming.
r = d.submit("shards_capture", {"title": "t2", "content": "c2"}, down,
             local_retries=0)
check("outage write spools on default dam", r["queued_fallback"] is True)

# 4. THIS machine has broken TLS. Preflight must still arm.
rep = Preflight(LocalDamStore(tempfile.mkdtemp()), key=KEY, hmac_key=HMAC,
                health_probe=lambda: True,
                verify_tls_host="huggingface.co").run(strict=False)
check("preflight ARMS on this box despite real TLS failure",
      rep["armed"] is True,
      f"failed gates: {rep['failed'] or 'none'} (non-critical only)")

# 5. strict=True must not raise when only non-critical gates fail.
raised = False
try:
    Preflight(LocalDamStore(tempfile.mkdtemp()), key=KEY, hmac_key=HMAC,
              verify_tls_host="huggingface.co").run(strict=True)
except PreflightFailure:
    raised = True
check("strict preflight does NOT raise on TLS-only failure", not raised,
      "broken TLS is reported, never fatal")

# 6. A dishonest probe is reported, not fatal.
rep2 = Preflight(LocalDamStore(tempfile.mkdtemp()), key=KEY, hmac_key=HMAC,
                 health_probe=lambda: "yes").run(strict=False)
check("dishonest health probe is non-fatal", rep2["armed"] is True)

# 7. Opt-in strict dam arms cleanly on a healthy store.
d2 = Dam(LocalDamStore(tempfile.mkdtemp()), key=KEY, lane="l", hmac_key=HMAC,
         require_preflight=True)
d2.arm(health_probe=lambda: True, verify_tls_host="huggingface.co")
check("require_preflight dam arms on this box", d2.armed is True)
r = d2.submit("shards_capture", {"title": "t", "content": "c"}, down,
              local_retries=0)
check("armed strict dam still spools", r["queued_fallback"] is True)

# 8. The one case that SHOULD block: a store that loses writes.
class LyingStore(LocalDamStore):
    def put_pending(self, env):
        return "pending/nope.json"


blocked = False
try:
    Preflight(LyingStore(tempfile.mkdtemp()), key=KEY, hmac_key=HMAC).run()
except PreflightFailure:
    blocked = True
check("a store that LOSES writes is correctly refused", blocked,
      "this is the only blocking case, and it protects data")

# 9. No network dependency in the default path.
d3 = Dam(LocalDamStore(tempfile.mkdtemp()), key=KEY, lane="l")
t0 = time.monotonic()
d3.submit("shards_capture", {"title": "x", "content": "y"}, down,
          local_retries=0)
elapsed = time.monotonic() - t0
check("spooling makes no network call", elapsed < 0.5,
      f"{elapsed*1000:.1f}ms — local, offline-safe")

# 10. Forbidden ops fail fast, no hang.
r = d3.submit("shards_forget", {"id": 1}, down, local_retries=0)
check("forbidden op refused instantly, no retry storm",
      r["durable"] is False and r["terminal"] is True)

print(f"\n  {sum(checks)}/{len(checks)} non-blocking checks passed")
print()
print("VERDICT:", "NOT BLOCKING" if all(checks) and all(results)
      else "REVIEW NEEDED")
