"""Find a lane's breaking point by ramping load until it degrades, then stopping.

Written against a node that was ALREADY saturated (blade, ~2.8 cores pegged,
timing out on first request and answering 200 on the second). So this is
deliberately not a flood: it escalates concurrency one step at a time, measures
each step, and aborts the moment a step fails its gate. The goal is the ceiling,
not a crater — the node under test holds the fleet's only complete vault.

Gates, and why each one:
  * error rate  — the obvious signal, but the last to move on a slow origin.
  * p95 latency — degradation shows here long before requests actually fail.
  * timeouts    — a saturated origin times out intermittently rather than
                  refusing, so these are counted separately from errors.

Aborts on the FIRST failing step and reports the last healthy level, because
continuing past that point only tells you how hard you hit it.

    python tools/lane_loadtest.py --url https://blade.nougenai.com/health
    python tools/lane_loadtest.py --url ... --levels 1,2,4,8 --requests 12
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "nougen-lane-loadtest/1.0"}


def one(url: str, timeout: float) -> dict:
    t0 = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        r.read(2000)
        return {"ok": True, "ms": (time.time() - t0) * 1000, "status": r.status}
    except urllib.error.HTTPError as e:
        return {"ok": False, "ms": (time.time() - t0) * 1000, "status": e.code, "kind": "http"}
    except Exception as e:  # noqa: BLE001
        kind = "timeout" if "timed out" in str(e).lower() or "timeout" in type(e).__name__.lower() else "error"
        return {"ok": False, "ms": (time.time() - t0) * 1000, "kind": kind, "err": type(e).__name__}


def level(url: str, concurrency: int, requests: int, timeout: float) -> dict:
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        res = list(ex.map(lambda _: one(url, timeout), range(requests)))
    lat = sorted(r["ms"] for r in res)
    ok = [r for r in res if r["ok"]]
    timeouts = [r for r in res if r.get("kind") == "timeout"]
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else 0.0  # noqa: E731
    return {
        "concurrency": concurrency, "requests": requests,
        "ok": len(ok), "failed": len(res) - len(ok), "timeouts": len(timeouts),
        "error_rate": round((len(res) - len(ok)) / len(res), 3),
        "p50_ms": int(statistics.median(lat)) if lat else 0,
        "p95_ms": int(p(0.95)), "max_ms": int(lat[-1]) if lat else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--levels", default="1,2,4,8,16")
    ap.add_argument("--requests", type=int, default=8, help="requests per level")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--max-error-rate", type=float, default=0.25)
    ap.add_argument("--max-p95-ms", type=int, default=20000)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    steps, broke_at, last_ok = [], None, None
    for c in levels:
        s = level(args.url, c, max(args.requests, c), args.timeout)
        steps.append(s)
        if not args.json:
            print(f"  c={s['concurrency']:<3} ok={s['ok']}/{s['requests']:<3} "
                  f"err={s['error_rate']:<5} timeouts={s['timeouts']:<3} "
                  f"p50={s['p50_ms']:>6}ms p95={s['p95_ms']:>6}ms max={s['max_ms']:>6}ms")
        failed_gate = (s["error_rate"] > args.max_error_rate) or (s["p95_ms"] > args.max_p95_ms)
        if failed_gate:
            broke_at = s
            break
        last_ok = s

    report = {"url": args.url, "steps": steps, "last_healthy": last_ok, "broke_at": broke_at,
              "gates": {"max_error_rate": args.max_error_rate, "max_p95_ms": args.max_p95_ms}}
    if args.json:
        print(json.dumps(report, indent=2))
    elif broke_at:
        print(f"\nBROKE at concurrency {broke_at['concurrency']}: "
              f"error_rate={broke_at['error_rate']} p95={broke_at['p95_ms']}ms "
              f"timeouts={broke_at['timeouts']}")
        print(f"Last healthy: concurrency {last_ok['concurrency'] if last_ok else 0}"
              + (f" (p95={last_ok['p95_ms']}ms)" if last_ok else " — failed at the lowest level"))
        print("Stopped here deliberately; pushing past the break only measures the crater.")
    else:
        print(f"\nNo break through concurrency {levels[-1]}. "
              f"p95 at ceiling: {steps[-1]['p95_ms']}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
